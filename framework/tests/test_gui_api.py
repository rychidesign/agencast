"""Doplňky API pro GUI (agencast 0.6.0, api.md): validate bez zápisu, chyby jako objekty, příznaky
proměnných prostředí, pole běhů pro seznam, spuštění z GUI (bez callbacku, dry_run), servírování ui/ a CORS."""
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
    ('ig-post.yaml: krok "copy", ask.prompt: krok \'x\' neexistuje',
     {"file": "scenarios/ig-post.yaml", "step": "copy", "field": "ask.prompt"}),
    ('ig-post.yaml: krok "copy": agent \'nikdo\' neexistuje (agents/nikdo.md)',
     {"file": "scenarios/ig-post.yaml", "step": "copy"}),
    ("ig-post.yaml: krok 'copy': ask: chybí povinné pole 'prompt'",
     {"file": "scenarios/ig-post.yaml", "step": "copy", "field": "ask"}),
    ("ig-post.yaml, inputs.tema.default: hodnota neodpovídá type string",
     {"file": "scenarios/ig-post.yaml", "field": "inputs.tema.default"}),
    ("ig-post.yaml, řádek 7: duplicitní klíč 'id' (poprvé na řádku 5)", {"file": "scenarios/ig-post.yaml", "line": 7}),
    ("agents/copy.md, řádek 3: YAML nejde přečíst — hodnota s {, [, ': ' …", {"file": "agents/copy.md", "line": 3}),
    ("skills/hlas/SKILL.md: tělo skillu je prázdné", {"file": "skills/hlas/SKILL.md"}),
    ("config.yaml: openrouter: chybí povinné pole 'api_key_env'", {"file": "config.yaml", "field": "openrouter"}),
    ("mcp.yaml: proměnná X je už v config.yaml (openrouter.api_key_env)", {"file": "mcp.yaml"}),
    ("/p/workflows/config.yaml: chybí — zkopíruj …", {"file": "config.yaml"}),
    ("agents/a.md: s polem 'mcp' je povinné i 'tools' — …: tools: { fs: [nástroj, …] }", {"file": "agents/a.md"}),
    ("hlavička scénáře: pole 'name' tady měnit nejde", {}),
    ("text: má být text", {}),
])
def test_error_fields(msg, fields):
    assert error_fields(msg, ROOT) == {"message": msg, **fields}


def test_validate_without_write_and_structured_errors(registry_server):
    _, client, a, _ = registry_server
    assert client.post("/projects/alfa/validate").json() == {"errors": []}
    path = a / "workflows" / "scenarios" / "ukazka.yaml"
    text = path.read_text()
    broken = text.replace("  - id: vystup", "  - id: napis")  # duplicitní id kroku
    r = client.post("/projects/alfa/validate", json={"path": "scenarios/ukazka.yaml", "text": broken})
    assert r.status_code == 200 and path.read_text() == text  # nic se nezapsalo
    (e,) = r.json()["errors"]
    assert e["file"] == "scenarios/ukazka.yaml" and e["step"] == "napis" and "unikátní" in e["message"]
    r = client.post("/projects/alfa/validate", json={"path": "scenarios/ukazka.yaml", "text": text + "steps: []\n"})
    line = len(text.splitlines()) + 1
    assert r.json()["errors"][0] | {"message": ""} == {"message": "", "file": "scenarios/ukazka.yaml", "line": line}
    r = client.post("/projects/alfa/validate", json={"path": "agents/novy.md", "text": "---\nversion: 1\n---\nx\n"})
    assert r.status_code == 200 and not (a / "workflows" / "agents" / "novy.md").exists()
    assert {e.get("file") for e in r.json()["errors"]} == {"agents/novy.md"}
    assert client.post("/projects/alfa/validate", json={"path": "../.env", "text": "X=1"}).status_code == 404
    assert client.post("/projects/alfa/validate", json={"path": "config.yaml"}).status_code == 422

    # GET /projects/<p> a files/ vrací chyby jako objekty (i u agentů)
    (a / "workflows" / "agents" / "pisatel.md").write_text("---\nversion: 1\nname: a\nname: b\n---\nx\n")
    p = client.get("/projects/alfa").json()
    assert p["agents"][0]["errors"][0] | {"message": ""} == {"message": "", "file": "agents/pisatel.md", "line": 4}
    assert p["scenarios"][0]["errors"][0]["file"] == "agents/pisatel.md"
    f = client.get("/projects/alfa/files/agents/pisatel.md").json()
    assert f["errors"][0]["line"] == 4 and "duplicitní klíč" in f["errors"][0]["message"]


