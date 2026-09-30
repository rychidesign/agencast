"""Run record (run-record.md): run directory, events.jsonl, step files,
summary.md, plan.md, callback.json. Every write masks secret
values; base64 and reasoning_details never reach the record.
"""
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .expressions import FileRef, to_json
from .loader import nested_lists
from .validate import DEFAULT_TIMEOUT, Project, effective_tools

MIN_SECRET_LEN = 8  # shorter values are not masked (run-record.md)
SUM_DIGITS = 10  # cost totals are rounded only to remove float noise (0.30000000000000004 → 0.3)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _dump(obj, indent=None) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"), default=lambda o: o.path if isinstance(o, FileRef) else str(o))


def scrub(obj, file_note: str | None = None):
    """Copy without base64 (data URLs) or reasoning_details (run-record.md)."""
    if isinstance(obj, dict):
        return {k: (f"<omitted: reasoning_details, {len(_dump(v).encode())} B>"
                    if k == "reasoning_details" and v is not None else scrub(v, file_note)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v, file_note) for v in obj]
    if isinstance(obj, str) and obj.startswith("data:") and ";base64," in obj[:100]:
        return file_note or f"<omitted: base64, {len(obj)} B>"
    return obj


def redact(obj, notes: dict):
    """Data URLs of known files as `<file: …>` (`notes`), the rest as `scrub` (run-record.md)."""
    def walk(o):
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v) for v in o]
        return notes.get(o, o) if isinstance(o, str) else o
    return scrub(walk(obj))


