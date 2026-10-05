"""`agencast mcp` (docs/spec/mcp-server.md): the server, its exit (codes, masking), the read tools and the run tools.
Tool logic through the SDK's in-memory client; stdio through a real subprocess. The registry is the temp one of
conftest (`AGENCAST_CONFIG_DIR`); no model is called. Runs execute in worker processes even in-memory; the tests of
their life apart from the server (disconnect, signals, restarts, the cap) are in test_mcp_workers.py."""
import base64
import fcntl
import getpass
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import anyio
import pytest
import yaml
from mcp import Client, StdioServerParameters

from conftest import golden_config, mcp_leftovers
from test_mcp_http import Http
from test_mcp_workers import cleanup, until  # noqa: F401 (a fixture)
from test_owner_only import marked

from agencast import api, engine, mcp_server, resources
from agencast.cli import main
from agencast.fake import png
from agencast.mcp_server import INSTRUCTIONS, START, build

SPEC = (Path(__file__).resolve().parents[2] / "docs" / "spec" / "mcp-server.md").read_text()
KEY = "sk-test-abcdefgh12345678"
READ_TOOLS = {"list_projects", "describe_project", "list_scenarios", "describe_scenario", "read_file", "validate",
              "get_guide", "run_status", "wait_run", "list_runs", "get_run_file"}
RUN_TOOLS = {"dry_run", "fake_run", "run_scenario"}
RUN_ID = re.compile(r"\d{8}-\d{6}-demo-[0-9a-f]{4}")
RUN_CARD = "ui://agencast/run-card.html"


def spec_description(tool: str) -> str:
    m = re.search(rf"\nDescription of `{tool}`: `(.*?)`\n", SPEC, re.S) or re.search(
        r"\nDescription: `(.*?)`\n", SPEC.split(f"### `{tool}`", 1)[1], re.S)
    return " ".join(m[1].split())


def calls(server, *requests):
    """Results of `(tool, arguments)` calls in one in-memory session."""
    async def go():
        async with Client(server) as c:
            return [await c.call_tool(tool, args) for tool, args in requests]
    return anyio.run(go)


def call(server, tool, args=None):
    return calls(server, (tool, args or {}))[0]


def ok(r) -> dict:
    """A successful result: structured content, and a text block that is the same object."""
    assert not r.is_error, r.content[0].text
    assert isinstance(r.structured_content, dict) and json.loads(r.content[0].text) == r.structured_content
    return r.structured_content


def err(r) -> str:
    assert r.is_error and len(r.content) == 1
    return r.content[0].text


@pytest.fixture
def root(tmp_path, monkeypatch) -> Path:
    """A project made by `agencast new project`, registered as `lumen`; no key in the environment."""
    for name in ("OPENROUTER_API_KEY", "HTTPS_PROXY"):
        monkeypatch.setenv(name, "")  # recorded first, so a value a test loads is removed afterwards
        monkeypatch.delenv(name)
    assert main(["new", "project", str(tmp_path / "lumen")]) == 0
    return tmp_path / "lumen"


def test_spec_texts():
    """The server's own texts are the spec's: `instructions` and the `start` topic of get_guide."""
    assert " ".join(re.search(r"\*\*`instructions`\*\* \(sent at connect\): `(.*?)`", SPEC, re.S)[1].split()) == INSTRUCTIONS
    assert re.search(r"The text of `start`:\n\n```markdown\n(.*?)```\n", SPEC, re.S)[1] == START


def test_read_level_over_stdio(root, registry):
    """--allow read: the seven read tools with the spec's descriptions; started inside a project without
    --project it is still registry mode; --project serves exactly that project."""
    env = {"PATH": os.environ["PATH"], "HOME": str(root.parent), "AGENCAST_CONFIG_DIR": str(registry.parent)}

    async def go(*args):
        params = StdioServerParameters(command=sys.executable, args=["-m", "agencast.cli", *args], env=env, cwd=root)
        async with Client(params, mode="legacy") as c:
            return (c.server_info.name, (await c.list_tools()).tools, (await c.list_resources()).resources,
                    (await c.list_prompts()).prompts, ok(await c.call_tool("list_projects", {})))

    name, tools, resources, prompts, listed = anyio.run(go, "mcp", "--allow", "read")
    assert name == "agencast" and prompts == []
    assert [(r.uri, r.mime_type) for r in resources] == [("ui://agencast/run-card.html", "text/html;profile=mcp-app")]
    assert {t.name for t in tools} == READ_TOOLS
    for t in tools:
        assert t.annotations.read_only_hint is True and t.annotations.open_world_hint is False
        assert t.output_schema["type"] == "object"
        assert t.description == spec_description(t.name) and "COSTS MONEY" not in t.description
    assert listed["server"] | {"version": None} == {"version": None, "mode": "registry", "allow": "read",
                                                    "fake_only": False, "input_dirs": [],
                                                    "host": socket.gethostname(), "user": getpass.getuser()}
    assert listed["server"]["host"] and listed["server"]["user"]  # the scp target for image inputs
    assert listed["projects"] == [{"name": "lumen", "root": str(root), "available": True, "trusted": True}]
    listed = anyio.run(go, "--project", str(root), "mcp", "--allow", "read")[4]
    assert listed["server"]["mode"] == "project" and listed["server"]["allow"] == "read"
    assert listed["projects"] == [{"name": "lumen", "root": str(root), "available": True, "trusted": True}]


def test_run_card_resource_and_bindings():
    """The card is a bundled MCP Apps resource, bound only to the tools that start or show a run."""
    async def read_card(mode):
        async with Client(build(allow="read"), mode=mode) as client:
            result = await client.read_resource(RUN_CARD)
            return client.server_capabilities.extensions, result.contents[0].text

    extensions, html = anyio.run(read_card, "auto")
    assert "io.modelcontextprotocol/ui" in extensions
    assert anyio.run(read_card, "legacy") == (None, html)  # the 2025 handshake has no `extensions`; the card is served
    assert html.lower().startswith(("<!doctype html>", "<html"))
    assert all(text in html for text in ("ui/initialize", "tools/call", "run_status", "get_run_file"))
    assert "http://" not in html and "https://" not in html
    for server, names in ((build(allow="edit"), {"fake_run", "run_scenario", "run_status"}),
                          (build(fake=""), {"fake_run", "run_status"}),
                          (build(allow="read"), {"run_status"})):
        tools = {tool.name: tool for tool in anyio.run(_tools, server)}
        assert {name for name, tool in tools.items() if tool.meta} == names
        assert all(tools[name].meta == {"ui": {"resourceUri": RUN_CARD}} for name in names)


def test_project_and_scenarios(root):
    (root / "workflows" / "mcp.yaml").write_text(
        "version: 1\nservers:\n"
        "  files: {description: Files, command: /bin/true, args: [x], env: {TOKEN: FILES_TOKEN}, agents: [writer]}\n"
        "  remote: {description: Remote, url: 'https://mcp.example.com/x', bearer_token_env: REMOTE_TOKEN, agents: [writer]}\n")
    server = build(allow="read")
    project, listing, scenario = map(ok, calls(server, ("describe_project", {"project": "lumen"}),
                                               ("list_scenarios", {"project": "lumen"}),
                                               ("describe_scenario", {"project": "lumen", "scenario": "demo"})))
    assert project["project"] == "lumen" and project["root"] == str(root) and project["trusted"] is True
    assert project["models"]["smart"] == "anthropic/claude-haiku-4.5"
    assert {"OPENROUTER_API_KEY", "FILES_TOKEN", "REMOTE_TOKEN"} <= set(project["env"])
    assert all(v is False for v in project["env"].values())
    assert [s["name"] for s in project["mcp_servers"]] == ["files", "remote"]
    assert not {"command", "args", "url", "env", "bearer_token_env"} & {k for s in project["mcp_servers"] for k in s}
    assert not {"scenarios", "links", "models_used"} & set(project)
    assert [s["name"] for s in listing["scenarios"]] == ["demo"] and "topic" in listing["scenarios"][0]["inputs"]
    assert scenario["project"] == "lumen" and scenario["name"] == "demo" and len(scenario["steps"]) == 2
    texts = map(err, calls(server, ("describe_project", {"project": "nope"}),
                           ("describe_scenario", {"project": "lumen", "scenario": "nope"})))
    assert next(texts) == "Error executing tool describe_project: not_found: project 'nope' does not exist (list_projects)"
    assert next(texts) == ("Error executing tool describe_scenario: not_found: scenario 'nope' does not exist in "
                           "project 'lumen' (list_scenarios)")
    # no readable config.yaml = no known secret names: nothing of the project is returned
    (root / "workflows" / "config.yaml").write_text("version: 1\n")
    assert err(call(server, "list_scenarios", {"project": "lumen"})).startswith(
        "Error executing tool list_scenarios: config: config.yaml of project 'lumen' cannot be read")


