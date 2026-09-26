"""Záznam běhu (run-record.md): složka běhu, events.jsonl, soubory kroků,
summary.md, plan.md, callback.json. Každý zápis prochází maskováním tajných
hodnot; base64 a reasoning_details se do záznamu nikdy nedostanou.
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

MIN_SECRET_LEN = 8  # kratší hodnoty se nemaskují (run-record.md)
SUM_DIGITS = 10  # součty cen se zaokrouhlují jen kvůli šumu floatů (0.30000000000000004 → 0.3)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _dump(obj, indent=None) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"), default=lambda o: o.path if isinstance(o, FileRef) else str(o))


def scrub(obj, file_note: str | None = None):
    """Kopie bez base64 (data URL) a bez reasoning_details (run-record.md)."""
    if isinstance(obj, dict):
        return {k: (f"<vynecháno: reasoning_details, {len(_dump(v).encode())} B>"
                    if k == "reasoning_details" and v is not None else scrub(v, file_note)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v, file_note) for v in obj]
    if isinstance(obj, str) and obj.startswith("data:") and ";base64," in obj[:100]:
        return file_note or f"<vynecháno: base64, {len(obj)} B>"
    return obj


class Record:
    def __init__(self, directory: Path, secrets: dict[str, str], exist_ok: bool = False):
        self.dir = directory
        self.secrets = {n: v for n, v in secrets.items() if v and len(v) >= MIN_SECRET_LEN}
        self.masked: set[str] = set()
        self.events: list[dict] = []
        directory.mkdir(parents=True, exist_ok=exist_ok)  # exist_ok: přerušený běh po restartu serveru

    def mask(self, text: str) -> str:
        for name, value in self.secrets.items():
            if value in text:
                text = text.replace(value, f"<tajné: {name}>")
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


# --- formát pro člověka ------------------------------------------------------------

def cz(x: float, digits: int) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def cz_usd(x: float) -> str:
    """Cena pro člověka: desetinně (nikdy exponent), aspoň 4 místa, víc jen kvůli uloženým
    číslicím (max 10), desetinná čárka; skutečná nula → `0`."""
    if not x:
        return "0"
    whole, frac = f"{x:.{SUM_DIGITS}f}".split(".")
    return f"{whole},{frac.rstrip('0').ljust(4, '0')}"


def count(n: int, one: str, few: str, many: str) -> str:
    """Počet s tvarem: 1 krok, 2–4 kroky, 0 a 5+ kroků."""
    return f"{n} {one if n == 1 else few if 2 <= n <= 4 else many}"


def cz_value(v) -> str:
    if isinstance(v, str):
        return v if v.startswith(("https://", "http://", "file://")) else f"„{v}\""
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return ", ".join(v)
    if isinstance(v, float):
        return cz(v, 2) if abs(v) < 1000 else str(v)
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
    """Plán z validate (run-record.md plan.md, `--dry-run`). `offers` = server → nabízené nástroje
    (nebo hláška, proč se nespustil) — scenario.md §7."""
    sc, cfg, lim = p.scenario, p.config, p.config["limits"]
    models = cfg["models"]
    lines = [f"# Plán: {sc['name']}", "", sc["description"], "",
             f"Limity běhu: rozpočet {lim['run_budget_usd']} USD"
             + (f" (z toho obrázky {lim['run_image_budget_usd']} USD)" if "run_image_budget_usd" in lim else "")
             + f", čas {lim['run_timeout']}. Jev: {cfg['openrouter']['jev_model']}.", "",
             "| # | Krok | Typ | Podmínka | Co udělá | Limity |", "|---|---|---|---|---|---|"]

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
                    f"; schema: {', '.join(a['schema'])} (kaskáda od {level})" if "schema" in a else "; text")
            elif k == "jev":
                what = "otázky: " + ", ".join(f"{q} ({s['type']})" for q, s in st["jev"]["questions"].items())
            elif k == "image":
                m = st["image"]["model"]
                what = f"{m} ({models[m]['id']})" + (f", poměr {st['image']['aspect_ratio']}"
                                                     if "aspect_ratio" in st["image"] else "")
            elif k == "set":
                what = ", ".join(st["set"])
            elif k == "fail":
                what = "ukončí běh s chybou"
            elif k == "output":
                what = ", ".join(st["output"])
            elif k == "parallel":
                what = "větve: " + ", ".join(st["parallel"])
            elif k == "switch":
                what = f"podle {st['switch']['value']}: " + ", ".join(list(st["switch"]["cases"]) + ["default"])
            elif k == "call":
                what = f"scénář {st['call']['scenario']}"
            elif k == "task":
                t = st["task"]
                agent = p.agents[t["agent"]]
                alias = agent.data["model"]
                tools = effective_tools(agent.data, t)
                what = (f"agent {t['agent']} → {alias} ({models[alias]['id']}); nástroje: "
                        + ("; ".join(f"{s}: {', '.join(ts)}" for s, ts in tools.items()) or "žádné")
                        + (f"; skilly: {', '.join(n for n, _, _ in agent.skills)}" if agent.skills else "")
                        + f"; max_turns {t.get('max_turns', agent.data['limits'].get('max_turns'))}"
                        + (f"; schema: {', '.join(t['schema'])} (kaskáda od tool_wrapper)" if "schema" in t else "; text")
                        + ("; dedupe_key" if "dedupe_key" in st else ""))
            cond = f"`{st['when']}`" if "when" in st else ""
            lines.append(f"| {info.nn} | {'↳ ' * indent}{info.id} | {k} | {cond} | {what} | {_limits(p, st, k)} |")
            for _, lst in nested_lists(st):
                rows(lst, indent + 1)

    rows(sc["steps"], 0)
    if offers:
        lines += ["", "## MCP servery", ""]
        for s, got in sorted(offers.items()):
            lines.append(f"- **{s}** ({p.mcp[s]['description']}): "
                         + (f"nabízí {', '.join(got)}" if isinstance(got, list) else f"nepodařilo se spustit — {got}"))
    return "\n".join(lines)


STATUS_CS = {"succeeded": "✓", "failed": "chyba", "cancelled": "zrušeno", "skipped": "přeskočeno",
             "continued": "chyba, pokračuje"}


def summary_md(p: Project, run) -> str:
    """summary.md podle run-record.md (česky, vždy stejná stavba)."""
    sc = p.scenario
    ok = run.status == "succeeded"
    started = datetime.fromisoformat(run.started_at.replace("Z", "+00:00"))
    head = (f"Běh `{run.run_id}` · {started.day}. {started.month}. {started.year} {started:%H:%M:%S} UTC · "
            f"{cz(run.duration, 1)} s · {cz_usd(run.cost)} USD")
    if run.image_cost:
        head += f" (z toho obrázky {cz_usd(run.image_cost)} USD)"
    lines = [f"# {sc['name']} — {'úspěch' if ok else 'chyba'}", "", sc["description"], head, ""]
    if run.fake:
        lines += ["**Falešný běh** (`--fake`) — odpovědi modelů jsou vymyšlené, dedupe v `_dedupe-fake/`.", ""]
    if run.callback_failed:
        lines += ["**Callback nedoručen** — viz události callback_sent v events.jsonl.", ""]
    if not ok and run.error:
        e = run.error
        lines += ["## Chyba", f"- třída: `{e['class']}`", f"- krok: `{e['step']}`" if e["step"] else "- krok: —",
                  "- zpráva:", "", "```", e["message"], "```", ""]
        if e["step"]:
            lines += [f"Běh skončil v kroku {e['step']}.", ""]
    lines += ["## Vstupy"] + [f"- {k}: {cz_value(v) if not isinstance(v, str) else v}" for k, v in run.inputs.items()]
    if not run.inputs:
        lines.append("žádné")
    lines += ["", "## Kroky", "| # | Krok | Typ | Stav | Čas | Cena | Poznámka |", "|---|---|---|---|---|---|---|"]
    for r in sorted(run.rows.values(), key=lambda r: r["nn"]):
        t = f"{cz(r['duration'], 1)} s" if r.get("duration") is not None else ""
        c = cz_usd(r["cost"]) if r.get("duration") is not None else ""
        note = str(r.get("note") or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r['nn']} | {r['id']} | {r['kind']} | {STATUS_CS[r['status']]} | {t} | {c} | {note} |")
    lines.append(f"| | Celkem | | | {cz(run.duration, 1)} s | {cz_usd(run.cost)} | {total_note(run)} |")
    lines += ["", "## Varování"] + ([f"- {w}" for w in run.warnings] or ["žádná"])
    lines += ["", "## Výstup"]
    if ok and run.outputs is not None:
        lines += [f"- {k}: {cz_value(v)}" for k, v in run.outputs.items()]
    else:
        lines.append("žádný")
    return "\n".join(lines)


def total_note(run) -> str:
    """Poznámka řádku Celkem. Čas a cena Celkem = čas a cena celého běhu (duration_s a cost_usd
    z run_finished), ne součet sloupců: kroky v parallel běží současně a vnořené kroky jsou už
    v čase i ceně nadřazeného parallel/switch/call."""
    return f"z toho obrázky {cz_usd(run.image_cost)}" if run.image_cost else ""


RUN_DIR = re.compile(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})-([a-z0-9-]+)-[0-9a-f]{4}")  # run_id (engine.RUN_ID)


def _events(run_dir: Path):
    ev = run_dir / "events.jsonl"
    for line in ev.read_text(encoding="utf-8").splitlines() if ev.is_file() else []:
        try:
            yield json.loads(line)
        except ValueError:
            continue  # řádek, který běh právě zapisuje


def run_status(run_dir: Path) -> dict:
    """Stav běhu z events.jsonl a zámku běhu (pro `agencast runs list`). `state` (0.7.0) je strojový stav:
    `running` jen se zámkem `run.lock` drženým živým procesem, bez `run_finished` a bez zámku `interrupted`."""
    from .task import run_locked  # task importuje record
    live = run_locked(run_dir)
    info: dict[str, Any] = {"run_id": run_dir.name, "status": "běží" if live else "přerušen", "state": "running" if live else "interrupted",
            "cost_usd": None, "duration_s": None, "callback": "", "scenario": None, "started_at": None,
            "finished_at": None, "current_step": None, "steps_total": None, "fake": None, "current_nn": None,
            "steps_done": None}
    if not (run_dir / "events.jsonl").is_file():
        m = RUN_DIR.fullmatch(run_dir.name)
        # dry-run = plan.md bez run.lock: ostrý běh bere zámek před plan.md (pořadí kontrol je proto tohle)
        if not live and (run_dir / "plan.md").is_file() and not (run_dir / "run.lock").exists():
            info.update(status="dry-run", state="dry_run")
            if m:  # dry-run nemá events.jsonl: scénář a čas z run_id
                info.update(scenario=m[7], started_at=f"{m[1]}-{m[2]}-{m[3]}T{m[4]}:{m[5]}:{m[6]}.000Z")
        elif not live:
            info["status"] = "?"
        return info
    running: dict[str, None] = {}  # rozběhnuté kroky bez step_finished, v pořadí startu
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
            done += "/" not in e["step"]  # jako steps_total: bez kroků volaných scénářů
        elif e["type"] == "run_finished":
            info.update(status=e["status"], state=e["status"], cost_usd=e["usage"]["cost_usd"], duration_s=e["duration_s"],
                        finished_at=e["ts"])
            if e.get("error"):
                info["status"] += f" ({e['error']['class']} v {e['error']['step']})"
        elif e["type"] == "callback_failed":
            info["callback"] = "callback nedoručen"
    if info["finished_at"] is None and running:
        info["current_step"] = list(running)[-1]
    if info["finished_at"] is None and live:
        cur = info["current_step"]
        info.update(current_nn=nns.get(cur.split("/")[0]) if cur else None, steps_done=done)
    return info


def _step_rows(run_dir: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """(kroky podle cesty v pořadí první události, všechny události)."""
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
            if e.get("output_file"):  # běhy před 0.7.0 nemají dir ve step_started
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
        elif not e.get("will_retry"):  # error: poslední, po které se už neopakovalo
            st["error"] = {"class": e.get("class"), "message": e.get("message")}
    for st in steps.values():
        if st["nn"] is None and st["dir"]:
            st["nn"] = int(re.findall(r"steps/(\d+)-", st["dir"])[-1])
        if st["kind"] == "task":
            st.setdefault("turns", 0)
            st.setdefault("tool_calls", 0)
    return steps, events


def run_detail(run_dir: Path) -> dict[str, Any]:
    """`run_status` + kroky (stav, čas, cena, složka, chyba, volání) z events.jsonl + soubory běhu
    (GET /projects/<p>/runs/<id>)."""
    steps, _ = _step_rows(run_dir)
    files = sorted(p.relative_to(run_dir).as_posix() for p in run_dir.rglob("*") if p.is_file())
    return {**run_status(run_dir), "steps": list(steps.values()), "files": files}


def step_detail(run_dir: Path, path: str) -> dict[str, Any] | None:
    """Jeden krok (GET …/runs/<id>/steps/<cesta>): položka `steps` + jeho události, výstup a soubory jeho
    složky (bez složek vnořených kroků `call`); None = krok v záznamu není."""
    steps, events = _step_rows(run_dir)
    if (st := steps.get(path)) is None:
        return None
    output, files, d = None, [], st["dir"]
    if d:
        try:
            output = json.loads((run_dir / d / "output.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass  # krok bez výstupu (nebo ho právě zapisuje)
        files = sorted(rel for p in (run_dir / d).rglob("*") if p.is_file()
                       and not (rel := p.relative_to(run_dir).as_posix()).startswith(f"{d}/steps/"))
    return {**st, "events": [e for e in events if e.get("step") == path], "output": output, "files": files}


# --- report.html (3b) ---------------------------------------------------------------

REPORT_CUT = 4000  # znaků promptu/odpovědi v report.html; celé jsou v záznamu běhu
DATA_URL = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]+")
CSS = """body{font:15px/1.5 system-ui,sans-serif;max-width:1100px;margin:2em auto;padding:0 1em;color:#222}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:4px 8px;text-align:left;vertical-align:top}
th{background:#f4f4f4}.ok{color:#176b2c}.err{color:#b00020}.muted{color:#777}
pre{white-space:pre-wrap;word-break:break-word;background:#f6f6f6;padding:8px;border-radius:4px}
details{margin:.3em 0}summary{cursor:pointer}h3{margin-top:1.5em}"""


def _cut(text: str) -> str:
    if len(text) <= REPORT_CUT:
        return text
    return text[:REPORT_CUT] + f"\n… (zkráceno, celkem {len(text)} znaků — celé v záznamu běhu)"


def _answer(path: Path) -> str:
    """Odpověď z calls/NN.response.json: text nebo argumenty _submit_output, jinak celé tělo."""
    try:
        b = json.loads(path.read_text(encoding="utf-8"))
        m = b["choices"][0]["message"]
        calls = m.get("tool_calls") or []
        return m.get("content") or (calls[0]["function"]["arguments"] if calls else None) or m.get("refusal") \
            or _dump(b, 2)
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return path.read_text(encoding="utf-8") if path.is_file() else "(soubor chybí)"


def _pre(title: str, text: str) -> str:
    return f"<details><summary>{html.escape(title)}</summary><pre>{html.escape(_cut(text))}</pre></details>"


def report_html(run) -> str:
    """report.html (run-record.md): totéž co summary.md plus rozbalitelné prompty a odpovědi.
    Z events.jsonl a steps/; jeden soubor, CSS uvnitř, žádné externí zdroje, bez base64."""
    e, d, sc = html.escape, run.rec.dir, run.p.scenario
    ok = run.status == "succeeded"
    steps: dict[str, dict] = {}
    for x in run.rec.events:
        if not x.get("step"):
            continue
        s = steps.setdefault(x["step"], {"kind": x.get("kind"), "status": "běží", "calls": [], "errors": [],
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
    cost = f"{cz_usd(run.cost)} USD" + (f" (z toho obrázky {cz_usd(run.image_cost)} USD)" if run.image_cost else "")
    out = [f"<!doctype html><html lang=\"cs\"><head><meta charset=\"utf-8\"><title>{e(sc['name'])} — "
           f"{'úspěch' if ok else 'chyba'}</title><style>{CSS}</style></head><body>",
           f"<h1>{e(sc['name'])} — <span class=\"{'ok' if ok else 'err'}\">{'úspěch' if ok else 'chyba'}</span></h1>",
           f"<p>{e(sc.get('description') or '')}</p>",
           f"<p class=\"muted\">Běh <code>{e(run.run_id)}</code> · {started.day}. {started.month}. {started.year} "
           f"{started:%H:%M:%S} UTC · {cz(run.duration, 1)} s · {e(cost)}"
           + (f" · request_key <code>{e(run.request_key)}</code>" if run.request_key else "")
           + (" · <strong>falešný běh</strong> (<code>--fake</code>)" if run.fake else "") + "</p>"]
    if run.error:
        er = run.error
        out += ["<h2 class=\"err\">Chyba</h2>",
                f"<p>třída <code>{e(er['class'])}</code> · krok <code>{e(er['step'] or '—')}</code></p>",
                f"<pre>{e(_cut(er['message']))}</pre>"]
    out += ["<h2>Varování</h2>", "<ul>" + "".join(f"<li>{e(w)}</li>" for w in run.warnings) + "</ul>"
            if run.warnings else "<p>žádná</p>"]
    out += ["<h2>Vstupy</h2>", f"<pre>{e(_cut(_dump(run.inputs, 2)))}</pre>"]
    out += ["<h2>Kroky</h2>", "<table><tr><th>#</th><th>Krok</th><th>Typ</th><th>Stav</th><th>Čas</th><th>Cena</th>"
            "<th>Poznámka</th></tr>"]
    for path, s in steps.items():
        note = s["note"] or (s["errors"][-1]["message"].splitlines()[0] if s["errors"] else "")
        cls = "ok" if s["status"] == "succeeded" else "err" if s["status"] in ("failed", "continued") else ""
        out.append(f"<tr><td>{nn(path, s)}</td><td>{e(path)}</td><td>{e(s['kind'] or '')}</td>"
                   f"<td class=\"{cls}\">{e(STATUS_CS.get(s['status'], s['status']))}</td>"
                   f"<td>{'' if s['duration'] is None else cz(s['duration'], 1) + ' s'}</td>"
                   f"<td>{'' if s['cost'] is None else cz_usd(s['cost'])}</td><td>{e(note)}</td></tr>")
    out.append(f"<tr><td></td><td>Celkem</td><td></td><td></td><td>{cz(run.duration, 1)} s</td><td>{cz_usd(run.cost)}</td>"
               f"<td>{e(total_note(run))}</td></tr></table>")
    out.append("<h2>Výstup</h2>")
    if ok and run.outputs is not None:
        out.append("<ul>" + "".join(
            f"<li>{e(k)}: " + (f"<a href=\"{e(v)}\">{e(v)}</a>" if isinstance(v, str) and v.startswith(
                ("https://", "http://", "file://")) else e(cz_value(v))) + "</li>" for k, v in run.outputs.items())
            + "</ul>")
    else:
        out.append("<p>žádný</p>")
    out.append("<h2>Detail kroků</h2>")
    for path, s in steps.items():
        if not (s["folder"] or s["errors"]):
            continue
        out.append(f"<h3>{nn(path, s)} · {e(path)} ({e(s['kind'] or '')})</h3>")
        f = d / s["folder"] if s["folder"] else None
        if f and (f / "prompt.md").is_file():
            out.append(_pre("Prompt", (f / "prompt.md").read_text(encoding="utf-8")))
        for c in s["calls"]:
            usage = c.get("usage") or {}
            head = (f"Volání {c['attempt']}" + (f" · {c['alias']} → {c['model']}" if "alias" in c else f" · {c['model']}")
                    + (f" · {c['finish_reason']}" if c.get("finish_reason") else "")
                    + f" · {usage.get('input_tokens')}+{usage.get('output_tokens')} tokenů"
                    + ("" if usage.get("cost_usd") is None else f" · {cz_usd(usage['cost_usd'])} USD")
                    + f" · {cz(c['duration_s'], 1)} s")
            out.append(_pre(head, _answer(d / c["response_file"])))
        if f and (f / "output.json").is_file():
            out.append(_pre("Výstup kroku", (f / "output.json").read_text(encoding="utf-8")))
        for er in s["errors"]:
            out.append(f"<p class=\"err\"><code>{e(er['class'])}</code>"
                       + (f" (pokus {er['attempt']}{', opakuje se' if er.get('will_retry') else ''})"
                          if er.get("attempt") else "") + f": {e(_cut(er['message']))}</p>")
    out.append("</body></html>")
    return DATA_URL.sub("<vynecháno: data URL>", "\n".join(out))