class Record:
    def __init__(self, directory: Path, secrets: dict[str, str], exist_ok: bool = False):
        self.dir = directory
        self.secrets = {n: v for n, v in secrets.items() if v and len(v) >= MIN_SECRET_LEN}
        self.masked: set[str] = set()
        self.events: list[dict] = list(_events(directory)) if exist_ok else []
        directory.mkdir(parents=True, exist_ok=exist_ok)  # exist_ok: interrupted run after server restart

    def mask(self, text: str) -> str:
        for name, value in self.secrets.items():
            if value in text:
                text = text.replace(value, f"<secret: {name}>")
                self.masked.add(name)
        return text

    def write(self, rel: str, content) -> str:
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.mask(content if isinstance(content, str) else _dump(content, 2)) + "\n", encoding="utf-8")
        return rel

    def write_bytes(self, rel: str, data: bytes) -> str:
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return rel

    def event(self, type_: str, **fields) -> dict:
        ev = {"ts": now_iso(), "type": type_, **fields}
        line = self.mask(_dump(ev))
        with open(self.dir / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
        self.events.append(json.loads(line))
        return ev


# --- human-readable format ------------------------------------------------------------

def format_number(x: float, digits: int) -> str:
    return f"{x:.{digits}f}"


def format_usd(x: float) -> str:
    """Human-readable cost: decimal (never exponent), at least 4 places, more only for stored
    digits (max 10), decimal point; actual zero → `0`."""
    if not x:
        return "0"
    whole, frac = f"{x:.{SUM_DIGITS}f}".split(".")
    return f"{whole}.{frac.rstrip('0').ljust(4, '0')}"


def count(n: int, one: str, other: str) -> str:
    """Count with English singular and plural forms."""
    return f"{n} {one if n == 1 else other}"


def format_value(v) -> str:
    if isinstance(v, str):
        return v if v.startswith(("https://", "http://", "file://")) else f"“{v}”"
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return ", ".join(v)
    if isinstance(v, float):
        return format_number(v, 2) if abs(v) < 1000 else str(v)
    return to_json(v)


def _limits(p: Project, st: dict, kind: str) -> str:
    parts = []
    if kind in ("ask", "task"):
        lim = p.agents[st[kind]["agent"]].data["limits"]
        budget = min(st.get("budget_usd", lim["budget_usd"]), lim["budget_usd"])
        parts += [f"{budget} USD", st.get("timeout") or lim.get("timeout") or DEFAULT_TIMEOUT[kind]]
    elif kind in DEFAULT_TIMEOUT:
        parts += [f"{st['budget_usd']} USD"] if "budget_usd" in st else []
        parts.append(st.get("timeout") or DEFAULT_TIMEOUT[kind])
    else:
        parts += [f"{st['budget_usd']} USD"] if "budget_usd" in st else []
        parts += [st["timeout"]] if "timeout" in st else []
    if "retry" in st:
        parts.append(f"retry {st['retry']}")
    if st.get("on_error") == "continue":
        parts.append("on_error: continue")
    return ", ".join(parts)


def plan_md(p: Project, offers: dict | None = None) -> str:
    """Plan from validate (run-record.md plan.md, `--dry-run`). `offers` = server → offered tools
    (or a message explaining why it did not start) — scenario.md §7."""
    sc, cfg, lim = p.scenario, p.config, p.config["limits"]
    models = cfg["models"]
    lines = [f"# Plan: {sc['name']}", "", sc["description"], "",
             f"Run limits: budget {lim['run_budget_usd']} USD"
             + (f" (of which images {lim['run_image_budget_usd']} USD)" if "run_image_budget_usd" in lim else "")
             + f", time {lim['run_timeout']}. Jev: {cfg['openrouter']['jev_model']}.", "",
             "| # | Step | Type | Condition | Action | Limits |", "|---|---|---|---|---|---|"]

    def rows(steps, indent):
        for st in steps:
            info = p.steps[st["id"]]
            k = info.kind
            what = ""
            if k == "ask":
                a = st["ask"]
                alias = p.agents[a["agent"]].data["model"]
                level = models[alias].get("structured_output", "native_schema")
                what = f"agent {a['agent']} → {alias} ({models[alias]['id']})" + (
                    f"; schema: {', '.join(a['schema'])} (cascade from {level})" if "schema" in a else "; text")
            elif k == "jev":
                what = "questions: " + ", ".join(f"{q} ({s['type']})" for q, s in st["jev"]["questions"].items())
            elif k == "image":
                m = st["image"]["model"]
                what = f"{m} ({models[m]['id']})" + (f", ratio {st['image']['aspect_ratio']}"
                                                     if "aspect_ratio" in st["image"] else "")
            elif k == "set":
                what = ", ".join(st["set"])
            elif k == "fail":
                what = "end the run with an error"
            elif k == "output":
                what = ", ".join(st["output"])
            elif k == "parallel":
                what = "branches: " + ", ".join(st["parallel"])
            elif k == "switch":
                what = f"based on {st['switch']['value']}: " + ", ".join(list(st["switch"]["cases"]) + ["default"])
            elif k == "call":
                what = f"scenario {st['call']['scenario']}"
            elif k == "task":
                t = st["task"]
                agent = p.agents[t["agent"]]
                alias = agent.data["model"]
                tools = effective_tools(agent.data, t)
                what = (f"agent {t['agent']} → {alias} ({models[alias]['id']}); tools: "
                        + ("; ".join(f"{s}: {', '.join(ts)}" for s, ts in tools.items()) or "none")
                        + (f"; skills: {', '.join(n for n, _, _ in agent.skills)}" if agent.skills else "")
                        + f"; max_turns {t.get('max_turns', agent.data['limits'].get('max_turns'))}"
                        + (f"; schema: {', '.join(t['schema'])} (cascade from tool_wrapper)" if "schema" in t else "; text")
                        + ("; dedupe_key" if "dedupe_key" in st else ""))
            cond = f"`{st['when']}`" if "when" in st else ""
            lines.append(f"| {info.nn} | {'↳ ' * indent}{info.id} | {k} | {cond} | {what} | {_limits(p, st, k)} |")
            for _, lst in nested_lists(st):
                rows(lst, indent + 1)

    rows(sc["steps"], 0)
    if offers:
        lines += ["", "## MCP servers", ""]
        for s, got in sorted(offers.items()):
            lines.append(f"- **{s}** ({p.mcp[s]['description']}): "
                         + (f"offers {', '.join(got)}" if isinstance(got, list) else f"failed to start — {got}"))
    return "\n".join(lines)


STATUS_LABELS = {"succeeded": "✓", "failed": "failed", "cancelled": "cancelled", "skipped": "skipped",
             "continued": "failed, continuing"}


def summary_md(p: Project, run) -> str:
    """summary.md per run-record.md (English, always the same structure)."""
    sc = p.scenario
    ok = run.status == "succeeded"
    started = datetime.fromisoformat(run.started_at.replace("Z", "+00:00"))
    head = (f"Run `{run.run_id}` · {started:%Y-%m-%d %H:%M} UTC · "
            f"{format_number(run.duration, 1)} s · {format_usd(run.cost)} USD")
    if run.image_cost:
        head += f" (of which images {format_usd(run.image_cost)} USD)"
    lines = [f"# {sc['name']} — {'success' if ok else 'failed'}", "", sc["description"], head, ""]
    if run.fake:
        lines += ["**Fake run** (`--fake`) — model responses are fabricated, dedupe in `_dedupe-fake/`.", ""]
    if run.callback_failed:
        lines += ["**Callback not delivered** — see callback_sent events in events.jsonl.", ""]
    if not ok and run.error:
        e = run.error
        lines += ["## Error", f"- class: `{e['class']}`", f"- step: `{e['step']}`" if e["step"] else "- step: —",
                  "- message:", "", "```", e["message"], "```", ""]
        if e["step"]:
            lines += [f"Run ended at step {e['step']}.", ""]
    lines += ["## Inputs"] + [f"- {k}: {format_value(v) if not isinstance(v, str) else v}" for k, v in run.inputs.items()]
    if not run.inputs:
        lines.append("none")
    lines += ["", "## Steps", "| # | Step | Type | Status | Time | Cost | Note |", "|---|---|---|---|---|---|---|"]
    for r in sorted(run.rows.values(), key=lambda r: r["nn"]):
        t = f"{format_number(r['duration'], 1)} s" if r.get("duration") is not None else ""
        c = format_usd(r["cost"]) if r.get("duration") is not None else ""
        note = str(r.get("note") or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r['nn']} | {r['id']} | {r['kind']} | {STATUS_LABELS[r['status']]} | {t} | {c} | {note} |")
    lines.append(f"| | Total | | | {format_number(run.duration, 1)} s | {format_usd(run.cost)} | {total_note(run)} |")
    lines += ["", "## Warnings"] + ([f"- {w}" for w in run.warnings] or ["none"])
    lines += ["", "## Output"]
    if ok and run.outputs is not None:
        lines += [f"- {k}: {format_value(v)}" for k, v in run.outputs.items()]
    else:
        lines.append("none")
    return "\n".join(lines)


def total_note(run) -> str:
    """Note for the Total row. Total time and cost = time and cost of the whole run (duration_s and cost_usd
    from run_finished), not column sums: parallel steps run concurrently and nested steps are already
    included in the parent parallel/switch/call time and cost."""
    return f"of which images {format_usd(run.image_cost)}" if run.image_cost else ""


RUN_DIR = re.compile(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})-([a-z0-9-]+)-[0-9a-f]{4}")  # run_id (engine.RUN_ID)
INTERRUPTED_BY_RESTART = "run interrupted by server restart"


