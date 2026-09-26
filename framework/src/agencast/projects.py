"""Registr projektů, nový projekt/agent/scénář ze šablon a popis projektu pro GUI
(`agencast projects`, `new`, `GET /projects/...`; projects.md, api.md).

Registr = `<AGENCAST_CONFIG_DIR, výchozí ~/.config/agencast>/projects.yaml`,
`projects: [{name, root}]`, bez tajemství; projekty se neskenují.
Šablony jsou tady jako řetězce, ne kopie z workflows/ — ty jsou zlaté testy
a mění se s nimi. Nic se nepřepisuje: existující soubor = chyba `config`.
"""
import ast
import hashlib
import os
import re
from pathlib import Path
from typing import Any

import yaml

from . import ConfigErrors
from .expressions import ExprError, parse, template_parts
from .loader import LoadError, nested_lists, read_frontmatter, read_yaml, step_kind
from .mcp_client import load_mcp, secret_names
from .validate import _strings, env_fields, load_agent, load_config, load_skill, validate

NAME = re.compile(r"[a-z][a-z0-9-]*")  # jako name agenta a scénáře ve schématech

CONFIG = """\
# Mění jen vlastník. Žádné tajné hodnoty: pole *_env obsahují JMÉNO
# proměnné prostředí, hodnota je v .env (zkopíruj .env.example).
version: 1

openrouter:
  api_key_env: OPENROUTER_API_KEY

# Aliasy modelů. Agenti a scénáře znají jen levou stranu.
models:
  chytry:       { id: anthropic/claude-haiku-4.5 }
  rychly:       { id: google/gemini-3.5-flash-lite, structured_output: tool_wrapper }
  gemini-image: { id: google/gemini-3.1-flash-image }

runs_dir: ./runs

storage:
  type: local
  local: { path: ./outputs }

# Pojistky jednoho běhu.
limits:
  run_budget_usd: 1.00
  run_image_budget_usd: 0.30
  run_timeout: 1h
  max_call_depth: 3

# Jen pro agencast serve.
webhook:
  token_env: WEBHOOK_TOKEN

callback:
  secret_env: CALLBACK_SECRET
"""

ENV_EXAMPLE = """\
# Zkopíruj na .env a doplň hodnoty. .env do gitu nepatří.
OPENROUTER_API_KEY=
# jen pro agencast serve
WEBHOOK_TOKEN=
CALLBACK_SECRET=
"""

GITIGNORE = ".env\nruns/\noutputs/\n"

AGENT = """\
---
version: 1
name: {name}
description: {description}
model: {model}{aliases}
limits:
  budget_usd: 0.02
---
{body}
"""

SCENARIO = """\
version: 1
name: {name}
description: {description}
inputs:
  tema: {{ type: string, default: káva, description: O čem psát }}
outputs:
  text: {{ type: string }}
steps:
  - id: napis
    ask:
      agent: {agent}
      prompt: "Napiš dvě věty na téma: {{{{ inputs.tema }}}}"
  - id: vystup
    output:
      text: "{{{{ steps.napis.text }}}}"
"""


def etag(text: str | None) -> str | None:
    """Otisk verze souboru pro editační operace (edit.py): sha256 obsahu, None = soubor není."""
    return None if text is None else hashlib.sha256(text.encode()).hexdigest()


