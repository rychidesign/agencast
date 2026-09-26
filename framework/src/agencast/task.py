"""Krok `task` (scenario.md task, agent.md, DESIGN §5.8) a `dedupe_key` (scenario.md §3).

Smyčka model ↔ nástroje: každý tah je jedno `Run.call_api` (opakování po
`transient`/`schema` jde uvnitř a do `max_turns` se nepočítá). Model vidí jen
efektivní sadu nástrojů (krok ⊆ agent ⊆ mcp.yaml), `load_skill` a na úrovni
kaskády `tool_wrapper` `_submit_output`, který smyčku ukončí a nikdy nejde
na MCP server.
"""
import base64
import hashlib
import json
import os
import time

from . import AgencastError
from .mcp_client import Pool, api_name, arg_errors, provider_schema
from .providers import (LEVELS, SUBMIT_TOOL, assistant_message, image_size, json_schema, parse_task,
                        prompt_level_suffix, task_body)
from .record import scrub
from .validate import DEFAULT_TIMEOUT, StepInfo, effective_tools, seconds

SKILLS_SERVER, SKILL_TOOL = "_skills", "load_skill"
IMAGE_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}


def system_prompt_task(agent) -> str:
    """Tělo agenta + oddíl `## Skilly` se seznamem `- jméno: description` (agent.md, u `task`)."""
    parts = [agent.body.strip()]
    if agent.skills:
        parts.append("## Skilly\n\n" + "\n".join(f"- {n}: {d}" for n, d, _ in agent.skills))
    return "\n\n".join(parts)


def skill_tool(agent) -> dict:
    return {"type": "function", "function": {
        "name": SKILL_TOOL,
        "description": "Načte celé instrukce skillu ze seznamu Skilly. Když je skill pro úkol relevantní, "
                       "načti ho dřív, než začneš.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string", "enum": [n for n, _, _ in agent.skills]}},
                       "required": ["name"], "additionalProperties": False}}}


# --- dedupe_key -----------------------------------------------------------------------

def dedupe_file(run, info: StepInfo):
    """`<runs>/_dedupe/<sha256(scénář/krok/klíč)>.json` — klíč vázaný na scénář a krok; falešný běh
    (`--fake`) má vlastní `_dedupe-fake/`, aby jeho vymyšlený výstup nepřeskočil ostrý krok (BUGS 8)."""
    key = run.text(info.data["dedupe_key"], "dedupe_key")
    h = hashlib.sha256(f"{run.p.scenario['name']}/{info.key}/{key}".encode()).hexdigest()  # key = id v souboru
    return run.p.runs_dir / ("_dedupe-fake" if run.fake else "_dedupe") / f"{h}.json", key


def dedupe_skip(run, info: StepInfo) -> bool:
    """Krok už v jiném běhu proběhl → přeskočit s jeho výstupem; `started` bez `succeeded` → `config`."""
    path, key = dedupe_file(run, info)
    if not path.is_file():
        return False
    rec = json.loads(path.read_text(encoding="utf-8"))
    if rec.get("state") != "succeeded":
        raise AgencastError("config", f"krok mohl proběhnout jen částečně (dedupe_key {key!r}, běh {rec.get('run_id')}), "
                                 f"ověř ručně a smaž {path}")
    reason = f"dedupe_key {key!r}: krok už proběhl v běhu {rec['run_id']}"
    run.rec.event("step_skipped", step=info.id, kind=info.kind, reason_code="dedupe", reason=reason,
                  default_used=False)
    run.rows[info.id] = {"nn": info.nn, "id": info.id, "kind": info.kind, "status": "skipped",
                         "duration": None, "cost": 0.0, "note": reason}
    run.values["steps"][info.key] = rec["output"]
    return True


