"""Webhook server (webhook.md): 401/422 bez run_id, 202 + callback, idempotence
request_key, fronta jeden po druhém, podpis HMAC, callback_failed. Server i
přijímač callbacku běží lokálně ve vláknech, poskytovatel je falešný."""
import hashlib
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from conftest import model_ids, scenario

from agencast.fake import Fake
from agencast.server import Server, Webhook

TOKEN, SECRET = "token-webhooku-123", "podpis-callbacku-456"


class Receiver:
    """Lokální přijímač callbacku; `status` = co odpoví."""

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
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/cb?resume=tajne"

    def wait(self, n=1, timeout=10.0):
        end = time.monotonic() + timeout
        while len(self.got) < n:
            assert time.monotonic() < end, f"callback nepřišel ({len(self.got)} z {n})"
            time.sleep(0.02)
        return [json.loads(b) for _, b in self.got]


def finished(hook, run_id, timeout=10.0):
    """Běh je celý hotový včetně callbacku a jeho událostí — server maže záznam fronty až potom.
    (Přijímač má callback dřív, než framework zapíše callback_sent: čekat jen na něj je souběh.)"""
    end = time.monotonic() + timeout
    while (hook.qdir / f"{run_id}.json").exists():
        assert time.monotonic() < end, f"běh {run_id} nedoběhl"
        time.sleep(0.02)


def hold(hook) -> threading.Event:
    """Pracovní vlákno nezačne běh, dokud test nezavolá .set() — pořadí ve frontě bez spoléhání na časy."""
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
    return {"scenario": "kontrola-tonu", "inputs": {"text": "Ahoj, dáš kafe?"}, "callback_url": rcv.url, **kw}


def no_runs(wf):
    runs = wf.parent / "runs"
    return [p.name for p in runs.glob("*") if not p.name.startswith("_")] == [] and not list(
        (runs / "_queue").glob("*.json"))


# --- synchronní odmítnutí ------------------------------------------------------------------

def test_401_without_or_with_wrong_token(wf, server):
    _, _, client = server()
    rcv = Receiver()
    r = client.post("/runs", json=req(rcv), headers={"Authorization": ""})
    assert r.status_code == 401 and "run_id" not in r.json()
    assert client.post("/runs", json=req(rcv), headers={"Authorization": "Bearer spatny"}).status_code == 401
    assert client.get("/runs/20260925-140311-ig-post-a1b2", headers={"Authorization": ""}).status_code == 401
    assert no_runs(wf) and rcv.got == []


@pytest.mark.parametrize("body,msg", [
    ({"scenario": "neexistuje"}, "neznámý scénář 'neexistuje'"),
    ({"scenario": "../config"}, "scenario: chybí"),
    ({"callback_url": None}, "callback_url"),
    ({"callback_url": "http://n8n.example.com/w"}, "callback_url"),
    ({"inputs": {}}, "chybí povinný vstup 'text'"),
    ({"inputs": {"text": 1}}, "vstup 'text' má být string"),
    ({"inputs": {"text": "x", "navic": 1}}, "neznámý vstup 'navic'"),
    ({"scenario": "rozbity"}, "neznámé jméno"),
    ({"scenario": "soubor", "inputs": {"obr": "/etc/passwd"}}, "typu file"),
    ({"tema": "x"}, "neznámé pole 'tema'"),
    ({"request_key": ""}, "request_key"),
])
def test_422_without_run_id(wf, server, body, msg):
    scenario(wf, "version: 1\nname: NAME\ndescription: x\nsteps: [{ id: a, set: { x: nic } }]\n", "rozbity")
    scenario(wf, "version: 1\nname: NAME\ndescription: x\ninputs: { obr: { type: file, required: true } }\n"
                 "steps: [{ id: a, set: { x: 1 } }]\n", "soubor")
    _, _, client = server()
    rcv = Receiver()
    r = client.post("/runs", json={k: v for k, v in {**req(rcv), **body}.items() if v is not None})
    assert r.status_code == 422, r.text
    assert "run_id" not in r.json() and msg in json.dumps(r.json(), ensure_ascii=False), r.json()
    assert no_runs(wf) and rcv.got == []


def test_422_all_errors_at_once(wf, server):
    """BUGS 9: neznámé pole i špatný vstup v jedné odpovědi."""
    _, _, client = server()
    r = client.post("/runs", json={**req(Receiver()), "priorita": 1, "inputs": {"text": 1}})
    assert r.status_code == 422 and r.json()["details"][0].startswith("neznámé pole 'priorita'")
    assert any("vstup 'text' má být string" in d for d in r.json()["details"]), r.json()


def test_422_not_json(wf, server):
    _, _, client = server()
    assert client.post("/runs", content=b"{nic").json()["error"] == "tělo není platný JSON"


# --- 202, callback, idempotence ------------------------------------------------------------------