def _etag(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_name(name: str, what: str):
    if not NAME.fullmatch(name):
        raise ConfigErrors([f"{what} '{name}': jméno má být malá písmena, číslice a pomlčka, začíná písmenem"])


def _write(files: dict[Path, str]) -> list[Path]:
    if taken := [p for p in files if p.exists()]:
        raise ConfigErrors([f"{p}: už existuje — nepřepisuju" for p in taken])
    for p, text in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return list(files)


# --- registr ---------------------------------------------------------------------

def registry_path() -> Path:
    return Path(os.environ.get("AGENCAST_CONFIG_DIR") or Path.home() / ".config" / "agencast") / "projects.yaml"


def _read() -> list[dict[str, str]]:
    p = registry_path()
    if not p.is_file():
        return []
    try:
        data = read_yaml(p, str(p)) or {}
    except LoadError as e:
        raise ConfigErrors([str(e)]) from None
    items = (data.get("projects") or []) if isinstance(data, dict) else None
    if not isinstance(items, list) or not all(
            isinstance(x, dict) and isinstance(x.get("name"), str) and isinstance(x.get("root"), str) for x in items):
        raise ConfigErrors([f"{p}: má mít tvar projects: [{{name, root}}]"])
    return items


def _save(items: list[dict[str, str]]):
    # ponytail: dva souběžné zápisy (add z dvou terminálů) — vyhraje poslední; zámek, až to začne vadit
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump({"projects": items}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    tmp.replace(p)  # serve čte registr při každém požadavku → nikdy půlka souboru


def list_projects() -> list[dict[str, str | bool]]:
    """Projekty z registru; `available: false` = chybí workflows/config.yaml (položka zůstává)."""
    return [{"name": x["name"], "root": x["root"], "available": (Path(x["root"]) / "workflows" / "config.yaml").is_file()}
            for x in _read()]


def default_name(root: Path) -> str:
    return re.sub(r"[^a-z0-9]+", "-", root.name.lower()).strip("-")


def _checked_name(root: Path, name: str | None, items: list[dict[str, str]]) -> str:
    name = name or default_name(root)
    other = next((x for x in items if x["name"] == name), None)
    if not NAME.fullmatch(name) or other:
        why = f"už v registru je ({other['root']})" if other else "není malá písmena, číslice a pomlčka od písmene"
        raise ConfigErrors([f"projekt '{name}' {why} — zvol jméno: agencast projects add {root} --name <jméno>"])
    return name


def add(root: Path, name: str | None = None) -> str:
    """Zapíše projekt do registru; jméno výchozí = složka (kebab). Vrací jméno."""
    items = _read()
    if hit := next((x for x in items if Path(x["root"]) == root), None):
        raise ConfigErrors([f"{root}: už je v registru jako '{hit['name']}'"])
    name = _checked_name(root, name, items)
    _save(items + [{"name": name, "root": str(root)}])
    return name


def remove(name: str):
    items = _read()
    if not any(x["name"] == name for x in items):
        raise ConfigErrors([f"projekt '{name}' v registru není ({registry_path()})"])
    _save([x for x in items if x["name"] != name])


def ensure(root: Path) -> str | None:
    """Po úspěšném validate/run: projekt, který v registru není, přidá. Vrací hlášku pro stderr."""
    if any(Path(x["root"]) == root for x in _read()):
        return None
    return f"projekt {add(root)} přidán do registru ({registry_path()})"


# --- šablony ------------------------------------------------------------------------

def new_project(root, name: str | None = None) -> list[Path]:
    """Kostra projektu s jedním agentem a scénářem, které projdou `validate --offline` i `--fake`;
    hned ji zapíše do registru (jméno se ověří před vytvořením souborů)."""
    root = Path(root).resolve()
    wf = root / "workflows"
    if wf.exists():
        raise ConfigErrors([f"{wf}: už existuje — agencast new project zakládá jen nový projekt"])
    name = _checked_name(root, name, _read())
    files = {
        wf / "config.yaml": CONFIG,
        root / ".env.example": ENV_EXAMPLE,
        wf / "agents" / "pisatel.md": AGENT.format(
            name="pisatel", description="Píše krátké texty na zadané téma", model="chytry", aliases="",
            body="Píšeš krátké, věcné texty česky. Jen text, bez emoji a bez nadpisů."),
        wf / "scenarios" / "ukazka.yaml": SCENARIO.format(
            name="ukazka", description="Napíše krátký text na zadané téma", agent="pisatel"),
    }
    if not (root / ".gitignore").exists():
        files[root / ".gitignore"] = GITIGNORE
    made = _write(files)
    add(root, name)
    return made


def _workflows(root: Path):
    wf = root / "workflows"
    errs = []
    cfg = load_config(wf, errs)
    if errs or cfg is None:
        raise ConfigErrors(errs)
    return wf, cfg


def new_agent(root: Path, name: str) -> list[Path]:
    """Minimální agent; model = první alias z config.yaml, ostatní aliasy v komentáři."""
    _check_name(name, "agent")
    wf, cfg = _workflows(root)
    aliases = list(cfg["models"])
    return _write({wf / "agents" / f"{name}.md": AGENT.format(
        name=name, description="TODO — co agent dělá (pro lidi, modelu se neposílá)", model=aliases[0],
        aliases=f"    # alias z config.yaml: {', '.join(aliases)}",
        body="TODO: instrukce agenta (systémový prompt).")})


def new_scenario(root: Path, name: str) -> list[Path]:
    """Minimální scénář (vstup → ask → output) s prvním agentem projektu podle abecedy."""
    _check_name(name, "scénář")
    wf, _ = _workflows(root)
    agents = sorted(p.stem for p in (wf / "agents").glob("*.md"))
    if not agents:
        raise ConfigErrors([f"{wf / 'agents'}: projekt nemá agenta — nejdřív agencast new agent <jméno>"])
    return _write({wf / "scenarios" / f"{name}.yaml": SCENARIO.format(
        name=name, description="TODO — co scénář dělá", agent=agents[0])})


# --- popis projektu pro GUI (api.md) ------------------------------------------------
# Z YAML přes loader, chyby z validate (check_models=False) — i rozbitý soubor jde zobrazit.

def _refs(own: dict[str, Any]) -> list[str]:
    """Odkazy `steps.<id>.<pole>` ve výrazech a šablonách kroku (bez vnořených kroků)."""
    out = set()
    for path, text in _strings(own):
        if "{{" in text:
            try:
                srcs = [e for _, _, e in template_parts(text)]
            except ExprError:
                continue
        elif path in (("when",), ("switch", "value")) or (len(path) == 2 and path[0] == "set"):
            srcs = [text]
        else:
            continue
        for src in srcs:
            try:
                tree = parse(src)
            except ExprError:
                continue
            out |= {f"steps.{n.value.attr}.{n.attr}" for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                    and isinstance(n.value, ast.Attribute) and isinstance(n.value.value, ast.Name)
                    and n.value.value.id == "steps"}
    return sorted(out)


def _steps(steps, flat: list[dict[str, Any]], at: tuple[Any, ...] = ("steps",)) -> list[dict[str, Any]]:
    """Strom kroků pro karty; `nn` = pořadí v souboru hloubkově (jako složky běhu). `flat` = všechny kroky.
    `address` = cesta kroku v dokumentu (`at` + index), jak ji berou editační operace (edit.py)."""
    out = []
    for i, st in enumerate(steps if isinstance(steps, list) else []):
        if not isinstance(st, dict):
            continue
        k = step_kind(st)
        own = {key: v for key, v in st.items() if key not in ("id", "when", "parallel")}
        if k == "switch" and isinstance(st["switch"], dict):
            own["switch"] = {key: v for key, v in st["switch"].items() if key not in ("cases", "default")}
        item: dict[str, Any] = {"nn": len(flat) + 1, "address": [*at, i], "id": st.get("id"), "type": k, "when": st.get("when"), "fields": own,
                "refs": _refs({**own, **({"when": st["when"]} if "when" in st else {})})}
        if k in ("ask", "task", "call") and isinstance(st[k], dict):
            item["call" if k == "call" else "agent"] = st[k].get("scenario" if k == "call" else "agent")
        flat.append(item)
        for p, lst in nested_lists(st):
            sub = _steps(lst, flat, (*at, i, *p))
            if p[0] == "parallel":
                item.setdefault("branches", {})[p[1]] = sub
            elif p[1] == "cases":
                item.setdefault("cases", {})[p[2]] = sub
            else:
                item["default"] = sub
        if k == "switch":
            item.setdefault("cases", {})
            item.setdefault("default", [])
        out.append(item)
    return out


# Začátek hlášky validate/loaderu: `<soubor>[, řádek N][: krok "id"][, pole|: pole]: …` (_Checker.err,
# schema_errors, load_yaml). Scénář se hlásí jménem souboru (ig-post.yaml), ostatní cestou ve workflows/.
ERROR_HEAD = re.compile(r"(?P<file>agents/[^/:,\s]+\.md|skills/[^/:,\s]+/SKILL\.md|(?:scenarios/)?[^/:,\s]+\.yaml)"
                        r"(?:, řádek (?P<line>\d+))?(?:: krok [\"'](?P<step>[^\"']+)[\"'])?"
                        r"(?:(?:, |: )(?P<field>[\w.\[\]-]+(?: \(klíč\))?)(?=: ))?: ")


def error_fields(message: str, root: Path) -> dict[str, Any]:
    """Hláška jako objekt pro GUI (api.md): `{message, file?, step?, field?, line?}`; `message` beze změny.
    ponytail: pole se čtou ze začátku hlášky — hláška jiného tvaru má jen `message`."""
    out: dict[str, Any] = {"message": message}
    m = ERROR_HEAD.match(message.removeprefix(f"{root / 'workflows'}/"))
    if not m:
        return out
    f = m["file"]
    # ponytail: scénář pojmenovaný config nebo mcp se tu splete s config.yaml/mcp.yaml
    out["file"] = f if "/" in f or f in ("config.yaml", "mcp.yaml") else f"scenarios/{f}"
    out |= {k: m[k] for k in ("step", "field") if m[k]}
    if m["line"]:
        out["line"] = int(m["line"])
    return out


def _scenario(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(popis scénáře se stromem kroků a chybami validate, všechny kroky)."""
    info: dict[str, Any] = {"name": path.stem, "etag": _etag(path), "description": None, "inputs": {}, "outputs": {}, "callable": False}
    try:
        sc = read_yaml(path, path.name)
    except LoadError as e:
        return {**info, "steps_count": 0, "errors": [str(e)], "steps": []}, []
    sc = sc if isinstance(sc, dict) else {}
    flat: list[dict[str, Any]] = []
    tree = _steps(sc.get("steps"), flat)
    try:
        validate(path, check_models=False)
        errors = []
    except ConfigErrors as e:
        errors = e.errors
    info.update({k: sc.get(k) or info[k] for k in ("description", "inputs", "outputs")},
                callable=sc.get("callable") is True, steps_count=len(flat), errors=errors, steps=tree)
    return info, flat


def describe_scenario(root: Path, name: str) -> dict[str, Any] | None:
    """Scénář pro karty kroků; None = neexistuje."""
    path = root / "workflows" / "scenarios" / f"{name}.yaml"
    return _scenario(path)[0] if NAME.fullmatch(name) and path.is_file() else None


def describe_project(root: Path) -> dict[str, Any]:
    """Scénáře, agenti, skilly, MCP servery (bez tajemství), aliasy, limity a vazby mezi nimi."""
    wf, cfg = _workflows(root)
    errs = []
    mcp = load_mcp(wf, errs)
    links = {"scenario_agent": set(), "scenario_scenario": set(), "agent_skill": set(), "agent_server": set()}
    scenarios = []
    for path in sorted((wf / "scenarios").glob("*.yaml")):
        info, flat = _scenario(path)
        del info["steps"]
        scenarios.append(info)
        links["scenario_agent"] |= {(info["name"], s["agent"]) for s in flat if isinstance(s.get("agent"), str)}
        links["scenario_scenario"] |= {(info["name"], s["call"]) for s in flat if isinstance(s.get("call"), str)}
    agents = []
    for path in sorted((wf / "agents").glob("*.md")):
        a_errs = []
        try:
            fm = read_frontmatter(path, f"agents/{path.name}")[0]
        except LoadError as e:
            fm, a_errs = {}, [str(e)]
        fm = fm if isinstance(fm, dict) else {}
        if not a_errs:
            load_agent(wf, path.stem, cfg, a_errs, mcp=mcp)
        model = fm.get("model")
        agents.append({"name": path.stem, "etag": _etag(path), "description": fm.get("description"), "model": model,
                       "model_id": cfg["models"].get(model, {}).get("id") if isinstance(model, str) else None,
                       "skills": fm.get("skills") or [], "mcp": fm.get("mcp") or [], "tools": fm.get("tools") or {},
                       "errors": a_errs})
        links["agent_skill"] |= {(path.stem, x) for x in agents[-1]["skills"] if isinstance(x, str)}
        links["agent_server"] |= {(path.stem, x) for x in agents[-1]["mcp"] if isinstance(x, str)}
    skills = []
    for path in sorted((wf / "skills").glob("*/SKILL.md")):
        s_errs = []
        s = load_skill(wf, path.parent.name, s_errs, "skills")
        skills.append({"name": path.parent.name, "etag": _etag(path), "description": s[1] if s else None, "errors": s_errs})
    servers = [{"name": n, "type": "stdio" if "command" in s else "http", "agents": s["agents"],
                "tools": s.get("tools"), "scenarios": s.get("scenarios")} for n, s in mcp.items()]
    # proměnné z config.yaml (*_env) a mcp.yaml (env, bearer_token_env): jen jestli je nastavená, nikdy hodnota
    env = {n: bool(os.environ.get(n)) for n in sorted({n for _, n in env_fields(cfg)} | set(secret_names(mcp)))}
    return {"root": str(root), "models": {a: m["id"] for a, m in cfg["models"].items()}, "limits": cfg["limits"], "env": env,
            "scenarios": scenarios, "agents": agents, "skills": skills, "mcp_servers": servers,
            "links": {k: sorted(map(list, v)) for k, v in links.items()}, "errors": errs}
