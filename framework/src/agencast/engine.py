"""Scenario execution (scenario.md §2–§6, run-record.md).

Asyncio: `parallel` = TaskGroup (a failed branch cancels the others), timeouts
= `asyncio.timeout_at` with the nearest deadline (step, parallel, run).
Budgets and deadlines have an owner: `on_error: continue` cannot override
an exhausted limit belonging to something other than the step itself (scenario.md §6).
"""
import asyncio
import contextvars
import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import ConfigErrors, AgencastError, __version__
from .expressions import ExprError, FileRef, evaluate, kind, path_step, render, to_json, to_text
from .loader import nested_lists
from .mcp_client import Pool, _leaves, secret_names  # 3a
from .providers import (LEVELS, Client, assistant_message, chat_body, image_body, images_body, image_size, json_schema,
                        http_error, parse_chat, parse_image, parse_images, parse_jev, prompt_level_suffix)
from .record import (SUM_DIGITS, Record, count, format_number, format_usd, now_iso, plan_md,
                     report_html, scrub, summary_md)
from .task import dedupe_skip, hold_run_lock, local_dedupe, local_ledger, local_slots, run_task  # 3a
from .validate import DEFAULT_TIMEOUT, Project, StepInfo, _matches, env_fields, mcp_servers_used, seconds

RETRY_BASE_S = 2.0           # delay 2 s, 4 s, 8 s… (scenario.md §3 retry); tests reduce it to 0
CALLBACK_DELAYS = (5, 30)    # 3 attempts (run-record.md callback_sent, design)
SLOT_POLL_S = 0.5            # how often to check for a free max_parallel_runs slot; tests reduce it
# Read timeout for one provider HTTP call (ISSUES 34): min(remaining step time, cap); expiration = transient.
CALL_TIMEOUT_S = {"chat": 120, "jev": 30, "images": 180}  # chat = ask, task turn and image; images = Images API
STEP_DEADLINE = contextvars.ContextVar("step_deadline", default=None)  # step deadline (loop time) from with_deadline
IMAGE_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/svg+xml": "svg"}


@dataclass
class Scope:
    """Budget: step, parallel, run, run images."""
    label: str
    limit: float | None
    owner: str | None
    spent: float = 0.0


@dataclass
class Ctx:
    budgets: list
    deadlines: list          # (loop time, description, owner)
    owners: tuple = ()       # parent parallel/switch steps (cost is added to them too)
    branch: str | None = None

    def inner(self, info: StepInfo, branch=None) -> "Ctx":
        st, now = info.data, asyncio.get_running_loop().time()
        b = [Scope(f"step '{info.id}' (budget_usd)", st["budget_usd"], info.id)] if "budget_usd" in st else []
        d = [(now + seconds(st["timeout"]), f"step '{info.id}' ({st['timeout']})", info.id)] if "timeout" in st else []
        return Ctx(self.budgets + b, self.deadlines + d, self.owners + (info.id,), branch)


def secret_values(p: Project) -> dict[str, str]:
    """Values of all variables in `*_env` fields (masked in the record and callback)."""
    names = [name for _, name in env_fields(p.config)] + secret_names(p.mcp)  # 3a: env and *_env from mcp.yaml
    return {name: os.environ[name] for name in names if os.environ.get(name)}


def new_run_id(name: str) -> str:
    return f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{name}-{secrets.token_hex(2)}"


RUN_ID_TRIES = 5
RUN_ID = re.compile(r"\d{8}-\d{6}-[a-z0-9-]+-[0-9a-f]{4}")


def new_record(runs_dir: Path, name: str, secret_vals: dict) -> Record:
    """New run directory; run_id collision (concurrent runs in the same second, ISSUES 35) → new suffix."""
    for _ in range(RUN_ID_TRIES):
        try:
            return Record(runs_dir / new_run_id(name), secret_vals)
        except FileExistsError:
            pass
    raise AgencastError("internal", f"{RUN_ID_TRIES}× run_id collisions in {runs_dir} — run directory already existed")


def safe_url(url: str) -> str:
    u = urlsplit(url)
    return f"{u.scheme}://{u.hostname}{u.path}"


