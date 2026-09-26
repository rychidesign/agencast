"""Čtecí API `serve` (api.md): režim registru s AGENCAST_TOKEN a jeden projekt; falešný poskytovatel."""
import threading

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
        {"name": "alfa", "root": str(a), "available": True}, {"name": "beta", "root": str(b), "available": True}]}
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
        (p,) = client.get("/projects").json()["projects"]
        assert p == {"name": default_name(wf.parent), "root": str(wf.parent.resolve()), "available": True}
        api.add_project(wf.parent, "muj")
        assert client.get("/projects").json()["projects"][0]["name"] == "muj"
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


def test_serve_registry_needs_token(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENCAST_TOKEN", raising=False)
    assert main(["serve", "--port", "0"]) == 2
    assert "AGENCAST_TOKEN" in capsys.readouterr().err
