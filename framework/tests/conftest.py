import re
import shutil
import subprocess
import sys
import textwrap
import threading
import time
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
WORKFLOWS = REPO / "examples" / "showcase" / "workflows"
TUTORIAL = REPO / "examples" / "tutorial" / "workflows"
FAKE_MCP = Path(__file__).resolve().parent / "fake_mcp_server.py"
TOKEN, SECRET = "token-webhook-123", "callback-signature-456"  # webhook and server in registry mode

# Test config: aliases (models) come from examples/showcase/workflows/config.yaml — golden_config().
CONFIG = """\
version: 1
openrouter:
  api_key_env: OPENROUTER_API_KEY
  jev_model: jev-1.13
models:
  smart:       { id: anthropic/claude-haiku-4.5 }
  fast:       { id: google/gemini-3.5-flash-lite, structured_output: tool_wrapper }
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


def example_files(pattern: str) -> list[Path]:
    """Both projects; shared tone-check is tested once in the combined project."""
    return sorted({str(p.relative_to(root)): p for root in (WORKFLOWS, TUTORIAL) for p in root.glob(pattern)}.values())


def golden_config(real: Path = WORKFLOWS / "config.yaml") -> str:
    """CONFIG with aliases from the real config.yaml: a new owner alias does not break golden tests (BUGS.md #6);
    keys, limits, base_url and storage keep their test values."""
    if not real.is_file():
        return CONFIG
    models = yaml.safe_load(real.read_text())["models"]
    models = yaml.safe_dump({"models": models}, allow_unicode=True, sort_keys=False)
    return re.sub(r"models:\n(  .*\n)+", lambda _: models, CONFIG)  # the rest unchanged: tests replace text in it


def model_ids(wf: Path) -> list[str]:
    """Model IDs from config.yaml in the workflows/ copy — recognized by the fake GET /models."""
    return [m["id"] for m in yaml.safe_load((wf / "config.yaml").read_text())["models"].values()
            if m.get("api", "chat") == "chat"]


def image_model_ids(wf: Path) -> list[str]:
    """IDs of `api: images` aliases recognized by the fake GET /images/models."""
    return [m["id"] for m in yaml.safe_load((wf / "config.yaml").read_text())["models"].values()
            if m.get("api", "chat") == "images"]


def add_image_model(wf: Path, alias="gpt-image", model_id="openai/gpt-image-2", quality="low"):
    cfg_path = wf / "config.yaml"
    config = yaml.safe_load(cfg_path.read_text())
    config["models"][alias] = {"id": model_id, "api": "images", **({"quality": quality} if quality else {})}
    cfg_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))


def mcp_leftovers(basetemp: Path) -> set[str]:
    """What the MCP server tests may leave behind: `agencast mcp` servers and `--mcp-job` workers of this session
    (their registry is under its basetemp), `agencast-mcp-test-*` user units, `agencast-mcp-*` copies of file inputs."""
    found = {f"temp dir {p}" for p in basetemp.rglob("agencast-mcp-*") if p.is_dir()}
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            args = (proc / "cmdline").read_bytes().split(b"\0")
            if b"agencast.cli" in b" ".join(args) and (b"mcp" in args or b"--mcp-job" in args) and \
                    f"AGENCAST_CONFIG_DIR={basetemp}".encode() in (proc / "environ").read_bytes():
                found.add(f"process {proc.name}: {b' '.join(args).decode(errors='replace')}")
        except OSError:  # gone meanwhile, or another user's
            pass
    if shutil.which("systemctl"):
        units = subprocess.run(["systemctl", "--user", "list-units", "--all", "--plain", "--no-legend",
                                "agencast-mcp-test-*"], capture_output=True, text=True, timeout=30).stdout
        found |= {f"unit {line.split()[0]}" for line in units.splitlines() if line.strip()}
    return found


@pytest.fixture(scope="session", autouse=True)
def no_mcp_leftovers(tmp_path_factory):
    """After the whole suite no MCP server, run worker, test unit or temporary copy of file inputs that the tests
    started remains (mcp-server.md; a worker of the last test gets a few seconds to finish)."""
    basetemp = tmp_path_factory.getbasetemp()
    before = mcp_leftovers(basetemp)
    yield
    end = time.monotonic() + 10
    while (left := mcp_leftovers(basetemp) - before) and time.monotonic() < end:
        time.sleep(0.2)
    assert not left, sorted(left)


@pytest.fixture(autouse=True)
def no_delays(monkeypatch):
    monkeypatch.setattr(engine, "RETRY_BASE_S", 0)
    monkeypatch.setattr(engine, "CALLBACK_DELAYS", (0, 0))


@pytest.fixture
def wf(tmp_path) -> Path:
    """Merged workflows from both examples with test config.yaml (aliases from showcase)."""
    w = tmp_path / "workflows"
    for source in (WORKFLOWS, TUTORIAL):
        for d in ("agents", "skills", "scenarios"):
            shutil.copytree(source / d, w / d, dirs_exist_ok=True)
    (w / "config.yaml").write_text(golden_config())
    (w / "mcp.yaml").write_text(fake_mcp_yaml(WORKFLOWS / "mcp.yaml", TUTORIAL / "mcp.yaml"))
    return w


def fake_mcp_yaml(path: Path, tutorial: Path) -> str:
    """mcp.yaml with every stdio server replaced by a fake (tests/fake_mcp_server.py, no network or Node)."""
    data = yaml.safe_load(path.read_text())
    for name, server in yaml.safe_load(tutorial.read_text())["servers"].items():
        if name in data["servers"]:
            data["servers"][name]["agents"] += server["agents"]
        else:
            data["servers"][name] = server
    for s in data["servers"].values():
        if "command" in s:
            s["command"], s["args"] = sys.executable, [str(FAKE_MCP), *s.get("args", [])]
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def scenario(wf: Path, text: str, name: str = "test") -> Path:
    p = wf / "scenarios" / f"{name}.yaml"
    p.write_text(textwrap.dedent(text).lstrip().replace("NAME", name))
    return p


def run(path: Path, inputs=None, script=None, **kw):
    """validate + run with a fake provider; returns (Run, Fake)."""
    fake = Fake(script, model_ids(path.parents[1]), image_model_ids(path.parents[1]))
    p = validate(path, transport=fake.transport())
    r = run_scenario(p, resolve_inputs(p.scenario, inputs or {}), fake=fake, **kw)
    return r, fake


def events(r, type_=None):
    return [e for e in r.rec.events if type_ is None or e["type"] == type_]


@pytest.fixture(autouse=True)
def registry(tmp_path, monkeypatch) -> Path:
    """Project registry in tmp — tests never touch ~/.config/agencast."""
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
    a, b = tmp_path / "alpha", tmp_path / "beta"
    api.new_project(a)
    api.new_project(b)
    projects = Projects(token=TOKEN, fake=lambda: Fake(None))
    projects.start()
    srv, client = serve(projects=projects)
    yield projects, client, a, b
    client.close()
    srv.shutdown()
    srv.server_close()
