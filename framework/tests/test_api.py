"""Čtecí API `serve` (api.md): režim registru s AGENCAST_TOKEN a jeden projekt; falešný poskytovatel."""
import threading
from pathlib import Path

import httpx
import pytest
from test_webhook import SECRET, TOKEN, Receiver, finished

from agencast import api
from agencast.cli import main
from agencast.fake import Fake
from agencast.projects import default_name
from agencast.server import Projects, Server, Webhook
from agencast.task import local_ledger


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


def test_registry_mode_read_api(registry_server):
    projects, client, a, b = registry_server
    assert client.get("/projects", headers={"Authorization": "Bearer spatne"}).status_code == 401
    assert client.get("/projects").json() == {"projects": [
        {"name": "alfa", "root": str(a), "available": True, "last_run": None,
         "counts": {"scenarios": 1, "agents": 1}, "spend_today_usd": 0},
        {"name": "beta", "root": str(b), "available": True, "last_run": None,
         "counts": {"scenarios": 1, "agents": 1}, "spend_today_usd": 0}],
        "registry": str(a.parent / "agencast-config" / "projects.yaml"),
        "projects_root": str(api.projects_root()), "writable": True}
    p = client.get("/projects/alfa").json()
    assert p["name"] == "alfa" and p["models"]["chytry"] == "anthropic/claude-haiku-4.5" and p["errors"] == []
    (sc,) = p["scenarios"]
    assert (sc["name"], sc["steps_count"], sc["callable"], sc["errors"]) == ("ukazka", 2, False, [])
    assert p["agents"][0]["model_id"] == "anthropic/claude-haiku-4.5"
    assert p["links"]["scenario_agent"] == [["ukazka", "pisatel"]] and p["limits"]["run_timeout"] == "1h"
    steps = client.get("/projects/alfa/scenarios/ukazka").json()["steps"]
    assert [(s["nn"], s["id"], s["type"]) for s in steps] == [(1, "napis", "ask"), (2, "vystup", "output")]
    assert steps[0]["agent"] == "pisatel" and steps[1]["refs"] == ["steps.napis.text"]
    for url in ("/projects/nic", "/projects/alfa/scenarios/nic", "/projects/alfa/runs/20260101-000000-x-abcd",
                "/projects/alfa/nic"):
        r = client.get(url)
        assert r.status_code == 404 and r.json()["error"], url
    assert client.post("/runs", json={}).status_code == 404  # bez projektu jen /projects/<p>/runs

    rcv = Receiver()
    r = client.post("/projects/alfa/runs", json={"scenario": "ukazka", "callback_url": rcv.url})
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    finished(projects.hooks[a], run_id)
    assert rcv.wait()[0]["status"] == "succeeded"
    assert [x["run_id"] for x in client.get("/projects/alfa/runs").json()["runs"]] == [run_id]
    d = client.get(f"/projects/alfa/runs/{run_id}").json()
    assert d["status"] == "succeeded" and [(s["step"], s["status"]) for s in d["steps"]] == [
        ("napis", "succeeded"), ("vystup", "succeeded")]
    assert d["steps"][0]["cost_usd"] > 0 and "summary.md" in d["files"] and "events.jsonl" in d["files"]
    f = client.get(f"/projects/alfa/runs/{run_id}/files/summary.md")
    assert f.status_code == 200 and "# ukazka — úspěch" in f.text
    assert client.get(f"/projects/alfa/runs/{run_id}/files/steps/01-napis/output.json").json()
    for rel in ("%2e%2e/%2e%2e/workflows/config.yaml", "..%2F..%2F.env.example", "%2Fetc%2Fpasswd", "nic.md"):
        assert client.get(f"/projects/alfa/runs/{run_id}/files/{rel}").status_code == 404, rel
    assert projects.get(f"Bearer {TOKEN}", f"/projects/alfa/runs/{run_id}/files/../../../.env.example", "")[0] == 404
    assert client.get("/projects/beta/runs").json() == {"runs": []}

    local_ledger(a / "runs", False).add("2000-01-01", {"run_id": "x", "cost_usd": 0.25, "finished_at": "…"})
    local_ledger(a / "runs", False).add("2000-01-01", {"run_id": "y", "cost_usd": 0.05, "finished_at": "…"})
    s = client.get("/projects/alfa/spend", params={"day": "2000-01-01"}).json()
    assert s["total_usd"] == 0.3 and [x["run_id"] for x in s["runs"]] == ["x", "y"]
    assert client.get("/projects/alfa/spend").json()["runs"] == []  # dnešek: falešné běhy mají vlastní knihu
    assert client.get("/projects/alfa/spend", params={"day": "včera"}).status_code == 422

    (b / "workflows" / "config.yaml").unlink()
    assert client.get("/projects").json()["projects"][1]["available"] is False
    assert "nedostupný" in client.get("/projects/beta").json()["error"]


