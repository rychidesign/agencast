"""The `task` step (scenario.md task, agent.md, DESIGN §5.8), `dedupe_key` (scenario.md §3) and shared
run state behind an interface (DedupeStore, SlotStore, Ledger — DESIGN “Wrappers”).

Model ↔ tools loop: each turn is one `Run.call_api` (retries after
`transient`/`schema` happen internally and do not count toward `max_turns`). The model sees only
the effective tool set (step ⊆ agent ⊆ mcp.yaml), `load_skill` and, at the
`tool_wrapper` cascade level, `_submit_output`, which ends the loop and never goes
to an MCP server.
"""
import asyncio
import base64
import fcntl
import hashlib
import json
import os
import threading
import time
from typing import Any

from . import AgencastError
from .mcp_client import Pool, api_name, arg_errors, provider_schema
from .providers import (LEVELS, SUBMIT_TOOL, assistant_message, image_size, json_schema, parse_task,
                        prompt_level_suffix, schema_feedback, task_body)
from .record import redact
from .validate import DEFAULT_TIMEOUT, StepInfo, effective_tools, seconds

SKILLS_SERVER, SKILL_TOOL = "_skills", "load_skill"
IMAGE_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif", "image/avif": "avif"}


def images_md(lines: list) -> str:
    """`# Images` section of prompt.md: one line per image sent with the message (0.18.0)."""
    return "\n\n# Images\n\n" + "\n".join(f"- {n}" for n in lines) if lines else ""


def system_prompt_task(agent) -> str:
    """Agent body + `## Skills` section listing `- name: description` (agent.md, for `task`)."""
    parts = [agent.body.strip()]
    if agent.skills:
        parts.append("## Skills\n\n" + "\n".join(f"- {n}: {d}" for n, d, _ in agent.skills))
    return "\n\n".join(parts)


def skill_tool(agent) -> dict:
    return {"type": "function", "function": {
        "name": SKILL_TOOL,
        "description": "Load the full instructions for a skill from the Skills list. When a skill is relevant to the task, "
                       "load it before starting.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string", "enum": [n for n, _, _ in agent.skills]}},
                       "required": ["name"], "additionalProperties": False}}}


# --- dedupe_key -----------------------------------------------------------------------

class DedupeStore:
    """`dedupe_key` store (DESIGN “Wrappers”): local `<directory>/<sha256>.json`. On Modal,
    the wrapper supplies its own store (Dict etc.) with the same three methods."""

    def __init__(self, directory):
        self.dir = directory

    def where(self, key: str) -> str:
        return str(self.dir / f"{key}.json")

    def get(self, key: str) -> dict | None:
        path = self.dir / f"{key}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def claim(self, key: str, run_id: str):
        """Exclusively and atomically write `started`; if a record exists, raise `config`."""
        path = self.dir / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            raise AgencastError("config", f"another run has started the step in the meantime, check manually and delete {path}") from None
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps({"state": "started", "run_id": run_id, "output": None}, ensure_ascii=False))

    def finish(self, key: str, data: dict):
        """Atomically (by renaming) replace the record with `data` (`state: succeeded`)."""
        path = self.dir / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)


def local_dedupe(runs_dir, fake: bool) -> DedupeStore:
    """`<runs>/_dedupe/`; a fake run (`--fake`) has its own `_dedupe-fake/` so its fabricated
    output cannot cause a real step to be skipped (BUGS 8)."""
    return DedupeStore(runs_dir / ("_dedupe-fake" if fake else "_dedupe"))


# --- limits.max_parallel_runs and daily_budget_usd (ISSUES 40) ----------------------------