def test_env_flags_never_values(registry_server, monkeypatch):
    _, client, a, _ = registry_server
    (a / "workflows" / "mcp.yaml").write_text(
        "version: 1\nservers:\n  web:\n    description: Web\n    url: https://mcp.example.com\n"
        "    bearer_token_env: WEB_TOKEN\n    agents: [pisatel]\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-tajna-hodnota")
    monkeypatch.delenv("WEBHOOK_TOKEN", raising=False)
    monkeypatch.delenv("WEB_TOKEN", raising=False)
    r = client.get("/projects/alfa")
    assert r.json()["env"] == {"CALLBACK_SECRET": True, "OPENROUTER_API_KEY": True, "WEBHOOK_TOKEN": False,
                               "WEB_TOKEN": False}
    assert "sk-or-tajna-hodnota" not in r.text and SECRET not in r.text


def test_config_schema_errors_have_key_lines(registry_server):
    _, client, a, _ = registry_server
    path = a / "workflows" / "config.yaml"
    lines = path.read_text().splitlines()
    at = next(i for i, line in enumerate(lines) if line.lstrip().startswith("run_budget_usd:"))
    lines[at:at + 1] = ['  run_budget_usd: "x"', "  run_budegt_usd: 2"]
    path.write_text("\n".join(lines) + "\n")
    value_line, unknown_line = at + 1, at + 2
    errors = client.get("/projects/alfa/files/config.yaml").json()["errors"]
    assert {e["field"]: e["line"] for e in errors} == {
        "limits.run_budget_usd": value_line, "limits.run_budegt_usd": unknown_line}
    response = client.get("/projects/alfa")
    assert response.status_code == 422
    assert {e["field"]: e["line"] for e in response.json()["errors"]} == {
        "limits.run_budget_usd": value_line, "limits.run_budegt_usd": unknown_line}


