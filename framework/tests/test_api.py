"""Read API for `serve` (api.md): registry mode with AGENCAST_TOKEN and single-project mode; fake provider."""
import os
from pathlib import Path

from conftest import SECRET, TOKEN, serve
from test_webhook import Receiver, finished

from agencast import api
from agencast.cli import main
from agencast.fake import Fake
from agencast.projects import default_name
from agencast.record import Mask
from agencast.server import Projects, Webhook
from agencast.task import local_ledger


def test_registry_mode_read_api(registry_server):
    projects, client, a, b = registry_server
    assert client.get("/projects", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/projects").json() == {"projects": [
        {"name": "alpha", "root": str(a), "available": True, "trusted": True, "last_run": None,
         "counts": {"scenarios": 1, "agents": 1}, "spend_today_usd": 0},
        {"name": "beta", "root": str(b), "available": True, "trusted": True, "last_run": None,
         "counts": {"scenarios": 1, "agents": 1}, "spend_today_usd": 0}],
        "registry": str(a.parent / "agencast-config" / "projects.yaml"),
        "projects_root": str(api.projects_root()), "writable": True}
    p = client.get("/projects/alpha").json()
    assert p["name"] == "alpha" and p["models"]["smart"] == "anthropic/claude-haiku-4.5" and p["errors"] == []
    (sc,) = p["scenarios"]
    assert (sc["name"], sc["steps_count"], sc["callable"], sc["errors"]) == ("demo", 2, False, [])
    assert p["agents"][0]["model_id"] == "anthropic/claude-haiku-4.5"
    assert p["links"]["scenario_agent"] == [["demo", "writer"]] and p["limits"]["run_timeout"] == "1h"
    steps = client.get("/projects/alpha/scenarios/demo").json()["steps"]
    assert [(s["nn"], s["id"], s["type"]) for s in steps] == [(1, "write", "ask"), (2, "result", "output")]
    assert steps[0]["agent"] == "writer" and steps[1]["refs"] == ["steps.write.text"]
    for url in ("/projects/missing", "/projects/alpha/scenarios/missing", "/projects/alpha/runs/20260101-000000-x-abcd",
                "/projects/alpha/missing"):
        r = client.get(url)
        assert r.status_code == 404 and r.json()["error"], url
    assert client.post("/runs", json={}).status_code == 404  # outside a project, only /projects/<p>/runs

    rcv = Receiver()
    r = client.post("/projects/alpha/runs", json={"scenario": "demo", "callback_url": rcv.url})
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    finished(projects.hooks[a], run_id)
    assert rcv.wait()[0]["status"] == "succeeded"
    assert [x["run_id"] for x in client.get("/projects/alpha/runs").json()["runs"]] == [run_id]
    d = client.get(f"/projects/alpha/runs/{run_id}").json()
    assert d["status"] == "succeeded" and [(s["step"], s["status"]) for s in d["steps"]] == [
        ("write", "succeeded"), ("result", "succeeded")]
    assert d["steps"][0]["cost_usd"] > 0 and "summary.md" in d["files"] and "events.jsonl" in d["files"]
    f = client.get(f"/projects/alpha/runs/{run_id}/files/summary.md")
    assert f.status_code == 200 and "# demo — success" in f.text
    assert client.get(f"/projects/alpha/runs/{run_id}/files/steps/01-write/output.json").json()
    for rel in ("%2e%2e/%2e%2e/workflows/config.yaml", "..%2F..%2F.env.example", "%2Fetc%2Fpasswd", "missing.md"):
        assert client.get(f"/projects/alpha/runs/{run_id}/files/{rel}").status_code == 404, rel
    assert projects.get(f"Bearer {TOKEN}", f"/projects/alpha/runs/{run_id}/files/../../../.env.example", "")[0] == 404
    assert client.get("/projects/beta/runs").json() == {"runs": []}

    local_ledger(a / "runs", False).add("2000-01-01", {"run_id": "x", "cost_usd": 0.25, "finished_at": "…"})
    local_ledger(a / "runs", False).add("2000-01-01", {"run_id": "y", "cost_usd": 0.05, "finished_at": "…"})
    s = client.get("/projects/alpha/spend", params={"day": "2000-01-01"}).json()
    assert s["total_usd"] == 0.3 and [x["run_id"] for x in s["runs"]] == ["x", "y"]
    assert client.get("/projects/alpha/spend").json()["runs"] == []  # today: fake runs have their own ledger
    assert client.get("/projects/alpha/spend", params={"day": "yesterday"}).status_code == 422

    (b / "workflows" / "config.yaml").unlink()
    assert client.get("/projects").json()["projects"][1]["available"] is False
    assert "unavailable" in client.get("/projects/beta").json()["error"]


