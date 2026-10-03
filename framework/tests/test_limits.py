"""limits.max_parallel_runs and daily_budget_usd (ISSUES 40): slots `_slots/`, daily ledger `_ledger/`."""
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

import pytest
from conftest import events, run, scenario

from agencast import engine
from agencast.cli import main
from agencast.task import SlotStore, local_slots

SC = """version: 1
name: NAME
description: Test scenario
outputs: { text: { type: string } }
steps:
  - id: write
    ask: { agent: copywriter, prompt: "Say hello" }
  - id: out
    output: { text: "{{ steps.write.text }}" }
"""


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    monkeypatch.setattr(engine, "SLOT_POLL_S", 0.05)


def limits(wf, extra: str, run_timeout="1h"):
    cfg = wf / "config.yaml"
    cfg.write_text(cfg.read_text().replace("run_timeout: 1h", f"run_timeout: {run_timeout}\n  {extra}"))


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def ledger_rows(wf, name="_ledger-fake") -> list[dict]:
    f = wf.parent / "runs" / name / f"{today()}.jsonl"
    return [json.loads(line) for line in f.read_text().splitlines()]


def test_without_keys_no_slots_no_waiting(wf):
    r, _ = run(scenario(wf, SC))
    assert r.status == "succeeded" and events(r, "run_waiting") == []
    assert not (wf.parent / "runs" / "_slots").exists()


