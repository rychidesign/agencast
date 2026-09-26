"""Nový projekt, agent a scénář ze šablon (`agencast new`, projects.md).

Šablony jsou tady jako řetězce, ne kopie z workflows/ — ty jsou zlaté testy
a mění se s nimi. Nic se nepřepisuje: existující soubor = chyba `config`.
"""
import re
from pathlib import Path

from . import ConfigErrors
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


def new_project(root) -> list[Path]:
    """Kostra projektu s jedním agentem a scénářem, které projdou `validate --offline` i `--fake`."""
    root = Path(root).resolve()
    wf = root / "workflows"
    if wf.exists():
        raise ConfigErrors([f"{wf}: už existuje — agencast new project zakládá jen nový projekt"])
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
    return _write(files)


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