def test_single_project_mode(wf, monkeypatch):
    """Current serve inside a project: /runs unchanged, /projects with this single project and its token."""
    monkeypatch.setenv("WEBHOOK_TOKEN", TOKEN)
    monkeypatch.setenv("CALLBACK_SECRET", SECRET)
    hook = Webhook(wf, fake=Fake(None))
    hook.start()
    srv, client = serve(hook)
    try:
        counts = {"scenarios": sum(1 for _ in (wf / "scenarios").glob("*.yaml")),
                  "agents": sum(1 for _ in (wf / "agents").glob("*.md"))}
        (p,) = client.get("/projects").json()["projects"]
        assert p == {"name": default_name(wf.parent), "root": str(wf.parent.resolve()), "available": True,
                     "trusted": True, "last_run": None, "counts": counts, "spend_today_usd": 0}
        listing = client.get("/projects").json()
        assert listing["writable"] is False and listing["projects_root"] == str(api.projects_root())
        api.add_project(wf.parent, "mine")
        assert client.get("/projects").json()["projects"][0]["name"] == "mine"
        for response in (client.post("/projects", json={"root": str(wf.parent)}),
                         client.post("/projects/new", json={"name": "new"}),
                         client.delete("/projects/mine")):
            assert response.status_code == 405 and "registry mode" in response.json()["error"]
        assert (wf.parent / "workflows" / "config.yaml").is_file()
        assert "ig-post" in [s["name"] for s in client.get("/projects/mine").json()["scenarios"]]
        rcv = Receiver()
        body = {"scenario": "tone-check", "inputs": {"text": "Hello"}, "callback_url": rcv.url}
        run_id = client.post("/projects/mine/runs", json=body).json()["run_id"]
        finished(hook, run_id)
        assert client.get(f"/runs/{run_id}").json()["status"] == "succeeded"
        assert client.get(f"/projects/mine/runs/{run_id}").json()["status"] == "succeeded"
        assert client.post("/projects/other/runs", json=body).status_code == 404
        sw = client.get("/projects/mine/scenarios/demo-call").json()["steps"]
        assert [s["call"] for s in sw if s["type"] == "call"] == ["tone-check"]
    finally:
        client.close()
        srv.shutdown()
        srv.server_close()