def test_scenario_file(root, tmp_path):
    """The scenario really lies in the project's own workflows/scenarios: a link to a sibling is that sibling; a
    link out of it — the file, a linked scenarios/ or workflows/ — is not found. A linked workflows/ serves no file
    to read or to validate a draft in either (the other tree's text, masked with the wrong project's secrets)."""
    other = tmp_path / "other"
    assert main(["new", "project", str(other)]) == 0
    d = root / "workflows" / "scenarios"
    assert api.scenario_file(root, "demo") == d / "demo.yaml"
    (d / "same.yaml").symlink_to(d / "demo.yaml")
    assert api.scenario_file(root, "same") == d / "demo.yaml"
    (d / "evil.yaml").symlink_to(other / "workflows" / "scenarios" / "demo.yaml")
    (tmp_path / "linked-scenarios" / "workflows").mkdir(parents=True)
    (tmp_path / "linked-scenarios" / "workflows" / "scenarios").symlink_to(other / "workflows" / "scenarios")
    (tmp_path / "linked-workflows").mkdir()
    (tmp_path / "linked-workflows" / "workflows").symlink_to(other / "workflows")
    for at, name in [(root, "evil"), (root, "nope"), (root, "../scenarios/demo"), (tmp_path / "linked-scenarios", "demo"),
                     (tmp_path / "linked-workflows", "demo")]:
        with pytest.raises(api.NotFound):
            api.scenario_file(at, name)
    with pytest.raises(api.NotFound):
        api.read_file(tmp_path / "linked-workflows", "agents/writer.md")
    with pytest.raises(api.NotFound):
        api.validate_text(tmp_path / "linked-workflows", "scenarios/demo.yaml", "version: 1\n")
    texts = map(err, calls(build(allow="read"), ("describe_scenario", {"project": "lumen", "scenario": "evil"}),
                           ("read_file", {"project": "lumen", "kind": "scenario", "name": "evil"})))
    assert next(texts).startswith("Error executing tool describe_scenario: not_found: scenario 'evil' does not exist")
    assert next(texts).startswith("Error executing tool read_file: not_found: ")
    (d / "loop.yaml").symlink_to(d / "loop.yaml")  # a link loop is no file, not RuntimeError (Python 3.12's resolve())
    (root / "workflows" / "agents" / "loop.md").symlink_to(root / "workflows" / "agents" / "loop.md")
    texts = map(err, calls(build(allow="read"), ("describe_scenario", {"project": "lumen", "scenario": "loop"}),
                           ("read_file", {"project": "lumen", "kind": "agent", "name": "loop"})))
    assert next(texts).startswith("Error executing tool describe_scenario: not_found: scenario 'loop' does not exist")
    assert next(texts).startswith("Error executing tool read_file: not_found: agents/loop.md: file does not exist")


def test_linked_out_agent_skill_and_callee(root, tmp_path):
    """An agent, skill or called scenario that is a link out of the project's own workflows/ is no file, as a linked
    top-level scenario is: another tree's text would run under this project's key and budget. A draft that uses
    one is invalid too (the copy `validate` checks it in leaves such links out)."""
    third, agent = tmp_path / "third" / "workflows", "---\nversion: 1\nname: {}\ndescription: d\nmodel: smart\n" \
                                                      "limits: {{budget_usd: 0.02}}\n{}---\nSENTINEL\n"
    for rel, text in {"scenarios/ext.yaml": "version: 1\nname: ext\ndescription: d\ncallable: true\nsteps:\n"
                                            "  - {id: w, ask: {agent: writer, prompt: SENTINEL}}\n",
                      "agents/extagent.md": agent.format("extagent", ""),
                      "skills/extskill/SKILL.md": "---\nname: extskill\ndescription: d\n---\nSENTINEL\n"}.items():
        (third / rel).parent.mkdir(parents=True, exist_ok=True)
        (third / rel).write_text(text)
    wf = root / "workflows"
    (wf / "skills").mkdir()
    for rel in ("scenarios/ext.yaml", "agents/extagent.md", "skills/extskill"):
        (wf / rel).symlink_to(third / rel)
    head = "version: 1\nname: {}\ndescription: d\nsteps:\n  - "
    drafts = [("scenario", "outer", head.format("outer") + "{id: c, call: {scenario: ext}}\n", "scenario 'ext'"),
              ("scenario", "useext", head.format("useext") + "{id: w, ask: {agent: extagent, prompt: hi}}\n",
               "agent 'extagent'"),
              ("agent", "skilled", agent.format("skilled", "skills: [extskill]\n"), "skill 'extskill'")]
    (wf / "scenarios" / "useskill.yaml").write_text(head.format("useskill") + "{id: w, ask: {agent: skilled, prompt: hi}}\n")
    server = build(allow="edit")
    for kind, name, text, what in drafts:
        r = ok(call(server, "validate", {"project": "lumen", "kind": kind, "name": name, "text": text}))
        assert r["valid"] is False and any(f"{what} does not exist" in e["message"] for e in r["added"]), r
        (wf / r["path"]).write_text(text)
        assert f"{what} does not exist" in err(call(server, "dry_run", {
            "project": "lumen", "scenario": "useskill" if kind == "agent" else name})), name
    assert run_dirs(root) == []


def test_wrong_types_pydantic_could_convert_are_refused(root):
    """The schema's types hold as written: "yes" or 1 is no boolean, "5" or true no integer — refused by the SDK
    before the tool runs (lax pydantic would have taken them)."""
    rid = "20260101-000000-demo-abcd"
    texts = list(map(err, calls(build(allow="read"), *[(tool, {"project": "lumen", **a}) for tool, a in (
        ("run_status", {"run_id": rid, "detail": "yes"}), ("run_status", {"run_id": rid, "detail": 1}),
        ("get_run_file", {"run_id": rid, "path": "summary.md", "offset": "5"}),
        ("get_run_file", {"run_id": rid, "path": "summary.md", "offset": True}),
        ("list_runs", {"limit": "2"}), ("wait_run", {"run_id": rid, "timeout_s": "1"}))],
        ("get_guide", {"topic": "start", "offset": "10"}), ("get_guide", {"topic": "start", "offset": 10.5}))))
    assert all(re.match(r"Error executing tool (\w+): 1 validation error for \1Arguments\n", t) for t in texts), texts
    # JSON Schema's integer is a number without a fraction: 2.0 is one (Gemini's clients send every number so)
    runs, guide, guide10 = map(ok, calls(build(allow="read"), ("list_runs", {"project": "lumen", "limit": 2.0}),
                                         ("get_guide", {"topic": "start", "offset": 10.0}),
                                         ("get_guide", {"topic": "start", "offset": 10})))
    assert runs["runs"] == [] and guide == guide10


def test_read_file(root):
    server = build(allow="read")
    agent, config = map(ok, calls(server, ("read_file", {"project": "lumen", "kind": "agent", "name": "writer"}),
                                  ("read_file", {"project": "lumen", "kind": "config"})))
    raw = (root / "workflows" / "agents" / "writer.md").read_bytes()
    assert agent | {"text": None} == {"project": "lumen", "kind": "agent", "name": "writer", "path": "agents/writer.md",
                                      "etag": hashlib.sha256(raw).hexdigest(), "text": None, "errors": []}
    assert agent["text"] == raw.decode()
    assert config["path"] == "config.yaml" and config["name"] is None and "api_key_env: OPENROUTER_API_KEY" in config["text"]
    (root / "workflows" / "agents" / "other.md").symlink_to(root / "workflows" / "scenarios" / "demo.yaml")
    texts = list(map(err, calls(server, ("read_file", {"project": "lumen", "kind": "mcp", "name": "x"}),
                                ("read_file", {"project": "lumen", "kind": "agent"}),
                                ("read_file", {"project": "lumen", "kind": "config", "name": "writer"}),
                                ("read_file", {"project": "lumen", "kind": "agent", "name": "other"}))))
    assert "validation error" in texts[0]
    assert texts[1].startswith("Error executing tool read_file: invalid: ") and texts[1] == texts[2]
    assert texts[3].startswith("Error executing tool read_file: not_found: agents/other.md: a link to another kind")


def test_names_too_long_for_the_file_system(root):
    """A name the pattern allows but the file system cannot hold names no file: not_found, not internal."""
    (root / "workflows" / "skills").mkdir()
    long = "a" * 300
    texts = map(err, calls(build(allow="read"), ("describe_scenario", {"project": "lumen", "scenario": long}),
                           *[("read_file", {"project": "lumen", "kind": k, "name": long}) for k in ("agent", "scenario", "skill")],
                           *[("validate", {"project": "lumen", "kind": k, "name": n, "text": "x"})
                             for k, n in (("agent", long), ("skill", long), ("scenario", "a" * 250))]))
    assert all(re.match(r"Error executing tool \w+: not_found: ", t) for t in texts)


def test_validate(root, tmp_path):
    wf = root / "workflows"

    def hashes():
        return {p: p.read_bytes() for p in wf.rglob("*") if p.is_file()}
    before = hashes()
    server = build(allow="read")
    disk, broken = map(ok, calls(server, ("validate", {"project": "lumen"}), (
        "validate", {"project": "lumen", "kind": "scenario", "name": "hello",
                     "text": "version: 1\nname: hello\nsteps:\n  - id: a\n    ask: {agent: writer, prompt: {{ x }}\n"})))
    assert disk == {"project": "lumen", "path": None, "valid": True, "errors": []}
    assert broken["valid"] is False and broken["path"] == "scenarios/hello.yaml"
    assert broken["added"] and broken["added"][0]["file"] == "scenarios/hello.yaml" and broken["added"][0]["line"] == 6
    assert hashes() == before
    # another file is broken: a correct draft adds nothing, the whole project still has errors
    (wf / "scenarios" / "unfinished.yaml").write_text("version: 1\nname: unfinished\n")
    agent = (wf / "agents" / "writer.md").read_text().replace("name: writer", "name: helper")
    draft, disk = map(ok, calls(server, ("validate", {"project": "lumen", "kind": "agent", "name": "helper", "text": agent}),
                                ("validate", {"project": "lumen"})))
    assert draft["valid"] is True and draft["added"] == [] and draft["errors"] and draft["path"] == "agents/helper.md"
    assert disk["valid"] is False and disk["errors"] and "added" not in disk
    assert not (wf / "agents" / "helper.md").exists()
    for args in ({"kind": "agent", "name": "helper"}, {"text": agent}, {"kind": "agent", "text": agent}):
        assert err(call(server, "validate", {"project": "lumen", **args})).startswith(
            "Error executing tool validate: invalid: ")
    # nine levels of nested anchors under 1 KB: refused before anything is built
    bomb = "version: 1\nname: bomb\na0: &a0 [x, x, x, x, x, x, x, x, x, x]\n" + "".join(
        f"a{i}: &a{i} [{', '.join([f'*a{i - 1}'] * 10)}]\n" for i in range(1, 9))
    assert len(bomb) < 1000
    start = time.monotonic()
    r = ok(call(server, "validate", {"project": "lumen", "kind": "scenario", "name": "bomb", "text": bomb}))
    assert time.monotonic() - start < 2
    assert r["valid"] is False and any("aliases expand to too many values" in e["message"] for e in r["added"])