class SlotStore:
    """Cross-process `max_parallel_runs` slots (DESIGN “Wrappers”): local `flock` on
    `<directory>/<n>.lock`, n = 1..N; a process crash also releases the lock. On Modal, the wrapper supplies
    its own semaphore with the same two methods."""

    def __init__(self, directory, size: int):
        self.dir, self.size = directory, size

    def acquire(self) -> int | None:
        """Free slot (held descriptor), otherwise None — nonblocking."""
        self.dir.mkdir(parents=True, exist_ok=True)
        for n in range(1, self.size + 1):
            fd = os.open(self.dir / f"{n}.lock", os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                os.close(fd)
        return None

    def release(self, fd: int):
        os.close(fd)  # closing the descriptor releases flock


class Ledger:
    """Daily spend ledger (DESIGN “Wrappers”): local `<directory>/<YYYY-MM-DD>.jsonl` (UTC), one
    `{run_id, cost_usd, finished_at}` row per completed run, appended under `flock`. On Modal, the wrapper
    supplies its own store with the same methods (`rows` is read by GET /projects/<p>/spend)."""

    def __init__(self, directory):
        self.dir = directory

    def total(self, day: str) -> float:
        return sum(r["cost_usd"] for r in self.rows(day))

    def rows(self, day: str) -> list[dict[str, Any]]:
        path = self.dir / f"{day}.jsonl"
        if not path.is_file():
            return []
        with open(path, encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            return [json.loads(line) for line in f if line.strip()]

    def add(self, day: str, row: dict):
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / f"{day}.jsonl", "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def hold_run_lock(run_dir) -> int:
    """Live run lock (api-findings 1): `flock` on `<run>/run.lock` for the process lifetime; released by
    `os.close` or a process crash. Blocks because the `run_locked` reader holds a shared lock only briefly.
    On Modal, the wrapper supplies its own (like `SlotStore`)."""
    fd = os.open(run_dir / "run.lock", os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def run_locked(run_dir) -> bool:
    """True = run lock held by a live process (even this one — flock belongs to the open file, not the process)."""
    try:
        fd = os.open(run_dir / "run.lock", os.O_RDONLY)
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        return False
    except BlockingIOError:
        return True
    finally:
        os.close(fd)


def local_slots(runs_dir, size: int) -> SlotStore:
    """`<runs>/_slots/`; fake runs share slots with real runs (concurrency, not data)."""
    return SlotStore(runs_dir / "_slots", size)


def local_ledger(runs_dir, fake: bool) -> Ledger:
    """`<runs>/_ledger/`; fake runs use `_ledger-fake/` (symmetrical with `_dedupe-fake/`)."""
    return Ledger(runs_dir / ("_ledger-fake" if fake else "_ledger"))


def dedupe_key(run, info: StepInfo) -> tuple[str, str]:
    """(sha256(scenario/step/key), key) — key scoped to the scenario and step."""
    key = run.text(info.data["dedupe_key"], "dedupe_key")
    return hashlib.sha256(f"{run.p.scenario['name']}/{info.key}/{key}".encode()).hexdigest(), key


def dedupe_skip(run, info: StepInfo) -> bool:
    """Step already ran in another run → skip with its output; `started` without `succeeded` → `config`."""
    h, key = dedupe_key(run, info)
    rec = run.dedupe.get(h)
    if rec is None:
        return False
    if rec.get("state") != "succeeded":
        raise AgencastError("config", f"step may have run only partially (dedupe_key {key!r}, run {rec.get('run_id')}), "
                                 f"check manually and delete {run.dedupe.where(h)}")
    reason = f"dedupe_key {key!r}: step already ran in run {rec['run_id']}"
    run.rec.event("step_skipped", step=info.id, kind=info.kind, nn=info.nn, reason_code="dedupe", reason=reason,
                  default_used=False)
    run.rows[info.id] = {"nn": info.nn, "id": info.id, "kind": info.kind, "status": "skipped",
                         "duration": None, "cost": 0.0, "note": reason}
    run.values["steps"][info.key] = rec["output"]
    return True


# --- loop -----------------------------------------------------------------------------

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
        self.dedupe = dedupe_key(run, info)[0] if "dedupe_key" in info.data else None
        self.started = False     # dedupe `started` already written
        self.routes: dict = {}   # API name → (Server, mcp Tool)
        self.notes: dict = {}    # image data URL → record text
        self.tool_calls = 0
        self.ran = False         # a call went to an MCP server: a schema retry must not run tools again

    async def tools(self) -> list:
        out = []
        for s, names in effective_tools(self.agent.data, self.t).items():
            srv = await self.run.mcp_server(self.info, s)
            for n in names:
                tool = srv.tools.get(n)
                if tool is None:
                    raise AgencastError("config", f"MCP server '{s}' has no tool '{n}' (offers: {', '.join(srv.tools)})")
                try:
                    params = provider_schema(tool.input_schema)
                except ValueError as e:
                    raise AgencastError("config", f"tool schema {s}.{n}: {e}") from None
                self.routes[api_name(s, n)] = (srv, tool)
                out.append({"type": "function", "function": {"name": api_name(s, n),
                                                             "description": tool.description or "",
                                                             "parameters": params}})
        return out + ([skill_tool(self.agent)] if self.agent.skills else [])

    def redact(self, body):
        """Tool and input images as `<file: …>`, the rest as in other steps (run-record.md)."""
        return redact(body, self.notes)

    async def execute(self):
        run, info = self.run, self.info
        tools = await self.tools()
        system = system_prompt_task(self.agent)
        prompt = run.text(self.t["prompt"], "task.prompt")
        parts, notes, lines, _ = run.image_parts(self.t.get("images"), "task.images")  # 0.18.0
        self.notes.update(notes)
        max_turns = self.t.get("max_turns", self.agent.data["limits"]["max_turns"])
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}, *parts] if parts else prompt}]
        # always start with tool_wrapper regardless of alias: native schema on each turn tempts the model (Haiku)
        # to answer with JSON without calling tools (BUGS 7, ISSUES 36); alias applies only to ask
        st = {"level": "tool_wrapper" if self.schema else None, "feedback": [], "prev": None, "turn": 0,
              "answer_only": False}
        run.rec.write(f"{info.folder}/prompt.md", "# System prompt\n\n" + system + "\n\n# Message\n\n" + prompt
                      + images_md(lines))

        def build(attempt, last):
            if last and last.cls == "schema":  # cascade one level down + feedback (as with ask)
                if st["level"] != "prompt":
                    st["level"] = LEVELS[LEVELS.index(st["level"]) + 1]
                # tools that already ran must not run again (side effects, §5.2): from now on only the answer.
                # Before the first call to a server there is nothing to repeat and the model still needs its tools.
                st["answer_only"] = self.ran
                st["feedback"] = schema_feedback(
                    st["prev"], last.message, st["level"],
                    (f" Call only {SUBMIT_TOOL}." if st["level"] == "tool_wrapper" else " Do not call tools.")
                    + " The tool calls above already ran — use their results." if st["answer_only"] else "")
            sysp = system + (prompt_level_suffix(self.schema) if st["level"] == "prompt" else "")
            return task_body(self.m["id"], sysp, messages + st["feedback"], tools, st["level"], self.schema,
                             self.m.get("max_tokens"), st["answer_only"]), \
                {"turn": st["turn"], "alias": self.alias, "model": self.m["id"], "structured_output": st["level"]}

        def parse(status, body, headers):
            meta, value, err = parse_task(status, body, headers, st["level"], self.schema)
            st["prev"] = meta.pop("message")
            if st["answer_only"] and value and "calls" in value:  # `tool_choice` ignored: a retry never runs tools
                value, err = None, AgencastError("schema", "model called tools instead of answering")
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
                    run.warnings.append(f"step {info.id}: model called other tools together with {SUBMIT_TOOL} "
                                        f"({', '.join(c['function']['name'] for c in calls)}) — they were not executed")
                if self.dedupe:
                    run.dedupe.finish(self.dedupe, {"state": "succeeded", "run_id": run.run_id, "output": out})
                run.rows[info.id]["note"] = (f"{self.alias} → {self.m['id']}, turns {turn}, tools {self.tool_calls}"
                                             + (f" ({st['level']})" if self.schema else ""))
                return out
            if turn == max_turns:  # last turn requests more tools — do not execute, the model would not see the result
                break
            messages.append(assistant_message(st["prev"]))
            images = []
            for c in value["calls"]:
                messages.append(await self.dispatch(c, turn, images))
            if images:  # images in a user message after tool messages (Gemini rejects them in tool messages, §5.8)
                messages.append({"role": "user", "content": [{"type": "text", "text": "Images from tool results:"},
                                                             *images]})
        raise AgencastError("budget", f"max_turns {max_turns} exhausted without a final answer (model keeps calling tools)")

    async def dispatch(self, call: dict, turn: int, images: list) -> dict:
        """One tool call → tool message. Disallowed names and invalid arguments are not sent to the server."""
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

        def record(text, **error):
            call_file = run.rec.write(f"{info.folder}/calls/{n:02d}.tool.json", {
                "turn": turn, "name": name, "server": server, "tool": tool, "arguments": args, **flags,
                "result": text, "files": files, **error})
            run.rec.event("tool_call", step=info.id, turn=turn, server=server, tool=tool, **flags, **error,
                          duration_s=round(time.monotonic() - t0, 3), call_file=call_file)
        try:
            args = json.loads(raw)
        except ValueError as e:
            args, errs = raw, [f"arguments are not JSON: {e}"]
        else:
            errs = [] if isinstance(args, dict) else ["arguments must be an object"]
        if not flags["allowed"]:
            text = f"Error: tool {name} is not allowed. Allowed: {', '.join(self.routes) or '—'}" + \
                   (f", {SKILL_TOOL}" if self.agent.skills else "")
        elif errs or (errs := arg_errors(route[1].input_schema if route else skill_tool(self.agent)["function"]["parameters"],
                                         args)):
            flags["invalid_args"] = True
            text = "Error: arguments did not match the tool schema: " + "; ".join(errs[:5])
        elif server == SKILLS_SERVER:
            text = next(b for s, _, b in self.agent.skills if s == args["name"])
        else:
            if self.dedupe and not self.started:  # started before the first tool call (§5.2)
                run.dedupe.claim(self.dedupe, run.run_id)
                self.started = True
            self.ran = True
            try:
                res = await Pool.call(route[0], tool, args)
            except BaseException as e:  # timeout, dead server, cancellation (deadline, interrupt): it may have run
                flags["is_error"] = True
                record(None, error=e.message if isinstance(e, AgencastError) else "cancelled before the tool answered "
                       "(may have run)" if isinstance(e, asyncio.CancelledError) else f"{type(e).__name__}: {e}")
                raise
            flags["is_error"] = res.is_error
            text = ("Tool error: " if res.is_error else "") + res.text
            for k, (data, media) in enumerate(res.images, 1):
                rel = run.rec.write_bytes(f"{info.folder}/tool-{n:02d}-{k}.{IMAGE_EXT.get(media, 'bin')}", data)
                w, h = image_size(data)
                size = run.rec.size(rel)
                run.rec.event("image_saved", step=info.id, path=rel, media_type=media, bytes=size, width=w, height=h)
                url = f"data:{media};base64,{base64.b64encode(data).decode()}"
                self.notes.setdefault(url, f"<file: {rel}, {size} B>")  # same bytes as an input image: first wins
                images.append({"type": "image_url", "image_url": {"url": url}})
                files.append(rel)
                text += f"\nimage in the next message: {rel.rsplit('/', 1)[1]}"
        record(text)
        return {"role": "tool", "tool_call_id": call.get("id"), "content": text}
