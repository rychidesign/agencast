"""Běh scénáře (scenario.md §2–§6, run-record.md).

Asyncio: `parallel` = TaskGroup (selhání větve zruší ostatní), časové
limity = `asyncio.timeout_at` nad nejbližší lhůtou (krok, parallel, běh).
Rozpočty a lhůty mají vlastníka: vyčerpání limitu jiného než vlastního
kroku `on_error: continue` nepřebije (scenario.md §6).
"""
import asyncio
import hashlib
import hmac
import json
import os
import secrets
import shutil
import time
import traceback
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from . import ConfigErrors, MawError, __version__
from .expressions import ExprError, FileRef, evaluate, kind, path_step, render, to_json, to_text
from .loader import nested_lists
from .mcp_client import Pool, secret_names  # 3a
from .providers import (LEVELS, Client, assistant_message, chat_body, image_body, image_size, json_schema,
                        parse_chat, parse_image, parse_jev, prompt_level_suffix)
from .record import Record, cz, now_iso, plan_md, scrub, summary_md
from .task import dedupe_skip, run_task  # 3a
from .validate import DEFAULT_TIMEOUT, Project, StepInfo, _matches, effective_tools, env_fields, seconds

RETRY_BASE_S = 2.0           # prodleva 2 s, 4 s, 8 s… (scenario.md §3 retry); testy ji stáhnou na 0
CALLBACK_DELAYS = (5, 30)    # 3 pokusy (run-record.md callback_sent, návrh)
IMAGE_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


@dataclass
class Scope:
    """Rozpočet: kroku, parallel, běhu, obrázků běhu."""
    label: str
    limit: float | None
    owner: str | None
    spent: float = 0.0


@dataclass
class Ctx:
    budgets: list
    deadlines: list          # (čas smyčky, popis, vlastník)
    owners: tuple = ()       # nadřazené kroky parallel/switch (cena se přičte i jim)
    branch: str | None = None

    def inner(self, info: StepInfo, branch=None) -> "Ctx":
        st, now = info.data, asyncio.get_running_loop().time()
        b = [Scope(f"kroku '{info.id}' (budget_usd)", st["budget_usd"], info.id)] if "budget_usd" in st else []
        d = [(now + seconds(st["timeout"]), f"kroku '{info.id}' ({st['timeout']})", info.id)] if "timeout" in st else []
        return Ctx(self.budgets + b, self.deadlines + d, self.owners + (info.id,), branch)


def secret_values(p: Project) -> dict[str, str]:
    """Hodnoty všech proměnných z polí `*_env` (maskují se v záznamu i callbacku)."""
    names = [name for _, name in env_fields(p.config)] + secret_names(p.mcp)  # 3a: env a *_env z mcp.yaml
    return {name: os.environ[name] for name in names if os.environ.get(name)}


def new_run_id(name: str) -> str:
    return f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{name}-{secrets.token_hex(2)}"


def safe_url(url: str) -> str:
    u = urlsplit(url)
    return f"{u.scheme}://{u.hostname}{u.path}"


def system_prompt_ask(agent) -> str:
    """Tělo agenta + celé skilly (agent.md, u `ask`)."""
    parts = [agent.body.strip()] + [f"## Skill: {name}\n\n{body.strip()}" for name, _, body in agent.skills]
    return "\n\n".join(parts)


def preflight(p: Project, *, fake: bool, callback_url: str | None) -> str | None:
    """Kontroly prostředí před přidělením run_id; vrací API klíč. Chyba = běh nezačne."""
    errs, key = [], None
    if not fake:
        name = p.config["openrouter"]["api_key_env"]
        key = os.environ.get(name)
        if not key:
            errs.append(f"chybí proměnná prostředí {name} (klíč OpenRouteru; .env nebo prostředí)")
    if callback_url:
        if not callback_url.startswith("https://"):
            errs.append("callback URL musí začínat https://")
        if not os.environ.get(p.config["callback"]["secret_env"]):
            errs.append(f"chybí proměnná prostředí {p.config['callback']['secret_env']} (podpis callbacku)")
    for srv in sorted({s for st in p.steps.values() if st.kind == "task"  # 3a: klíče MCP serverů, které běh použije
                       for s in effective_tools(p.agents[st.data["task"]["agent"]].data, st.data["task"])}):
        spec = p.mcp[srv]
        for var in secret_names({srv: spec}):
            if not os.environ.get(var):
                errs.append(f"chybí proměnná prostředí {var} (MCP server {srv} v mcp.yaml)")
    if errs:
        raise ConfigErrors(errs)
    return key