def test_single_project_mode(wf, monkeypatch):
    """Dnešní serve v projektu: /runs beze změny, /projects s tímhle jedním projektem a jeho tokenem."""
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
                     "last_run": None, "counts": counts, "spend_today_usd": 0}
        listing = client.get("/projects").json()
        assert listing["writable"] is False and listing["projects_root"] == str(api.projects_root())
        api.add_project(wf.parent, "muj")
        assert client.get("/projects").json()["projects"][0]["name"] == "muj"
        for response in (client.post("/projects", json={"root": str(wf.parent)}),
                         client.post("/projects/new", json={"name": "novy"}),
                         client.delete("/projects/muj")):
            assert response.status_code == 405 and "režimu registru" in response.json()["error"]
        assert (wf.parent / "workflows" / "config.yaml").is_file()
        assert "ig-post" in [s["name"] for s in client.get("/projects/muj").json()["scenarios"]]
        rcv = Receiver()
        body = {"scenario": "kontrola-tonu", "inputs": {"text": "Ahoj"}, "callback_url": rcv.url}
        run_id = client.post("/projects/muj/runs", json=body).json()["run_id"]
        finished(hook, run_id)
        assert client.get(f"/runs/{run_id}").json()["status"] == "succeeded"
        assert client.get(f"/projects/muj/runs/{run_id}").json()["status"] == "succeeded"
        assert client.post("/projects/jiny/runs", json=body).status_code == 404
        sw = client.get("/projects/muj/scenarios/ukazka-call").json()["steps"]
        assert [s["call"] for s in sw if s["type"] == "call"] == ["kontrola-tonu"]
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

        created = client.post("/projects/new", json={"name": "nova"})
        assert created.status_code == 201
        body = created.json()
        root = workspace / "nova"
        assert body["name"] == "nova" and body["root"] == str(root)
        assert {Path(path).relative_to(root).as_posix() for path in body["created"]} == {
            ".env.example", ".gitignore", "workflows/config.yaml", "workflows/agents/pisatel.md",
            "workflows/scenarios/ukazka.yaml"}
        assert [p["name"] for p in client.get("/projects").json()["projects"]] == ["nova"]
        assert "projects_root:" in registry.read_text()
        assert client.post("/projects/new", json={"name": "nova"}).status_code == 409
        exists = client.post("/projects/new", json={"name": "jin", "root": str(root)})
        assert exists.status_code == 409 and "přidej existující" in exists.json()["error"]

        imported = workspace / "imported"
        api.new_project(imported, "odlozeny")
        api.remove_project("odlozeny")
        registered = client.post("/projects", json={"root": "imported", "name": "import"})
        assert registered.status_code == 201 and registered.json() == {"name": "import", "root": str(imported)}
        assert client.post("/projects", json={"root": str(imported)}).status_code == 409
        assert client.post("/projects", json={"root": "../mimo"}).status_code == 422
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
        assert "soubory zůstávají" in removed.json()["message"]
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
    """Editační operace přes HTTP (api.md „Editace“): etag, 409, 422, 404 mimo workflows/, stejný token."""
    _, client, a, _ = registry_server
    sc = client.get("/projects/alfa/scenarios/ukazka").json()
    assert [s["address"] for s in sc["steps"]] == [["steps", 0], ["steps", 1]]
    assert client.put("/projects/alfa/scenarios/ukazka", json={"etag": sc["etag"], "fields": {}},
                      headers={"Authorization": "Bearer spatne"}).status_code == 401
    step = {"id": "zkrat", "ask": {"agent": "pisatel", "prompt": "Zkrať: {{ steps.napis.text }}"}}
    r = client.post("/projects/alfa/scenarios/ukazka/steps", json={"etag": sc["etag"], "after": ["steps", 0], "step": step})
    assert r.status_code == 200 and r.json()["errors"] == []
    tag = r.json()["etag"]
    stale = client.patch("/projects/alfa/scenarios/ukazka/steps/1", json={"etag": sc["etag"], "fields": {"timeout": "1m"}})
    assert stale.status_code == 409 and stale.json()["etag"] == tag
    bad = client.patch("/projects/alfa/scenarios/ukazka/steps/1",
                       json={"etag": tag, "fields": {"ask": {"agent": "nikdo"}}})
    assert bad.status_code == 422
    (e,) = [e for e in bad.json()["errors"] if "nikdo" in e["message"]]  # 0.6.0: chyby jako objekty
    assert e == {"message": 'ukazka.yaml: krok "zkrat": agent \'nikdo\' neexistuje (agents/nikdo.md)',
                 "file": "scenarios/ukazka.yaml", "step": "zkrat"}
    r = client.post("/projects/alfa/scenarios/ukazka/steps/1/move", json={"etag": tag, "to": ["steps"]})
    assert r.status_code == 422  # zkrat by odkazoval na krok, který běží až po něm
    r = client.patch("/projects/alfa/scenarios/ukazka/steps/1", json={"etag": tag, "fields": {"timeout": "1m"}})
    assert r.status_code == 200
    assert client.request("DELETE", "/projects/alfa/scenarios/ukazka/steps/9", json={"etag": r.json()["etag"]}).status_code == 404
    r = client.request("DELETE", "/projects/alfa/scenarios/ukazka/steps/1", json={"etag": r.json()["etag"]})
    assert r.status_code == 200
    f = client.get("/projects/alfa/files/scenarios/ukazka.yaml").json()
    assert f["etag"] == r.json()["etag"] and f["data"]["name"] == "ukazka" and "zkrat" not in f["text"]
    assert client.put("/projects/alfa/files/scenarios/ukazka.yaml",
                      json={"etag": f["etag"], "text": "# nahoře\n" + f["text"]}).status_code == 200
    assert (a / "workflows" / "scenarios" / "ukazka.yaml").read_text().startswith("# nahoře\n")
    for url in ("/projects/alfa/files/..%2F.env", "/projects/alfa/files/%2e%2e/.env", "/projects/alfa/files/.env",
                "/projects/alfa/files/agents/..%2F..%2F.env.example", "/projects/beta/files/runs/x.yaml"):
        assert client.get(url).status_code == 404, url
        assert client.put(url, json={"etag": None, "text": "X=1"}).status_code == 404, url
    assert not (a / "workflows" / ".env").exists()

    # agent: new přes HTTP, PUT, DELETE odmítnutý, když ho scénář používá
    r = client.post("/projects/alfa/agents", json={"name": "redaktor"})
    assert r.status_code == 200
    r = client.put("/projects/alfa/agents/redaktor", json={"etag": r.json()["etag"],
                                                           "frontmatter": {"description": "Rediguje"}, "body": "Rediguj.\n"})
    assert r.status_code == 200
    assert client.request("DELETE", "/projects/alfa/agents/redaktor", json={"etag": r.json()["etag"]}).status_code == 200
    pis = client.get("/projects/alfa/files/agents/pisatel.md").json()
    assert pis["frontmatter"]["name"] == "pisatel"
    r = client.request("DELETE", "/projects/alfa/agents/pisatel", json={"etag": pis["etag"]})
    assert r.status_code == 422 and "ukazka" in r.json()["errors"][0]["message"]
    assert client.post("/projects/alfa/scenarios", json={"name": "druhy"}).status_code == 200
    assert client.post("/projects/alfa/scenarios", json={"name": "druhy"}).status_code == 422  # nepřepisuje

    # skill a config
    r = client.put("/projects/alfa/skills/hlas", json={"etag": None, "text": "---\nname: hlas\ndescription: Tón\n---\nTykáme.\n"})
    assert r.status_code == 200
    assert client.request("DELETE", "/projects/alfa/skills/hlas", json={"etag": r.json()["etag"]}).status_code == 200
    c = client.get("/projects/alfa/files/config.yaml").json()
    r = client.put("/projects/alfa/config", json={"etag": c["etag"], "fields": {"limits": {"run_budget_usd": 2}}})
    assert r.status_code == 200 and client.get("/projects/alfa").json()["limits"]["run_budget_usd"] == 2
    assert client.put("/projects/alfa/config", json={"etag": r.json()["etag"], "fields": {"version": 2}}).status_code == 422
    assert client.put("/projects/alfa/nic", json={}).status_code == 404
