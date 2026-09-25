"""Záznam běhu (run-record.md): složka běhu, events.jsonl, soubory kroků,
summary.md, plan.md, callback.json. Každý zápis prochází maskováním tajných
hodnot; base64 a reasoning_details se do záznamu nikdy nedostanou.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from .expressions import FileRef, to_json
from .loader import nested_lists
from .validate import DEFAULT_TIMEOUT, Project

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
    def __init__(self, directory: Path, secrets: dict[str, str]):
        self.dir = directory
        self.secrets = {n: v for n, v in secrets.items() if v and len(v) >= MIN_SECRET_LEN}
        self.masked: set[str] = set()
        self.events: list[dict] = []
        directory.mkdir(parents=True)

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


def plan_md(p: Project) -> str:
    """Plán z validate (run-record.md plan.md, `--dry-run`)."""
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
            cond = f"`{st['when']}`" if "when" in st else ""
            lines.append(f"| {info.nn} | {'↳ ' * indent}{info.id} | {k} | {cond} | {what} | {_limits(p, st, k)} |")
            for _, lst in nested_lists(st):
                rows(lst, indent + 1)

    rows(sc["steps"], 0)
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