def _dedupe_write(path, data: dict, exclusive: bool):
    """Atomicky: `started` jen když soubor neexistuje, `succeeded` přes přejmenování."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False)
    if exclusive:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            raise AgencastError("config", f"krok mezitím spustil jiný běh, ověř ručně a smaž {path}") from None
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        return
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# --- smyčka -----------------------------------------------------------------------------

async def run_task(run, info: StepInfo, ctx):
    t = info.data["task"]
    agent = run.p.agents[t["agent"]]
    lim = agent.data["limits"]
    timeout = min(info.data.get("timeout") or lim.get("timeout") or DEFAULT_TIMEOUT["task"],
                  lim.get("timeout") or "24h", key=seconds)
    loop = _Loop(run, info, ctx, agent)
    return await run.with_deadline(info, ctx, timeout, loop.execute())


class _Loop:
    def __init__(self, run, info: StepInfo, ctx, agent):
        self.run, self.info, self.ctx, self.agent = run, info, ctx, agent
        self.t = info.data["task"]
        self.alias = agent.data["model"]
        self.m = run.p.config["models"][self.alias]
        self.schema = json_schema(self.t["schema"]) if "schema" in self.t else None
        self.dedupe = dedupe_file(run, info)[0] if "dedupe_key" in info.data else None
        self.started = False     # dedupe `started` už zapsán
        self.routes: dict = {}   # jméno pro API → (Server, mcp Tool)
        self.notes: dict = {}    # data URL obrázku → text do záznamu
        self.tool_calls = 0

    async def tools(self) -> list:
        out = []
        for s, names in effective_tools(self.agent.data, self.t).items():
            srv = await self.run.mcp.get(s)
            for n in names:
                tool = srv.tools.get(n)
                if tool is None:
                    raise AgencastError("config", f"MCP server '{s}' nemá nástroj '{n}' (nabízí: {', '.join(srv.tools)})")
                try:
                    params = provider_schema(tool.input_schema)
                except ValueError as e:
                    raise AgencastError("config", f"schéma nástroje {s}.{n}: {e}") from None
                self.routes[api_name(s, n)] = (srv, tool)
                out.append({"type": "function", "function": {"name": api_name(s, n),
                                                             "description": tool.description or "",
                                                             "parameters": params}})
        return out + ([skill_tool(self.agent)] if self.agent.skills else [])

    def redact(self, body):
        """Obrázky z nástrojů jako `<soubor: …>`, zbytek jako u ostatních kroků (run-record.md)."""
        def walk(o):
            if isinstance(o, dict):
                return {k: walk(v) for k, v in o.items()}
            if isinstance(o, list):
                return [walk(v) for v in o]
            return self.notes.get(o, o) if isinstance(o, str) else o
        return scrub(walk(body))

    async def execute(self):
        run, info = self.run, self.info
        tools = await self.tools()
        system = system_prompt_task(self.agent)
        prompt = run.text(self.t["prompt"], "task.prompt")
        max_turns = self.t.get("max_turns", self.agent.data["limits"]["max_turns"])
        messages = [{"role": "user", "content": prompt}]
        # vždy od tool_wrapper, bez ohledu na alias: nativní schéma v každém tahu svádí model (Haiku)
        # odpovědět JSONem bez volání nástrojů (BUGS 7, ISSUES 36); alias platí jen pro ask
        st = {"level": "tool_wrapper" if self.schema else None, "feedback": [], "prev": None, "turn": 0}
        run.rec.write(f"{info.folder}/prompt.md", "# System prompt\n\n" + system + "\n\n# Zpráva\n\n" + prompt)

        def build(attempt, last):
            if last and last.cls == "schema":  # kaskáda o úroveň níž + zpětná vazba (jako u ask)
                if st["level"] != "prompt":
                    st["level"] = LEVELS[LEVELS.index(st["level"]) + 1]
                prev = st["prev"]
                st["feedback"] = ([assistant_message(prev)] if prev and prev.get("content") and not prev.get("tool_calls")
                                  else []) + [{"role": "user", "content": f"Předchozí odpověď byla neplatná: "
                                               f"{last.message}\nOdpověz znovu, přesně v požadovaném tvaru."}]
            sysp = system + (prompt_level_suffix(self.schema) if st["level"] == "prompt" else "")
            return task_body(self.m["id"], sysp, messages + st["feedback"], tools, st["level"], self.schema,
                             self.m.get("max_tokens")), \
                {"turn": st["turn"], "alias": self.alias, "model": self.m["id"], "structured_output": st["level"]}

        def parse(status, body, headers):
            meta, value, err = parse_task(status, body, headers, st["level"], self.schema)
            st["prev"] = meta.pop("message")
            return meta, value, err

        scopes = run.leaf_budgets(info, self.ctx, self.agent.data["limits"]["budget_usd"])
        for turn in range(1, max_turns + 1):
            st["turn"] = turn
            value = await run.call_api(info, self.ctx, scopes, "/chat/completions", build, parse, "model_call",
                                       record=self.redact)
            messages += st["feedback"]
            st["feedback"] = []
            if "final" in value:
                out = value["final"] if self.schema else {"text": value["final"]}
                calls = [c for c in st["prev"].get("tool_calls") or [] if c["function"]["name"] != SUBMIT_TOOL]
                if calls:
                    run.warnings.append(f"krok {info.id}: model spolu s {SUBMIT_TOOL} volal i jiné nástroje "
                                        f"({', '.join(c['function']['name'] for c in calls)}) — nespustily se")
                if self.dedupe:
                    _dedupe_write(self.dedupe, {"state": "succeeded", "run_id": run.run_id, "output": out}, False)
                run.rows[info.id]["note"] = (f"{self.alias} → {self.m['id']}, tahů {turn}, nástrojů {self.tool_calls}"
                                             + (f" ({st['level']})" if self.schema else ""))
                return out
            if turn == max_turns:  # poslední tah chce další nástroje — nespouštět, model by výsledek neviděl
                break
            messages.append(assistant_message(st["prev"]))
            images = []
            for c in value["calls"]:
                messages.append(await self.dispatch(c, turn, images))
            if images:  # obrázky až v user zprávě za tool zprávami (Gemini je v tool zprávě odmítne, §5.8)
                messages.append({"role": "user", "content": [{"type": "text", "text": "Obrázky z výsledků nástrojů:"},
                                                             *images]})
        raise AgencastError("budget", f"max_turns {max_turns} vyčerpán bez finální odpovědi (model dál volá nástroje)")

    async def dispatch(self, call: dict, turn: int, images: list) -> dict:
        """Jedno volání nástroje → tool zpráva. Nepovolené jméno ani špatné argumenty na server nejdou."""
        run, info = self.run, self.info
        fn = call.get("function") or {}
        name, raw = fn.get("name") or "", fn.get("arguments") or "{}"
        n = run.calls[info.id] = run.calls.get(info.id, 0) + 1
        self.tool_calls += 1
        route = self.routes.get(name)
        if route:
            server, tool = route[0].name, route[1].name
        elif name == SKILL_TOOL and self.agent.skills:
            server, tool = SKILLS_SERVER, SKILL_TOOL
        else:
            server, tool = (name.split("__", 1) if "__" in name else (None, name))
        flags = {"allowed": bool(route) or server == SKILLS_SERVER, "invalid_args": False, "is_error": False}
        t0, files = time.monotonic(), []
        try:
            args = json.loads(raw)
        except ValueError as e:
            args, errs = raw, [f"argumenty nejsou JSON: {e}"]
        else:
            errs = [] if isinstance(args, dict) else ["argumenty musí být objekt"]
        if not flags["allowed"]:
            text = f"Chyba: nástroj {name} není povolen. Povolené: {', '.join(self.routes) or '—'}" + \
                   (f", {SKILL_TOOL}" if self.agent.skills else "")
        elif errs or (errs := arg_errors(route[1].input_schema if route else skill_tool(self.agent)["function"]["parameters"],
                                         args)):
            flags["invalid_args"] = True
            text = "Chyba: argumenty neprošly schématem nástroje: " + "; ".join(errs[:5])
        elif server == SKILLS_SERVER:
            text = next(b for s, _, b in self.agent.skills if s == args["name"])
        else:
            if self.dedupe and not self.started:  # started před prvním voláním nástroje (§5.2)
                _dedupe_write(self.dedupe, {"state": "started", "run_id": run.run_id, "output": None}, True)
                self.started = True
            res = await Pool.call(route[0], tool, args)
            flags["is_error"] = res.is_error
            text = ("Chyba nástroje: " if res.is_error else "") + res.text
            for k, (data, media) in enumerate(res.images, 1):
                rel = run.rec.write_bytes(f"{info.folder}/tool-{n:02d}-{k}.{IMAGE_EXT.get(media, 'bin')}", data)
                w, h = image_size(data)
                run.rec.event("image_saved", step=info.id, path=rel, media_type=media, bytes=len(data), width=w, height=h)
                url = f"data:{media};base64,{base64.b64encode(data).decode()}"
                self.notes[url] = f"<soubor: {rel}, {len(data)} B>"
                images.append({"type": "image_url", "image_url": {"url": url}})
                files.append(rel)
                text += f"\nobrázek v další zprávě: {rel.rsplit('/', 1)[1]}"
        call_file = run.rec.write(f"{info.folder}/calls/{n:02d}.tool.json", {
            "turn": turn, "name": name, "server": server, "tool": tool, "arguments": args, **flags,
            "result": text, "files": files})
        run.rec.event("tool_call", step=info.id, turn=turn, server=server, tool=tool, **flags,
                      duration_s=round(time.monotonic() - t0, 3), call_file=call_file)
        return {"role": "tool", "tool_call_id": call.get("id"), "content": text}