def test_fake_template_project_runs_without_callback_secret(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("CALLBACK_SECRET", raising=False)
    monkeypatch.delenv("WEBHOOK_TOKEN", raising=False)
    root = tmp_path / "sablona"
    api.new_project(root)
    projects = server.Projects(token=TOKEN, fake=lambda: Fake(None))
    projects.start()
    assert "CALLBACK_SECRET" not in capsys.readouterr().err
    srv, client = serve(projects=projects)
    try:
        rejected = client.post("/projects/sablona/runs", json={"scenario": "ukazka",
                                                                "callback_url": "https://example.com/cb"})
        assert rejected.status_code == 422 and "CALLBACK_SECRET" in rejected.json()["details"][0]
        response = client.post("/projects/sablona/runs", json={"scenario": "ukazka"})
        assert response.status_code == 202
        hook = projects.hooks[root.resolve()]
        finished(hook, response.json()["run_id"])
        assert client.get(f"/projects/sablona/runs/{response.json()['run_id']}").json()["status"] == "succeeded"
    finally:
        client.close()
        srv.shutdown()
        srv.server_close()


def test_runs_for_gui(registry_server):
    projects, client, a, _ = registry_server
    # běh z GUI bez callback_url: proběhne, callback se neposílá, v záznamu callback_url: null
    r = client.post("/projects/alfa/runs", json={"scenario": "ukazka"})
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    finished(projects.hooks[a], run_id)
    events = [json.loads(x) for x in (a / "runs" / run_id / "events.jsonl").read_text().splitlines()]
    assert events[0]["callback_url"] is None and events[0]["steps_total"] == 2
    assert "callback_sent" not in {e["type"] for e in events}
    (item,) = client.get("/projects/alfa/runs").json()["runs"]
    assert item | {"started_at": None, "finished_at": None} == {
        "run_id": run_id, "status": "succeeded", "state": "succeeded", "cost_usd": item["cost_usd"],
        "duration_s": item["duration_s"], "callback": "", "scenario": "ukazka", "started_at": None,
        "finished_at": None, "current_step": None, "steps_total": 2, "fake": True, "current_nn": None,
        "steps_done": None}
    assert item["started_at"] <= item["finished_at"]

    # běžící běh: current_step = poslední step_started bez step_finished
    d = a / "runs" / "20990101-000000-ukazka-abcd"
    d.mkdir()
    lines = [{"ts": "2099-01-01T00:00:00.000Z", "type": "run_started", "scenario": "ukazka", "steps_total": 2},
             {"ts": "2099-01-01T00:00:01.000Z", "type": "step_started", "step": "napis", "kind": "ask", "nn": 1},
             {"ts": "2099-01-01T00:00:02.000Z", "type": "step_finished", "step": "napis", "kind": "ask",
              "status": "succeeded"},
             {"ts": "2099-01-01T00:00:02.100Z", "type": "step_started", "step": "vystup", "kind": "output", "nn": 2}]
    (d / "events.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines) + '{"ts": "2099-')  # půlka řádku
    # bez zámku run.lock = přerušený (proces skončil); zámek drží jiný proces = běží (nalezy-api 1)
    interrupted = client.get("/projects/alfa/runs").json()["runs"][0]
    assert interrupted == {"run_id": d.name, "status": "přerušen", "state": "interrupted", "cost_usd": None,
                           "duration_s": None, "callback": "", "scenario": "ukazka",
                           "started_at": "2099-01-01T00:00:00.000Z", "finished_at": None, "current_step": "vystup",
                           "steps_total": 2, "fake": None, "current_nn": None, "steps_done": None}
    with held_lock(d):
        running = client.get("/projects/alfa/runs").json()["runs"][0]
        assert running == interrupted | {
            "status": "běží", "state": "running", "current_nn": 2, "steps_done": 1}
        detail = client.get(f"/projects/alfa/runs/{d.name}").json()
        assert detail["state"] == "running" and detail["current_step"] == "vystup"
        assert detail["steps"][-1]["status"] == "running"
    assert client.get(f"/projects/alfa/runs/{d.name}").json()["state"] == "interrupted"  # pád procesu zámek pustí

    # dry_run: jen plan.md a inputs.json, run_id hned
    r = client.post("/projects/alfa/runs", json={"scenario": "ukazka", "inputs": {"tema": "čaj"}, "dry_run": True})
    assert r.status_code == 200 and r.json() == {"run_id": r.json()["run_id"], "dry_run": True}
    assert sorted(x.name for x in (a / "runs" / r.json()["run_id"]).iterdir()) == ["inputs.json", "plan.md"]
    bad = client.post("/projects/alfa/runs", json={"scenario": "ukazka", "dry_run": True,
                                                   "callback_url": "https://n8n.example.com/x"})
    assert bad.status_code == 422 and "dry_run" in bad.json()["details"][0]
    bad = client.post("/projects/alfa/runs", json={"scenario": "ukazka", "callback_url": "http://evil"})
    assert bad.status_code == 422 and bad.json()["details"] == ["callback_url: nezačíná https://"]


@contextmanager
def held_lock(run_dir: Path):
    """Zámek běhu drží jiný proces (jako `agencast run` vedle `serve`); na konci ho zabije."""
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
    """webhook.md: POST /runs dál vyžaduje callback_url a pole dry_run nezná."""
    monkeypatch.setenv("WEBHOOK_TOKEN", TOKEN)
    monkeypatch.setenv("CALLBACK_SECRET", SECRET)
    hook = server.Webhook(wf, fake=Fake(None))
    auth = f"Bearer {TOKEN}"
    s, body = hook.accept(auth, json.dumps({"scenario": "kontrola-tonu"}).encode())
    assert s == 422 and body["details"][0] == "callback_url: chybí nebo nezačíná https://"
    s, body = hook.accept(auth, json.dumps({"scenario": "kontrola-tonu", "dry_run": True,
                                            "callback_url": "https://x.example.com"}).encode())
    assert s == 422 and "neznámé pole 'dry_run'" in body["details"][0]


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
    (tmp_path / "tajne.txt").write_text("tajne")
    r = client.get("/", headers=anon)
    assert r.status_code == 200 and "AgenCast" in r.text and r.headers["content-type"].startswith("text/html")
    r = client.get("/assets/app.js", headers=anon)
    assert r.text == "console.log(1)" and "javascript" in r.headers["content-type"]
    assert "AgenCast" in client.get("/projekty/alfa", headers=anon).text  # hash routing → index.html
    for url in ("/assets/chybi.js", "/..%2Ftajne.txt", "/assets/..%2F..%2Ftajne.txt"):
        assert client.get(url, headers=anon).status_code == 404, url
    assert client.get("/projects", headers=anon).status_code == 401  # token dál chrání API
    assert "access-control-allow-origin" not in client.get("/", headers=anon).headers
    assert client.options("/projects").status_code == 404

    srv, cors = serve(projects=projects)
    srv.cors = "http://localhost:5173"
    try:
        r = cors.options("/projects/alfa", headers={"Origin": "http://localhost:5173"})
        assert r.status_code == 204 and r.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert "Authorization" in r.headers["access-control-allow-headers"]
        assert "PATCH" in r.headers["access-control-allow-methods"]
        assert cors.get("/projects").headers["access-control-allow-origin"] == "http://localhost:5173"
    finally:
        cors.close()
        srv.shutdown()
        srv.server_close()


def test_projects_list_survives_root_without_workflows(registry_server):
    """0.15.1: zapsaný kořen bez workflows/ (smazaný worktree) nesmí shodit GET /projects na 500."""
    import yaml
    from agencast.projects import registry_path
    reg = registry_path()
    data = yaml.safe_load(reg.read_text())
    data["projects"].append({"name": "zmizely", "root": "/tmp/agencast-neexistuje-xyz"})
    reg.write_text(yaml.safe_dump(data, allow_unicode=True))
    _, client, _, _ = registry_server
    r = client.get("/projects")
    assert r.status_code == 200
    items = {p["name"]: p for p in r.json()["projects"]}
    assert items["alfa"]["available"] is True
    z = items["zmizely"]
    assert z["available"] is False and "workflows" in z["reason"]
    assert z["spend_today_usd"] == 0 and z["last_run"] is None and z["counts"] == {"scenarios": 0, "agents": 0}