def test_get_guide():
    server = build(allow="read")
    start = ok(call(server, "get_guide"))
    assert start["topic"] == "start" and "fake_run" in start["text"] and "run_scenario" in start["text"]
    assert {"start", "create", "run", "spec/scenario.md", "getting-started.md"} <= set(start["topics"])
    assert start["next_offset"] is None and start["total_chars"] == len(START)
    assert "name:" in ok(call(server, "get_guide", {"topic": "create"}))["text"]
    pages = [ok(call(server, "get_guide", {"topic": "spec/scenario.md"}))]
    assert pages[0]["next_offset"] == 40_000 and len(pages[0]["text"]) == 40_000 and "topics" not in pages[0]
    while pages[-1]["next_offset"] is not None:
        pages.append(ok(call(server, "get_guide", {"topic": "spec/scenario.md", "offset": pages[-1]["next_offset"]})))
    assert "".join(p["text"] for p in pages) == resources.read_doc("spec/scenario.md")
    assert '"$schema"' in ok(call(server, "get_guide", {"topic": "spec/schema/scenario.schema.json"}))["text"]
    for topic in ("../../pyproject.toml", "/etc/passwd", "spec/nope.md", "a" * 300, "spec/\0.md"):
        assert err(call(server, "get_guide", {"topic": topic})).startswith("Error executing tool get_guide: not_found: ")


def test_environment(root, tmp_path, monkeypatch):
    """Only the variables the project names come from its .env; never the current directory's .env."""
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    (cwd / ".env").write_text(f"OPENROUTER_API_KEY={KEY}\n")
    monkeypatch.chdir(cwd)
    server = build(allow="read")
    assert ok(call(server, "describe_project", {"project": "lumen"}))["env"]["OPENROUTER_API_KEY"] is False
    assert "OPENROUTER_API_KEY" not in os.environ
    (root / ".env").write_text(f"OPENROUTER_API_KEY={KEY}\nHTTPS_PROXY=http://127.0.0.1:9\n")
    assert ok(call(server, "describe_project", {"project": "lumen"}))["env"]["OPENROUTER_API_KEY"] is True
    assert os.environ["OPENROUTER_API_KEY"] == KEY and "HTTPS_PROXY" not in os.environ
    # core: the values for masking; a variable already set is never overwritten
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-the-environment")
    assert api.project_env(root) == [("OPENROUTER_API_KEY", "sk-from-the-environment"), ("OPENROUTER_API_KEY", KEY)]


def test_masking(root, monkeypatch, capsys):
    """A secret value of the addressed project never leaves the server: not in results, errors or stderr."""
    (root / ".env").write_text(f"OPENROUTER_API_KEY={KEY}\n")
    agent = root / "workflows" / "agents" / "writer.md"
    agent.write_text(agent.read_text() + f"Use the key {KEY}.\n")
    server = build(allow="read")
    results = calls(server, ("read_file", {"project": "lumen", "kind": "agent", "name": "writer"}),
                    ("describe_project", {"project": "lumen"}), ("list_scenarios", {"project": "lumen"}),
                    ("validate", {"project": "lumen", "kind": "agent", "name": "writer", "text": agent.read_text()}))
    assert "Use the key <secret: OPENROUTER_API_KEY>." in ok(results[0])["text"]
    # an unexpected exception: `internal`, its text and the traceback on stderr masked
    monkeypatch.setattr(api, "describe_scenario", lambda *_: (_ for _ in ()).throw(RuntimeError(f"boom {KEY}")))
    text = err(call(server, "describe_scenario", {"project": "lumen", "scenario": "demo"}))
    assert text == ("Error executing tool describe_scenario: internal: RuntimeError: boom <secret: OPENROUTER_API_KEY>")
    stderr = capsys.readouterr().err
    assert "Traceback" in stderr and "<secret: OPENROUTER_API_KEY>" in stderr
    for r in results:
        assert KEY not in json.dumps(r.structured_content) and KEY not in r.content[0].text
    assert KEY not in stderr


