import re
import shutil
import sys
import textwrap
import threading
from pathlib import Path

import httpx
import pytest
import yaml

from agencast import api, engine
from agencast.engine import run_scenario
from agencast.fake import Fake
from agencast.server import Projects, Server
from agencast.validate import resolve_inputs, validate

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / "workflows"
FAKE_MCP = Path(__file__).resolve().parent / "fake_mcp_server.py"
TOKEN, SECRET = "token-webhooku-123", "podpis-callbacku-456"  # webhook a server v režimu registru

# Testovací config: aliasy (models) se berou ze skutečného workflows/config.yaml — golden_config().
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


def golden_config(real: Path = WORKFLOWS / "config.yaml") -> str:
    """CONFIG s aliasy ze skutečného config.yaml: nový alias vlastníka nerozbije zlaté testy (BUGS.md #6);
    klíče, limity, base_url a úložiště zůstávají testovací."""
    if not real.is_file():
        return CONFIG
    models = yaml.safe_load(real.read_text())["models"]
    models = yaml.safe_dump({"models": models}, allow_unicode=True, sort_keys=False)
    return re.sub(r"models:\n(  .*\n)+", lambda _: models, CONFIG)  # zbytek doslova: testy v něm nahrazují text


def model_ids(wf: Path) -> list[str]:
    """Id modelů z config.yaml v kopii workflows/ — ty zná falešné GET /models."""
    return [m["id"] for m in yaml.safe_load((wf / "config.yaml").read_text())["models"].values()
            if m.get("api", "chat") == "chat"]


def image_model_ids(wf: Path) -> list[str]:
    """Id aliasů `api: images`, které zná falešný GET /images/models."""
    return [m["id"] for m in yaml.safe_load((wf / "config.yaml").read_text())["models"].values()
            if m.get("api", "chat") == "images"]


def add_image_model(wf: Path, alias="gpt-image", model_id="openai/gpt-image-2", quality="low"):
    cfg_path = wf / "config.yaml"
    config = yaml.safe_load(cfg_path.read_text())
    config["models"][alias] = {"id": model_id, "api": "images", **({"quality": quality} if quality else {})}
    cfg_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))


@pytest.fixture(autouse=True)
def no_delays(monkeypatch):
    monkeypatch.setattr(engine, "RETRY_BASE_S", 0)
    monkeypatch.setattr(engine, "CALLBACK_DELAYS", (0, 0))


@pytest.fixture
def wf(tmp_path) -> Path:
    """Kopie workflows/ (agenti, skilly, scénáře) s testovacím config.yaml (aliasy ze skutečného)."""
    w = tmp_path / "workflows"
    for d in ("agents", "skills", "scenarios"):
        shutil.copytree(WORKFLOWS / d, w / d)
    (w / "config.yaml").write_text(golden_config())
    (w / "mcp.yaml").write_text(fake_mcp_yaml(WORKFLOWS / "mcp.yaml"))
    return w


def fake_mcp_yaml(path: Path) -> str:
    """mcp.yaml, ve kterém každý stdio server nahradí falešný (tests/fake_mcp_server.py, bez sítě a Node)."""
    data = yaml.safe_load(path.read_text())
    for s in data["servers"].values():
        if "command" in s:
            s["command"], s["args"] = sys.executable, [str(FAKE_MCP), *s.get("args", [])]
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def scenario(wf: Path, text: str, name: str = "test") -> Path:
    p = wf / "scenarios" / f"{name}.yaml"
    p.write_text(textwrap.dedent(text).lstrip().replace("NAME", name))
    return p


def run(path: Path, inputs=None, script=None, **kw):
    """validate + běh s falešným poskytovatelem; vrací (Run, Fake)."""
    fake = Fake(script, model_ids(path.parents[1]), image_model_ids(path.parents[1]))
    p = validate(path, transport=fake.transport())
    r = run_scenario(p, resolve_inputs(p.scenario, inputs or {}), fake=fake, **kw)
    return r, fake


def events(r, type_=None):
    return [e for e in r.rec.events if type_ is None or e["type"] == type_]


@pytest.fixture(autouse=True)
def registry(tmp_path, monkeypatch) -> Path:
    """Registr projektů v tmp — testy nikdy nesahají na ~/.config/agencast."""
    d = tmp_path / "agencast-config"
    monkeypatch.setenv("AGENCAST_CONFIG_DIR", str(d))
    return d / "projects.yaml"


def serve(hook=None, projects=None):
    srv = Server(hook, "127.0.0.1", 0, projects)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, httpx.Client(base_url=f"http://127.0.0.1:{srv.server_address[1]}",
                             headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10)


@pytest.fixture
def registry_server(tmp_path, monkeypatch):
    monkeypatch.setenv("CALLBACK_SECRET", SECRET)
    a, b = tmp_path / "alfa", tmp_path / "beta"
    api.new_project(a)
    api.new_project(b)
    projects = Projects(token=TOKEN, fake=lambda: Fake(None))
    projects.start()
    srv, client = serve(projects=projects)
    yield projects, client, a, b
    client.close()
    srv.shutdown()
    srv.server_close()
