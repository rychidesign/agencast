"""Webhook server (webhook.md): 401/422 without run_id, 202 + callback, request_key
idempotency, sequential queue, HMAC signature, callback_failed. The server and
callback receiver run locally in threads with a fake provider."""
import hashlib
import hmac
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from conftest import SECRET, TOKEN, model_ids, scenario

from agencast.fake import Fake
from agencast import api
from agencast.server import Server, Webhook

class Receiver:
    """Local callback receiver; `status` = response status."""

    def __init__(self, status=200):
        self.status, self.got = status, []
        me = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                me.got.append(({k.lower(): v for k, v in self.headers.items()}, body))
                self.send_response(me.status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/cb?resume=secret"

    def wait(self, n=1, timeout=10.0):
        end = time.monotonic() + timeout
        while len(self.got) < n:
            assert time.monotonic() < end, f"callback did not arrive ({len(self.got)} of {n})"
            time.sleep(0.02)
        return [json.loads(b) for _, b in self.got]


def finished(hook, run_id, timeout=10.0):
    """The run is fully finished, including its callback and events — only then does the server delete the queue entry.
    (The receiver gets the callback before the framework records callback_sent: waiting only for it creates a race.)"""
    end = time.monotonic() + timeout
    while (hook.qdir / f"{run_id}.json").exists():
        assert time.monotonic() < end, f"run {run_id} did not finish"
        time.sleep(0.02)


def hold(hook) -> threading.Event:
    """The worker does not start a run until the test calls .set() — queue ordering without relying on timing."""
    gate, execute = threading.Event(), hook.execute
    hook.execute = lambda entry: (gate.wait(10), execute(entry))[1]
    return gate


def start(wf, script=None, workers=1):
    hook = Webhook(wf, fake=Fake(script, model_ids(wf)), workers=workers)
    hook.start()
    srv = Server(hook, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    client = httpx.Client(base_url=f"http://127.0.0.1:{srv.server_address[1]}",
                          headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10)
    return hook, srv, client


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("WEBHOOK_TOKEN", TOKEN)
    monkeypatch.setenv("CALLBACK_SECRET", SECRET)


@pytest.fixture
def server(wf, env):
    started = []

    def make(script=None, workers=1):
        started.append(start(wf, script, workers))
        return started[-1]
    yield make
    for _, srv, client in started:
        client.close()
        srv.shutdown()
        srv.server_close()


def req(rcv, **kw):
    return {"scenario": "tone-check", "inputs": {"text": "Hi, want some coffee?"}, "callback_url": rcv.url, **kw}


def no_runs(wf):
    runs = wf.parent / "runs"
    return [p.name for p in runs.glob("*") if not p.name.startswith("_")] == [] and not list(
        (runs / "_queue").glob("*.json"))


# --- synchronous rejection ------------------------------------------------------------------

def test_401_without_or_with_wrong_token(wf, server):
    _, _, client = server()
    rcv = Receiver()
    r = client.post("/runs", json=req(rcv), headers={"Authorization": ""})
    assert r.status_code == 401 and "run_id" not in r.json()
    assert client.post("/runs", json=req(rcv), headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/runs/20260925-140311-ig-post-a1b2", headers={"Authorization": ""}).status_code == 401
    assert no_runs(wf) and rcv.got == []


@pytest.mark.parametrize("body,msg", [
    ({"scenario": "nonexistent"}, "unknown scenario 'nonexistent'"),
    ({"scenario": "../config"}, "scenario: missing"),
    ({"callback_url": None}, "callback_url"),
    ({"callback_url": "http://caller.example.com/w"}, "callback_url"),
    ({"inputs": {}}, "missing required input 'text'"),
    ({"inputs": {"text": 1}}, "input 'text' must be string"),
    ({"inputs": {"text": "x", "extra": 1}}, "unknown input 'extra'"),
    ({"scenario": "broken"}, "unknown name"),
    ({"scenario": "file", "inputs": {"image": "/etc/passwd"}}, "has type file"),
    ({"topic": "x"}, "unknown field 'topic'"),
    ({"request_key": ""}, "request_key"),
])
def test_422_without_run_id(wf, server, body, msg):
    scenario(wf, "version: 1\nname: NAME\ndescription: x\nsteps: [{ id: a, set: { x: missing } }]\n", "broken")
    scenario(wf, "version: 1\nname: NAME\ndescription: x\ninputs: { image: { type: file, required: true } }\n"
                 "steps: [{ id: a, set: { x: 1 } }]\n", "file")
    _, _, client = server()
    rcv = Receiver()
    r = client.post("/runs", json={k: v for k, v in {**req(rcv), **body}.items() if v is not None})
    assert r.status_code == 422, r.text
    assert "run_id" not in r.json() and msg in json.dumps(r.json(), ensure_ascii=False), r.json()
    assert no_runs(wf) and rcv.got == []


def test_422_all_errors_at_once(wf, server):
    """BUGS 9: unknown field and invalid input in one response."""
    _, _, client = server()
    r = client.post("/runs", json={**req(Receiver()), "priority": 1, "inputs": {"text": 1}})
    assert r.status_code == 422 and r.json()["details"][0].startswith("unknown field 'priority'")
    assert any("input 'text' must be string" in d for d in r.json()["details"]), r.json()


def test_422_not_json(wf, server):
    _, _, client = server()
    assert client.post("/runs", content=b"{missing").json()["error"] == "body is not valid JSON"


def test_scenario_link_outside_project_is_never_run(wf, env, tmp_path):
    marker, other = tmp_path / "marker", tmp_path / "other"
    other_wf = other / "workflows"
    (other_wf / "agents").mkdir(parents=True)
    (other_wf / "scenarios").mkdir()
    (other_wf / "config.yaml").write_text((wf / "config.yaml").read_text())
    (other_wf / "mcp.yaml").write_text(f"""version: 1
servers:
  marker:
    description: Starts a marker
    command: {json.dumps(sys.executable)}
    args: {json.dumps(["-c", "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()", str(marker)])}
    agents: [evil]
""")
    (other_wf / "agents" / "evil.md").write_text("""---
version: 1
name: evil
description: Starts an MCP server
model: smart
mcp: [marker]
tools: { marker: [tool] }
limits: { max_turns: 1, budget_usd: 0.01 }
---
Start the tool.
""")
    (other_wf / "scenarios" / "evil.yaml").write_text("""version: 1
name: evil
description: Starts an MCP server
steps: [{ id: task, task: { agent: evil, prompt: Start } }]
""")
    (wf / "scenarios" / "evil.yaml").symlink_to(other_wf / "scenarios" / "evil.yaml")
    rcv = Receiver()
    hook, srv, client = start(wf)
    try:
        body = {"scenario": "evil", "inputs": {}, "callback_url": rcv.url}
        result = client.post("/runs", json=body)
        assert result.status_code == 422 and result.json() == {"error": "unknown scenario 'evil'", "details": []}
        assert hook.accept(f"Bearer {TOKEN}", json.dumps({"scenario": "evil", "inputs": {}, "dry_run": True}).encode(),
                           gui=True) == (422, {"error": "unknown scenario 'evil'", "details": []})
    finally:
        client.close()
        srv.shutdown()
        srv.server_close()
    assert not marker.exists() and no_runs(wf) and not (other / "runs").exists()

    run_id = "20260925-140000-evil-aaaa"
    waiting = {"run_id": run_id, "scenario": "evil", "inputs": {}, "callback_url": rcv.url,
               "request_key": None, "queued_ns": 1}
    runs = wf.parent / "runs"
    (runs / "_queue").mkdir(parents=True, exist_ok=True)
    (runs / "_queue" / f"{run_id}.json").write_text(json.dumps(waiting))
    hook, srv, client = start(wf)
    try:
        callback = rcv.wait()[0]
        finished(hook, run_id)
    finally:
        client.close()
        srv.shutdown()
        srv.server_close()
    assert callback["run_id"] == run_id and callback["status"] == "failed"
    assert callback["error"]["class"] == "config"
    assert (runs / run_id).is_dir() and not marker.exists() and not (other / "runs").exists()


# --- 202, callback, idempotence ------------------------------------------------------------------

def test_202_and_signed_callback(wf, server):
    hook, _, client = server()
    rcv = Receiver()
    r = client.post("/runs", json=req(rcv, request_key="caller-1"))
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    assert r.json()["queue_position"] == 1
    cb = rcv.wait()[0]
    finished(hook, run_id)
    headers, raw = rcv.got[0]
    assert headers["x-run-id"] == run_id
    assert headers["x-signature"] == "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    assert cb["run_id"] == run_id and cb["status"] == "succeeded" and cb["request_key"] == "caller-1"
    assert cb["outputs"] == {"on_brand": 0.5, "passed": False}
    assert cb["report_url"].startswith("file://") and cb["report_url"].endswith("/report.html")
    d = hook.runs / run_id
    assert json.loads((d / "callback.json").read_text()) == cb
    sent = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if '"callback_sent"' in x]
    assert sent[0]["url"].endswith("/cb") and "secret" not in sent[0]["url"]  # only the URL path is logged, without the query
    st = client.get(f"/runs/{run_id}").json()
    assert st["status"] == "succeeded" and st["callback_failed"] is False
    assert client.get("/runs/20260925-140311-missing-a1b2").status_code == 404


def test_request_key_is_idempotent_across_restart(wf, server):
    hook, _, client = server()
    rcv = Receiver()
    first = client.post("/runs", json=req(rcv, request_key="caller-4711")).json()
    again = client.post("/runs", json=req(rcv, request_key="caller-4711"))
    assert again.status_code == 200 and again.json() == {"run_id": first["run_id"], "queue_position": None}
    finished(hook, first["run_id"])  # otherwise the new server would treat the unfinished queue entry as an interrupted run
    _, _, client2 = server()  # restart: new server using the same run directory
    third = client2.post("/runs", json=req(rcv, request_key="caller-4711"))
    assert third.status_code == 200 and third.json()["run_id"] == first["run_id"]
    time.sleep(0.2)
    assert len(rcv.got) == 1
    assert [p.name for p in (wf.parent / "runs").glob("*tone-check*")] == [first["run_id"]]


def test_queue_runs_one_after_another(wf, server):
    hook, _, client = server()
    gate, rcv = hold(hook), Receiver()
    a = client.post("/runs", json=req(rcv)).json()
    b = client.post("/runs", json=req(rcv)).json()
    assert (a["queue_position"], b["queue_position"]) == (1, 2)
    assert client.get(f"/runs/{b['run_id']}").json() == {"run_id": b["run_id"], "status": "queued", "queue_position": 2}
    gate.set()
    cbs = rcv.wait(2)
    assert [c["run_id"] for c in cbs] == [a["run_id"], b["run_id"]]

    def ts(run_id, type_):
        for line in (hook.runs / run_id / "events.jsonl").read_text().splitlines():
            e = json.loads(line)
            if e["type"] == type_:
                return e["ts"]
    assert ts(a["run_id"], "callback_sent") <= ts(b["run_id"], "run_started")  # no overlap


def test_workers_run_in_parallel(wf, server):
    """--workers 2: three requests, two runs overlap, all callbacks arrive."""
    hook, _, client = server({"check": {"sleep": 0.3}}, workers=2)
    gate, rcv = hold(hook), Receiver()
    ids = [client.post("/runs", json=req(rcv)).json()["run_id"] for _ in range(3)]
    assert len(set(ids)) == 3
    gate.set()
    assert sorted(c["run_id"] for c in rcv.wait(3)) == sorted(ids)
    for run_id in ids:
        finished(hook, run_id)
    spans = []
    for run_id in ids:
        ev = [json.loads(x) for x in (hook.runs / run_id / "events.jsonl").read_text().splitlines()]
        spans.append((ev[0]["ts"], next(e["ts"] for e in ev if e["type"] == "run_finished")))
    spans.sort()
    assert spans[1][0] < spans[0][1]  # the second run started before the first finished


def test_validate_failing_after_dequeue_still_sends_callback(wf, server):
    hook, _, client = server()
    gate, rcv = hold(hook), Receiver()
    client.post("/runs", json=req(rcv))
    b = client.post("/runs", json=req(rcv, scenario="demo-call", inputs={"topic": "coffee"})).json()
    (wf / "agents" / "copywriter.md").unlink()  # files change while the request is queued
    gate.set()
    cb = rcv.wait(2)[1]
    assert cb["run_id"] == b["run_id"] and cb["status"] == "failed"
    assert cb["error"]["class"] == "config" and "agent 'copywriter' does not exist" in cb["error"]["message"]


def test_callback_failed_after_three_attempts(wf, server):
    hook, _, client = server()
    rcv = Receiver(status=500)
    run_id = client.post("/runs", json=req(rcv)).json()["run_id"]
    finished(hook, run_id)
    st = client.get(f"/runs/{run_id}").json()
    assert st["status"] == "succeeded" and st["callback_failed"] is True  # run status is unchanged
    events = [json.loads(x) for x in (hook.runs / run_id / "events.jsonl").read_text().splitlines()]
    assert [e["attempt"] for e in events if e["type"] == "callback_sent"] == [1, 2, 3]
    assert events[-1]["type"] == "callback_failed" and events[-1]["attempts"] == 3
    # sent again after a restart and refused again: only a delivered attempt clears the flag, as in `runs`
    log = hook.runs / run_id / "events.jsonl"
    log.write_text(log.read_text() + log.read_text().splitlines()[-2] + "\n")
    assert client.get(f"/runs/{run_id}").json()["callback_failed"] is True
    assert api.runs_list(wf.parent)[0]["callback"] == "callback not delivered"


def test_queue_survives_restart(wf, env):
    rcv = Receiver()
    runs = wf.parent / "runs"
    (runs / "_queue").mkdir(parents=True)
    waiting = {"run_id": "20260925-140000-tone-check-aaaa", "scenario": "tone-check",
               "inputs": {"text": "x"}, "callback_url": rcv.url, "request_key": None, "queued_ns": 1}
    broken = {**waiting, "run_id": "20260925-135959-tone-check-bbbb", "queued_ns": 0}
    interrupted = runs / broken["run_id"]
    interrupted.mkdir()
    prior = [
        {"ts": "2026-09-25T13:59:59.250Z", "type": "run_started", "run_id": broken["run_id"],
         "scenario": "tone-check", "scenario_version": 1, "fake": True},
        {"ts": "2026-09-25T13:59:59.500Z", "type": "step_started", "step": "check", "kind": "jev"},
    ]
    (interrupted / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in prior))
    for e in (waiting, broken):
        (runs / "_queue" / f"{e['run_id']}.json").write_text(json.dumps(e))
    hook, srv, client = start(wf)
    try:
        cbs = rcv.wait(2)
    finally:
        srv.shutdown()
        srv.server_close()
    assert [c["run_id"] for c in cbs] == [broken["run_id"], waiting["run_id"]]
    assert cbs[0]["status"] == "failed" and cbs[0]["error"]["class"] == "internal"
    assert cbs[0]["error"]["step"] == "check"
    events = [json.loads(x) for x in (interrupted / "events.jsonl").read_text().splitlines()]
    assert sum(e["type"] == "run_started" for e in events) == 1
    finished_event = next(e for e in events if e["type"] == "run_finished")
    assert finished_event["status"] == "failed" and finished_event["error"] == {
        "class": "internal", "step": "check", "message": "run interrupted by server restart"}
    detail = api.run_detail(wf.parent, broken["run_id"])
    assert detail["state"] == "interrupted" and detail["started_at"] == prior[0]["ts"]
    assert detail["steps"][0]["status"] == "interrupted"
    assert cbs[1]["status"] == "succeeded"


def test_restart_sends_the_callback_a_stop_cut_short(wf, env, monkeypatch):
    """`serve` stopped while a finished run's callback was being retried: the restart used to run a 'did not start'
    stub over the record — status failed, outputs null, cost 0 in callback.json, summary.md and the callback of a
    run that had succeeded."""
    from agencast import engine
    monkeypatch.setattr(engine, "_STOPPING", None)  # restored after the test: stop_runs sets it for good
    monkeypatch.setattr(engine, "CALLBACK_DELAYS", (30, 30))
    rcv = Receiver(status=500)
    hook, srv, client = start(wf)
    try:
        run_id = client.post("/runs", json=req(rcv)).json()["run_id"]
        d = hook.runs / run_id
        rcv.wait(1)  # attempt 1 was refused; the run waits before attempt 2
        end = time.monotonic() + 10
        while '"callback_sent"' not in (d / "events.jsonl").read_text():  # the receiver has it before the record does
            assert time.monotonic() < end, "attempt 1 was not recorded"
            time.sleep(0.02)
        assert engine.stop_runs() is True
        types = [json.loads(x)["type"] for x in (d / "events.jsonl").read_text().splitlines()]
        assert types[-3:] == ["run_finished", "callback_sent", "callback_failed"]
        assert (hook.qdir / f"{run_id}.json").exists()  # kept for the restart
        assert client.get(f"/runs/{run_id}").json()["callback_failed"] is True
    finally:
        srv.shutdown()
        srv.server_close()
        client.close()
    stored, summary = (d / "callback.json").read_bytes(), (d / "summary.md").read_bytes()
    monkeypatch.setattr(engine, "_STOPPING", None)  # the next `agencast serve`
    rcv.status = 200
    hook, srv, client = start(wf)
    try:
        finished(hook, run_id)
        (_, first), (headers, again) = rcv.got
        assert again == first and json.loads(again)["status"] == "succeeded"  # the run's own result, not a stub
        assert headers["x-signature"] == "sha256=" + hmac.new(SECRET.encode(), again, hashlib.sha256).hexdigest()
        assert ((d / "callback.json").read_bytes(), (d / "summary.md").read_bytes()) == (stored, summary)
        after = [json.loads(x)["type"] for x in (d / "events.jsonl").read_text().splitlines()]
        assert after == types + ["callback_sent"]  # no second run_started/run_finished over the record
        st = client.get(f"/runs/{run_id}").json()
        assert st["status"] == "succeeded" and st["callback_failed"] is False  # delivered after all
        assert api.runs_list(wf.parent)[0]["callback"] == ""
    finally:
        srv.shutdown()
        srv.server_close()
        client.close()


def test_server_needs_token_env(wf, monkeypatch):
    monkeypatch.delenv("WEBHOOK_TOKEN", raising=False)
    monkeypatch.setenv("CALLBACK_SECRET", SECRET)
    with pytest.raises(Exception, match="WEBHOOK_TOKEN"):
        Webhook(wf, fake=Fake(None, model_ids(wf)))
