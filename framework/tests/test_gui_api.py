"""API additions for the GUI (agencast 0.6.0, api.md): validation without writes, errors as objects,
environment variable flags, run list fields, runs from the GUI (no callback, dry_run), serving ui/ and CORS."""
import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from conftest import SECRET, TOKEN, serve
from test_webhook import finished

from agencast import api, server
from agencast.fake import Fake
from agencast.projects import error_fields

ROOT = Path("/p")


@pytest.mark.parametrize("msg,fields", [
    ('ig-post.yaml: step "copy", ask.prompt: step \'x\' does not exist',
     {"file": "scenarios/ig-post.yaml", "step": "copy", "field": "ask.prompt"}),
    ('ig-post.yaml: step "copy": agent \'nobody\' does not exist (agents/nobody.md)',
     {"file": "scenarios/ig-post.yaml", "step": "copy"}),
    ("ig-post.yaml: step 'copy': ask: missing required field 'prompt'",
     {"file": "scenarios/ig-post.yaml", "step": "copy", "field": "ask"}),
    ("ig-post.yaml, inputs.topic.default: value does not match type string",
     {"file": "scenarios/ig-post.yaml", "field": "inputs.topic.default"}),
    ("ig-post.yaml, line 7: duplicate key 'id' (first seen on line 5)", {"file": "scenarios/ig-post.yaml", "line": 7}),
    ("agents/copy.md, line 3: cannot read YAML — a value with {, [, ': ' …", {"file": "agents/copy.md", "line": 3}),
    ("skills/voice/SKILL.md: skill body is empty", {"file": "skills/voice/SKILL.md"}),
    ("config.yaml: openrouter: missing required field 'api_key_env'", {"file": "config.yaml", "field": "openrouter"}),
    ("mcp.yaml: variable X is already in config.yaml (openrouter.api_key_env)", {"file": "mcp.yaml"}),
    ("/p/workflows/config.yaml: missing — copy …", {"file": "config.yaml"}),
    ("agents/a.md: 'tools' is required when 'mcp' is set — …: tools: { fs: [tool, …] }", {"file": "agents/a.md"}),
    ("scenario header: field 'name' cannot be changed here", {}),
    ("text: must be a string", {}),
])
def test_error_fields(msg, fields):
    assert error_fields(msg, ROOT) == {"message": msg, **fields}


def test_validate_without_write_and_structured_errors(registry_server):
    _, client, a, _ = registry_server
    assert client.post("/projects/alpha/validate").json() == {"errors": []}
    path = a / "workflows" / "scenarios" / "demo.yaml"
    text = path.read_text()
    broken = text.replace("  - id: result", "  - id: write")  # duplicate step id
    r = client.post("/projects/alpha/validate", json={"path": "scenarios/demo.yaml", "text": broken})
    assert r.status_code == 200 and path.read_text() == text  # nothing was written
    (e,) = r.json()["errors"]
    assert e["file"] == "scenarios/demo.yaml" and e["step"] == "write" and "id is not unique" in e["message"]
    r = client.post("/projects/alpha/validate", json={"path": "scenarios/demo.yaml", "text": text + "steps: []\n"})
    line = len(text.splitlines()) + 1
    assert r.json()["errors"][0] | {"message": ""} == {"message": "", "file": "scenarios/demo.yaml", "line": line}
    r = client.post("/projects/alpha/validate", json={"path": "agents/new.md", "text": "---\nversion: 1\n---\nx\n"})
    assert r.status_code == 200 and not (a / "workflows" / "agents" / "new.md").exists()
    assert {e.get("file") for e in r.json()["errors"]} == {"agents/new.md"}
    assert client.post("/projects/alpha/validate", json={"path": "../.env", "text": "X=1"}).status_code == 404
    assert client.post("/projects/alpha/validate", json={"path": "config.yaml"}).status_code == 422

    # GET /projects/<p> and files/ return errors as objects (including agents)
    (a / "workflows" / "agents" / "writer.md").write_text("---\nversion: 1\nname: a\nname: b\n---\nx\n")
    p = client.get("/projects/alpha").json()
    assert p["agents"][0]["errors"][0] | {"message": ""} == {"message": "", "file": "agents/writer.md", "line": 4}
    assert p["scenarios"][0]["errors"][0]["file"] == "agents/writer.md"
    f = client.get("/projects/alpha/files/agents/writer.md").json()
    assert f["errors"][0]["line"] == 4 and "duplicate key" in f["errors"][0]["message"]


def test_env_flags_never_values(registry_server, monkeypatch):
    _, client, a, _ = registry_server
    (a / "workflows" / "mcp.yaml").write_text(
        "version: 1\nservers:\n  web:\n    description: Web\n    url: https://mcp.example.com\n"
        "    bearer_token_env: WEB_TOKEN\n    agents: [writer]\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-secret-value")
    monkeypatch.delenv("WEBHOOK_TOKEN", raising=False)
    monkeypatch.delenv("WEB_TOKEN", raising=False)
    r = client.get("/projects/alpha")
    assert r.json()["env"] == {"CALLBACK_SECRET": True, "OPENROUTER_API_KEY": True, "WEBHOOK_TOKEN": False,
                               "WEB_TOKEN": False}
    assert "sk-or-secret-value" not in r.text and SECRET not in r.text