def system_prompt_ask(agent) -> str:
    """Agent body + full skills (agent.md, for `ask`)."""
    parts = [agent.body.strip()] + [f"## Skill: {name}\n\n{body.strip()}" for name, _, body in agent.skills]
    return "\n\n".join(parts)


def preflight(p: Project, *, fake: bool, callback_url: str | None) -> str | None:
    """Environment checks before assigning run_id; returns the API key. Error = run does not start."""
    errs, key = [], None
    if not fake:
        name = p.config["openrouter"]["api_key_env"]
        key = os.environ.get(name)
        if not key:
            errs.append(f"missing environment variable {name} (OpenRouter key; .env or environment)")
    if callback_url:
        if not callback_url.startswith(("https://", "http://127.0.0.1:", "http://127.0.0.1/")):  # 3b: 127.0.0.1 for tests
            errs.append("callback URL must start with https://")
        if not os.environ.get(p.config["callback"]["secret_env"]):
            errs.append(f"missing environment variable {p.config['callback']['secret_env']} (callback signature)")
    for srv in sorted(mcp_servers_used(p)):  # 3a: keys for MCP servers used by the run
        spec = p.mcp[srv]
        for var in secret_names({srv: spec}):
            if not os.environ.get(var):
                errs.append(f"missing environment variable {var} (MCP server {srv} in mcp.yaml)")
    if errs:
        raise ConfigErrors(errs)
    return key