def _events(run_dir: Path):
    ev = run_dir / "events.jsonl"
    for line in ev.read_text(encoding="utf-8").splitlines() if ev.is_file() else []:
        try:
            yield json.loads(line)
        except ValueError:
            continue  # line currently being written by the run


def run_status(run_dir: Path) -> dict:
    """Run status from events.jsonl and the run lock (for `agencast runs list`). `state` (0.7.0) is the machine status:
    `running` only with `run.lock` held by a live process; without `run_finished` or a lock, `interrupted`."""
    from .task import run_locked  # task imports record
    live = run_locked(run_dir)
    info: dict[str, Any] = {"run_id": run_dir.name, "status": "running" if live else "interrupted", "state": "running" if live else "interrupted",
            "cost_usd": None, "duration_s": None, "callback": "", "scenario": None, "started_at": None,
            "finished_at": None, "current_step": None, "steps_total": None, "fake": None, "current_nn": None,
            "steps_done": None}
    if not (run_dir / "events.jsonl").is_file():
        m = RUN_DIR.fullmatch(run_dir.name)
        # dry run = plan.md without run.lock: a real run takes the lock before plan.md (hence this check order)
        if not live and (run_dir / "plan.md").is_file() and not (run_dir / "run.lock").exists():
            info.update(status="dry-run", state="dry_run")
            if m:  # dry run has no events.jsonl: scenario and time come from run_id
                info.update(scenario=m[7], started_at=f"{m[1]}-{m[2]}-{m[3]}T{m[4]}:{m[5]}:{m[6]}.000Z")
        elif not live:
            info["status"] = "?"
        return info
    running: dict[str, None] = {}  # started steps without step_finished, in start order
    nns: dict[str, int] = {}
    done = 0
    for e in _events(run_dir):
        if "nn" in e:
            nns[e["step"]] = e["nn"]
        if e["type"] == "run_started":
            info.update(scenario=e["scenario"], started_at=e["ts"], steps_total=e.get("steps_total"), fake=e.get("fake"))
        elif e["type"] == "step_started":
            running[e["step"]] = None
        elif e["type"] in ("step_finished", "step_skipped"):
            running.pop(e["step"], None)
            done += "/" not in e["step"]  # like steps_total: excluding steps of called scenarios
        elif e["type"] == "run_finished":
            info.update(status=e["status"], state=e["status"], cost_usd=e["usage"]["cost_usd"], duration_s=e["duration_s"],
                        finished_at=e["ts"])
            if e.get("error"):
                step = e["error"].get("step")
                info["status"] += f" ({e['error']['class']} in {step})" if step else f" ({e['error']['class']})"
                if e["error"].get("message") == INTERRUPTED_BY_RESTART:
                    info["state"] = "interrupted"
        elif e["type"] == "callback_failed":
            info["callback"] = "callback not delivered"
    if info["finished_at"] is None and running:
        info["current_step"] = list(running)[-1]
    if info["finished_at"] is None and live:
        cur = info["current_step"]
        info.update(current_nn=nns.get(cur.split("/")[0]) if cur else None, steps_done=done)
    return info