def test_registry_project_create_register_remove(tmp_path, registry, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    workspace = tmp_path / "workspace"
    registry.parent.mkdir(parents=True)
    registry.write_text("projects_root: ~/workspace\nprojects: []\n")
    projects = Projects(token=TOKEN, fake=lambda: Fake(None))
    srv, client = serve(projects=projects)
    try:
        info = client.get("/projects").json()
        assert info["projects"] == [] and info["projects_root"] == str(workspace) and info["writable"] is True

        created = client.post("/projects/new", json={"name": "fresh"})
        assert created.status_code == 201
        body = created.json()
        root = workspace / "fresh"
        assert body["name"] == "fresh" and body["root"] == str(root)
        assert {Path(path).relative_to(root).as_posix() for path in body["created"]} == {
            ".env.example", ".gitignore", "workflows/config.yaml", "workflows/agents/writer.md",
            "workflows/scenarios/demo.yaml"}
        assert body["trusted"] is False  # every registration over HTTP: no MCP servers until `projects trust`
        assert [(p["name"], p["trusted"]) for p in client.get("/projects").json()["projects"]] == [("fresh", False)]
        assert client.get("/projects/fresh").json()["trusted"] is False
        assert "projects_root:" in registry.read_text()
        assert client.post("/projects/new", json={"name": "fresh"}).status_code == 409
        exists = client.post("/projects/new", json={"name": "another", "root": str(root)})
        assert exists.status_code == 409 and "add the existing" in exists.json()["error"]

        imported = workspace / "imported"
        api.new_project(imported, "detached")
        api.remove_project("detached")
        registered = client.post("/projects", json={"root": "imported", "name": "import"})
        assert registered.status_code == 201
        assert registered.json() == {"name": "import", "root": str(imported), "trusted": False}
        assert client.post("/projects", json={"root": str(imported)}).status_code == 409
        assert client.post("/projects", json={"root": "../outside"}).status_code == 422
        assert client.post("/projects", json={"root": str(tmp_path / "missing")}).status_code == 422
        outside = tmp_path / "outside"
        api.new_project(outside, "outside")
        api.remove_project("outside")
        expanded = client.post("/projects", json={"root": "~/outside", "name": "expanded"})
        assert expanded.status_code == 201 and expanded.json()["root"] == str(outside)
        (workspace / "escape").symlink_to(tmp_path, target_is_directory=True)
        assert client.post("/projects", json={"root": "escape"}).status_code == 422

        removed = client.delete("/projects/import")
        assert removed.status_code == 200 and removed.json()["files_deleted"] is False
        assert "files are kept" in removed.json()["message"]
        assert (imported / "workflows" / "config.yaml").is_file()
        assert client.get("/projects/import").status_code == 404
        assert client.delete("/projects/expanded").status_code == 200
    finally:
        client.close()
        srv.shutdown()
        srv.server_close()


def test_serve_registry_needs_token(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENCAST_TOKEN", raising=False)
    assert main(["serve", "--port", "0"]) == 2
    assert "AGENCAST_TOKEN" in capsys.readouterr().err


def test_edit_api(registry_server):
    """Editing via HTTP (api.md “Editing”): etag, 409, 422, 404 outside workflows/, same token."""
    _, client, a, _ = registry_server
    sc = client.get("/projects/alpha/scenarios/demo").json()
    assert [s["address"] for s in sc["steps"]] == [["steps", 0], ["steps", 1]]
    assert client.put("/projects/alpha/scenarios/demo", json={"etag": sc["etag"], "fields": {}},
                      headers={"Authorization": "Bearer wrong"}).status_code == 401
    step = {"id": "shorten", "ask": {"agent": "writer", "prompt": "Shorten: {{ steps.write.text }}"}}
    r = client.post("/projects/alpha/scenarios/demo/steps", json={"etag": sc["etag"], "after": ["steps", 0], "step": step})
    assert r.status_code == 200 and r.json()["errors"] == []
    tag = r.json()["etag"]
    stale = client.patch("/projects/alpha/scenarios/demo/steps/1", json={"etag": sc["etag"], "fields": {"timeout": "1m"}})
    assert stale.status_code == 409 and stale.json()["etag"] == tag
    bad = client.patch("/projects/alpha/scenarios/demo/steps/1",
                       json={"etag": tag, "fields": {"ask": {"agent": "nobody"}}})
    assert bad.status_code == 422
    (e,) = [e for e in bad.json()["errors"] if "nobody" in e["message"]]  # 0.6.0: errors as objects
    assert e == {"message": 'demo.yaml: step "shorten": agent \'nobody\' does not exist (agents/nobody.md)',
                 "file": "scenarios/demo.yaml", "step": "shorten"}
    r = client.post("/projects/alpha/scenarios/demo/steps/1/move", json={"etag": tag, "to": ["steps"]})
    assert r.status_code == 422  # shorten would reference a step that runs after it
    r = client.patch("/projects/alpha/scenarios/demo/steps/1", json={"etag": tag, "fields": {"timeout": "1m"}})
    assert r.status_code == 200
    assert client.request("DELETE", "/projects/alpha/scenarios/demo/steps/9", json={"etag": r.json()["etag"]}).status_code == 404
    r = client.request("DELETE", "/projects/alpha/scenarios/demo/steps/1", json={"etag": r.json()["etag"]})
    assert r.status_code == 200
    f = client.get("/projects/alpha/files/scenarios/demo.yaml").json()
    assert f["etag"] == r.json()["etag"] and f["data"]["name"] == "demo" and "shorten" not in f["text"]
    assert client.put("/projects/alpha/files/scenarios/demo.yaml",
                      json={"etag": f["etag"], "text": "# at the top\n" + f["text"]}).status_code == 200
    assert (a / "workflows" / "scenarios" / "demo.yaml").read_text().startswith("# at the top\n")
    for url in ("/projects/alpha/files/..%2F.env", "/projects/alpha/files/%2e%2e/.env", "/projects/alpha/files/.env",
                "/projects/alpha/files/agents/..%2F..%2F.env.example", "/projects/beta/files/runs/x.yaml"):
        assert client.get(url).status_code == 404, url
        assert client.put(url, json={"etag": None, "text": "X=1"}).status_code == 404, url
    assert not (a / "workflows" / ".env").exists()

    # agent: new via HTTP, PUT, DELETE rejected when used by a scenario
    r = client.post("/projects/alpha/agents", json={"name": "editor"})
    assert r.status_code == 200
    r = client.put("/projects/alpha/agents/editor", json={"etag": r.json()["etag"],
                                                           "frontmatter": {"description": "Edits"}, "body": "Edit.\n"})
    assert r.status_code == 200
    assert client.request("DELETE", "/projects/alpha/agents/editor", json={"etag": r.json()["etag"]}).status_code == 200
    writer = client.get("/projects/alpha/files/agents/writer.md").json()
    assert writer["frontmatter"]["name"] == "writer"
    r = client.request("DELETE", "/projects/alpha/agents/writer", json={"etag": writer["etag"]})
    assert r.status_code == 422 and "demo" in r.json()["errors"][0]["message"]
    assert client.post("/projects/alpha/scenarios", json={"name": "second"}).status_code == 200
    assert client.post("/projects/alpha/scenarios", json={"name": "second"}).status_code == 422  # no overwrites

    # skill and config
    r = client.put("/projects/alpha/skills/voice", json={"etag": None, "text": "---\nname: voice\ndescription: Tone\n---\nUse an informal tone.\n"})
    assert r.status_code == 200
    assert client.request("DELETE", "/projects/alpha/skills/voice", json={"etag": r.json()["etag"]}).status_code == 200
    c = client.get("/projects/alpha/files/config.yaml").json()
    r = client.put("/projects/alpha/config", json={"etag": c["etag"], "fields": {"limits": {"run_budget_usd": 2}}})
    assert r.status_code == 200 and client.get("/projects/alpha").json()["limits"]["run_budget_usd"] == 2
    assert client.put("/projects/alpha/config", json={"etag": r.json()["etag"], "fields": {"version": 2}}).status_code == 422
    assert client.put("/projects/alpha/missing", json={}).status_code == 404


def test_rename_api_routes(registry_server):
    _, client, root, _ = registry_server
    callee = api.read_file(root, "scenarios/demo.yaml")
    api.set_header(root, "demo", callee["etag"], {"callable": True})
    api.new_scenario(root, "caller")
    caller = api.read_file(root, "scenarios/caller.yaml")
    api.add_step(root, "caller", caller["etag"], ["steps", 0],
                 {"id": "invoke", "call": {"scenario": "demo"}})
    source = client.get("/projects/alpha/scenarios/demo").json()

    stale = client.post("/projects/alpha/scenarios/demo/rename", json={"etag": "stale", "name": "intro"})
    assert stale.status_code == 409 and stale.json()["etag"] == source["etag"]
    invalid = client.post("/projects/alpha/scenarios/demo/rename", json={"etag": source["etag"], "name": "Intro"})
    assert invalid.status_code == 422 and isinstance(invalid.json()["errors"][0], dict)
    collision = client.post("/projects/alpha/scenarios/demo/rename",
                            json={"etag": source["etag"], "name": "caller"})
    assert collision.status_code == 422

    renamed = client.post("/projects/alpha/scenarios/demo/rename", json={"etag": source["etag"], "name": "intro"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "intro" and renamed.json()["etag"] and renamed.json()["errors"] == []
    assert renamed.json()["changed"] == ["scenarios/caller.yaml", "scenarios/intro.yaml"]
    assert client.get("/projects/alpha/files/scenarios/caller.yaml").json()["data"]["steps"][1]["call"]["scenario"] == "intro"
    assert client.get("/projects/alpha/scenarios/demo").status_code == 404

    agent = client.get("/projects/alpha/files/agents/writer.md").json()
    renamed_agent = client.post("/projects/alpha/agents/writer/rename", json={"etag": agent["etag"], "name": "editor"})
    assert renamed_agent.status_code == 200 and renamed_agent.json()["name"] == "editor"
    assert client.get("/projects/alpha/files/agents/editor.md").json()["frontmatter"]["name"] == "editor"
    assert client.post("/projects/alpha/agents/missing/rename", json={"etag": "x", "name": "other"}).status_code == 404


A_KEY, B_KEY = "sk-test-A-0123456789abcdef", "sk-test-B-0123456789abcdef"


def test_project_env_masks_with_each_projects_own_value(tmp_path, monkeypatch):
    """0.19.0, a server of several projects: A's `.env` sets OPENROUTER_API_KEY in the process first; B's results
    are still masked with B's own value — the one B's runs use (mcp-server.md “Secrets and environment”)."""
    for name in ("OPENROUTER_API_KEY", "HTTPS_PROXY"):
        monkeypatch.setenv(name, "")  # recorded, so the values loaded here are removed afterwards
        monkeypatch.delenv(name)
    a, b = tmp_path / "a", tmp_path / "b"
    api.new_project(a)
    api.new_project(b)
    (a / ".env").write_text(f"OPENROUTER_API_KEY={A_KEY}\nHTTPS_PROXY=http://127.0.0.1:9\n")
    (b / ".env").write_text(f"OPENROUTER_API_KEY={B_KEY}\n")
    assert api.project_env(a) == [("OPENROUTER_API_KEY", A_KEY)]
    assert api.project_env(b) == [("OPENROUTER_API_KEY", A_KEY), ("OPENROUTER_API_KEY", B_KEY)]
    assert Mask(api.project_env(b)).mask(f"{B_KEY} {A_KEY}") == "<secret: OPENROUTER_API_KEY> <secret: OPENROUTER_API_KEY>"
    assert os.environ["OPENROUTER_API_KEY"] == A_KEY and "HTTPS_PROXY" not in os.environ


def test_load_without_dotenv_and_runs_dir(tmp_path, monkeypatch):
    """`api.load(..., dotenv=False)` reads no `.env` — neither the project's nor the current directory's;
    `api.runs_dir` is `runs_dir` of config.yaml."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.delenv("OPENROUTER_API_KEY")
    root = tmp_path / "p"
    api.new_project(root)
    (root / ".env").write_text(f"OPENROUTER_API_KEY={A_KEY}\n")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(f"OPENROUTER_API_KEY={B_KEY}\n")
    p = api.load(api.scenario_file(root, "demo"), fake=Fake(), dotenv=False)
    assert p.scenario["name"] == "demo" and "OPENROUTER_API_KEY" not in os.environ
    api.load(api.scenario_file(root, "demo"), fake=Fake())
    assert os.environ["OPENROUTER_API_KEY"] == A_KEY
    assert api.runs_dir(root) == root / "runs"
    (root / "workflows" / "config.yaml").write_text((root / "workflows" / "config.yaml").read_text().replace(
        "runs_dir: ./runs", "runs_dir: ./records"))
    assert api.runs_dir(root) == root / "records"