def test_stdio_stdout_is_protocol_only(root, registry):
    """A raw client: every stdout line is a JSON-RPC message; the start line is on stderr; closing stdin ends the
    server with 0. A secret pasted into a file reaches neither stdout nor stderr."""
    (root / ".env").write_text(f"OPENROUTER_API_KEY={KEY}\n")
    agent = root / "workflows" / "agents" / "writer.md"
    agent.write_text(agent.read_text() + f"Use the key {KEY}.\n")
    env = {"PATH": os.environ["PATH"], "HOME": str(root.parent), "AGENCAST_CONFIG_DIR": str(registry.parent)}
    p = subprocess.Popen([sys.executable, "-m", "agencast.cli", "mcp", "--allow", "read"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=root)
    watchdog = threading.Timer(60, p.kill)
    watchdog.start()
    try:
        def send(*messages):
            p.stdin.write("".join(json.dumps({"jsonrpc": "2.0", **m}) + "\n" for m in messages))
            p.stdin.flush()
        send({"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                                                          "clientInfo": {"name": "test", "version": "1"}}})
        lines = [p.stdout.readline()]
        send({"method": "notifications/initialized"}, {"id": 2, "method": "tools/list"},
             {"id": 3, "method": "tools/call", "params": {"name": "read_file", "arguments": {
                 "project": "lumen", "kind": "agent", "name": "writer"}}},
             {"id": 4, "method": "tools/call", "params": {"name": "describe_project", "arguments": {"project": "nope"}}})
        lines += [p.stdout.readline() for _ in range(3)]
        p.stdin.close()
        start = time.monotonic()
        assert p.wait(timeout=2) == 0 and time.monotonic() - start < 2
        lines += p.stdout.read().splitlines(keepends=True)
        stderr = p.stderr.read()
    finally:
        watchdog.cancel()
        p.kill()
        p.wait()
    messages = {m["id"]: m for m in map(json.loads, lines)}  # calls are answered as they finish
    assert all(m["jsonrpc"] == "2.0" for m in messages.values()) and sorted(messages) == [1, 2, 3, 4]
    assert messages[4]["result"]["isError"] is True and messages[3]["result"]["isError"] is False
    assert "<secret: OPENROUTER_API_KEY>" in messages[3]["result"]["structuredContent"]["text"]
    assert stderr.startswith("agencast mcp: stdio — registry mode (") and "allow read · input dirs: none" in stderr
    assert KEY not in "".join(lines) + stderr


@pytest.mark.parametrize("args", [["--project", "/nonexistent", "mcp"], ["mcp", "--input-dir", "/nonexistent"],
                                  ["mcp", "--fake", "/nonexistent/script.yaml"]])
def test_start_errors(args, capsys):
    assert main(args) == 2
    out, stderr = capsys.readouterr()
    assert out == "" and stderr.startswith("config: ") and "/nonexistent" in stderr


# --- runs (step S2) -----------------------------------------------------------------------------------------------

def workers(run_id: str) -> list[int]:
    out = subprocess.run(["pgrep", "-f", "--", f"--mcp-job {run_id}"], capture_output=True, text=True).stdout
    return [int(x) for x in out.split()]


def gone(run_id: str, timeout: float = 5.0) -> bool:
    """The worker of `run_id` has exited (after a run reached `done` it exits within moments)."""
    end = time.monotonic() + timeout
    while workers(run_id):
        if time.monotonic() > end:
            return False
        time.sleep(0.05)
    return True


def run_dirs(root: Path) -> list[str]:
    return sorted(d.name for d in (root / "runs").glob("*") if d.is_dir() and not d.name.startswith("_"))


def seed_catalog(root: Path):
    """The provider's model catalog as `run_scenario` validates against it — no network (providers.list_models)."""
    cfg = yaml.safe_load((root / "workflows" / "config.yaml").read_text())
    (root / "runs").mkdir(exist_ok=True)
    (root / "runs" / "_models.json").write_text(json.dumps({
        "base_url": cfg["openrouter"].get("base_url", "https://openrouter.ai/api/v1"), "fetched_at": time.time(),
        "data": [{"id": m["id"], "output_modalities": ["text"], "supported_parameters": ["response_format",
                                                                                       "structured_outputs"]}
                 for m in cfg["models"].values() if m.get("api", "chat") == "chat"]}))


def test_run_tools_by_level():
    """The run tools with the spec's descriptions; only run_scenario costs money and no run tool takes a provider;
    --allow read has none of them, a --fake server no live runs."""
    async def go(server, *calls_):
        async with Client(server) as c:
            return (await c.list_tools()).tools, [await c.call_tool(t, a) for t, a in calls_]

    # an argument a tool does not have is refused, not dropped: `provider: fake` would otherwise start a paid run
    tools, extra = anyio.run(go, build(), ("run_scenario", {"project": "lumen", "scenario": "demo", "provider": "fake"}),
                             ("dry_run", {"project": "lumen", "scenario": "demo", "callback_url": "https://example.invalid"}))
    assert {t.name for t in tools} == READ_TOOLS | RUN_TOOLS
    for t in tools:
        assert t.description == spec_description(t.name) and ("COSTS MONEY" in t.description) == (t.name == "run_scenario")
        assert (t.annotations.read_only_hint, t.annotations.open_world_hint) == (
            (False, True) if t.name in RUN_TOOLS else (True, False))
        assert t.input_schema["additionalProperties"] is False
    for text, (tool, name) in zip(map(err, extra), (("run_scenario", "provider"), ("dry_run", "callback_url"))):
        assert text.startswith(f"Error executing tool {tool}: 1 validation error for {tool}Arguments\n{name}\n")
        assert "Extra inputs are not permitted" in text
    for t in tools:
        if t.name in ("fake_run", "run_scenario"):
            assert set(t.input_schema["properties"]) == {"project", "scenario", "inputs"}
    tools, (unknown,) = anyio.run(go, build(allow="read"), ("run_scenario", {"project": "lumen", "scenario": "demo"}))
    assert {t.name for t in tools} == READ_TOOLS and "Unknown tool: run_scenario" in err(unknown)
    tools, (unknown, listed) = anyio.run(go, build(fake=""), ("run_scenario", {"project": "lumen", "scenario": "demo"}),
                                         ("list_projects", {}))
    assert {t.name for t in tools} == READ_TOOLS | {"dry_run", "fake_run"} and "Unknown tool: run_scenario" in err(unknown)
    assert ok(listed)["server"]["fake_only"] is True


def test_fake_run_in_a_worker(root, capsys):
    """fake_run returns at once with a queued run; the run executes in a worker process and ends with its record;
    the session's end stops nothing in the process — the next session plans a dry run."""
    server = build()

    async def first():
        async with Client(server) as c:
            start = time.monotonic()
            started = ok(await c.call_tool("fake_run", {"project": "lumen", "scenario": "demo"}))
            assert time.monotonic() - start < 2
            while not (done := ok(await c.call_tool("wait_run", {"project": "lumen", "run_id": started["run_id"]})))["done"]:
                pass
            return started, done, ok(await c.call_tool("list_runs", {"project": "lumen"}))

    started, done, listed = anyio.run(first)
    run_id = started["run_id"]
    assert RUN_ID.fullmatch(run_id) and started | {"run_id": None} == {
        "project": "lumen", "run_id": None, "scenario": "demo", "state": "queued", "status": "queued", "done": False,
        "fake": None, "started_at": None, "finished_at": None, "duration_s": None, "cost_usd": None,
        "current_step": None, "steps_done": None, "steps_total": None, "outputs": None, "output_files": {},
        "error": None, "warnings": [], "report_url": None, "run_dir": None}
    assert done["state"] == "succeeded" and done["outputs"] == {"text": "Fake response."} and done["fake"] is True
    assert done["output_files"] == {} and done["error"] is None and done["run_dir"] == str(root / "runs" / run_id)
    assert (root / "runs" / run_id / "callback.json").is_file() and (root / "runs" / "_mcp-slots").is_dir()
    assert not (root / "runs" / "_queue").exists()
    assert [r["run_id"] for r in listed["runs"]] == [run_id] and "outputs" not in listed["runs"][0]
    assert gone(run_id)
    assert f"run {run_id} started (project lumen, fake, worker " in capsys.readouterr().err
    assert engine._STOPPING is None
    planned = ok(call(server, "dry_run", {"project": "lumen", "scenario": "demo"}))
    assert planned["state"] == "dry_run"


def test_interrupted_while_held_reads_queued(root):
    """A run directory that reads `interrupted` (run.lock free, no events) while a worker holds the MCP slot naming
    the run is `queued` for every reader; once the slot is free it is `interrupted`."""
    run_id = "20261002-101512-demo-2cf1"
    (root / "runs" / run_id).mkdir(parents=True)
    (root / "runs" / run_id / "run.lock").touch()
    (root / "runs" / "_mcp-slots").mkdir()
    with open(root / "runs" / "_mcp-slots" / "1.lock", "w") as f:
        f.write(run_id)
        f.flush()
        fcntl.flock(f, fcntl.LOCK_EX)
        held, listed = map(ok, calls(build(allow="read"), ("run_status", {"project": "lumen", "run_id": run_id}),
                                     ("list_runs", {"project": "lumen", "scenario": "demo"})))
    assert (held["state"], held["done"], held["run_dir"]) == ("queued", False, str(root / "runs" / run_id))
    assert [(r["run_id"], r["state"]) for r in listed["runs"]] == [(run_id, "queued")]
    free = ok(call(build(allow="read"), "run_status", {"project": "lumen", "run_id": run_id}))
    assert (free["state"], free["done"]) == ("interrupted", True)
    assert err(call(build(allow="read"), "run_status", {"project": "lumen", "run_id": "20261002-101512-demo-0000"})
               ).startswith("Error executing tool run_status: not_found: run 20261002-101512-demo-0000 does not exist")


def test_errors_before_anything_starts(root, tmp_path, monkeypatch):
    """Every check runs in the tool call: nothing is recorded or started — wrong inputs, inputs too large, a live
    run without a key (also with a key in the server's current directory)."""
    seed_catalog(root)
    server, before = build(), set(mcp_server.STARTED)
    texts = list(map(err, calls(server, ("fake_run", {"project": "lumen", "scenario": "demo", "inputs": {"nope": 1}}),
                                ("fake_run", {"project": "lumen", "scenario": "demo",
                                              "inputs": {"topic": "x" * 1_000_001}}),
                                ("run_scenario", {"project": "lumen", "scenario": "demo"}),
                                ("dry_run", {"project": "lumen", "scenario": "demo", "inputs": {"nope": 1}}))))
    assert texts[0] == ("Error executing tool fake_run: config: scenario 'demo' or its inputs failed validation — the run "
                        "did not start\n- unknown input 'nope' (scenario has: topic)")
    assert texts[1].startswith("Error executing tool fake_run: invalid: inputs are 1,000,014 bytes as JSON — at most 1,000,000")
    assert texts[2].startswith("Error executing tool run_scenario: config: ") and \
        "missing environment variable OPENROUTER_API_KEY" in texts[2]
    assert "unknown input 'nope'" in texts[3]
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(f"OPENROUTER_API_KEY={KEY}\n")
    assert "missing environment variable OPENROUTER_API_KEY" in err(call(server, "run_scenario", {
        "project": "lumen", "scenario": "demo"}))
    assert run_dirs(root) == [] and set(mcp_server.STARTED) == before


def test_unquoted_template_is_a_validation_error(root):
    """`v: {{ x }}` unquoted (a mapping as a key) is an error with the file and line, not `internal`: a draft is
    invalid and refused, and with such a file on disk the project tools and read_file still answer, so a client can
    read the file, take its etag and fix it."""
    server = build(allow="edit")
    text = "version: 1\nname: broken\ndescription: d\nsteps:\n  - id: a\n    set:\n      v: {{ x }}\n"
    draft, refused = calls(server, ("validate", {"project": "lumen", "kind": "scenario", "name": "broken", "text": text}),
                           ("write_scenario", {"project": "lumen", "name": "broken", "text": text}))
    assert ok(draft)["added"][0]["line"] == 7 and "must be quoted" in ok(draft)["added"][0]["message"]
    assert err(refused).startswith("Error executing tool write_scenario: config: ")
    (root / "workflows" / "scenarios" / "broken.yaml").write_text(text)
    *_, scenario, file = map(ok, calls(server, *[(t, {"project": "lumen"}) for t in (
        "list_scenarios", "describe_project", "validate")], ("describe_scenario", {"project": "lumen", "scenario": "broken"}),
        ("read_file", {"project": "lumen", "kind": "scenario", "name": "broken"})))
    assert scenario["errors"][0]["line"] == 7 and file["text"] == text and file["etag"]


def test_dry_run(root):
    server, before = build(), set(mcp_server.STARTED)
    r = ok(call(server, "dry_run", {"project": "lumen", "scenario": "demo", "inputs": {"topic": "tea"}}))
    assert RUN_ID.fullmatch(r["run_id"]) and r["state"] == "dry_run" and r["plan"].startswith("# Plan: demo")
    assert r["next_offset"] is None and r["run_dir"] == str(root / "runs" / r["run_id"])
    assert sorted(p.name for p in (root / "runs" / r["run_id"]).iterdir()) == ["inputs.json", "plan.md"]
    assert [f.read_text() for f in (root / "runs" / "_mcp-slots").glob("*.lock")] == [""]
    assert set(mcp_server.STARTED) == before


def test_scenario_link_and_trust(root, wf, tmp_path):
    """No run tool plans or starts a scenario that is a link into another tree (its MCP servers would start under
    this project's trust), or one whose MCP servers an untrusted project names: no process, no worker."""
    marker, before = tmp_path / "server-started", set(mcp_server.STARTED)
    (wf / "config.yaml").write_text(golden_config())
    marked(wf, marker)  # tree B, not registered: scenario `test` with a task step whose server leaves the marker
    (root / "workflows" / "scenarios" / "evil.yaml").symlink_to(wf / "scenarios" / "test.yaml")
    api.add_project(wf.parent, "foreign", trusted=False)
    texts = list(map(err, calls(build(), *[(t, {"project": "lumen", "scenario": "evil"}) for t in ("dry_run", "fake_run")],
                                *[(t, {"project": "foreign", "scenario": "test"}) for t in ("dry_run", "fake_run")])))
    assert all(t.startswith(f"Error executing tool {n}: not_found: scenario 'evil' does not exist")
               for t, n in zip(texts[:2], ("dry_run", "fake_run")))
    assert all(t.startswith(f"Error executing tool {n}: config: ") and "are disabled" in t
               for t, n in zip(texts[2:], ("dry_run", "fake_run")))
    assert not marker.exists() and not (wf.parent / "runs").exists() and run_dirs(root) == []
    assert set(mcp_server.STARTED) == before


# --- results and files (step S3) ---------------------------------------------------------------------------------

def finished(server, project="lumen", scenario="demo", inputs=None):
    """Start one fake worker, wait for its record, then reap it."""
    started = ok(call(server, "fake_run", {"project": project, "scenario": scenario, "inputs": inputs or {}}))
    done = ok(call(server, "wait_run", {"project": project, "run_id": started["run_id"], "timeout_s": 50}))
    assert done["done"] and gone(started["run_id"])
    return started["run_id"], done


def test_run_status_and_text_files(root):
    """Detailed records list bounded files and safely page, mask and reject run files."""
    (root / ".env").write_text(f"OPENROUTER_API_KEY={KEY}\n")
    run_id, plain = finished(build())
    d = root / "runs" / run_id
    (d / "work").mkdir()
    long = "ž" * 39_990 + KEY + "ž" * 55_000  # the key across the first page boundary: masked before paging
    (d / "work" / "long.txt").write_text(long)
    (d / "work" / "leak.txt").write_text(KEY)
    (d / "work" / "binary.bin").write_bytes(b"x" * 10_000_001)
    (d / "escape").symlink_to(root / "workflows" / "config.yaml")
    (d / "loop").symlink_to(d / "loop")
    for n in range(501):
        (d / "work" / f"extra-{n:03}.txt").touch()
    server = build()
    detail = ok(call(server, "run_status", {"project": "lumen", "run_id": run_id, "detail": True}))
    assert "steps" not in plain and "files" not in plain and "outputs_file" not in plain
    assert [(s["step"], s["dir"], set(s)) for s in detail["steps"]] == [
        ("write", "steps/01-write", {"step", "kind", "status", "dir", "duration_s", "cost_usd", "error"}),
        ("result", "steps/02-result", {"step", "kind", "status", "dir", "duration_s", "cost_usd", "error"})]
    assert {"summary.md", "callback.json"} <= set(detail["files"]) and len(detail["files"]) == 500
    assert detail["files_truncated"] is True
    assert ok(call(server, "get_run_file", {"project": "lumen", "run_id": run_id,
                                              "path": f"{detail['steps'][0]['dir']}/output.json"}))["kind"] == "text"
    summary = ok(call(server, "get_run_file", {"project": "lumen", "run_id": run_id, "path": "summary.md"}))
    assert summary["text"].startswith("# demo — success") and summary["file"] == str(d / "summary.md") \
        and summary["bytes"] == (d / "summary.md").stat().st_size
    pages = [ok(call(server, "get_run_file", {"project": "lumen", "run_id": run_id, "path": "work/long.txt"}))]
    while pages[-1]["next_offset"] is not None:
        pages.append(ok(call(server, "get_run_file", {"project": "lumen", "run_id": run_id, "path": "work/long.txt",
                                                        "offset": pages[-1]["next_offset"]})))
    assert "".join(p["text"] for p in pages) == long.replace(KEY, "<secret: OPENROUTER_API_KEY>") and len(pages) == 3
    assert "<secret: OPENROUTER_API_KEY>" in ok(call(server, "get_run_file", {
        "project": "lumen", "run_id": run_id, "path": "work/leak.txt"}))["text"]
    assert ok(call(server, "get_run_file", {"project": "lumen", "run_id": run_id, "path": "work/binary.bin"}))["kind"] == "binary"
    for path in ("../../workflows/config.yaml", str(root / "workflows" / "config.yaml"), "escape", "loop", "work",
                 "a\0b", "x" * 5000):  # a NUL byte and a name too long for the file system: no such file
        assert err(call(server, "get_run_file", {"project": "lumen", "run_id": run_id, "path": path})).startswith(
            "Error executing tool get_run_file: not_found: ")
    assert err(call(server, "get_run_file", {"project": "lumen", "run_id": "20261002-101512-demo-0000",
                                              "path": "summary.md"})).startswith("Error executing tool get_run_file: not_found: ")


def test_image_output_files_are_inline_when_small(root):
    """A generated image is mapped as an output and reads inline, with large images and secrets withheld."""
    (root / ".env").write_text(f"OPENROUTER_API_KEY={KEY}\n")
    (root / "workflows" / "scenarios" / "picture.yaml").write_text("""\
version: 1
name: picture
description: One image
inputs: {prompt: {type: string, default: a cup}}
outputs: {image: {type: file}}
steps:
  - id: photo
    image: {model: gemini-image, prompt: "{{ inputs.prompt }}"}
  - id: out
    output: {image: "{{ steps.photo.file }}"}
""")
    run_id, done = finished(build(), scenario="picture")
    d, path = root / "runs" / run_id, done["output_files"]["image"]
    assert path in ok(call(build(), "run_status", {"project": "lumen", "run_id": run_id, "detail": True}))["files"]
    image = call(build(), "get_run_file", {"project": "lumen", "run_id": run_id, "path": path})
    body = ok(image)
    assert (body["kind"], body["format"], body["inline"], len(image.content)) == ("image", "png", True, 2)
    assert image.content[1].type == "image" and image.content[1].mime_type == "image/png" and \
        base64.b64decode(image.content[1].data) == (d / path).read_bytes()
    (d / "work").mkdir()
    (d / "work" / "big.png").write_bytes(png(4, 3) + b"\0" * 1_500_000)
    (d / "work" / "leak.png").write_bytes(png(4, 3) + KEY.encode())
    big = call(build(), "get_run_file", {"project": "lumen", "run_id": run_id, "path": "work/big.png"})
    big_body = ok(big)
    assert len(big.content) == 1 and big_body["file"] == str(d / "work" / "big.png") and big_body["inline"] is False
    leaked = call(build(), "get_run_file", {"project": "lumen", "run_id": run_id, "path": "work/leak.png"})
    assert KEY.encode() not in base64.b64decode(leaked.content[1].data)


def test_registry_masks_the_addressed_project(root, tmp_path, monkeypatch):
    """Registry mode: lumen's .env sets OPENROUTER_API_KEY in the process first; beta's own value is still masked
    in beta's files."""
    beta, beta_key = tmp_path / "beta", "sk-beta-abcdefgh12345678"
    assert main(["new", "project", str(beta)]) == 0
    (root / ".env").write_text(f"OPENROUTER_API_KEY={KEY}\n")
    (beta / ".env").write_text(f"OPENROUTER_API_KEY={beta_key}\n")
    run_id, _ = finished(build(), project="beta")
    (beta / "runs" / run_id / "work").mkdir()
    (beta / "runs" / run_id / "work" / "leak.txt").write_text(f"key: {beta_key}")
    monkeypatch.delenv("OPENROUTER_API_KEY")  # as in a new server: nothing loaded yet
    _, leaked = calls(build(), ("describe_project", {"project": "lumen"}),
                      ("get_run_file", {"project": "beta", "run_id": run_id, "path": "work/leak.txt"}))
    assert os.environ["OPENROUTER_API_KEY"] == KEY and ok(leaked)["text"] == "key: <secret: OPENROUTER_API_KEY>"


def test_file_inputs_are_scoped_and_cleaned(root, tmp_path, monkeypatch):
    """File inputs only from an allowed directory, read into a copy that the core checks under the caller's path;
    no copy outlives a run, a refusal (`busy` too) or a dry run."""
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))  # where this process puts its copies

    def fake_run(server, photo, tool="fake_run"):
        return call(server, tool, {"project": "lumen", "scenario": "demo", "inputs": {"photo": photo}})

    demo = root / "workflows" / "scenarios" / "demo.yaml"
    demo.write_text(demo.read_text().replace("inputs:\n", "inputs:\n  photo: { type: file, required: true }\n"))
    pictures, outside = tmp_path / "pictures", tmp_path / "outside.png"
    pictures.mkdir()
    photo = pictures / "photo.png"
    photo.write_bytes(png(4, 3))
    outside.write_bytes(png(4, 3))
    text = err(fake_run(build(), str(photo)))
    assert text.startswith("Error executing tool fake_run: denied: input 'photo' has type file") and "--input-dir" in text
    assert run_dirs(root) == []
    server = build(input_dirs=[pictures.resolve()])
    run_id, done = finished(server, inputs={"photo": str(photo)})
    assert done["state"] == "succeeded" and (root / "runs" / run_id / "inputs" / "photo.png").read_bytes() == photo.read_bytes()
    assert "inputs/photo.png" in ok(call(server, "run_status", {"project": "lumen", "run_id": run_id, "detail": True}))["files"]
    (pictures / "escape.png").symlink_to(outside)
    (pictures / "fake.png").write_text("not an image")
    for loop in (pictures / "loop.png", tmp_path / "loop.png"):  # Path.resolve() raises RuntimeError on a loop
        loop.symlink_to(loop)
    for tool in ("fake_run", "dry_run"):
        text = err(fake_run(server, str(pictures / "loop.png"), tool))
        assert text.startswith(f"Error executing tool {tool}: config: ") and \
            f"- input 'photo': file {pictures / 'loop.png'} does not exist" in text, text
    for path in (str(outside), str(pictures / "escape.png"), str(tmp_path / "loop.png")):
        assert err(fake_run(server, path)).startswith(f"Error executing tool fake_run: denied: input 'photo': {path} is "
                                                      f"not inside an allowed directory ({pictures.resolve()})")
    text = err(fake_run(server, str(pictures / "fake.png")))
    assert text.startswith("Error executing tool fake_run: config: ") and \
        f"file {pictures / 'fake.png'} is not a supported image" in text and "agencast-mcp-" not in text
    assert err(fake_run(server, "photo.png")).startswith("Error executing tool fake_run: invalid: input 'photo': photo.png")
    locked = pictures / "locked.png"
    locked.write_bytes(png(4, 3))
    locked.chmod(0)
    for path, why in ((f"{pictures}/a\0.png", "embedded null byte"), (f"/a\0/{pictures}", "embedded null byte"),
                      (f"{pictures}/{'x' * 300}.png", "File name too long"),
                      *[(str(locked), "Permission denied")] * (not os.access(locked, os.R_OK))):  # root reads it
        for tool in ("fake_run", "dry_run"):  # the file system's refusal is `config` too, not internal
            text = err(fake_run(server, path, tool))
            assert text.startswith(f"Error executing tool {tool}: config: ") and \
                f"- input 'photo': file {path} cannot be read ({why})" in text, text
    assert ok(fake_run(server, str(photo), "dry_run"))["state"] == "dry_run"
    slots, locks = root / "runs" / "_mcp-slots", []
    try:
        for n in range(1, 5):
            locks.append(open(slots / f"{n}.lock", "w"))
            fcntl.flock(locks[-1], fcntl.LOCK_EX)
        for tool in ("fake_run", "dry_run"):
            assert err(fake_run(server, str(photo), tool)).startswith(f"Error executing tool {tool}: busy: ")
    finally:
        for f in locks:
            f.close()
    assert list(tmp.iterdir()) == [] and not mcp_server.OWNED and len(run_dirs(root)) == 2


def test_large_outputs_use_callback_file(root, tmp_path):
    """Large fake output is omitted from run objects in favor of callback.json."""
    script = tmp_path / "large.yaml"
    script.write_text("write: [{text: '" + "x" * 45_000 + "'}]\n")
    run_id, done = finished(build(fake=str(script)))
    status = ok(call(build(fake=str(script)), "run_status", {"project": "lumen", "run_id": run_id}))
    assert done["outputs"] is None and done["outputs_file"] == status["outputs_file"] == "callback.json"


# --- editing (step S4) -------------------------------------------------------------------------------------------

AGENT = """\
---
version: 1
name: hello
description: Writes a hello
model: smart
limits: {budget_usd: 0.01}
---
Write a friendly hello.
"""
SCENARIO = """\
version: 1
name: hello
description: Writes a hello
outputs: {text: {type: string}}
steps:
  - id: write
    ask: {agent: hello, prompt: "Say hello."}
  - id: out
    output: {text: "{{ steps.write.text }}"}
"""


def test_write_tools(root, registry, tmp_path):
    """The edit-level wrappers have narrow paths, etag-only replacement and the core's no-new-errors rule."""
    server = build(allow="edit")
    tools = {t.name: t for t in anyio.run(lambda: _tools(server))}
    assert set(tools) == READ_TOOLS | RUN_TOOLS | {"write_agent", "write_scenario", "write_skill"}
    for name in ("write_agent", "write_scenario", "write_skill"):
        assert tools[name].description == spec_description(name)
        assert tools[name].annotations.destructive_hint is True
        assert {k: tools[name].input_schema["properties"][k].get("description", "")
                for k in ("name", "text", "etag")} == {
            "name": "the file name without extension; the `name:` field inside the text must equal it",
            "text": "the whole file",
            "etag": "`null` = create a **new** file; to replace a file, the `etag` from `read_file` (or from the previous `write_*`)"}
    assert "Unknown tool: write_scenario" in err(call(build(), "write_scenario", {
        "project": "lumen", "name": "hello", "text": SCENARIO}))

    agent = ok(call(server, "write_agent", {"project": "lumen", "name": "hello", "text": AGENT}))
    scenario = ok(call(server, "write_scenario", {"project": "lumen", "name": "hello", "text": SCENARIO}))
    skill_text = "---\nname: helper\ndescription: Helps writing\n---\nUse short answers.\n"
    skill = ok(call(server, "write_skill", {"project": "lumen", "name": "helper", "text": skill_text}))
    for item, path, text in ((agent, root / "workflows" / "agents" / "hello.md", AGENT),
                             (scenario, root / "workflows" / "scenarios" / "hello.yaml", SCENARIO),
                             (skill, root / "workflows" / "skills" / "helper" / "SKILL.md", skill_text)):
        assert item["created"] is True and item["etag"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert path.read_text() == text

    exists = err(call(server, "write_scenario", {"project": "lumen", "name": "hello", "text": SCENARIO}))
    assert "conflict:" in exists and "already exists" in exists and scenario["etag"] not in exists
    read = ok(call(server, "read_file", {"project": "lumen", "kind": "scenario", "name": "hello"}))
    changed = SCENARIO.replace("Say hello.", "Say a warm hello.")
    replaced = ok(call(server, "write_scenario", {"project": "lumen", "name": "hello", "text": changed,
                                                     "etag": read["etag"]}))
    assert replaced["created"] is False and (root / "workflows" / "scenarios" / "hello.yaml").read_text() == changed
    stale = err(call(server, "write_scenario", {"project": "lumen", "name": "hello", "text": SCENARIO,
                                                   "etag": read["etag"]}))
    assert "changed since you read it" in stale and replaced["etag"] not in stale
    disk = ok(call(server, "read_file", {"project": "lumen", "kind": "scenario", "name": "hello"}))
    (root / "workflows" / "scenarios" / "hello.yaml").write_text(changed.replace("warm", "disk"))
    changed_on_disk = err(call(server, "write_scenario", {"project": "lumen", "name": "hello", "text": changed,
                                                             "etag": disk["etag"]}))
    assert "changed since you read it" in changed_on_disk and disk["etag"] not in changed_on_disk
    missing = err(call(server, "write_scenario", {"project": "lumen", "name": "missing", "text": SCENARIO,
                                                     "etag": read["etag"]}))
    assert "does not exist" in missing and read["etag"] not in missing

    broken = "version: 1\nname: bad\nsteps: [\n"
    text = err(call(server, "write_scenario", {"project": "lumen", "name": "bad", "text": broken}))
    assert "config: change failed validation; nothing was written" in text and "line" in text
    assert not (root / "workflows" / "scenarios" / "bad.yaml").exists()
    assert not (root / "workflows" / "scenarios" / ".bad.yaml.tmp").exists()
    unknown = SCENARIO.replace("name: hello", "name: stranger").replace("agent: hello", "agent: unknown")
    assert "config:" in err(call(server, "write_scenario", {"project": "lumen", "name": "stranger", "text": unknown}))
    named = AGENT.replace("name: hello", "name: unknown")
    ok(call(server, "write_agent", {"project": "lumen", "name": "unknown", "text": named}))
    assert ok(call(server, "write_scenario", {"project": "lumen", "name": "stranger", "text": unknown}))["created"]

    bomb = "version: 1\nname: bomb\na0: &a0 [x, x, x, x, x, x, x, x, x, x]\n" + "".join(
        f"a{i}: &a{i} [{', '.join([f'*a{i - 1}'] * 10)}]\n" for i in range(1, 9))
    start = time.monotonic()
    bomb_error = err(call(server, "write_scenario", {"project": "lumen", "name": "bomb", "text": bomb}))
    assert time.monotonic() - start < 2 and "aliases expand to too many values" in bomb_error
    assert not (root / "workflows" / "scenarios" / "bomb.yaml").exists()

    protected = [root / "workflows" / "config.yaml", root / "workflows" / "mcp.yaml", root / ".env", registry]
    before = {p: p.read_bytes() if p.exists() else None for p in protected}
    assert "validation error" in err(call(server, "write_scenario", {"project": "lumen", "name": "Config", "text": SCENARIO}))
    assert "validation error" in err(call(server, "write_scenario", {"project": "lumen", "name": "../x", "text": SCENARIO}))
    config = SCENARIO.replace("name: hello", "name: config")
    assert ok(call(server, "write_scenario", {"project": "lumen", "name": "config", "text": config}))["path"] == "scenarios/config.yaml"
    assert {p: p.read_bytes() if p.exists() else None for p in protected} == before

    (root / "workflows" / "scenarios" / "owner-broken.yaml").write_text("version: 1\nname: owner-broken\n")
    later = ok(call(server, "write_agent", {"project": "lumen", "name": "later",
                                              "text": AGENT.replace("hello", "later")}))
    assert later["created"] and later["errors"]  # errors the owner already had do not block a correct draft

    tmp_target = tmp_path / "tmp-target"
    tmp_target.write_text("unchanged\n")
    (root / "workflows" / "scenarios" / ".linked.yaml.tmp").symlink_to(tmp_target)
    linked = SCENARIO.replace("name: hello", "name: linked")
    assert ok(call(server, "write_scenario", {"project": "lumen", "name": "linked", "text": linked}))["created"]
    assert tmp_target.read_text() == "unchanged\n"
    target = tmp_path / "outside.yaml"
    target.write_text("outside\n")
    (root / "workflows" / "scenarios" / "evil.yaml").symlink_to(target)
    assert "not_found:" in err(call(server, "write_scenario", {"project": "lumen", "name": "evil", "text": SCENARIO}))
    assert target.read_text() == "outside\n"
    agents, outside_agents = root / "workflows" / "agents", tmp_path / "outside-agents"
    agents.rename(tmp_path / "own-agents")
    outside_agents.mkdir()
    (outside_agents / "linked.md").write_text("outside\n")
    agents.symlink_to(outside_agents, target_is_directory=True)
    assert "not_found:" in err(call(server, "write_agent", {"project": "lumen", "name": "linked", "text": AGENT}))
    assert (outside_agents / "linked.md").read_text() == "outside\n"


async def _tools(server):
    async with Client(server) as client:
        return (await client.list_tools()).tools


def test_write_keeps_running_snapshot(root, tmp_path):
    """The worker parses its scenario once: an edit after it started cannot change its run snapshot."""
    old = (root / "workflows" / "scenarios" / "demo.yaml").read_text()
    script = tmp_path / "slow.yaml"
    script.write_text("write: [{sleep: 1, text: slow answer}]\n")
    server = build(allow="edit", fake=str(script))
    started = ok(call(server, "fake_run", {"project": "lumen", "scenario": "demo"}))
    run_id = started["run_id"]
    end = time.monotonic() + 3
    while time.monotonic() < end:
        state = ok(call(server, "run_status", {"project": "lumen", "run_id": run_id}))["state"]
        if state == "running":
            break
        time.sleep(.03)
    assert state == "running"
    read = ok(call(server, "read_file", {"project": "lumen", "kind": "scenario", "name": "demo"}))
    new = old.replace("Write two sentences", "Write exactly one sentence")
    ok(call(server, "write_scenario", {"project": "lumen", "name": "demo", "text": new, "etag": read["etag"]}))
    done = ok(call(server, "wait_run", {"project": "lumen", "run_id": run_id, "timeout_s": 5}))
    assert done["state"] == "succeeded"
    assert (root / "runs" / run_id / "scenario" / "demo.yaml").read_text() == old


def test_write_keeps_queued_snapshot(root):
    """The worker's loaded text, not a later edit while it waits for an engine slot, is snapshotted."""
    config = root / "workflows" / "config.yaml"
    data = yaml.safe_load(config.read_text())
    data.setdefault("limits", {})["max_parallel_runs"] = 1
    config.write_text(yaml.safe_dump(data, sort_keys=False))
    slot = root / "runs" / "_slots" / "1.lock"
    slot.parent.mkdir(parents=True)
    old = (root / "workflows" / "scenarios" / "demo.yaml").read_text()
    new = old.replace("id: write", "id: compose").replace("steps.write.text", "steps.compose.text")
    fd = os.open(slot, os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    server = build(allow="edit")
    try:
        started = ok(call(server, "fake_run", {"project": "lumen", "scenario": "demo"}))
        run_id = started["run_id"]
        end = time.monotonic() + 3
        while time.monotonic() < end:
            pids = workers(run_id)
            if pids and b"waiting for a free slot" in Path(f"/proc/{pids[0]}/fd/2").read_bytes():
                break  # `api.load` happened before engine.run_scenario waited for the slot
            time.sleep(.03)
        else:
            pytest.fail("worker did not wait for the engine slot")
        queued = ok(call(server, "run_status", {"project": "lumen", "run_id": run_id}))
        assert queued["state"] == "queued" and queued["run_dir"] is None
        read = ok(call(server, "read_file", {"project": "lumen", "kind": "scenario", "name": "demo"}))
        ok(call(server, "write_scenario", {"project": "lumen", "name": "demo", "text": new, "etag": read["etag"]}))
    finally:
        os.close(fd)
    done = ok(call(server, "wait_run", {"project": "lumen", "run_id": run_id, "timeout_s": 5}))
    assert done["state"] == "succeeded"
    assert (root / "runs" / run_id / "scenario" / "demo.yaml").read_text() == old
    assert gone(run_id)


def test_edit_stdio_build_flow_survives_disconnect(root, registry):
    """The documented build flow works through tools alone; EOF after fake_run leaves its worker to finish."""
    env = {"PATH": os.environ["PATH"], "HOME": str(root.parent), "AGENCAST_CONFIG_DIR": str(registry.parent)}
    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "agencast.cli", "--project", str(root), "mcp", "--allow", "edit"],
                                   env=env, cwd=root)
    agent = AGENT.replace("hello", "made")
    scenario = SCENARIO.replace("hello", "made")

    async def build_then_disconnect():
        async with Client(params, mode="legacy") as client:
            assert "name:" in ok(await client.call_tool("get_guide", {"topic": "create"}))["text"]
            draft = ok(await client.call_tool("validate", {"project": "lumen", "kind": "agent", "name": "made",
                                                            "text": agent}))
            assert draft["valid"] and draft["added"] == []
            ok(await client.call_tool("write_agent", {"project": "lumen", "name": "made", "text": agent}))
            ok(await client.call_tool("write_scenario", {"project": "lumen", "name": "made", "text": scenario}))
            assert ok(await client.call_tool("dry_run", {"project": "lumen", "scenario": "made"}))["state"] == "dry_run"
            return ok(await client.call_tool("fake_run", {"project": "lumen", "scenario": "made"}))["run_id"]

    run_id = anyio.run(build_then_disconnect)

    async def finish_in_new_session():
        async with Client(params, mode="legacy") as client:
            assert run_id in {r["run_id"] for r in ok(await client.call_tool("list_runs", {
                "project": "lumen", "scenario": "made"}))["runs"]}
            done = ok(await client.call_tool("wait_run", {"project": "lumen", "run_id": run_id, "timeout_s": 10}))
            summary = ok(await client.call_tool("get_run_file", {"project": "lumen", "run_id": run_id,
                                                                    "path": "summary.md"}))
            return done, summary

    done, summary = anyio.run(finish_in_new_session)
    assert done["state"] == "succeeded" and summary["kind"] == "text"
    assert gone(run_id)


# --- documentation, client setup and the whole surface (step S6) --------------------------------------------------

ALL_TOOLS = READ_TOOLS | RUN_TOOLS | {"write_scenario", "write_agent", "write_skill"}
REPO = Path(__file__).resolve().parents[2]
# objects whose keys the spec's examples document; any other object in a result is data (models, inputs, fields…)
SHAPED = {"server", "projects", "agents", "scenarios", "steps", "runs"}
PICTURE = """\
version: 1
name: picture
description: One image
outputs: {image: {type: file}}
steps:
  - id: photo
    image: {model: gemini-image, prompt: a cup}
  - id: out
    output: {image: "{{ steps.photo.file }}"}
"""


def spec_sections() -> dict[str, str]:
    """The section of each tool; a section titled with several tools serves each of them."""
    out = {}
    for part in SPEC.split("\n### ")[1:]:
        title, _, body = part.partition("\n")
        for tool in re.findall(r"`(\w+)`", title):
            out[tool] = body.split("\n## ")[0]
    return out


def argument_rows(section: str) -> list[list[str]]:
    """The cells of the argument table of a tool section (`\\|` inside a cell is a literal bar)."""
    m = re.search(r"\n\| Argument \|.*\n\|[-|]+\|\n((?:\|.*\n)*)", section)
    return [[c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row)[1:-1]]
            for row in m[1].splitlines()] if m else []