class Run:
    def __init__(self, p: Project, inputs: dict, record: Record, client: Client, run_id: str, *,
                 callback_url=None, request_key=None, callback_transport=None):
        self.p, self.inputs, self.rec, self.client, self.run_id = p, inputs, record, client, run_id
        self.callback_url, self.request_key, self.callback_transport = callback_url, request_key, callback_transport
        self.storage_prefix = f"{run_id}-{secrets.token_hex(16)}"
        self.values = {"inputs": inputs, "steps": {}}
        self.defaulted: set[str] = set()
        self.rows: dict[str, dict] = {}
        self.calls: dict[str, int] = {}
        self.step_cost: dict[str, float] = {}
        self.warnings: list[str] = []
        self.cost = self.image_cost = self.image_duration = self.duration = 0.0
        self.status, self.error, self.outputs, self.callback_failed = "failed", None, None, False
        self.started_at = now_iso()
        self.mcp = Pool(p.mcp, record.dir.resolve(), record)  # 3a: servery se startují při prvním task

    # --- běh -----------------------------------------------------------------------
    async def execute(self) -> str:
        t0, loop = time.monotonic(), asyncio.get_running_loop()
        cfg, lim, sc = self.p.config, self.p.config["limits"], self.p.scenario
        self.run_budget = Scope("běhu (run_budget_usd)", lim["run_budget_usd"], None)
        self.image_budget = Scope("obrázků běhu (run_image_budget_usd)", lim.get("run_image_budget_usd"), None)
        self.rec.event("run_started", run_id=self.run_id, scenario=sc["name"], scenario_version=sc["version"],
                       request_key=self.request_key, inputs=self.inputs,
                       models={a: m["id"] for a, m in cfg["models"].items()},
                       limits={"run_budget_usd": lim["run_budget_usd"],
                               "run_image_budget_usd": lim.get("run_image_budget_usd"),
                               "run_timeout": lim["run_timeout"]},
                       framework_version=__version__, storage_prefix=self.storage_prefix)
        root = Ctx([self.run_budget], [(loop.time() + seconds(lim["run_timeout"]),
                                         f"běhu (run_timeout {lim['run_timeout']})", None)])
        try:
            await self.run_list(sc["steps"], root)
            self.status = "succeeded"
        except MawError as e:
            self.error = {"class": e.cls, "step": e.step, "message": e.message}
        except Exception as e:  # chyba frameworku mimo krok
            self.error = {"class": "internal", "step": None, "message": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"}
            self.rec.event("error", **{"class": "internal"}, message=self.error["message"], attempt=None,
                           will_retry=False, http_status=None)
        finally:
            await self.mcp.close()  # 3a
            await self.client.aclose()
        self.duration = round(time.monotonic() - t0, 3)
        self.warnings += [f"tajná hodnota {n} byla v záznamu nahrazena textem <tajné: {n}>" for n in sorted(self.rec.masked)]
        self.rec.event("run_finished", status=self.status, error=self.error, warnings=self.warnings,
                       duration_s=self.duration, usage={"input_tokens": None, "output_tokens": None,
                                                        "cost_usd": round(self.cost, 8)} | self.tokens(),
                       image_cost_usd=round(self.image_cost, 8), image_duration_s=round(self.image_duration, 3))
        body = {"run_id": self.run_id, "scenario": sc["name"], "request_key": self.request_key,
                "status": self.status, "outputs": self.outputs if self.status == "succeeded" else None,
                "error": self.error, "warnings": self.warnings, "cost_usd": round(self.cost, 8),
                "duration_s": self.duration, "report_url": None, "sent_at": now_iso()}
        data = self.rec.mask(json.dumps(body, ensure_ascii=False)).encode()
        self.rec.write("callback.json", json.loads(data))
        if self.callback_url:
            self.callback_failed = not await self.send_callback(data)
        self.rec.write("summary.md", summary_md(self.p, self))
        return self.status

    def tokens(self) -> dict:
        inp = out = 0
        for e in self.rec.events:
            if e["type"] in ("model_call", "jev_call"):
                inp += e["usage"]["input_tokens"] or 0
                out += e["usage"]["output_tokens"] or 0
        return {"input_tokens": inp, "output_tokens": out}

    async def run_list(self, steps: list, ctx: Ctx):
        for i, st in enumerate(steps):
            try:
                await self.run_step(st, ctx)
            except asyncio.CancelledError:
                for rest in steps[i + 1:]:
                    self.skip(rest, "cancelled", "zrušeno — selhala jiná větev parallel")
                raise

    async def run_step(self, st: dict, ctx: Ctx):
        info = self.p.steps[st["id"]]
        sid, k = info.id, info.kind
        t0 = time.monotonic()
        self.step_cost.setdefault(sid, 0.0)
        started = False

        def start():
            nonlocal started
            if not started:
                self.rec.event("step_started", step=sid, kind=k, **({"branch": ctx.branch} if ctx.branch else {}))
                self.rows[sid] = {"nn": info.nn, "id": sid, "kind": k, "status": "failed", "duration": None,
                                  "cost": 0.0, "note": ""}
                started = True
        try:
            if "when" in st:
                ok = self.expr(st["when"], "when")
                if not isinstance(ok, bool):
                    raise MawError("expression", f"when musí dát true/false, dal {kind(ok)}")
                if not ok:
                    self.skip(st, "when", f"when: {st['when']} → false")
                    return
            if "dedupe_key" in st and dedupe_skip(self, info):  # 3a: krok už proběhl v jiném běhu
                return
            start()
            out = await getattr(self, f"step_{k}")(info, ctx)
            output_file = None
            if out is not None:
                self.values["steps"][sid] = out
                output_file = self.rec.write(f"{info.folder}/output.json", out)
            self.finish(info, "succeeded", t0, output_file=output_file)
        except asyncio.CancelledError:
            start()
            self.finish(info, "cancelled", t0)
            raise
        except Exception as e:
            if not isinstance(e, MawError):
                e = MawError("internal", f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            start()
            e.step = e.step or sid
            if not e.logged:
                self.rec.event("error", step=sid, **{"class": e.cls}, message=e.message, attempt=None,
                               will_retry=False, http_status=e.http_status)
                e.logged = True
            cont = st.get("on_error") == "continue" and not e.fatal and e.step == sid
            self.finish(info, "failed", t0, continued=cont)
            if cont:
                self.rows[sid]["status"] = "continued"
                self.warnings.append(f"krok {sid} selhal ({e.cls}: {e.message.splitlines()[0]}) — běh pokračuje "
                                     "s default (on_error: continue)")
                self.use_default(info)
                return
            raise e from None

    def finish(self, info: StepInfo, status: str, t0: float, continued=False, output_file=None):
        dur = round(time.monotonic() - t0, 3)
        cost = round(self.step_cost.get(info.id, 0.0), 8)
        self.rec.event("step_finished", step=info.id, kind=info.kind, status=status, continued=continued,
                       duration_s=dur, cost_usd=cost, **({"output_file": output_file} if output_file else {}))
        row = self.rows[info.id]
        row.update(status=status, duration=dur, cost=cost)
        if status == "failed" and not row["note"]:
            row["note"] = "viz Chyba" if not continued else "selhal, použit default"

    def use_default(self, info: StepInfo):
        if "default" in info.data:
            d = dict(info.data["default"])
            if info.kind == "jev":
                d.setdefault("details", {q: {} for q in info.data["jev"]["questions"]})
            self.values["steps"][info.id] = d
            self.defaulted.add(info.id)

    def skip(self, st: dict, code: str, reason: str):
        """Krok neproběhl: důvod do záznamu, výstup = default; totéž pro kroky uvnitř."""
        info = self.p.steps[st["id"]]
        self.rec.event("step_skipped", step=info.id, kind=info.kind, reason_code=code, reason=reason,
                       default_used="default" in st)
        self.rows[info.id] = {"nn": info.nn, "id": info.id, "kind": info.kind, "status": "skipped",
                              "duration": None, "cost": 0.0, "note": reason}
        self.use_default(info)
        for _, lst in nested_lists(st):
            for s in lst:
                self.skip(s, code, reason)

    # --- výrazy a šablony ------------------------------------------------------------
    def expr(self, expr: str, fld: str):
        try:
            return evaluate(expr, self.values)
        except ExprError as e:
            raise MawError("expression", f"{fld}: {e}") from None

    def tpl(self, s: str, fld: str):
        try:
            return render(s, self.values, null_ok=lambda tree: path_step(tree) in self.defaulted)
        except ExprError as e:
            raise MawError("expression", f"{fld}: {e}") from None

    def text(self, s: str, fld: str) -> str:
        return to_text(self.tpl(s, fld))

    # --- volání API: pokusy, rozpočet, záznam ------------------------------------------
    def leaf_budgets(self, info: StepInfo, ctx: Ctx, agent_budget=None, image=False) -> list:
        limits = [x for x in (info.data.get("budget_usd"), agent_budget) if x is not None]
        own = [Scope(f"kroku '{info.id}'", min(limits), info.id)] if limits else []
        return own + ctx.budgets + ([self.image_budget] if image else [])

    async def with_deadline(self, info: StepInfo, ctx: Ctx, timeout: str, coro):
        loop = asyncio.get_running_loop()
        dl = min(ctx.deadlines + [(loop.time() + seconds(timeout), f"kroku ({timeout})", info.id)],
                 key=lambda d: d[0])
        try:
            async with asyncio.timeout_at(dl[0]):
                return await coro
        except TimeoutError:
            raise MawError("timeout", f"překročen časový limit {dl[1]}", fatal=dl[2] != info.id) from None

    async def call_api(self, info, ctx, scopes, path, build, parse, event_type, on_value=None, image=False,
                       record=scrub):  # 3a: record = úprava těla pro záznam (obrázky z nástrojů)
        sid, retries, attempt, last = info.id, info.data.get("retry", 2), 0, None
        while True:
            attempt += 1
            for s in scopes:
                if s.limit is not None and s.spent >= s.limit:
                    raise MawError("budget", f"rozpočet {s.label} vyčerpán ({s.spent:.4f} z {s.limit} USD)",
                                   fatal=s.owner != sid)
            body, fields = build(attempt, last)
            n = self.calls[sid] = self.calls.get(sid, 0) + 1
            req = self.rec.write(f"{info.folder}/calls/{n:02d}.request.json", record(body))
            t = time.monotonic()
            status, rbody, headers = await self.client.post(path, body, sid)
            dur = round(time.monotonic() - t, 3)
            meta, value, err = parse(status, rbody, headers)
            note = None
            if err is None and on_value:
                try:
                    value, note = on_value(value)
                except MawError as e:
                    err = e
            resp = self.rec.write(f"{info.folder}/calls/{n:02d}.response.json", scrub(rbody, note))
            cost = meta["usage"]["cost_usd"]
            over = self.add_cost(info, ctx, scopes, cost, image)
            if cost is None:
                self.warnings.append(f"krok {sid}: poskytovatel nevrátil cenu (usage.cost) — rozpočet nejde hlídat přesně")
            self.rec.event(event_type, step=sid, attempt=attempt, **fields, **meta,
                           **({"budget_exceeded_usd": over} if over else {}),
                           duration_s=dur, request_file=req, response_file=resp)
            if err is None:
                return value
            retry = err.cls in ("transient", "schema") and attempt <= retries
            cls = err.cls if retry else (err.final or err.cls)
            self.rec.event("error", step=sid, **{"class": cls}, message=err.message, attempt=attempt,
                           will_retry=retry, http_status=err.http_status)
            if not retry:
                e = MawError(cls, err.message, http_status=err.http_status, fatal=err.fatal)
                e.logged = True
                raise e
            last = err
            if err.cls == "transient":
                await asyncio.sleep(err.retry_after if err.retry_after is not None
                                    else RETRY_BASE_S * 2 ** (attempt - 1))

    def add_cost(self, info, ctx, scopes, cost, image=False):
        if cost is None:
            return None
        self.cost += cost
        if image:
            self.image_cost += cost
        for sid in (info.id, *ctx.owners):
            self.step_cost[sid] = self.step_cost.get(sid, 0.0) + cost
        over = 0.0
        for s in scopes:
            s.spent += cost
            if s.limit is not None and s.spent > s.limit:
                over = max(over, s.spent - s.limit)
                self.warnings.append(f"rozpočet {s.label} překročen o {s.spent - s.limit:.4f} USD (krok {info.id})")
        return round(over, 8) or None

    # --- typy kroků -----------------------------------------------------------------
    async def step_ask(self, info: StepInfo, ctx: Ctx):
        a = info.data["ask"]
        agent = self.p.agents[a["agent"]]
        alias = agent.data["model"]
        m = self.p.config["models"][alias]
        prompt = self.text(a["prompt"], "ask.prompt")
        schema = json_schema(a["schema"]) if "schema" in a else None
        base = system_prompt_ask(agent)
        st = {"level": m.get("structured_output", "native_schema") if schema else None, "feedback": [], "prev": None}

        def build(attempt, last):
            if last and last.cls == "schema":
                if st["level"] != "prompt":
                    st["level"] = LEVELS[LEVELS.index(st["level"]) + 1]
                prev = st["prev"]
                st["feedback"] = ([assistant_message(prev)] if prev and prev.get("content") and not prev.get("tool_calls")
                                  else []) + [{"role": "user", "content": f"Předchozí odpověď byla neplatná: "
                                               f"{last.message}\nOdpověz znovu, přesně v požadovaném tvaru."}]
            system = base + (prompt_level_suffix(schema) if st["level"] == "prompt" else "")
            msgs = [{"role": "user", "content": prompt}, *st["feedback"]]
            self.rec.write(f"{info.folder}/prompt.md", "# System prompt\n\n" + system + "\n\n# Zpráva\n\n" + prompt
                           + "".join(f"\n\n# Zpětná vazba ({x['role']})\n\n{x.get('content') or ''}"
                                     for x in st["feedback"]))
            return chat_body(m["id"], system, msgs, st["level"], schema, m.get("max_tokens")), \
                {"alias": alias, "model": m["id"], "structured_output": st["level"]}

        def parse(status, body, headers):
            meta, value, err = parse_chat(status, body, headers, st["level"], schema)
            st["prev"] = meta.pop("message")
            return meta, value, err

        lim = agent.data["limits"]
        timeout = min(info.data.get("timeout") or lim.get("timeout") or DEFAULT_TIMEOUT["ask"],
                      lim.get("timeout") or "24h", key=seconds)
        value = await self.with_deadline(info, ctx, timeout, self.call_api(
            info, ctx, self.leaf_budgets(info, ctx, lim["budget_usd"]), "/chat/completions", build, parse,
            "model_call"))
        self.rows[info.id]["note"] = f"{alias} → {m['id']}" + (f" ({st['level']})" if schema else "")
        return value if schema else {"text": value}

    async def step_task(self, info: StepInfo, ctx: Ctx):  # 3a
        return await run_task(self, info, ctx)

    async def step_jev(self, info: StepInfo, ctx: Ctx):
        j = info.data["jev"]
        state = self.text(j["state"], "jev.state")
        questions = {}
        for q, spec in j["questions"].items():
            qq = {"type": spec["type"], "instructions": self.text(spec["instructions"], f"jev.questions.{q}.instructions")}
            crit = spec.get("criteria")
            if isinstance(crit, dict):
                qq["criteria"] = {c: self.text(t, f"jev.questions.{q}.criteria.{c}") for c, t in crit.items()}
            elif crit:
                qq["criteria"] = [self.text(t, f"jev.questions.{q}.criteria.{i}") for i, t in enumerate(crit)]
            questions[q] = qq
        model = self.p.config["openrouter"]["jev_model"]
        body = {"model": model, "state": state, "questions": questions}
        value = await self.with_deadline(info, ctx, info.data.get("timeout", DEFAULT_TIMEOUT["jev"]), self.call_api(
            info, ctx, self.leaf_budgets(info, ctx), "/systemone", lambda a, l: (body, {"model": model}),
            lambda s, b, h: parse_jev(s, b, h, questions), "jev_call"))
        self.rows[info.id]["note"] = ", ".join(
            f"{q} = {cz(v, 2) if isinstance(v, (int, float)) else v}" for q, v in value.items() if q != "details")
        return value

    async def step_image(self, info: StepInfo, ctx: Ctx):
        im = info.data["image"]
        alias, ratio = im["model"], im.get("aspect_ratio")
        m = self.p.config["models"][alias]
        prompt = self.text(im["prompt"], "image.prompt")
        self.rec.write(f"{info.folder}/prompt.md", "# Prompt obrázku\n\n" + prompt)
        body = image_body(m["id"], prompt, ratio)

        def on_value(v):
            data, media = v
            rel = self.rec.write_bytes(f"{info.folder}/image.{IMAGE_EXT.get(media, 'bin')}", data)
            w, h = image_size(data)
            self.rec.event("image_saved", step=info.id, path=rel, media_type=media, bytes=len(data), width=w, height=h)
            self.rows[info.id]["note"] = f"{rel.rsplit('/', 1)[1]}, {w}×{h}"
            if ratio:
                a, b = map(int, ratio.split(":"))
                if not w or not h:
                    raise MawError("config", f"rozměry obrázku ({media}) nejde zjistit — aspect_ratio nejde ověřit")
                dev = abs(w / h - a / b) / (a / b)
                if dev > 0.02:
                    raise MawError("config", f"model nepodporuje aspect_ratio {ratio}: obrázek má {w}×{h} "
                                             f"(odchylka {dev:.1%}, povoleno 2 %) — nic se neořezává")
            return {"file": FileRef(rel)}, f"<soubor: {rel}, {len(data)} B>"

        t0 = time.monotonic()
        try:
            return await self.with_deadline(info, ctx, info.data.get("timeout", DEFAULT_TIMEOUT["image"]), self.call_api(
                info, ctx, self.leaf_budgets(info, ctx, image=True), "/chat/completions",
                lambda a, l: (body, {"alias": alias, "model": m["id"], "structured_output": None}),
                parse_image, "model_call", on_value, image=True))
        finally:
            self.image_duration += time.monotonic() - t0

    async def step_set(self, info: StepInfo, ctx: Ctx):
        return {k: self.expr(v, f"set.{k}") if isinstance(v, str) else v for k, v in info.data["set"].items()}

    async def step_fail(self, info: StepInfo, ctx: Ctx):
        raise MawError("fail", self.text(info.data["fail"], "fail"))

    async def step_output(self, info: StepInfo, ctx: Ctx):
        specs, values, public = self.p.scenario["outputs"], {}, {}
        for k, v in info.data["output"].items():
            val = self.tpl(v, f"output.{k}") if isinstance(v, str) else v
            want = specs[k]["type"]
            if val is not None and (isinstance(val, FileRef) != (want == "file")
                                    or want != "file" and not _matches(want, val)):
                raise MawError("expression", f"output.{k}: výstup má být {want}, hodnota je {kind(val)}")
            values[k] = val
            public[k] = self.upload(k, val) if isinstance(val, FileRef) else val
        self.outputs = public
        return values

    def upload(self, name: str, ref: FileRef) -> str:
        """Soubor z output → úložiště; callback nese URL (§5.7)."""
        run_dir = self.rec.dir.resolve()
        src = (run_dir / ref.path).resolve()
        if not src.is_relative_to(run_dir) or not src.is_file():
            raise MawError("config", f"soubor {ref.path} není uvnitř složky běhu")
        st = self.p.config["storage"]
        if st["type"] != "local":  # validate to hlídá; R2 = Fáze 3
            raise MawError("config", "úložiště r2 framework zatím neumí (Fáze 3)")
        key = f"{self.storage_prefix}/{name}{src.suffix}"
        dest = self.p.base / st["local"]["path"] / key
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        except OSError as e:
            raise MawError("transient", f"nahrání {ref.path} do úložiště selhalo: {e}") from None
        base = st["local"].get("public_base_url")
        url = f"{base.rstrip('/')}/{key}" if base else dest.resolve().as_uri()
        self.rec.event("file_uploaded", output=name, path=ref.path, url=url)
        return url

    async def step_parallel(self, info: StepInfo, ctx: Ctx):
        inner = ctx.inner(info)
        try:
            async with asyncio.TaskGroup() as tg:
                for b, lst in info.data["parallel"].items():
                    tg.create_task(self.run_list(lst, replace(inner, branch=b)))
        except BaseExceptionGroup as eg:
            errs = _leaves(eg)
            raise next((e for e in errs if isinstance(e, MawError)), errs[0]) from None
        return None

    async def step_switch(self, info: StepInfo, ctx: Ctx):
        sw = info.data["switch"]
        v = self.expr(sw["value"], "switch.value")
        if not isinstance(v, str):
            raise MawError("expression", f"switch.value musí dát text (string), dal {kind(v)}: {to_json(v)[:80]}")
        reason = f"switch: {info.id} = {to_json(v)}"
        chosen = sw["cases"][v] if v in sw["cases"] else sw["default"]
        for lst in [*sw["cases"].values(), sw["default"]]:
            if lst is not chosen:
                for s in lst:
                    self.skip(s, "switch", reason)
        self.rows[info.id]["note"] = f"větev {v if v in sw['cases'] else 'default'}"
        await self.run_list(chosen, ctx.inner(info, branch=v))
        return None

    # --- callback --------------------------------------------------------------------
    async def send_callback(self, data: bytes) -> bool:
        """POST na callback URL, HMAC-SHA256 nad přesnými bajty těla (run-record.md Podpis)."""
        secret = os.environ[self.p.config["callback"]["secret_env"]].encode()
        headers = {"Content-Type": "application/json", "X-Run-Id": self.run_id,
                   "X-Signature": "sha256=" + hmac.new(secret, data, hashlib.sha256).hexdigest()}
        url, error = safe_url(self.callback_url), None
        async with httpx.AsyncClient(timeout=30, transport=self.callback_transport) as http:
            for attempt in (1, 2, 3):
                try:
                    r = await http.post(self.callback_url, content=data, headers=headers)
                    status, error = r.status_code, None if r.is_success else f"HTTP {r.status_code}"
                except httpx.HTTPError as e:
                    status, error = None, f"{type(e).__name__}: {e}"
                self.rec.event("callback_sent", url=url, attempt=attempt, http_status=status,
                               **({"error": error} if error else {}))
                if not error:
                    return True
                if attempt < 3:
                    await asyncio.sleep(CALLBACK_DELAYS[attempt - 1])
        self.rec.event("callback_failed", url=url, attempts=3, error=error)
        return False


def _leaves(eg: BaseExceptionGroup) -> list:
    out = []
    for e in eg.exceptions:
        out += _leaves(e) if isinstance(e, BaseExceptionGroup) else [e]
    return out


def dry_run(p: Project, inputs: dict) -> Record:
    """Složka jen s plan.md a inputs.json (run-record.md)."""
    rec = Record(p.runs_dir / new_run_id(p.scenario["name"]), secret_values(p))
    rec.write("plan.md", plan_md(p))
    rec.write("inputs.json", inputs)
    return rec


def run_scenario(p: Project, inputs: dict, *, fake=None, callback_url=None, request_key=None,
                 callback_transport=None) -> Run:
    """Spustí ověřený scénář; `fake` = maw.fake.Fake místo sítě."""
    key = preflight(p, fake=fake is not None, callback_url=callback_url)
    run_id = new_run_id(p.scenario["name"])
    rec = Record(p.runs_dir / run_id, secret_values(p))
    rec.write("plan.md", plan_md(p))
    rec.write("inputs.json", inputs)
    client = Client(p.config["openrouter"]["base_url"], key, fake.transport() if fake else None)
    run = Run(p, inputs, rec, client, run_id, callback_url=callback_url, request_key=request_key,
              callback_transport=callback_transport)
    asyncio.run(run.execute())
    return run
