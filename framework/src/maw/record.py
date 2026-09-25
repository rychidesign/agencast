"""Záznam běhu (run-record.md): složka běhu, events.jsonl, soubory kroků,
summary.md, plan.md, callback.json. Každý zápis prochází maskováním tajných
hodnot; base64 a reasoning_details se do záznamu nikdy nedostanou.
"""
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .expressions import FileRef, to_json
from .loader import nested_lists
from .validate import DEFAULT_TIMEOUT, Project, effective_tools

MIN_SECRET_LEN = 8  # kratší hodnoty se nemaskují (run-record.md)


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
                        + (f"; schema: {', '.join(t['schema'])}" if "schema" in t else "; text")
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
            f"{cz(run.duration, 1)} s · {cz(run.cost, 4)} USD")
    if run.image_cost:
        head += f" (z toho obrázky {cz(run.image_cost, 4)} USD)"
    lines = [f"# {sc['name']} — {'úspěch' if ok else 'chyba'}", "", sc["description"], head, ""]
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
        c = cz(r["cost"], 4) if r.get("duration") is not None else ""
        note = str(r.get("note") or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r['nn']} | {r['id']} | {r['kind']} | {STATUS_CS[r['status']]} | {t} | {c} | {note} |")
    lines += ["", "## Varování"] + ([f"- {w}" for w in run.warnings] or ["žádná"])
    lines += ["", "## Výstup"]
    if ok and run.outputs is not None:
        lines += [f"- {k}: {cz_value(v)}" for k, v in run.outputs.items()]
    else:
        lines.append("žádný")
    return "\n".join(lines)


def run_status(run_dir: Path) -> dict:
    """Stav běhu z events.jsonl (pro `maw runs list`)."""
    info = {"run_id": run_dir.name, "status": "běží nebo přerušen", "cost_usd": None, "duration_s": None,
            "callback": ""}
    ev = run_dir / "events.jsonl"
    if not ev.is_file():
        info["status"] = "dry-run" if (run_dir / "plan.md").is_file() else "?"
        return info
    for line in ev.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e["type"] == "run_finished":
            info.update(status=e["status"], cost_usd=e["usage"]["cost_usd"], duration_s=e["duration_s"])
            if e.get("error"):
                info["status"] += f" ({e['error']['class']} v {e['error']['step']})"
        elif e["type"] == "callback_failed":
            info["callback"] = "callback nedoručen"
    return info


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
    cost = f"{cz(run.cost, 4)} USD" + (f" (z toho obrázky {cz(run.image_cost, 4)} USD)" if run.image_cost else "")
    out = [f"<!doctype html><html lang=\"cs\"><head><meta charset=\"utf-8\"><title>{e(sc['name'])} — "
           f"{'úspěch' if ok else 'chyba'}</title><style>{CSS}</style></head><body>",
           f"<h1>{e(sc['name'])} — <span class=\"{'ok' if ok else 'err'}\">{'úspěch' if ok else 'chyba'}</span></h1>",
           f"<p>{e(sc.get('description') or '')}</p>",
           f"<p class=\"muted\">Běh <code>{e(run.run_id)}</code> · {started.day}. {started.month}. {started.year} "
           f"{started:%H:%M:%S} UTC · {cz(run.duration, 1)} s · {e(cost)}"
           + (f" · request_key <code>{e(run.request_key)}</code>" if run.request_key else "") + "</p>"]
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
                   f"<td>{'' if s['cost'] is None else cz(s['cost'], 4)}</td><td>{e(note)}</td></tr>")
    out.append("</table>")
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
                    + ("" if usage.get("cost_usd") is None else f" · {cz(usage['cost_usd'], 4)} USD")
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
