"""Registr projektů a nový projekt, agent a scénář ze šablon (`agencast projects`, `new`; projects.md).

Registr = `<AGENCAST_CONFIG_DIR, výchozí ~/.config/agencast>/projects.yaml`,
`projects: [{name, root}]`, bez tajemství; projekty se neskenují.
Šablony jsou tady jako řetězce, ne kopie z workflows/ — ty jsou zlaté testy
a mění se s nimi. Nic se nepřepisuje: existující soubor = chyba `config`.
"""
import os
import re
from pathlib import Path

import yaml

from . import ConfigErrors
from .loader import LoadError, read_yaml
from .validate import load_config

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


def _checked_name(root: Path, name: str | None, items: list[dict[str, str]]) -> str:
    name = name or re.sub(r"[^a-z0-9]+", "-", root.name.lower()).strip("-")
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
