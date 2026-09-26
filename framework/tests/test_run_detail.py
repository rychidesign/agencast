"""API podle nálezů z GUI (agencast 0.7.0, docs/ui/nalezy-api.md): stav běží/přerušen přes run.lock,
podrobnosti kroků a krok běhu, snímek scénáře, pole seznamu běhů, filtr a limit, last_run, typy kroků,
trojice scénář–krok–agent, rozbitý config, důvod nedostupnosti projektu, řádek duplicitního klíče."""
import json
from pathlib import Path

import pytest
from conftest import run
from test_api import registry_server  # noqa: F401 — fixture

from agencast import api, engine
from agencast.loader import LoadError, read_frontmatter, read_yaml
from agencast.record import run_detail, step_detail
from agencast.task import run_locked

GOLDEN = Path(__file__).parent / "golden" / "ukazka-call.yaml"


def write_events(d: Path, events: list[dict]):
    d.mkdir(parents=True, exist_ok=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def test_run_holds_lock_and_snapshots_scenarios(wf, monkeypatch):
    seen = []
    orig = engine.snapshot
    monkeypatch.setattr(engine, "snapshot", lambda p, rec: (seen.append(run_locked(rec.dir)), orig(p, rec)))
    r, _ = run(wf / "scenarios" / "ukazka-call.yaml", {"tema": "káva"}, read_yaml(GOLDEN))
    assert r.status == "succeeded", r.error
    d = r.rec.dir
    assert seen == [True] and not run_locked(d)  # zámek jen po dobu běhu
    for name in ("ukazka-call", "kontrola-tonu"):  # spouštěný i volaný přes call, bajt po bajtu
        assert (d / "scenario" / f"{name}.yaml").read_bytes() == (wf / "scenarios" / f"{name}.yaml").read_bytes()

    root = wf.parent
    (wf / "scenarios" / "ukazka-call.yaml").write_text(
        (wf / "scenarios" / "ukazka-call.yaml").read_text().replace("id: stop", "id: zastav"))
    body = api.run_detail(root, d.name)
    assert body["state"] == "succeeded" and body["fake"] is True and body["tree_source"] == "snapshot"
    assert [s["id"] for s in body["tree"]] == ["copy", "ton", "stop", "out"]  # strom, jak platil při běhu
    assert body["tree"][1] | {"fields": None, "refs": None} == {
        "nn": 2, "address": ["steps", 1], "id": "ton", "type": "call", "when": None, "fields": None, "refs": None,
        "call": "kontrola-tonu"}
    assert list(body["callees"]) == ["kontrola-tonu"] and body["callees"]["kontrola-tonu"][0]["id"] == "kontrola"

    steps = {s["step"]: s for s in body["steps"]}
    assert (steps["ton"]["nn"], steps["ton"]["dir"]) == (2, "steps/02-ton")
    assert (steps["ton/kontrola"]["nn"], steps["ton/kontrola"]["dir"]) == (1, "steps/02-ton/steps/01-kontrola")
    assert steps["ton/kontrola"]["answers"] == {"on_brand": 0.91}
    (call,) = steps["copy"]["calls"]
    assert call | {"duration_s": 0} == {"attempt": 1, "alias": "chytry", "model": call["model"], "input_tokens": 100,
                                        "output_tokens": 20, "cost_usd": 0.0001, "finish_reason": "stop",
                                        "structured_output": "native_schema", "duration_s": 0}
    assert steps["stop"] | {"reason": None} == {
        "step": "stop", "kind": "fail", "nn": 3, "dir": None, "error": None, "continued": False, "default_used": False,
        "calls": [], "status": "skipped", "reason_code": "when", "reason": None}

    one = api.step_detail(root, d.name, "ton/kontrola")
    assert one["output"]["on_brand"] == 0.91 and {e["type"] for e in one["events"]} >= {"step_started", "jev_call"}
    assert all(e["step"] == "ton/kontrola" for e in one["events"])
    assert "steps/02-ton/steps/01-kontrola/calls/01.request.json" in one["files"]
    ton = api.step_detail(root, d.name, "ton")
    assert ton["files"] == ["steps/02-ton/inputs.json", "steps/02-ton/output.json"]  # bez složek vnořených kroků
    assert api.step_detail(root, d.name, "nic") is None and api.step_detail(root, "../x", "copy") is None

    # starší běh bez snímku: strom ze současného souboru s příznakem
    for f in (d / "scenario").iterdir():
        f.unlink()
    (d / "scenario").rmdir()
    body = api.run_detail(root, d.name)
    assert body["tree_source"] == "current" and body["tree"][2]["id"] == "zastav" and body["callees"] == {}


def test_step_details_from_events(tmp_path):
    """Volání task (tahy, nástroje), chyba po posledním pokusu, continued s default a běh před 0.7.0 bez nn/dir."""
    d = tmp_path / "20260926-120000-x-abcd"
    usage = {"input_tokens": 3, "output_tokens": 2, "cost_usd": 0.5}
    write_events(d, [
        {"ts": "t0", "type": "run_started", "scenario": "x", "steps_total": 2, "fake": False},
        {"ts": "t1", "type": "step_started", "step": "hledej", "kind": "task", "nn": 1, "dir": "steps/01-hledej"},
        *({"ts": "t2", "type": "model_call", "step": "hledej", "attempt": 1, "turn": t, "alias": "a", "model": "m",
           "usage": usage, "request_file": "steps/01-hledej/calls/0{t}.request.json"} for t in (1, 2)),
        {"ts": "t3", "type": "tool_call", "step": "hledej", "turn": 1, "server": "fs", "tool": "read"},
        {"ts": "t4", "type": "error", "step": "hledej", "class": "transient", "message": "5xx", "will_retry": True},
        {"ts": "t5", "type": "error", "step": "hledej", "class": "schema", "message": "špatně", "will_retry": False},
        {"ts": "t6", "type": "step_finished", "step": "hledej", "kind": "task", "status": "failed", "continued": True,
         "default_used": True, "duration_s": 1.0, "cost_usd": 1.0},
        # formát před 0.7.0: nn a dir z cesty souboru
        {"ts": "t7", "type": "step_started", "step": "out", "kind": "output"},
        {"ts": "t8", "type": "step_finished", "step": "out", "kind": "output", "status": "succeeded",
         "continued": False, "duration_s": 0, "cost_usd": 0, "output_file": "steps/02-out/output.json"}])
    steps = {s["step"]: s for s in run_detail(d)["steps"]}
    h = steps["hledej"]
    assert (h["turns"], h["tool_calls"], len(h["calls"])) == (2, 1, 2)
    assert h["error"] == {"class": "schema", "message": "špatně"} and h["continued"] and h["default_used"]
    assert (steps["out"]["nn"], steps["out"]["dir"]) == (2, "steps/02-out")
    assert step_detail(d, "out")["output"] is None  # soubor chybí → null, ne chyba


def test_runs_list_fields_filter_limit_and_last_run(registry_server):  # noqa: F811
    projects, client, a, b = registry_server
    runs = a / "runs"
    done = {"ts": "2026-09-26T10:00:05.000Z", "type": "run_finished", "status": "failed", "duration_s": 5,
            "usage": {"cost_usd": 0.25}, "error": {"class": "fail", "step": "napis"}}
    write_events(runs / "20260926-100000-ukazka-0001", [
        {"ts": "2026-09-26T10:00:00.000Z", "type": "run_started", "scenario": "ukazka", "fake": False}, done])
    write_events(runs / "20260926-110000-jiny-0002", [
        {"ts": "2026-09-26T11:00:00.000Z", "type": "run_started", "scenario": "jiny", "fake": True}])
    dry = runs / "20260926-120000-ukazka-0003"
    dry.mkdir()
    (dry / "plan.md").write_text("# Plán: ukazka\n")
    (runs / "_queue").mkdir(parents=True, exist_ok=True)
    for n, (rid, ns) in enumerate([("20260926-130000-ukazka-0004", 2), ("20260926-130001-ukazka-0005", 3),
                                   ("20260926-100000-ukazka-0001", 1)]):  # poslední = běžící (složka už je)
        (runs / "_queue" / f"{rid}.json").write_text(json.dumps({"run_id": rid, "scenario": "ukazka", "queued_ns": ns}))

    items = client.get("/projects/alfa/runs").json()["runs"]
    assert [(x["run_id"][-4:], x["state"]) for x in items] == [
        ("0005", "queued"), ("0004", "queued"), ("0003", "dry_run"), ("0002", "interrupted"), ("0001", "failed")]
    assert [x.get("queue_position") for x in items[:2]] == [3, 2]
    assert items[0]["scenario"] == "ukazka" and items[3]["fake"] is True and items[4]["fake"] is False
    assert (items[2]["scenario"], items[2]["started_at"]) == ("ukazka", "2026-09-26T12:00:00.000Z")
    assert items[4]["status"] == "failed (fail v napis)" and items[3]["status"] == "přerušen"

    only = client.get("/projects/alfa/runs", params={"scenario": "ukazka", "limit": "3"}).json()["runs"]
    assert [x["run_id"][-4:] for x in only] == ["0005", "0004", "0003"]
    assert [x["run_id"][-4:] for x in client.get("/projects/alfa/runs?scenario=jiny").json()["runs"]] == ["0002"]
    assert client.get("/projects/alfa/runs?limit=0").status_code == 422
    first = client.get("/projects/alfa/runs?limit=2").json()
    assert [x["run_id"][-4:] for x in first["runs"]] == ["0005", "0004"]
    assert first["next_before"] == first["runs"][-1]["run_id"]
    second = client.get("/projects/alfa/runs", params={"limit": 2, "before": first["next_before"]}).json()
    assert [x["run_id"][-4:] for x in second["runs"]] == ["0003", "0002"]
    assert second["next_before"] == second["runs"][-1]["run_id"]
    last = client.get("/projects/alfa/runs", params={"limit": 2, "before": second["next_before"]}).json()
    assert [x["run_id"][-4:] for x in last["runs"]] == ["0001"] and "next_before" not in last
    assert client.get("/projects/alfa/runs?before=wrong").status_code == 422
    assert client.get("/projects/alfa/runs/20260926-130000-ukazka-0004").json()["queue_position"] == 2

    for f in (runs / "_queue").glob("*.json"):
        f.unlink()
    (sc,) = client.get("/projects/alfa").json()["scenarios"]
    assert sc["last_run"] == {"run_id": dry.name, "state": "dry_run", "started_at": items[2]["started_at"],
                              "finished_at": None, "cost_usd": None}
    assert sc["types"] == ["ask", "output"]
    listing = client.get("/projects").json()["projects"]
    assert listing[0]["last_run"]["run_id"] == dry.name and listing[1]["last_run"] is None
    assert client.get("/projects/alfa").json()["links"]["scenario_step_agent"] == [["ukazka", "napis", "pisatel"]]

    (b / "workflows" / "config.yaml").rename(b / "workflows" / "config.old")
    beta = client.get("/projects").json()["projects"][1]
    assert beta["available"] is False and beta["last_run"] is None
    assert beta["reason"] == f"chybí {b / 'workflows' / 'config.yaml'}"


def test_broken_config_errors_and_runs_still_readable(registry_server):  # noqa: F811
    _, client, a, _ = registry_server
    cfg = a / "workflows" / "config.yaml"
    text = cfg.read_text()
    run_id = client.post("/projects/alfa/runs", json={"scenario": "ukazka", "dry_run": True}).json()["run_id"]

    cfg.write_text(text + "runs_dir: ./jinde\n")  # duplicitní klíč: loader zná řádek
    f = client.get("/projects/alfa/files/config.yaml").json()
    line = len(text.splitlines()) + 1
    assert f["errors"][0] | {"message": ""} == {"message": "", "file": "config.yaml", "line": line}
    r = client.get("/projects/alfa")
    assert r.status_code == 422 and r.json()["errors"][0]["line"] == line and r.json()["details"][0].startswith("config")
    assert [x["run_id"] for x in client.get("/projects/alfa/runs").json()["runs"]] == [run_id]  # výchozí ./runs
    assert client.get(f"/projects/alfa/runs/{run_id}").json()["state"] == "dry_run"
    assert client.get("/projects/alfa/spend").status_code == 200

    cfg.write_text(text.replace("run_timeout: 1h", "run_timeout: hodina"))  # schéma: řádek loader nezná
    f = client.get("/projects/alfa/files/config.yaml").json()
    assert f["data"]["limits"]["run_timeout"] == "hodina" and f["errors"][0]["file"] == "config.yaml"
    assert f["errors"][0]["line"] == next(i for i, row in enumerate(text.splitlines(), 1)
                                             if row.lstrip().startswith("run_timeout:"))
    assert "run_timeout" in f["errors"][0]["message"]
    assert [x["run_id"] for x in client.get("/projects/alfa/runs").json()["runs"]] == [run_id]  # runs_dir z configu

    (a / "workflows" / "mcp.yaml").write_text("version: 1\nservers:\n  web: { url: https://x.example.com }\n")
    assert client.get("/projects/alfa/files/mcp.yaml").json()["errors"][0]["file"] == "mcp.yaml"


def test_frontmatter_duplicate_key_first_line(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("---\nversion: 1\nname: a\nname: b\n---\ntělo\n")
    with pytest.raises(LoadError) as e:
        read_frontmatter(p, "agents/a.md")
    assert str(e.value) == "agents/a.md, řádek 4: duplicitní klíč 'name' (poprvé na řádku 3)"