def test_one_slot_second_run_waits(wf):
    limits(wf, "max_parallel_runs: 1")
    path = scenario(wf, SC)
    runs = []
    threads = [threading.Thread(target=lambda: runs.append(run(path, script={"write": {"text": "hello", "sleep": 0.5}})[0]))
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [r.status for r in runs] == ["succeeded", "succeeded"], [r.error for r in runs]
    first, second = runs  # second in the list finished later = waited
    assert events(first, "run_waiting") == []
    w = events(second, "run_waiting")
    assert len(w) == 1 and w[0]["max_parallel_runs"] == 1 and w[0]["waited_s"] > 0.2
    assert [e["type"] for e in second.rec.events[:2]] == ["run_started", "run_waiting"]
    assert events(first, "run_finished")[0]["ts"] <= events(second, "step_started")[0]["ts"]  # no overlap


def test_slot_wait_over_run_timeout_is_timeout(wf, capsys):
    limits(wf, "max_parallel_runs: 1", run_timeout="1s")
    path = scenario(wf, SC)
    slots = local_slots(wf.parent / "runs", 1)
    held = slots.acquire()                      # slot held by another process (n8n, cron…)
    try:
        r, fake = run(path)
    finally:
        slots.release(held)
    assert "waiting for a free slot (max_parallel_runs=1)" in capsys.readouterr().err
    assert r.error == {"class": "timeout", "step": None,
                       "message": "no slot became available within run_timeout 1s (max_parallel_runs=1) — run did not start"}
    assert fake.calls == [] and events(r, "run_waiting")[0]["waited_s"] >= 1
    assert json.loads((r.rec.dir / "callback.json").read_text())["error"]["class"] == "timeout"
    r2, _ = run(path)                           # slot is free again (released even after an error)
    assert r2.status == "succeeded" and events(r2, "run_waiting") == []


def test_waiting_run_does_not_start_once_serve_is_stopping(wf, monkeypatch):
    """`stop_runs` interrupts a run in flight, which frees its slot: a request waiting for that slot must not take
    it and start — it stays queued for the next `serve` (no run directory)."""
    limits(wf, "max_parallel_runs: 1", run_timeout="30s")
    path = scenario(wf, SC)
    slots = local_slots(wf.parent / "runs", 1)
    held, got = slots.acquire(), []

    def waiting():
        try:
            run(path)
        except BaseException as e:  # noqa: BLE001 — Interrupted is a KeyboardInterrupt
            got.append(e)
    t = threading.Thread(target=waiting)
    t.start()
    time.sleep(0.5)  # waits for the slot
    monkeypatch.setattr(engine, "_STOPPING", signal.SIGTERM)  # stop_runs
    slots.release(held)                                       # … and the run it interrupted
    t.join(10)
    assert [type(e) for e in got] == [engine.Interrupted]
    assert not list((wf.parent / "runs").glob("2*")) and slots.acquire() is not None  # nothing started, slot given back


def test_daily_budget_exhausted_before_any_call(wf, capsys):
    limits(wf, "daily_budget_usd: 0.5")
    path = scenario(wf, SC)
    book = wf.parent / "runs" / "_ledger-fake" / f"{today()}.jsonl"
    book.parent.mkdir(parents=True)
    book.write_text('{"run_id": "a", "cost_usd": 0.3, "finished_at": "x"}\n'
                    '{"run_id": "b", "cost_usd": 0.2, "finished_at": "x"}\n')
    r, fake = run(path)
    msg = f"daily spend limit exhausted: already 0.5000 today ({today()} UTC) of 0.5 USD (daily_budget_usd) — run did not start"
    assert r.error == {"class": "budget", "step": None, "message": msg}
    assert fake.calls == [] and events(r, "step_started") == []
    assert json.loads((r.rec.dir / "callback.json").read_text())["error"]["message"] == msg
    assert main(["run", "test", "--fake", "--project", str(wf.parent)]) == 1         # CLI message
    assert f"budget: {msg}" in capsys.readouterr().err
    assert not (wf.parent / "runs" / "_ledger").exists()                               # no real ledger created


def test_run_that_cannot_start_never_writes_into_another_run(wf):
    """A given run_id that another process took meanwhile: a run that cannot start (budget, slot timeout) is not
    recorded over that run's directory; only a caller's own `error` (serve after a restart) reuses one."""
    limits(wf, "daily_budget_usd: 0.5")
    path = scenario(wf, SC)
    book = wf.parent / "runs" / "_ledger-fake" / f"{today()}.jsonl"
    book.parent.mkdir(parents=True)
    book.write_text('{"run_id": "a", "cost_usd": 0.5, "finished_at": "x"}\n')
    theirs = wf.parent / "runs" / "20260101-000000-test-aaaa"
    theirs.mkdir()
    (theirs / "events.jsonl").write_text("{}\n")
    with pytest.raises(FileExistsError):
        run(path, run_id=theirs.name)
    assert [p.name for p in theirs.iterdir()] == ["events.jsonl"] and (theirs / "events.jsonl").read_text() == "{}\n"


def test_ledger_filled_after_run_fake_separate(wf):
    limits(wf, "daily_budget_usd: 5")
    path = scenario(wf, SC)
    r1, _ = run(path, script={"write": {"text": "a", "cost": 0.25}})
    r2, _ = run(path, script={"write": {"text": "b", "cost": 0.5}})
    assert r1.status == r2.status == "succeeded"
    rows = ledger_rows(wf)
    assert [(x["run_id"], x["cost_usd"]) for x in rows] == [(r1.run_id, 0.25), (r2.run_id, 0.5)]
    assert rows[1]["finished_at"].startswith(today()) and rows[1]["finished_at"].endswith("Z")
    assert not (wf.parent / "runs" / "_ledger").exists()
    assert engine.local_ledger(wf.parent / "runs", True).total(today()) == 0.75


def test_held_slot_names_its_run(tmp_path):
    """`SlotStore.held_ids`: the run ids in the slot files a live process holds — how every MCP server finds a run
    started through MCP before its directory exists (mcp-server.md “Unfinished runs”). An empty held slot (a dry
    run) names none; the content of a free slot is stale."""
    store, run_id = SlotStore(tmp_path / "_mcp-slots", 4), "20261002-101512-demo-2cf1"
    fd = store.acquire()
    os.pwrite(fd, run_id.encode(), 0)
    child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE, pass_fds=(fd,))
    store.release(fd)  # the child holds it now, as a worker does
    empty = store.acquire()
    try:
        assert store.held_ids() == {run_id}
    finally:
        child.stdin.close()
        child.wait()
    assert store.held_ids() == set() and (tmp_path / "_mcp-slots" / "1.lock").read_text() == run_id
    store.release(empty)