def spec_examples() -> list[tuple[str, dict, dict | str]]:
    """Every example call of the spec, `// <tool> {arguments}` (a comment line indented further continues it):
    (tool, arguments, the documented result object — or, for a call marked `→ isError`, the documented text)."""
    out, decode = [], json.JSONDecoder().raw_decode
    for block in re.findall(r"```\w*\n(.*?)```", SPEC, re.S):
        found = []
        for line in block.splitlines():
            if m := re.match(r"// (\w+) (\{.*)", line):
                found.append([m[1], m[2], []])
            elif line.startswith("//  ") and found and not found[-1][2]:
                found[-1][1] += " " + line[2:].strip()
            elif not line.startswith("//") and found:
                found[-1][2].append(line)
        for tool, text, lines in found:
            args, end = decode(text)
            result = "\n".join(lines).strip()
            out.append((tool, args, result if "isError" in text[end:] else json.loads(result)))
    return out


def missing_keys(got, documented, at="") -> list[str]:
    """Where a result's keys differ from the documented example's: the top level, the shaped objects (SHAPED), and
    list items position by position."""
    if isinstance(documented, dict) and isinstance(got, dict):
        diff = [f"{at or 'result'}: {sorted(set(got) ^ set(documented))}"] if set(got) != set(documented) else []
        return diff + [d for k in SHAPED & got.keys() & documented.keys() for d in missing_keys(got[k], documented[k], f"{at}.{k}")]
    if isinstance(documented, list) and isinstance(got, list):
        return [d for i, (g, e) in enumerate(zip(got, documented)) for d in missing_keys(g, e, f"{at}[{i}]")]
    return []


