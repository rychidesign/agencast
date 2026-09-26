"""limits.max_parallel_runs a daily_budget_usd (ISSUES 40): sloty `_slots/`, denní kniha `_ledger/`."""
import json
import threading
from datetime import datetime, timezone

import pytest
from conftest import events, run, scenario

from agencast import engine
from agencast.cli import main
from agencast.task import local_slots

SC = """version: 1
name: NAME
description: Testovací scénář
outputs: { text: { type: string } }
steps:
  - id: napis
    ask: { agent: copywriter, prompt: "Pozdrav" }
  - id: out
    output: { text: "{{ steps.napis.text }}" }
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
    threads = [threading.Thread(target=lambda: runs.append(run(path, script={"napis": {"text": "ahoj", "sleep": 0.5}})[0]))
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [r.status for r in runs] == ["succeeded", "succeeded"], [r.error for r in runs]
    first, second = runs  # druhý v seznamu doběhl později = čekal
    assert events(first, "run_waiting") == []
    w = events(second, "run_waiting")
    assert len(w) == 1 and w[0]["max_parallel_runs"] == 1 and w[0]["waited_s"] > 0.2
    assert [e["type"] for e in second.rec.events[:2]] == ["run_started", "run_waiting"]
    assert events(first, "run_finished")[0]["ts"] <= events(second, "step_started")[0]["ts"]  # nepřekrývají se


def test_slot_wait_over_run_timeout_is_timeout(wf, capsys):
    limits(wf, "max_parallel_runs: 1", run_timeout="1s")
    path = scenario(wf, SC)
    slots = local_slots(wf.parent / "runs", 1)
    held = slots.acquire()                      # slot drží jiný proces (n8n, cron…)
    try:
        r, fake = run(path)
    finally:
        slots.release(held)
    assert "čekám na volný slot (max_parallel_runs=1)" in capsys.readouterr().err
    assert r.error == {"class": "timeout", "step": None,
                       "message": "volný slot se neuvolnil do run_timeout 1s (max_parallel_runs=1) — běh nezačal"}
    assert fake.calls == [] and events(r, "run_waiting")[0]["waited_s"] >= 1
    assert json.loads((r.rec.dir / "callback.json").read_text())["error"]["class"] == "timeout"
    r2, _ = run(path)                           # slot je zase volný (uvolní se i po chybě)
    assert r2.status == "succeeded" and events(r2, "run_waiting") == []


def test_daily_budget_exhausted_before_any_call(wf, capsys):
    limits(wf, "daily_budget_usd: 0.5")
    path = scenario(wf, SC)
    book = wf.parent / "runs" / "_ledger-fake" / f"{today()}.jsonl"
    book.parent.mkdir(parents=True)
    book.write_text('{"run_id": "a", "cost_usd": 0.3, "finished_at": "x"}\n'
                    '{"run_id": "b", "cost_usd": 0.2, "finished_at": "x"}\n')
    r, fake = run(path)
    msg = f"denní limit útraty vyčerpán: dnes ({today()} UTC) už 0,5000 z 0.5 USD (daily_budget_usd) — běh nezačal"
    assert r.error == {"class": "budget", "step": None, "message": msg}
    assert fake.calls == [] and events(r, "step_started") == []
    assert json.loads((r.rec.dir / "callback.json").read_text())["error"]["message"] == msg
    assert main(["run", "test", "--fake", "--project", str(wf.parent)]) == 1         # hláška CLI
    assert f"budget: {msg}" in capsys.readouterr().err
    assert not (wf.parent / "runs" / "_ledger").exists()                               # ostrá kniha nevznikla


def test_ledger_filled_after_run_fake_separate(wf):
    limits(wf, "daily_budget_usd: 5")
    path = scenario(wf, SC)
    r1, _ = run(path, script={"napis": {"text": "a", "cost": 0.25}})
    r2, _ = run(path, script={"napis": {"text": "b", "cost": 0.5}})
    assert r1.status == r2.status == "succeeded"
    rows = ledger_rows(wf)
    assert [(x["run_id"], x["cost_usd"]) for x in rows] == [(r1.run_id, 0.25), (r2.run_id, 0.5)]
    assert rows[1]["finished_at"].startswith(today()) and rows[1]["finished_at"].endswith("Z")
    assert not (wf.parent / "runs" / "_ledger").exists()
    assert engine.local_ledger(wf.parent / "runs", True).total(today()) == 0.75