def test_config_schema_errors_have_key_lines(registry_server):
    _, client, a, _ = registry_server
    path = a / "workflows" / "config.yaml"
    lines = path.read_text().splitlines()
    at = next(i for i, line in enumerate(lines) if line.lstrip().startswith("run_budget_usd:"))
    lines[at:at + 1] = ['  run_budget_usd: "x"', "  run_budegt_usd: 2"]
    path.write_text("\n".join(lines) + "\n")
    value_line, unknown_line = at + 1, at + 2
    errors = client.get("/projects/alpha/files/config.yaml").json()["errors"]
    assert {e["field"]: e["line"] for e in errors} == {
        "limits.run_budget_usd": value_line, "limits.run_budegt_usd": unknown_line}
    response = client.get("/projects/alpha")
    assert response.status_code == 422
    assert {e["field"]: e["line"] for e in response.json()["errors"]} == {
        "limits.run_budget_usd": value_line, "limits.run_budegt_usd": unknown_line}


def test_fake_template_project_runs_without_callback_secret(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("CALLBACK_SECRET", raising=False)
    monkeypatch.delenv("WEBHOOK_TOKEN", raising=False)
    root = tmp_path / "template"
    api.new_project(root)
    projects = server.Projects(token=TOKEN, fake=lambda: Fake(None))
    projects.start()
    assert "CALLBACK_SECRET" not in capsys.readouterr().err
    srv, client = serve(projects=projects)
    try:
        rejected = client.post("/projects/template/runs", json={"scenario": "demo",
                                                                "callback_url": "https://example.com/cb"})
        assert rejected.status_code == 422 and "CALLBACK_SECRET" in rejected.json()["details"][0]
        response = client.post("/projects/template/runs", json={"scenario": "demo"})
        assert response.status_code == 202
        hook = projects.hooks[root.resolve()]
        finished(hook, response.json()["run_id"])
        assert client.get(f"/projects/template/runs/{response.json()['run_id']}").json()["status"] == "succeeded"
    finally:
        client.close()
        srv.shutdown()
        srv.server_close()


def test_runs_for_gui(registry_server):
    projects, client, a, _ = registry_server
    # GUI run without callback_url: executes without a callback, callback_url: null in the record
    r = client.post("/projects/alpha/runs", json={"scenario": "demo"})
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    finished(projects.hooks[a], run_id)
    events = [json.loads(x) for x in (a / "runs" / run_id / "events.jsonl").read_text().splitlines()]
    assert events[0]["callback_url"] is None and events[0]["steps_total"] == 2
    assert "callback_sent" not in {e["type"] for e in events}
    (item,) = client.get("/projects/alpha/runs").json()["runs"]
    assert item | {"started_at": None, "finished_at": None} == {
        "run_id": run_id, "status": "succeeded", "state": "succeeded", "cost_usd": item["cost_usd"],
        "duration_s": item["duration_s"], "callback": "", "scenario": "demo", "started_at": None,
        "finished_at": None, "current_step": None, "steps_total": 2, "fake": True, "current_nn": None,
        "steps_done": None}
    assert item["started_at"] <= item["finished_at"]

    # running run: current_step = latest step_started without step_finished
    d = a / "runs" / "20990101-000000-demo-abcd"
    d.mkdir()
    lines = [{"ts": "2099-01-01T00:00:00.000Z", "type": "run_started", "scenario": "demo", "steps_total": 2},
             {"ts": "2099-01-01T00:00:01.000Z", "type": "step_started", "step": "write", "kind": "ask", "nn": 1},
             {"ts": "2099-01-01T00:00:02.000Z", "type": "step_finished", "step": "write", "kind": "ask",
              "status": "succeeded"},
             {"ts": "2099-01-01T00:00:02.100Z", "type": "step_started", "step": "result", "kind": "output", "nn": 2}]
    (d / "events.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines) + '{"ts": "2099-')  # partial line
    # no run.lock held = interrupted (process exited); another process holds the lock = running (API findings 1)
    interrupted = client.get("/projects/alpha/runs").json()["runs"][0]
    assert interrupted == {"run_id": d.name, "status": "interrupted", "state": "interrupted", "cost_usd": None,
                           "duration_s": None, "callback": "", "scenario": "demo",
                           "started_at": "2099-01-01T00:00:00.000Z", "finished_at": None, "current_step": "result",
                           "steps_total": 2, "fake": None, "current_nn": None, "steps_done": None}
    with held_lock(d):
        running = client.get("/projects/alpha/runs").json()["runs"][0]
        assert running == interrupted | {
            "status": "running", "state": "running", "current_nn": 2, "steps_done": 1}
        detail = client.get(f"/projects/alpha/runs/{d.name}").json()
        assert detail["state"] == "running" and detail["current_step"] == "result"
        assert detail["steps"][-1]["status"] == "running"
    assert client.get(f"/projects/alpha/runs/{d.name}").json()["state"] == "interrupted"  # a process crash releases the lock

    # dry_run: only plan.md and inputs.json, run_id returned immediately
    r = client.post("/projects/alpha/runs", json={"scenario": "demo", "inputs": {"topic": "tea"}, "dry_run": True})
    assert r.status_code == 200 and r.json() == {"run_id": r.json()["run_id"], "dry_run": True}
    assert sorted(x.name for x in (a / "runs" / r.json()["run_id"]).iterdir()) == ["inputs.json", "plan.md"]
    bad = client.post("/projects/alpha/runs", json={"scenario": "demo", "dry_run": True,
                                                   "callback_url": "https://n8n.example.com/x"})
    assert bad.status_code == 422 and "dry_run" in bad.json()["details"][0]
    bad = client.post("/projects/alpha/runs", json={"scenario": "demo", "callback_url": "http://evil"})
    assert bad.status_code == 422 and bad.json()["details"] == ["callback_url: does not start with https://"]


@contextmanager
def held_lock(run_dir: Path):
    """Hold the run lock in another process (like `agencast run` alongside `serve`); kill it on exit."""
    code = ("import fcntl, sys, time\nf = open(sys.argv[1], 'a')\nfcntl.flock(f, fcntl.LOCK_EX)\n"
            "print('ok', flush=True)\ntime.sleep(60)")
    proc = subprocess.Popen([sys.executable, "-c", code, str(run_dir / "run.lock")], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout and proc.stdout.readline() == "ok\n"
        yield
    finally:
        proc.kill()
        proc.wait()


def test_post_runs_contract_unchanged(wf, monkeypatch):
    """webhook.md: POST /runs still requires callback_url and does not accept dry_run."""
    monkeypatch.setenv("WEBHOOK_TOKEN", TOKEN)
    monkeypatch.setenv("CALLBACK_SECRET", SECRET)
    hook = server.Webhook(wf, fake=Fake(None))
    auth = f"Bearer {TOKEN}"
    s, body = hook.accept(auth, json.dumps({"scenario": "tone-check"}).encode())
    assert s == 422 and body["details"][0] == "callback_url: missing or does not start with https://"
    s, body = hook.accept(auth, json.dumps({"scenario": "tone-check", "dry_run": True,
                                            "callback_url": "https://x.example.com"}).encode())
    assert s == 422 and "unknown field 'dry_run'" in body["details"][0]


def test_serves_gui_without_token_and_cors(registry_server, tmp_path, monkeypatch):
    projects, client, _, _ = registry_server
    ui = tmp_path / "ui"
    monkeypatch.setattr(server, "UI", ui)
    anon = {"Authorization": ""}
    r = client.get("/", headers=anon)
    assert r.status_code == 404 and "npm run build" in r.json()["error"]
    (ui / "assets").mkdir(parents=True)
    (ui / "index.html").write_text("<!doctype html><title>AgenCast</title>")
    (ui / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("secret")
    r = client.get("/", headers=anon)
    assert r.status_code == 200 and "AgenCast" in r.text and r.headers["content-type"].startswith("text/html")
    r = client.get("/assets/app.js", headers=anon)
    assert r.text == "console.log(1)" and "javascript" in r.headers["content-type"]
    assert "AgenCast" in client.get("/p/alpha", headers=anon).text  # hash routing → index.html
    for url in ("/assets/missing.js", "/..%2Fsecret.txt", "/assets/..%2F..%2Fsecret.txt"):
        assert client.get(url, headers=anon).status_code == 404, url
    assert client.get("/projects", headers=anon).status_code == 401  # the token still protects the API
    assert "access-control-allow-origin" not in client.get("/", headers=anon).headers
    assert client.options("/projects").status_code == 404

    srv, cors = serve(projects=projects)
    srv.cors = "http://localhost:5173"
    try:
        r = cors.options("/projects/alpha", headers={"Origin": "http://localhost:5173"})
        assert r.status_code == 204 and r.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert "Authorization" in r.headers["access-control-allow-headers"]
        assert "PATCH" in r.headers["access-control-allow-methods"]
        assert cors.get("/projects").headers["access-control-allow-origin"] == "http://localhost:5173"
    finally:
        cors.close()
        srv.shutdown()
        srv.server_close()


def test_projects_list_survives_root_without_workflows(registry_server):
    """0.15.1: a registered root without workflows/ (deleted worktree) must not cause GET /projects to return 500."""
    import yaml
    from agencast.projects import registry_path
    reg = registry_path()
    data = yaml.safe_load(reg.read_text())
    data["projects"].append({"name": "vanished", "root": "/tmp/agencast-nonexistent-xyz"})
    reg.write_text(yaml.safe_dump(data, allow_unicode=True))
    _, client, _, _ = registry_server
    r = client.get("/projects")
    assert r.status_code == 200
    items = {p["name"]: p for p in r.json()["projects"]}
    assert items["alpha"]["available"] is True
    z = items["vanished"]
    assert z["available"] is False and "workflows" in z["reason"]
    assert z["spend_today_usd"] == 0 and z["last_run"] is None and z["counts"] == {"scenarios": 0, "agents": 0}