def test_help(capsys):
    """`agencast --help` lists mcp; `mcp --help` its options; the worker's --mcp-job is not in `run --help`."""
    texts = []
    for args in (["--help"], ["mcp", "--help"], ["run", "--help"]):
        with pytest.raises(SystemExit) as e:
            main(args)
        assert e.value.code == 0
        texts.append(capsys.readouterr().out)
    assert re.search(r"\n    mcp +MCP server", texts[0])
    assert all(o in texts[1] for o in ("--allow", "--input-dir", "--fake", "--http", "--host", "--port", "--allow-host"))
    assert "--mcp-job" not in texts[2] and "--dry-run" in texts[2]


def test_the_spec_is_bundled(capsys):
    """`agencast docs` lists the spec of the server, and get_guide serves it whole."""
    assert main(["docs"]) == 0 and "spec/mcp-server.md" in capsys.readouterr().out.split()
    server, pages = build(allow="read"), [{"next_offset": 0}]
    while pages[-1]["next_offset"] is not None:
        pages.append(ok(call(server, "get_guide", {"topic": "spec/mcp-server.md", "offset": pages[-1]["next_offset"]})))
    assert "".join(p["text"] for p in pages[1:]) == SPEC


def test_tools_match_the_spec():
    """tools/list of an `--allow edit` server is the spec's: all 17 Description strings, and per argument of each
    tool's table its name and order, required, default, enum, bounds and description (the last column)."""
    tools, sections = {t.name: t for t in anyio.run(_tools, build(allow="edit"))}, spec_sections()
    assert set(tools) == set(sections) == ALL_TOOLS and len(tools) == 17
    assert "COSTS MONEY" in tools["run_scenario"].description
    # no Markdown link: `[x](scenario.md)` means something inside the spec only, a model cannot follow it
    assert "](" not in json.dumps([[t.description, t.input_schema] for t in tools.values()])
    assert all("COSTS MONEY" not in t.description and "Free" in t.description
               for name, t in tools.items() if name != "run_scenario")
    for name, t in tools.items():
        assert t.description == spec_description(name), name
        rows, props = argument_rows(sections[name]), t.input_schema["properties"]
        assert [r[0].strip("`") for r in rows] == list(props), name
        for r in rows:
            arg, kind, text = r[0].strip("`"), r[1], r[-1]
            p = props[arg] | next((s for s in props[arg].get("anyOf", []) if s.get("type") != "null"), {})
            where = f"{name}.{arg}"
            assert (r[2] == "yes") == (arg in t.input_schema.get("required", [])), where
            assert p.get("description", "") == ("Project name from list_projects." if arg == "project" else text), where
            if len(r) == 5 and r[3]:  # the Default column; `all` (no filter) is null
                assert p.get("default") == (None if r[3] == "all" else json.loads(r[3].strip("`"))), where
            if values := re.findall(r'`"(\w+)"`', kind):
                assert set(p["enum"]) == set(values), where
            if m := re.search(r"(\d+)–(\d+)", kind):
                assert (p["minimum"], p["maximum"]) == (int(m[1]), int(m[2])), where
            if m := re.search(r"≥ (\d+)", kind):
                assert p["minimum"] == int(m[1]), where
            if m := re.search(r"≤ ([\d,]+) characters", kind):
                assert p["maxLength"] == int(m[1].replace(",", "")), where
            assert ("pattern" in p) == ("(name)" in kind or "(run id)" in kind), where