def test_202_and_signed_callback(wf, server):
    hook, _, client = server()
    rcv = Receiver()
    r = client.post("/runs", json=req(rcv, request_key="n8n-1"))
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    assert r.json()["queue_position"] == 1
    cb = rcv.wait()[0]
    finished(hook, run_id)
    headers, raw = rcv.got[0]
    assert headers["x-run-id"] == run_id
    assert headers["x-signature"] == "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    assert cb["run_id"] == run_id and cb["status"] == "succeeded" and cb["request_key"] == "n8n-1"
    assert cb["outputs"] == {"on_brand": 0.5, "v_poradku": False}
    assert cb["report_url"].startswith("file://") and cb["report_url"].endswith("/report.html")
    d = hook.runs / run_id
    assert json.loads((d / "callback.json").read_text()) == cb
    sent = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if '"callback_sent"' in x]
    assert sent[0]["url"].endswith("/cb") and "tajne" not in sent[0]["url"]  # z URL se loguje jen cesta bez query
    st = client.get(f"/runs/{run_id}").json()
    assert st["status"] == "succeeded" and st["callback_failed"] is False
    assert client.get("/runs/20260925-140311-nic-a1b2").status_code == 404


def test_request_key_is_idempotent_across_restart(wf, server):
    hook, _, client = server()
    rcv = Receiver()
    first = client.post("/runs", json=req(rcv, request_key="n8n-4711")).json()
    again = client.post("/runs", json=req(rcv, request_key="n8n-4711"))
    assert again.status_code == 200 and again.json() == {"run_id": first["run_id"], "queue_position": None}
    finished(hook, first["run_id"])  # jinak by nový server vzal nedokončený záznam fronty jako přerušený běh
    _, _, client2 = server()  # restart: nový server nad stejnou složkou běhů
    third = client2.post("/runs", json=req(rcv, request_key="n8n-4711"))
    assert third.status_code == 200 and third.json()["run_id"] == first["run_id"]
    time.sleep(0.2)
    assert len(rcv.got) == 1
    assert [p.name for p in (wf.parent / "runs").glob("*kontrola-tonu*")] == [first["run_id"]]


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
    assert ts(a["run_id"], "callback_sent") <= ts(b["run_id"], "run_started")  # bez překryvu


def test_workers_run_in_parallel(wf, server):
    """--workers 2: tři požadavky, dva běhy se časově překrývají, všechny callbacky dojdou."""
    hook, _, client = server({"kontrola": {"sleep": 0.3}}, workers=2)
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
    assert spans[1][0] < spans[0][1]  # druhý běh začal dřív, než první skončil


def test_validate_failing_after_dequeue_still_sends_callback(wf, server):
    hook, _, client = server()
    gate, rcv = hold(hook), Receiver()
    client.post("/runs", json=req(rcv))
    b = client.post("/runs", json=req(rcv, scenario="ukazka-call", inputs={"tema": "káva"})).json()
    (wf / "agents" / "copywriter.md").unlink()  # změna souborů, zatímco požadavek čeká ve frontě
    gate.set()
    cb = rcv.wait(2)[1]
    assert cb["run_id"] == b["run_id"] and cb["status"] == "failed"
    assert cb["error"]["class"] == "config" and "agent 'copywriter' neexistuje" in cb["error"]["message"]


def test_callback_failed_after_three_attempts(wf, server):
    hook, _, client = server()
    rcv = Receiver(status=500)
    run_id = client.post("/runs", json=req(rcv)).json()["run_id"]
    finished(hook, run_id)
    st = client.get(f"/runs/{run_id}").json()
    assert st["status"] == "succeeded" and st["callback_failed"] is True  # stav běhu se nemění
    events = [json.loads(x) for x in (hook.runs / run_id / "events.jsonl").read_text().splitlines()]
    assert [e["attempt"] for e in events if e["type"] == "callback_sent"] == [1, 2, 3]
    assert events[-1]["type"] == "callback_failed" and events[-1]["attempts"] == 3


def test_queue_survives_restart(wf, env):
    rcv = Receiver()
    runs = wf.parent / "runs"
    (runs / "_queue").mkdir(parents=True)
    waiting = {"run_id": "20260925-140000-kontrola-tonu-aaaa", "scenario": "kontrola-tonu",
               "inputs": {"text": "x"}, "callback_url": rcv.url, "request_key": None, "queued_ns": 1}
    broken = {**waiting, "run_id": "20260925-135959-kontrola-tonu-bbbb", "queued_ns": 0}
    (runs / broken["run_id"]).mkdir()  # běh začal, pak server spadl
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
    assert cbs[1]["status"] == "succeeded"


def test_server_needs_token_env(wf, monkeypatch):
    monkeypatch.delenv("WEBHOOK_TOKEN", raising=False)
    monkeypatch.setenv("CALLBACK_SECRET", SECRET)
    with pytest.raises(Exception, match="WEBHOOK_TOKEN"):
        Webhook(wf, fake=Fake(None, model_ids(wf)))