def _step_rows(run_dir: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """(steps by path in order of first event, all events)."""
    steps: dict[str, dict[str, Any]] = {}
    events = list(_events(run_dir))
    for e in events:
        if not e.get("step") or e["type"] not in ("step_started", "step_skipped", "step_finished", "model_call",
                                                  "jev_call", "tool_call", "error"):
            continue
        st = steps.setdefault(e["step"], {"step": e["step"], "kind": e.get("kind"), "nn": None, "dir": None,
                                          "error": None, "continued": False, "default_used": False, "calls": []})
        t = e["type"]
        if "nn" in e:
            st["nn"] = e["nn"]
        if t == "step_started":
            st.update(status="running", branch=e.get("branch"), started_at=e["ts"], dir=e.get("dir") or st["dir"])
        elif t == "step_skipped":
            st.update(status="skipped", reason_code=e.get("reason_code"), reason=e.get("reason"),
                      default_used=bool(e.get("default_used")))
        elif t == "step_finished":
            st.update(status=e["status"], finished_at=e["ts"], duration_s=e.get("duration_s"),
                      cost_usd=e.get("cost_usd"), continued=bool(e.get("continued")),
                      default_used=bool(e.get("default_used")))
            if e.get("output_file"):  # runs before 0.7.0 have no dir in step_started
                st["dir"] = st["dir"] or e["output_file"].rsplit("/", 1)[0]
        elif t in ("model_call", "jev_call"):
            u = e.get("usage") or {}
            st["calls"].append({"attempt": e.get("attempt"), "alias": e.get("alias"), "model": e.get("model"),
                                "input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
                                "cost_usd": u.get("cost_usd"), "finish_reason": e.get("finish_reason"),
                                "structured_output": e.get("structured_output"), "duration_s": e.get("duration_s")})
            if e.get("request_file"):
                st["dir"] = st["dir"] or e["request_file"].rsplit("/", 2)[0]
            if t == "jev_call":
                st["answers"] = e.get("answers")
            elif e.get("turn"):
                st["turns"] = max(st.get("turns", 0), e["turn"])
        elif t == "tool_call":
            st["tool_calls"] = st.get("tool_calls", 0) + 1
        elif not e.get("will_retry"):  # error: the last one, not retried
            st["error"] = {"class": e.get("class"), "message": e.get("message")}
    for st in steps.values():
        if st["nn"] is None and st["dir"]:
            st["nn"] = int(re.findall(r"steps/(\d+)-", st["dir"])[-1])
        if st["kind"] == "task":
            st.setdefault("turns", 0)
            st.setdefault("tool_calls", 0)
    from .task import run_locked
    recovered = any(e["type"] == "run_finished" and (e.get("error") or {}).get("message") == INTERRUPTED_BY_RESTART
                    for e in events)
    if recovered or not run_locked(run_dir):
        for st in steps.values():
            if st.get("status") == "running":
                st["status"] = "interrupted"
    return steps, events


def run_detail(run_dir: Path) -> dict[str, Any]:
    """`run_status` + steps (status, time, cost, directory, error, calls) from events.jsonl + run files
    (GET /projects/<p>/runs/<id>)."""
    steps, _ = _step_rows(run_dir)
    files = sorted(p.relative_to(run_dir).as_posix() for p in run_dir.rglob("*") if p.is_file())
    return {**run_status(run_dir), "steps": list(steps.values()), "files": files}


def step_detail(run_dir: Path, path: str) -> dict[str, Any] | None:
    """One step (GET …/runs/<id>/steps/<path>): `steps` entry + its events, output and files in its
    directory (excluding nested `call` step directories); None = step is not in the record."""
    steps, events = _step_rows(run_dir)
    if (st := steps.get(path)) is None:
        return None
    output, files, d = None, [], st["dir"]
    if d:
        try:
            output = json.loads((run_dir / d / "output.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass  # step without output (or currently writing it)
        files = sorted(rel for p in (run_dir / d).rglob("*") if p.is_file()
                       and not (rel := p.relative_to(run_dir).as_posix()).startswith(f"{d}/steps/"))
    return {**st, "events": [e for e in events if e.get("step") == path], "output": output, "files": files}


# --- report.html (3b) ---------------------------------------------------------------

REPORT_CUT = 4000  # prompt/response characters in report.html; full text is in the run record
DATA_URL = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]+")
CSS = """body{font:15px/1.5 system-ui,sans-serif;max-width:1100px;margin:2em auto;padding:0 1em;color:#222}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:4px 8px;text-align:left;vertical-align:top}
th{background:#f4f4f4}.ok{color:#176b2c}.err{color:#b00020}.muted{color:#777}
pre{white-space:pre-wrap;word-break:break-word;background:#f6f6f6;padding:8px;border-radius:4px}
details{margin:.3em 0}summary{cursor:pointer}h3{margin-top:1.5em}"""


def _cut(text: str) -> str:
    if len(text) <= REPORT_CUT:
        return text
    return text[:REPORT_CUT] + f"\n… (truncated, {len(text)} characters total — full text in the run record)"


def _answer(path: Path) -> str:
    """Response from calls/NN.response.json: text or _submit_output arguments, otherwise the full body."""
    try:
        b = json.loads(path.read_text(encoding="utf-8"))
        m = b["choices"][0]["message"]
        calls = m.get("tool_calls") or []
        return m.get("content") or (calls[0]["function"]["arguments"] if calls else None) or m.get("refusal") \
            or _dump(b, 2)
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return path.read_text(encoding="utf-8") if path.is_file() else "(file missing)"


def _pre(title: str, text: str) -> str:
    return f"<details><summary>{html.escape(title)}</summary><pre>{html.escape(_cut(text))}</pre></details>"


def report_html(run) -> str:
    """report.html (run-record.md): same as summary.md plus expandable prompts and responses.
    From events.jsonl and steps/; one file, inline CSS, no external resources, no base64."""
    e, d, sc = html.escape, run.rec.dir, run.p.scenario
    ok = run.status == "succeeded"
    steps: dict[str, dict] = {}
    for x in run.rec.events:
        if not x.get("step"):
            continue
        s = steps.setdefault(x["step"], {"kind": x.get("kind"), "status": "running", "calls": [], "errors": [],
                                         "folder": None, "note": "", "duration": None, "cost": None})
        t = x["type"]
        if t == "step_finished":
            s.update(status="continued" if x["continued"] else x["status"], duration=x["duration_s"],
                     cost=x["cost_usd"])
            s["folder"] = s["folder"] or (x["output_file"].rsplit("/", 1)[0] if x.get("output_file") else None)
        elif t == "step_skipped":
            s.update(kind=x["kind"], status="skipped", note=x["reason"])
        elif t in ("model_call", "jev_call"):
            s["calls"].append(x)
            s["folder"] = x["request_file"].rsplit("/", 2)[0]
            s["note"] = (", ".join(f"{q} = {v}" for q, v in (x["answers"] or {}).items()) if t == "jev_call"
                         else f"{x['alias']} → {x['model']}")
        elif t == "error":
            s["errors"].append(x)

    def nn(path, s):
        if s["folder"]:
            return ".".join(str(int(n)) for n in re.findall(r"steps/(\d+)-", s["folder"]))
        info = run.p.steps.get(path)
        return str(info.nn) if info and "/" not in path else ""

    started = datetime.fromisoformat(run.started_at.replace("Z", "+00:00"))
    cost = f"{format_usd(run.cost)} USD" + (f" (of which images {format_usd(run.image_cost)} USD)" if run.image_cost else "")
    out = [f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>{e(sc['name'])} — "
           f"{'success' if ok else 'failed'}</title><style>{CSS}</style></head><body>",
           f"<h1>{e(sc['name'])} — <span class=\"{'ok' if ok else 'err'}\">{'success' if ok else 'failed'}</span></h1>",
           f"<p>{e(sc.get('description') or '')}</p>",
           f"<p class=\"muted\">Run <code>{e(run.run_id)}</code> · {started:%Y-%m-%d %H:%M} UTC · "
           f"{format_number(run.duration, 1)} s · {e(cost)}"
           + (f" · request_key <code>{e(run.request_key)}</code>" if run.request_key else "")
           + (" · <strong>fake run</strong> (<code>--fake</code>)" if run.fake else "") + "</p>"]
    if run.error:
        er = run.error
        out += ["<h2 class=\"err\">Error</h2>",
                f"<p>class <code>{e(er['class'])}</code> · step <code>{e(er['step'] or '—')}</code></p>",
                f"<pre>{e(_cut(er['message']))}</pre>"]
    out += ["<h2>Warnings</h2>", "<ul>" + "".join(f"<li>{e(w)}</li>" for w in run.warnings) + "</ul>"
            if run.warnings else "<p>none</p>"]
    out += ["<h2>Inputs</h2>", f"<pre>{e(_cut(_dump(run.inputs, 2)))}</pre>"]
    out += ["<h2>Steps</h2>", "<table><tr><th>#</th><th>Step</th><th>Type</th><th>Status</th><th>Time</th><th>Cost</th>"
            "<th>Note</th></tr>"]
    for path, s in steps.items():
        note = s["note"] or (s["errors"][-1]["message"].splitlines()[0] if s["errors"] else "")
        cls = "ok" if s["status"] == "succeeded" else "err" if s["status"] in ("failed", "continued") else ""
        out.append(f"<tr><td>{nn(path, s)}</td><td>{e(path)}</td><td>{e(s['kind'] or '')}</td>"
                   f"<td class=\"{cls}\">{e(STATUS_LABELS.get(s['status'], s['status']))}</td>"
                   f"<td>{'' if s['duration'] is None else format_number(s['duration'], 1) + ' s'}</td>"
                   f"<td>{'' if s['cost'] is None else format_usd(s['cost'])}</td><td>{e(note)}</td></tr>")
    out.append(f"<tr><td></td><td>Total</td><td></td><td></td><td>{format_number(run.duration, 1)} s</td><td>{format_usd(run.cost)}</td>"
               f"<td>{e(total_note(run))}</td></tr></table>")
    out.append("<h2>Output</h2>")
    if ok and run.outputs is not None:
        out.append("<ul>" + "".join(
            f"<li>{e(k)}: " + (f"<a href=\"{e(v)}\">{e(v)}</a>" if isinstance(v, str) and v.startswith(
                ("https://", "http://", "file://")) else e(format_value(v))) + "</li>" for k, v in run.outputs.items())
            + "</ul>")
    else:
        out.append("<p>none</p>")
    out.append("<h2>Step details</h2>")
    for path, s in steps.items():
        if not (s["folder"] or s["errors"]):
            continue
        out.append(f"<h3>{nn(path, s)} · {e(path)} ({e(s['kind'] or '')})</h3>")
        f = d / s["folder"] if s["folder"] else None
        if f and (f / "prompt.md").is_file():
            out.append(_pre("Prompt", (f / "prompt.md").read_text(encoding="utf-8")))
        for c in s["calls"]:
            usage = c.get("usage") or {}
            head = (f"Call {c['attempt']}" + (f" · {c['alias']} → {c['model']}" if "alias" in c else f" · {c['model']}")
                    + (f" · {c['finish_reason']}" if c.get("finish_reason") else "")
                    + f" · {usage.get('input_tokens')}+{usage.get('output_tokens')} tokens"
                    + ("" if usage.get("cost_usd") is None else f" · {format_usd(usage['cost_usd'])} USD")
                    + f" · {format_number(c['duration_s'], 1)} s")
            out.append(_pre(head, _answer(d / c["response_file"])))
        if f and (f / "output.json").is_file():
            out.append(_pre("Step output", (f / "output.json").read_text(encoding="utf-8")))
        for er in s["errors"]:
            out.append(f"<p class=\"err\"><code>{e(er['class'])}</code>"
                       + (f" (attempt {er['attempt']}{', retrying' if er.get('will_retry') else ''})"
                          if er.get("attempt") else "") + f": {e(_cut(er['message']))}</p>")
    out.append("</body></html>")
    return DATA_URL.sub("<omitted: data URL>", "\n".join(out))
