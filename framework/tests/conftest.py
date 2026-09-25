import shutil
import textwrap
from pathlib import Path

import pytest

from maw import engine
from maw.engine import run_scenario
from maw.fake import Fake
from maw.validate import resolve_inputs, validate

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / "workflows"

CONFIG = """\
version: 1
openrouter:
  api_key_env: OPENROUTER_API_KEY
  jev_model: jev-1.13
models:
  chytry:       { id: anthropic/claude-haiku-4.5 }
  rychly:       { id: google/gemini-3.5-flash-lite, structured_output: tool_wrapper }
  gemini-image: { id: google/gemini-3.1-flash-image }
runs_dir: ./runs
storage:
  type: local
  local: { path: ./outputs }
limits:
  run_budget_usd: 1.00
  run_image_budget_usd: 0.30
  run_timeout: 1h
webhook:
  token_env: WEBHOOK_TOKEN
callback:
  secret_env: CALLBACK_SECRET
"""


@pytest.fixture(autouse=True)
def no_delays(monkeypatch):
    monkeypatch.setattr(engine, "RETRY_BASE_S", 0)
    monkeypatch.setattr(engine, "CALLBACK_DELAYS", (0, 0))


@pytest.fixture
def wf(tmp_path) -> Path:
    """Kopie workflows/ (agenti, skilly, scénáře) s testovacím config.yaml."""
    w = tmp_path / "workflows"
    for d in ("agents", "skills", "scenarios"):
        shutil.copytree(WORKFLOWS / d, w / d)
    (w / "config.yaml").write_text(CONFIG)
    return w


def scenario(wf: Path, text: str, name: str = "test") -> Path:
    p = wf / "scenarios" / f"{name}.yaml"
    p.write_text(textwrap.dedent(text).lstrip().replace("NAME", name))
    return p


def fake_for(p, script=None) -> Fake:
    return Fake(script, [m["id"] for m in p.config["models"].values()])


def run(path: Path, inputs=None, script=None, **kw):
    """validate + běh s falešným poskytovatelem; vrací (Run, Fake)."""
    fake = Fake(script, ["anthropic/claude-haiku-4.5", "google/gemini-3.5-flash-lite",
                         "google/gemini-3.1-flash-image"])
    p = validate(path, transport=fake.transport())
    r = run_scenario(p, resolve_inputs(p.scenario, inputs or {}), fake=fake, **kw)
    return r, fake


def events(r, type_=None):
    return [e for e in r.rec.events if type_ is None or e["type"] == type_]