class Run:
    def __init__(self, p: Project, inputs: dict, record: Record, client: Client, run_id: str, *,
                 callback_url=None, request_key=None, callback_transport=None, fake=False):
        self.p, self.inputs, self.rec, self.client, self.run_id = p, inputs, record, client, run_id
        self.fake = fake  # fake provider (--fake): separate dedupe, flag in the record
        self.dedupe = local_dedupe(p.runs_dir, fake)  # DedupeStore; Modal supplies its own
        self.ledger = local_ledger(p.runs_dir, fake)  # daily spend ledger (Ledger); Modal supplies its own
        self.waited_s = None  # wait for a max_parallel_runs slot (run_waiting), otherwise None
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
        self.mcp = Pool(p.mcp, record.dir.resolve(), record)  # 3a: servers start on the first task
        self.depth = 0  # 3b: call depth; nested runs do not upload files
        self.report_url = None

    # --- execution -----------------------------------------------------------------------
    async def execute(self, error: AgencastError | None = None, resume: bool = False) -> str:
        """`error` = run that will not start (3b: validate failed after dequeuing) — record and callback only."""
        t0, loop = time.monotonic(), asyncio.get_running_loop()
        cfg, lim, sc = self.p.config, self.p.config["limits"], self.p.scenario
        self.run_budget = Scope("run (run_budget_usd)", lim["run_budget_usd"], None)
        self.image_budget = Scope("run images (run_image_budget_usd)", lim.get("run_image_budget_usd"), None)
        if resume:
            started = next((e["ts"] for e in self.rec.events if e["type"] == "run_started"), None)
            if started:
                self.started_at = started
                try:
                    began = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    self.duration = max(0, round((datetime.now(timezone.utc) - began).total_seconds(), 3))
                except ValueError:
                    self.duration = round(time.monotonic() - t0, 3)
            images = {e.get("step") for e in self.rec.events
                      if e["type"] == "step_started" and e.get("kind") == "image"}
            calls = [e for e in self.rec.events if e["type"] in ("model_call", "jev_call")]
            self.cost = sum((e.get("usage") or {}).get("cost_usd") or 0 for e in calls)
            self.image_cost = sum((e.get("usage") or {}).get("cost_usd") or 0 for e in calls
                                  if e.get("step") in images)
        else:
            self.rec.event("run_started", run_id=self.run_id, scenario=sc["name"], scenario_version=sc["version"],
                           request_key=self.request_key, inputs=self.inputs,
                           models={a: m["id"] for a, m in cfg["models"].items()},
                           limits={"run_budget_usd": lim["run_budget_usd"],
                                   "run_image_budget_usd": lim.get("run_image_budget_usd"),
                                   "run_timeout": lim["run_timeout"]},
                           framework_version=__version__, storage_prefix=self.storage_prefix, fake=self.fake,
                           steps_total=len(self.p.order) or None,  # 0.6.0: scenario steps including branches (excluding callees)
                           callback_url=safe_url(self.callback_url) if self.callback_url else None)
        if self.waited_s is not None:
            self.rec.event("run_waiting", waited_s=self.waited_s, max_parallel_runs=lim["max_parallel_runs"])
        root = Ctx([self.run_budget], [(loop.time() + seconds(lim["run_timeout"]),
                                         f"run (run_timeout {lim['run_timeout']})", None)])
        try:
            if error:  # 3b
                self.rec.event("error", step=error.step, **{"class": error.cls}, message=error.message, attempt=None,
                               will_retry=False, http_status=None)
                raise error
            await self.run_list(sc["steps"], root)
            self.status = "succeeded"
        except AgencastError as e:
            self.error = {"class": e.cls, "step": e.step, "message": e.message}
        except Exception as e:  # framework error outside a step
            self.error = {"class": "internal", "step": None, "message": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"}
            self.rec.event("error", **{"class": "internal"}, message=self.error["message"], attempt=None,
                           will_retry=False, http_status=None)
        finally:
            await self.mcp.close()  # 3a
            await self.client.aclose()
        if not resume or not self.started_at:
            self.duration = round(time.monotonic() - t0, 3)
        self.warnings += [f"secret value {n} was replaced in the record with <secret: {n}>" for n in sorted(self.rec.masked)]
        self.publish_report()  # 3b: before run_finished so it includes upload warnings
        self.rec.event("run_finished", status=self.status, error=self.error, warnings=self.warnings,
                       duration_s=self.duration, usage=self.tokens() | {"cost_usd": round(self.cost, SUM_DIGITS)},
                       image_cost_usd=round(self.image_cost, SUM_DIGITS), image_duration_s=round(self.image_duration, 3))
        body = {"run_id": self.run_id, "scenario": sc["name"], "request_key": self.request_key,
                "status": self.status, "outputs": self.outputs if self.status == "succeeded" else None,
                "error": self.error, "warnings": self.warnings, "cost_usd": round(self.cost, SUM_DIGITS),
                "duration_s": self.duration, "report_url": self.report_url, "sent_at": now_iso()}
        data = self.rec.mask(json.dumps(body, ensure_ascii=False)).encode()
        self.rec.write("callback.json", json.loads(data))
        if self.callback_url:
            self.callback_failed = not await self.send_callback(data)
        self.rec.write("summary.md", summary_md(self.p, self))
        finished = now_iso()
        try:  # after the callback: a ledger error must not prevent the callback or record
            self.ledger.add(finished[:10], {"run_id": self.run_id, "cost_usd": round(self.cost, SUM_DIGITS),
                                            "finished_at": finished})
        except OSError as e:
            print(f"writing to the daily spend ledger failed ({e}) — run {self.run_id} will not count toward daily_budget_usd "
                  "accounting", file=sys.stderr)
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
                    self.skip(rest, "cancelled", "cancelled — another parallel branch failed")
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
                self.rec.event("step_started", step=sid, kind=k, nn=info.nn, dir=info.folder,  # 0.7.0: nn, dir
                               **({"branch": ctx.branch} if ctx.branch else {}))
                self.rows[sid] = {"nn": info.nn, "id": sid, "kind": k, "status": "failed", "duration": None,
                                  "cost": 0.0, "note": ""}
                started = True
        try:
            if "when" in st:
                ok = self.expr(st["when"], "when")
                if not isinstance(ok, bool):
                    raise AgencastError("expression", f"when must return true/false, got {kind(ok)}")
                if not ok:
                    self.skip(st, "when", f"when: {st['when']} → false")
                    return
            if "dedupe_key" in st and dedupe_skip(self, info):  # 3a: step already ran in another run
                return
            start()
            out = await getattr(self, f"step_{k}")(info, ctx)
            output_file = None
            if out is not None:
                self.values["steps"][info.key] = out  # 3b: key = id in the file (sid is a path for call)
                output_file = self.rec.write(f"{info.folder}/output.json", out)
            self.finish(info, "succeeded", t0, output_file=output_file)
        except asyncio.CancelledError:
            start()
            self.finish(info, "cancelled", t0)
            raise
        except Exception as e:
            if not isinstance(e, AgencastError):
                e = AgencastError("internal", f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            start()
            e.step = e.step or sid
            if not e.logged:
                self.rec.event("error", step=sid, **{"class": e.cls}, message=e.message, attempt=None,
                               will_retry=False, http_status=e.http_status)
                e.logged = True
            cont = st.get("on_error") == "continue" and not e.fatal and (e.step == sid or e.step.startswith(sid + "/"))  # 3b
            self.finish(info, "failed", t0, continued=cont)
            if cont:
                self.rows[sid]["status"] = "continued"
                self.warnings.append(f"step {sid} failed ({e.cls}: {e.message.splitlines()[0]}) — run continues "
                                     "with default (on_error: continue)")
                self.use_default(info)
                return
            raise e from None

    def finish(self, info: StepInfo, status: str, t0: float, continued=False, output_file=None):
        dur = round(time.monotonic() - t0, 3)
        cost = round(self.step_cost.get(info.id, 0.0), SUM_DIGITS)
        self.rec.event("step_finished", step=info.id, kind=info.kind, status=status, continued=continued,
                       duration_s=dur, cost_usd=cost, **({"output_file": output_file} if output_file else {}),
                       **({"default_used": "default" in info.data} if continued else {}))  # 0.7.0
        row = self.rows[info.id]
        row.update(status=status, duration=dur, cost=cost)
        if status == "failed" and not row["note"]:
            row["note"] = "see Error" if not continued else "failed, default used"

    def use_default(self, info: StepInfo):
        if "default" in info.data:
            d = dict(info.data["default"])
            if info.kind == "jev":
                d.setdefault("details", {q: {} for q in info.data["jev"]["questions"]})
            self.values["steps"][info.key] = d  # 3b
            self.defaulted.add(info.key)

    def skip(self, st: dict, code: str, reason: str):
        """Step did not run: record the reason, output = default; same for nested steps."""
        info = self.p.steps[st["id"]]
        self.rec.event("step_skipped", step=info.id, kind=info.kind, nn=info.nn, reason_code=code, reason=reason,
                       default_used="default" in st)
        self.rows[info.id] = {"nn": info.nn, "id": info.id, "kind": info.kind, "status": "skipped",
                              "duration": None, "cost": 0.0, "note": reason}
        self.use_default(info)
        for _, lst in nested_lists(st):
            for s in lst:
                self.skip(s, code, reason)

    # --- expressions and templates ------------------------------------------------------------
    def expr(self, expr: str, fld: str):
        try:
            return evaluate(expr, self.values)
        except ExprError as e:
            raise AgencastError("expression", f"{fld}: {e}") from None

    def tpl(self, s: str, fld: str):
        try:
            return render(s, self.values, null_ok=lambda tree: path_step(tree) in self.defaulted)
        except ExprError as e:
            raise AgencastError("expression", f"{fld}: {e}") from None

    def text(self, s: str, fld: str) -> str:
        return to_text(self.tpl(s, fld))

    # --- API calls: attempts, budget, record ------------------------------------------
    def leaf_budgets(self, info: StepInfo, ctx: Ctx, agent_budget=None, image=False) -> list:
        limits = [x for x in (info.data.get("budget_usd"), agent_budget) if x is not None]
        own = [Scope(f"step '{info.id}'", min(limits), info.id)] if limits else []
        return own + ctx.budgets + ([self.image_budget] if image else [])

    async def with_deadline(self, info: StepInfo, ctx: Ctx, timeout: str, coro):
        loop = asyncio.get_running_loop()
        dl = min(ctx.deadlines + [(loop.time() + seconds(timeout), f"step ({timeout})", info.id)],
                 key=lambda d: d[0])
        token = STEP_DEADLINE.set(dl[0])
        try:
            async with asyncio.timeout_at(dl[0]):
                return await coro
        except TimeoutError:
            raise AgencastError("timeout", f"timeout exceeded for {dl[1]}", fatal=dl[2] != info.id) from None
        finally:
            STEP_DEADLINE.reset(token)

    async def call_api(self, info, ctx, scopes, path, build, parse, event_type, on_value=None, image=False,
                       record=scrub, timeout_key="chat"):  # 3a: record = body transformation for the record (tool images)
        sid, retries, attempt, last = info.id, info.data.get("retry", 2), 0, None
        while True:
            attempt += 1
            for s in scopes:
                if s.limit is not None and s.spent >= s.limit:
                    raise AgencastError("budget", f"budget for {s.label} exhausted ({format_usd(s.spent)} of {s.limit} USD)",
                                   fatal=s.owner != sid)
            body, fields = build(attempt, last)
            n = self.calls[sid] = self.calls.get(sid, 0) + 1
            req = self.rec.write(f"{info.folder}/calls/{n:02d}.request.json", record(body))
            t, deadline = time.monotonic(), STEP_DEADLINE.get()
            cap = CALL_TIMEOUT_S["jev" if event_type == "jev_call" else timeout_key]
            timeout_s = round(min(cap, deadline - asyncio.get_running_loop().time()) if deadline else cap, 3)
            status, rbody, headers = await self.client.post(path, body, sid, timeout_s)
            dur = round(time.monotonic() - t, 3)
            meta, value, err = parse(status, rbody, headers)
            note = None
            if err is None and on_value:
                try:
                    value, note = on_value(value)
                except AgencastError as e:
                    err = e
            resp = self.rec.write(f"{info.folder}/calls/{n:02d}.response.json", scrub(rbody, note))
            cost = meta["usage"]["cost_usd"]
            over = self.add_cost(info, ctx, scopes, cost, image)
            if cost is None and http_error(status, rbody, headers) is None:  # an error response costs nothing
                self.warnings.append(f"step {sid}: provider returned no cost (usage.cost) — budget cannot be tracked precisely")
            self.rec.event(event_type, step=sid, attempt=attempt, **fields, **meta,
                           **({"budget_exceeded_usd": over} if over else {}),
                           timeout_s=timeout_s, duration_s=dur, request_file=req, response_file=resp)
            if err is None:
                return value
            retry = err.cls in ("transient", "schema") and attempt <= retries
            cls = err.cls if retry else (err.final or err.cls)
            self.rec.event("error", step=sid, **{"class": cls}, message=err.message, attempt=attempt,
                           will_retry=retry, http_status=err.http_status)
            if not retry:
                e = AgencastError(cls, err.message, http_status=err.http_status, fatal=err.fatal)
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
                self.warnings.append(f"budget for {s.label} exceeded by {format_usd(s.spent - s.limit)} USD (step {info.id})")
        return round(over, SUM_DIGITS) or None

    # --- step types -----------------------------------------------------------------
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
                                  else []) + [{"role": "user", "content": f"The previous response was invalid: "
                                               f"{last.message}\nRespond again, exactly in the required format."}]
            system = base + (prompt_level_suffix(schema) if st["level"] == "prompt" else "")
            msgs = [{"role": "user", "content": prompt}, *st["feedback"]]
            self.rec.write(f"{info.folder}/prompt.md", "# System prompt\n\n" + system + "\n\n# Message\n\n" + prompt
                           + "".join(f"\n\n# Feedback ({x['role']})\n\n{x.get('content') or ''}"
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
            f"{q} = {format_number(v, 2) if isinstance(v, (int, float)) else v}" for q, v in value.items() if q != "details")
        return value

    async def step_image(self, info: StepInfo, ctx: Ctx):
        im = info.data["image"]
        alias = im["model"]
        m = self.p.config["models"][alias]
        prompt = self.text(im["prompt"], "image.prompt")
        params = {}
        for field, pattern in (("aspect_ratio", r"[1-9][0-9]*:[1-9][0-9]*"),
                               ("quality", r"auto|low|medium|high"), ("resolution", r"512|1K|2K|4K")):
            value = im.get(field, m.get("quality") if field == "quality" else None)
            if value is not None:
                value = self.text(value, f"image.{field}")
                if not re.fullmatch(pattern, value):
                    raise AgencastError("config", f"image.{field}: invalid rendered value {value!r}")
                params[field] = value
        ratio = params.get("aspect_ratio")
        self.rec.write(f"{info.folder}/prompt.md", "# Image prompt\n\n" + prompt
                       + "\n\n## Parameters\n" + "\n".join(f"- {k}: {v}" for k, v in params.items()))
        images_api = m.get("api", "chat") == "images"
        body = (images_body(m["id"], prompt, ratio, params.get("quality"), params.get("resolution")) if images_api
                else image_body(m["id"], prompt, ratio))
        if not images_api and ("quality" in params or "resolution" in params):
            self.warnings.append(f"step {info.id}: model using the chat API ignores quality/resolution")
        parse = parse_images if images_api else parse_image
        endpoint = "/images" if images_api else "/chat/completions"

        def on_value(v):
            data, media = v
            rel = self.rec.write_bytes(f"{info.folder}/image.{IMAGE_EXT.get(media, 'bin')}", data)
            w, h = image_size(data)
            self.rec.event("image_saved", step=info.id, path=rel, media_type=media, bytes=len(data), width=w, height=h)
            self.rows[info.id]["note"] = f"{rel.rsplit('/', 1)[1]}, {w}×{h}"
            if ratio:
                a, b = map(int, ratio.split(":"))
                if not w or not h:
                    raise AgencastError("config", f"cannot determine image dimensions ({media}) — cannot verify aspect_ratio")
                dev = abs(w / h - a / b) / (a / b)
                if dev > 0.02:
                    raise AgencastError("config", f"model does not support aspect_ratio {ratio}: image is {w}×{h} "
                                             f"(deviation {dev:.1%}, allowed 2 %) — no cropping is performed")
            return {"file": FileRef(rel)}, f"<file: {rel}, {len(data)} B>"

        t0 = time.monotonic()
        try:
            return await self.with_deadline(info, ctx, info.data.get("timeout", DEFAULT_TIMEOUT["image"]), self.call_api(
                info, ctx, self.leaf_budgets(info, ctx, image=True), endpoint,
                lambda a, l: (body, {"alias": alias, "model": m["id"], "structured_output": None}),
                parse, "model_call", on_value, image=True, timeout_key="images" if images_api else "chat"))
        finally:
            self.image_duration += time.monotonic() - t0

    async def step_set(self, info: StepInfo, ctx: Ctx):
        return {k: self.expr(v, f"set.{k}") if isinstance(v, str) else v for k, v in info.data["set"].items()}

    async def step_fail(self, info: StepInfo, ctx: Ctx):
        raise AgencastError("fail", self.text(info.data["fail"], "fail"))

    async def step_output(self, info: StepInfo, ctx: Ctx):
        specs, values, public = self.p.scenario["outputs"], {}, {}
        for k, v in info.data["output"].items():
            val = self.tpl(v, f"output.{k}") if isinstance(v, str) else v
            want = specs[k]["type"]
            if val is not None and (isinstance(val, FileRef) != (want == "file")
                                    or want != "file" and not _matches(want, val)):
                raise AgencastError("expression", f"output.{k}: output must be {want}, value is {kind(val)}")
            values[k] = val
            public[k] = self.upload(k, val) if isinstance(val, FileRef) and not self.depth else val  # 3b
        self.outputs = public
        return values

    def upload(self, name: str, ref: FileRef) -> str:
        """File from output → storage; callback carries the URL (§5.7)."""
        run_dir = self.rec.dir.resolve()
        src = (run_dir / ref.path).resolve()
        if not src.is_relative_to(run_dir) or not src.is_file():
            raise AgencastError("config", f"file {ref.path} is not inside the run directory")
        st = self.p.config["storage"]
        if st["type"] != "local":  # validate checks this; R2 is not available yet
            raise AgencastError("config", "r2 storage is not supported yet — set storage.type: local")
        key = f"{self.storage_prefix}/{name}{src.suffix}"
        dest = self.p.base / st["local"]["path"] / key
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        except OSError as e:
            raise AgencastError("transient", f"uploading {ref.path} to storage failed: {e}") from None
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
            raise next((e for e in errs if isinstance(e, AgencastError)), errs[0]) from None
        return None

    async def step_switch(self, info: StepInfo, ctx: Ctx):
        sw = info.data["switch"]
        v = self.expr(sw["value"], "switch.value")
        if not isinstance(v, str):
            raise AgencastError("expression", f"switch.value must return text (string), got {kind(v)}: {to_json(v)[:80]}")
        reason = f"switch: {info.id} = {to_json(v)}"
        chosen = sw["cases"][v] if v in sw["cases"] else sw["default"]
        for lst in [*sw["cases"].values(), sw["default"]]:
            if lst is not chosen:
                for s in lst:
                    self.skip(s, "switch", reason)
        self.rows[info.id]["note"] = f"branch {v if v in sw['cases'] else 'default'}"
        await self.run_list(chosen, ctx.inner(info, branch=v))
        return None

    # --- 3b: call and report --------------------------------------------------------------
    async def step_call(self, info: StepInfo, ctx: Ctx):
        """Nested scenario in the same run (§5.3): shared record, budget and deadlines; steps have a path
        `propose/copy` and directories `steps/03-propose/steps/01-copy/` (run-record.md)."""
        c = info.data["call"]
        callee, given, inputs = self.p.callees[c["scenario"]], c.get("inputs") or {}, {}
        for k, sp in (callee.scenario.get("inputs") or {}).items():
            if k not in given:
                inputs[k] = sp["default"]
                continue
            v = self.tpl(given[k], f"call.inputs.{k}") if isinstance(given[k], str) else given[k]
            if not _matches(sp["type"], v):
                raise AgencastError("expression", f"call.inputs.{k}: input of scenario '{c['scenario']}' must be {sp['type']}, "
                                             f"value is {kind(v)}")
            inputs[k] = v
        self.rec.write(f"{info.folder}/inputs.json", inputs)
        sub = copy.copy(self)  # shares record, client, budgets, warnings and step costs (key = path)
        sub.p = replace(callee, steps={k: replace(s, id=f"{info.id}/{s.id}", dir=f"{info.folder}/")
                                       for k, s in callee.steps.items()})
        sub.inputs, sub.values, sub.defaulted, sub.rows, sub.outputs = inputs, {"inputs": inputs, "steps": {}}, set(), {}, None
        sub.cost = sub.image_cost = sub.image_duration = 0.0
        sub.depth = self.depth + 1
        try:
            await sub.run_list(callee.scenario["steps"], ctx.inner(info))
        except AgencastError as e:
            if e.fatal and f"step '{info.id}' (" in e.message:  # call step's own budget_usd/timeout is covered by its on_error
                e.fatal = False
            raise
        finally:
            self.cost += sub.cost
            self.image_cost += sub.image_cost
            self.image_duration += sub.image_duration
            self.rows[info.id]["note"] = f"scenario {c['scenario']} ({count(len(sub.rows), 'step', 'steps')})"
        return sub.outputs or {}

    def publish_report(self):
        """report.html to the run directory and storage; URL goes in the callback (run-record.md)."""
        try:  # a report error must not prevent the callback
            rel = self.rec.write("report.html", report_html(self))
            self.report_url = self.upload("report", FileRef(rel))
        except Exception as e:
            why = f"{e.cls}: {e.message}" if isinstance(e, AgencastError) else f"{type(e).__name__}: {e}"
            self.warnings.append(f"could not create or upload report.html ({why}) — report_url is null")

    # --- callback --------------------------------------------------------------------
    async def send_callback(self, data: bytes) -> bool:
        """POST to the callback URL, HMAC-SHA256 over exact body bytes (run-record.md Signature)."""
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


def dry_run(p: Project, inputs: dict) -> Record:
    """Directory with only plan.md and inputs.json (run-record.md); for task, also tools offered by MCP servers."""
    servers = mcp_servers_used(p)
    offers = asyncio.run(mcp_offers(p, servers)) if servers else None
    rec = new_record(p.runs_dir, p.scenario["name"], secret_values(p))
    rec.write("plan.md", plan_md(p, offers))
    rec.write("inputs.json", inputs)
    return rec


async def mcp_offers(p: Project, servers: set) -> dict:
    """3a: start servers only for tools/list (scenario.md §7 --dry-run) in a temporary directory — the plan
    directory keeps only plan.md; startup errors appear in the plan instead of the list."""
    offers = {}
    with tempfile.TemporaryDirectory() as tmp:
        rec = Record(Path(tmp) / "run", secret_values(p))
        pool = Pool(p.mcp, rec.dir, rec)
        try:
            for s in sorted(servers):
                try:
                    offers[s] = sorted((await pool.get(s)).tools)
                except AgencastError as e:
                    offers[s] = e.message
        finally:
            await pool.close()
    return offers


def run_scenario(p: Project, inputs: dict, *, fake=None, callback_url=None, request_key=None,
                 callback_transport=None, run_id=None, error: AgencastError | None = None, resume=False) -> Run:
    """Run a validated scenario; `fake` = agencast.fake.Fake instead of network calls.

    3b (webhook): `run_id` assigned when the request arrives; `error` = run will not start, only record
    and callback (validate failed after dequeuing, run interrupted by server restart).
    ISSUES 40: acquire a `max_parallel_runs` slot before creating the run directory; unavailable slots and exhausted
    `daily_budget_usd` follow the same path as `error`."""
    key = preflight(p, fake=fake is not None or error is not None, callback_url=callback_url)
    lim, held, waited, lock = p.config["limits"], None, None, None
    slots = local_slots(p.runs_dir, lim["max_parallel_runs"]) if error is None and "max_parallel_runs" in lim else None
    if slots:
        held, waited = take_slot(slots, lim["run_timeout"])
        if held is None:
            error = AgencastError("timeout", f"no slot became available within run_timeout {lim['run_timeout']} "
                                             f"(max_parallel_runs={slots.size}) — run did not start")
    try:
        if error is None and "daily_budget_usd" in lim:
            error = daily_budget_error(p, fake is not None, lim["daily_budget_usd"])
        if run_id:  # webhook: run_id assigned on receipt; exist_ok = interrupted run after server restart
            rec = Record(p.runs_dir / run_id, secret_values(p), exist_ok=error is not None)
        else:
            rec = new_record(p.runs_dir, p.scenario["name"], secret_values(p))
            run_id = rec.dir.name
        lock = hold_run_lock(rec.dir)  # 0.7.0: running = lock held by a live process (record.run_status)
        if error is None:
            rec.write("plan.md", plan_md(p))
            rec.write("inputs.json", inputs)
            snapshot(p, rec)
        client = Client(p.config["openrouter"]["base_url"], key, fake.transport() if fake else None)
        run = Run(p, inputs, rec, client, run_id, callback_url=callback_url, request_key=request_key,
                  callback_transport=callback_transport, fake=fake is not None)
        run.waited_s = waited
        asyncio.run(run.execute(error, resume=resume))
        return run
    finally:
        if lock is not None:
            os.close(lock)
        if held is not None:
            slots.release(held)


def snapshot(p: Project, rec: Record):
    """Copy the scenario being run and all `call` callees to `scenario/<name>.yaml` (run-record.md,
    0.7.0) — run detail then displays the step tree as it was during the run."""
    todo, seen = [p], set()
    while todo:
        q = todo.pop()
        if q.scenario["name"] not in seen:
            seen.add(q.scenario["name"])
            text = rec.mask(q.scenario_path.read_text(encoding="utf-8"))
            rec.write_bytes(f"scenario/{q.scenario['name']}.yaml", text.encode())
            todo += q.callees.values()


def take_slot(slots, run_timeout: str) -> tuple[int | None, float | None]:
    """(held slot or None after run_timeout, wait duration or None if no wait was needed)."""
    t0 = time.monotonic()
    if (held := slots.acquire()) is not None:
        return held, None
    print(f"waiting for a free slot (max_parallel_runs={slots.size})", file=sys.stderr, flush=True)
    while (held := slots.acquire()) is None and time.monotonic() - t0 < seconds(run_timeout):
        time.sleep(SLOT_POLL_S)
    return held, round(time.monotonic() - t0, 3)


def daily_budget_error(p: Project, fake: bool, limit: float) -> AgencastError | None:
    """Check only at startup: a run below the limit can exceed it by at most its run_budget_usd."""
    day = now_iso()[:10]
    spent = local_ledger(p.runs_dir, fake).total(day)
    if spent >= limit:
        return AgencastError("budget", f"daily spend limit exhausted: already {format_usd(spent)} today ({day} UTC) "
                                       f"of {limit} USD (daily_budget_usd) — run did not start")
    return None