def test_mcp_leftovers_are_session_scoped(tmp_path):
    """A different process's input copy does not make this pytest session fail its cleanup check."""
    foreign = Path(tempfile.mkdtemp(prefix="agencast-mcp-"))
    own = tmp_path / "agencast-mcp-own"
    own.mkdir()
    try:
        found = mcp_leftovers(tmp_path)
        assert f"temp dir {own}" in found
        assert f"temp dir {foreign}" not in found
    finally:
        shutil.rmtree(own)
        shutil.rmtree(foreign)


async def sweep(c, skip=()) -> list[tuple[str, dict | str, Any]]:
    """Every example call of the spec through client `c` on a fresh `agencast new project` project `lumen` (with the
    `picture` scenario and a seeded model catalog), in the spec's order: the example's run ids and image path are
    those of the runs this sweep starts, the truncated text of write_scenario a whole file. write_agent and
    write_skill, which have no example, return what write_scenario documents; tools in `skip` are not called.
    → (tool, documented, result)."""
    async def finished(run_id):
        while not (await c.call_tool("wait_run", {"project": "lumen", "run_id": run_id, "timeout_s": 50})
                   ).structured_content["done"]:
            pass
    picture = (await c.call_tool("fake_run", {"project": "lumen", "scenario": "picture"})).structured_content["run_id"]
    await finished(picture)
    image = (await c.call_tool("run_status", {"project": "lumen", "run_id": picture})).structured_content
    swap = {"20261002-110301-ig-post-a1b2": picture, "steps/07-photo/image.png": image["output_files"]["image"]}
    hello = SCENARIO.replace("Writes a hello", "Say hello").replace("agent: hello", "agent: writer")
    out, written = [], None
    for tool, args, documented in spec_examples():
        if tool in skip:
            continue
        args = {k: swap.get(v, v) if isinstance(v, str) else v for k, v in args.items()}
        if tool == "write_scenario":
            args["text"], written = hello, (args, documented)
        r = await c.call_tool(tool, args)
        out.append((tool, documented, r))
        if tool in ("dry_run", "fake_run") and not r.is_error:
            run_id = r.structured_content["run_id"]
            swap[{"dry_run": "20261002-101500-demo-90ad", "fake_run": "20261002-101512-demo-2cf1"}[tool]] = run_id
            if tool == "fake_run":
                await finished(run_id)
    conflict = re.search(r"// the same call again.*\n(Error executing tool write_scenario: conflict: .*)\n", SPEC)[1]
    out.append(("write_scenario", conflict, await c.call_tool("write_scenario", written[0])))
    skill = "---\nname: helper\ndescription: Helps writing\n---\nUse short answers.\n"
    for tool, args in (("write_agent", {"name": "hello", "text": AGENT}), ("write_skill", {"name": "helper", "text": skill})):
        out.append((tool, written[1], await c.call_tool(tool, {"project": "lumen", **args})))
    return out


@pytest.mark.parametrize("transport", ["stdio", "http"])
def test_spec_examples(transport, root, registry, cleanup):
    """Sweep: every tool called with the spec's example arguments over stdio and over --http; each result has the
    documented keys, each documented error its exact text."""
    seed_catalog(root)
    (root / "workflows" / "scenarios" / "picture.yaml").write_text(PICTURE)
    env = {"PATH": os.environ["PATH"], "HOME": str(root.parent), "AGENCAST_CONFIG_DIR": str(registry.parent)}

    async def go(client):
        async with client as c:
            return await sweep(c)
    if transport == "stdio":
        results = anyio.run(go, Client(StdioServerParameters(command=sys.executable, args=[
            "-m", "agencast.cli", "mcp", "--allow", "edit"], env=env, cwd=root.parent), mode="legacy"))
    else:
        s = Http(root, registry, cleanup, "--allow", "edit")
        results = anyio.run(go, s.client())
        assert s.stop() == -signal.SIGTERM
    assert {tool for tool, _, _ in results} == ALL_TOOLS
    for tool, documented, r in results:
        if isinstance(documented, str):
            assert err(r) == documented
        else:
            assert missing_keys(ok(r), documented) == [], tool
    assert all(gone(d.name) for d in (root / "runs").glob("2*"))


BOOM = """\
import sys
from pathlib import Path
from agencast import api
from agencast.cli import main
describe = api.describe_scenario
def boom(root, name):  # an unexpected exception whose text quotes a secret
    if name == "boom":
        raise RuntimeError("boom " + (Path(root) / ".env").read_text())
    return describe(root, name)
api.describe_scenario = boom
sys.exit(main())
"""


def test_secret_sweep(root, registry, cleanup):
    """With a key in the project's .env (pasted into an agent, sent as an input, quoted by a failing run and by an
    `internal` error) and a token for --http: no tool result of a whole session, no line of the server's stderr and
    no worker command line contains either — a failing run, a run that did not start and an internal error included."""
    seed_catalog(root)
    wf = root / "workflows"
    (root / ".env").write_text(f"OPENROUTER_API_KEY={KEY}\n")
    (wf / "agents" / "writer.md").write_text((wf / "agents" / "writer.md").read_text() + f"Use the key {KEY}.\n")
    (wf / "scenarios" / "picture.yaml").write_text(PICTURE)
    (wf / "scenarios" / "boom.yaml").write_text((wf / "scenarios" / "demo.yaml").read_text().replace("name: demo", "name: boom"))
    (wf / "scenarios" / "failing.yaml").write_text("version: 1\nname: failing\ndescription: Fails with its topic\n"
                                                   "inputs: {topic: {type: string, required: true}}\n"
                                                   "steps:\n  - id: stop\n    fail: \"stopped: {{ inputs.topic }}\"\n")
    seen, watching = {}, threading.Event()

    def watch():  # every worker's command line, from /proc, while the session lasts
        while not watching.is_set():
            for f in Path("/proc").glob("[0-9]*/cmdline"):
                try:
                    if b"--mcp-job" in (line := f.read_bytes()):
                        seen[int(f.parent.name)] = line
                except OSError:
                    pass
            time.sleep(0.02)
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    s = Http(root, registry, cleanup, "--allow", "edit", code=BOOM)
    results = []

    async def session():
        async with s.client() as c:
            async def tool(name, args):
                results.append(r := await c.call_tool(name, {"project": "lumen", **args}))
                return r
            failing = (await tool("fake_run", {"scenario": "failing", "inputs": {"topic": KEY}})).structured_content
            while not (done := (await tool("wait_run", {"run_id": failing["run_id"]})).structured_content)["done"]:
                pass
            assert done["state"] == "failed" and "<secret: OPENROUTER_API_KEY>" in done["error"]["message"]
            assert (await tool("describe_scenario", {"scenario": "boom"})).content[0].text.startswith(
                "Error executing tool describe_scenario: internal: RuntimeError: boom OPENROUTER_API_KEY=<secret: ")
            assert (await tool("run_scenario", {"scenario": "demo", "inputs": {KEY: 1}})).is_error  # refused: no run
            # a run that did not start: its worker waits for the only max_parallel_runs slot and is stopped
            config = wf / "config.yaml"
            data = yaml.safe_load(config.read_text())
            data["limits"]["max_parallel_runs"] = 1
            config.write_text(yaml.safe_dump(data, sort_keys=False))
            (root / "runs" / "_slots").mkdir(exist_ok=True)
            with open(root / "runs" / "_slots" / "1.lock", "w") as slot:
                fcntl.flock(slot, fcntl.LOCK_EX)
                queued = (await tool("fake_run", {"scenario": "demo", "inputs": {"topic": KEY}})).structured_content
                cleanup.run_ids.append(queued["run_id"])
                pid = (await anyio.to_thread.run_sync(until, lambda: workers(queued["run_id"])))[0]
                await anyio.to_thread.run_sync(until, lambda: b"waiting for a free slot" in Path(f"/proc/{pid}/fd/2").read_bytes())
                os.kill(pid, signal.SIGTERM)
                while (await tool("run_status", {"run_id": queued["run_id"]})).structured_content["state"] == "queued":
                    await anyio.sleep(0.1)
            assert (await tool("run_status", {"run_id": queued["run_id"]})).structured_content["error"][
                "message"].startswith("run did not start: worker exited with code 143 (SIGTERM)")
            data["limits"].pop("max_parallel_runs")
            config.write_text(yaml.safe_dump(data, sort_keys=False))
            # every other tool; no run_scenario: with a key in .env it would start a live run
            results.extend(r for _, _, r in await sweep(c, skip=("run_scenario",)))
    anyio.run(session)
    assert s.stop() == -signal.SIGTERM
    watching.set()
    watcher.join()
    started = [int(m[1]) for m in re.finditer(r"started \(project lumen, \w+, worker (\d+)\)", "".join(s.stderr))]
    assert len(started) == 4 and set(started) <= set(seen)  # every worker's command line was read
    text = "\n".join([*(json.dumps(r.structured_content, ensure_ascii=False) for r in results),
                      *(b.text if b.type == "text" else b.data for r in results for b in r.content), *s.stderr,
                      *(line.decode(errors="replace") for line in seen.values())])
    assert "Traceback" in text and "did not start" in text and "<secret: OPENROUTER_API_KEY>" in text
    assert KEY not in text and s.token not in text
    assert KEY not in base64.b64decode(next(b.data for r in results for b in r.content if b.type == "image")).decode(
        errors="replace")


def test_client_setup_docs():
    """The client setup in README.md and getting-started.md: no token the shell expands into a command, the unit that
    keeps runs over a restart, Open WebUI in Docker reaching the host."""
    for doc in (REPO / "README.md", REPO / "docs" / "getting-started.md"):
        text = doc.read_text()
        assert '--header "Authorization: Bearer $' not in text, doc
        unit = re.search(r"```ini\n(.*?)```", text, re.S)[1]
        assert "KillMode=process" in unit and "RestartSec=5" in unit
        assert "host.docker.internal:host-gateway" in text and "spec/mcp-server.md" in text
        for block in re.findall(r"```json\n(.*?)```", text, re.S):
            json.loads(block)
