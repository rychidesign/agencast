"""API based on GUI findings (agencast 0.7.0, docs/ui/api-findings.md): running/interrupted status via run.lock,
step details and current run step, scenario snapshot, run list fields, filter and limit, last_run, step types,
scenario–step–agent triples, broken config, reason for project unavailability, duplicate key line."""
import json
import os
from pathlib import Path

import pytest
from conftest import run, scenario

from agencast import api, engine
from agencast.fake import png
from agencast.loader import LoadError, read_frontmatter, read_yaml
from agencast.record import INTERRUPTED_BY_RESTART, run_detail, step_detail
from agencast.task import hold_run_lock, run_locked

GOLDEN = Path(__file__).resolve().parents[2] / "examples" / "showcase" / "fake" / "demo-call.yaml"


def write_events(d: Path, events: list[dict]):
    d.mkdir(parents=True, exist_ok=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def test_restart_records_remain_readable(tmp_path):
    message = INTERRUPTED_BY_RESTART
    write_events(tmp_path, [
        {"ts": "2026-09-29T14:05:00Z", "type": "step_started", "step": "write", "kind": "ask", "nn": 1},
        {"ts": "2026-09-29T14:06:00Z", "type": "run_finished", "status": "failed", "duration_s": 60,
         "usage": {"cost_usd": 0}, "error": {"class": "internal", "step": "write", "message": message}},
    ])
    lock = hold_run_lock(tmp_path)
    try:
        detail = run_detail(tmp_path)
    finally:
        os.close(lock)
    assert detail["status"] == "failed (internal in write)"
    assert detail["state"] == detail["steps"][0]["status"] == "interrupted"


def test_run_holds_lock_and_snapshots_scenarios(wf, monkeypatch):
    seen = []
    orig = engine.snapshot
    monkeypatch.setattr(engine, "snapshot", lambda p, rec: (seen.append(run_locked(rec.dir)), orig(p, rec)))
    r, _ = run(wf / "scenarios" / "demo-call.yaml", {"topic": "coffee"}, read_yaml(GOLDEN))
    assert r.status == "succeeded", r.error
    d = r.rec.dir
    assert seen == [True] and not run_locked(d)  # lock held only during the run
    for name in ("demo-call", "tone-check"):  # both the running scenario and call callee, byte for byte
        assert (d / "scenario" / f"{name}.yaml").read_bytes() == (wf / "scenarios" / f"{name}.yaml").read_bytes()

    root = wf.parent
    (wf / "scenarios" / "demo-call.yaml").write_text(
        (wf / "scenarios" / "demo-call.yaml").read_text().replace("id: stop", "id: halt"))
    body = api.run_detail(root, d.name)
    assert body["state"] == "succeeded" and body["fake"] is True and body["tree_source"] == "snapshot"
    assert [s["id"] for s in body["tree"]] == ["copy", "tone", "stop", "out"]  # tree as it was during the run
    assert body["tree"][1] | {"fields": None, "refs": None} == {
        "nn": 2, "address": ["steps", 1], "id": "tone", "type": "call", "when": None, "fields": None, "refs": None,
        "call": "tone-check"}
    assert list(body["callees"]) == ["tone-check"] and body["callees"]["tone-check"][0]["id"] == "check"

    steps = {s["step"]: s for s in body["steps"]}
    assert (steps["tone"]["nn"], steps["tone"]["dir"]) == (2, "steps/02-tone")
    assert (steps["tone/check"]["nn"], steps["tone/check"]["dir"]) == (1, "steps/02-tone/steps/01-check")
    assert steps["tone/check"]["answers"] == {"on_brand": 0.91}
    (call,) = steps["copy"]["calls"]
    assert call | {"duration_s": 0} == {"attempt": 1, "alias": "smart", "model": call["model"], "input_tokens": 100,
                                        "output_tokens": 20, "cost_usd": 0.0001, "finish_reason": "stop",
                                        "structured_output": "native_schema", "duration_s": 0}
    assert steps["stop"] | {"reason": None} == {
        "step": "stop", "kind": "fail", "nn": 3, "dir": None, "error": None, "continued": False, "default_used": False,
        "calls": [], "status": "skipped", "reason_code": "when", "reason": None}

    one = api.step_detail(root, d.name, "tone/check")
    assert one["output"]["on_brand"] == 0.91 and {e["type"] for e in one["events"]} >= {"step_started", "jev_call"}
    assert all(e["step"] == "tone/check" for e in one["events"])
    assert "steps/02-tone/steps/01-check/calls/01.request.json" in one["files"]
    tone = api.step_detail(root, d.name, "tone")
    assert tone["files"] == ["steps/02-tone/inputs.json", "steps/02-tone/output.json"]  # excluding nested step directories
    assert api.step_detail(root, d.name, "missing") is None and api.step_detail(root, "../x", "copy") is None

    # older run without a snapshot: tree from the current file, with a flag
    for f in (d / "scenario").iterdir():
        f.unlink()
    (d / "scenario").rmdir()
    body = api.run_detail(root, d.name)
    assert body["tree_source"] == "current" and body["tree"][2]["id"] == "halt" and body["callees"] == {}


def test_step_details_from_events(tmp_path):
    """Task calls (turns, tools), error after the last attempt, continued with default and a pre-0.7.0 run without nn/dir."""
    d = tmp_path / "20260926-120000-x-abcd"
    usage = {"input_tokens": 3, "output_tokens": 2, "cost_usd": 0.5}
    write_events(d, [
        {"ts": "t0", "type": "run_started", "scenario": "x", "steps_total": 2, "fake": False},
        {"ts": "t1", "type": "step_started", "step": "search", "kind": "task", "nn": 1, "dir": "steps/01-search"},
        *({"ts": "t2", "type": "model_call", "step": "search", "attempt": 1, "turn": t, "alias": "a", "model": "m",
           "usage": usage, "request_file": "steps/01-search/calls/0{t}.request.json"} for t in (1, 2)),
        {"ts": "t3", "type": "tool_call", "step": "search", "turn": 1, "server": "fs", "tool": "read"},
        {"ts": "t4", "type": "error", "step": "search", "class": "transient", "message": "5xx", "will_retry": True},
        {"ts": "t5", "type": "error", "step": "search", "class": "schema", "message": "invalid", "will_retry": False},
        {"ts": "t6", "type": "step_finished", "step": "search", "kind": "task", "status": "failed", "continued": True,
         "default_used": True, "duration_s": 1.0, "cost_usd": 1.0},
        # pre-0.7.0 format: nn and dir from the file path
        {"ts": "t7", "type": "step_started", "step": "out", "kind": "output"},
        {"ts": "t8", "type": "step_finished", "step": "out", "kind": "output", "status": "succeeded",
         "continued": False, "duration_s": 0, "cost_usd": 0, "output_file": "steps/02-out/output.json"}])
    steps = {s["step"]: s for s in run_detail(d)["steps"]}
    h = steps["search"]
    assert (h["turns"], h["tool_calls"], len(h["calls"])) == (2, 1, 2)
    assert h["error"] == {"class": "schema", "message": "invalid"} and h["continued"] and h["default_used"]
    assert (steps["out"]["nn"], steps["out"]["dir"]) == (2, "steps/02-out")
    assert step_detail(d, "out")["output"] is None  # missing file → null, not an error


def test_runs_list_fields_filter_limit_and_last_run(registry_server):
    projects, client, a, b = registry_server
    runs = a / "runs"
    done = {"ts": "2026-09-26T10:00:05.000Z", "type": "run_finished", "status": "failed", "duration_s": 5,
            "usage": {"cost_usd": 0.25}, "error": {"class": "fail", "step": "write"}}
    write_events(runs / "20260926-100000-demo-0001", [
        {"ts": "2026-09-26T10:00:00.000Z", "type": "run_started", "scenario": "demo", "fake": False}, done])
    write_events(runs / "20260926-110000-other-0002", [
        {"ts": "2026-09-26T11:00:00.000Z", "type": "run_started", "scenario": "other", "fake": True}])
    dry = runs / "20260926-120000-demo-0003"
    dry.mkdir()
    (dry / "plan.md").write_text("# Plan: demo\n")
    (runs / "_queue").mkdir(parents=True, exist_ok=True)
    for n, (rid, ns) in enumerate([("20260926-130000-demo-0004", 2), ("20260926-130001-demo-0005", 3),
                                   ("20260926-100000-demo-0001", 1)]):  # last = running (directory already exists)
        (runs / "_queue" / f"{rid}.json").write_text(json.dumps({"run_id": rid, "scenario": "demo", "queued_ns": ns}))

    items = client.get("/projects/alpha/runs").json()["runs"]
    assert [(x["run_id"][-4:], x["state"]) for x in items] == [
        ("0005", "queued"), ("0004", "queued"), ("0003", "dry_run"), ("0002", "interrupted"), ("0001", "failed")]
    assert [x.get("queue_position") for x in items[:2]] == [3, 2]
    assert items[0]["scenario"] == "demo" and items[3]["fake"] is True and items[4]["fake"] is False
    assert (items[2]["scenario"], items[2]["started_at"]) == ("demo", "2026-09-26T12:00:00.000Z")
    assert items[4]["status"] == "failed (fail in write)" and items[3]["status"] == "interrupted"

    only = client.get("/projects/alpha/runs", params={"scenario": "demo", "limit": "3"}).json()["runs"]
    assert [x["run_id"][-4:] for x in only] == ["0005", "0004", "0003"]
    assert [x["run_id"][-4:] for x in client.get("/projects/alpha/runs?scenario=other").json()["runs"]] == ["0002"]
    assert client.get("/projects/alpha/runs?limit=0").status_code == 422
    first = client.get("/projects/alpha/runs?limit=2").json()
    assert [x["run_id"][-4:] for x in first["runs"]] == ["0005", "0004"]
    assert first["next_before"] == first["runs"][-1]["run_id"]
    second = client.get("/projects/alpha/runs", params={"limit": 2, "before": first["next_before"]}).json()
    assert [x["run_id"][-4:] for x in second["runs"]] == ["0003", "0002"]
    assert second["next_before"] == second["runs"][-1]["run_id"]
    last = client.get("/projects/alpha/runs", params={"limit": 2, "before": second["next_before"]}).json()
    assert [x["run_id"][-4:] for x in last["runs"]] == ["0001"] and "next_before" not in last
    assert client.get("/projects/alpha/runs?before=wrong").status_code == 422
    assert client.get("/projects/alpha/runs/20260926-130000-demo-0004").json()["queue_position"] == 2

    for f in (runs / "_queue").glob("*.json"):
        f.unlink()
    (sc,) = client.get("/projects/alpha").json()["scenarios"]
    assert sc["last_run"] == {"run_id": dry.name, "state": "dry_run", "started_at": items[2]["started_at"],
                              "finished_at": None, "cost_usd": None}
    assert sc["types"] == ["ask", "output"]
    listing = client.get("/projects").json()["projects"]
    assert listing[0]["last_run"]["run_id"] == dry.name and listing[1]["last_run"] is None
    assert client.get("/projects/alpha").json()["links"]["scenario_step_agent"] == [["demo", "write", "writer"]]

    (b / "workflows" / "config.yaml").rename(b / "workflows" / "config.old")
    beta = client.get("/projects").json()["projects"][1]
    assert beta["available"] is False and beta["last_run"] is None
    assert beta["reason"] == f"missing {b / 'workflows' / 'config.yaml'}"


def test_broken_config_errors_and_runs_still_readable(registry_server):
    _, client, a, _ = registry_server
    cfg = a / "workflows" / "config.yaml"
    text = cfg.read_text()
    run_id = client.post("/projects/alpha/runs", json={"scenario": "demo", "dry_run": True}).json()["run_id"]

    cfg.write_text(text + "runs_dir: ./elsewhere\n")  # duplicate key: loader knows the line
    f = client.get("/projects/alpha/files/config.yaml").json()
    line = len(text.splitlines()) + 1
    assert f["errors"][0] | {"message": ""} == {"message": "", "file": "config.yaml", "line": line}
    r = client.get("/projects/alpha")
    assert r.status_code == 422 and r.json()["errors"][0]["line"] == line and r.json()["details"][0].startswith("config")
    assert [x["run_id"] for x in client.get("/projects/alpha/runs").json()["runs"]] == [run_id]  # default ./runs
    assert client.get(f"/projects/alpha/runs/{run_id}").json()["state"] == "dry_run"
    assert client.get("/projects/alpha/spend").status_code == 200

    cfg.write_text(text.replace("run_timeout: 1h", "run_timeout: hour"))  # schema: loader does not know the line
    f = client.get("/projects/alpha/files/config.yaml").json()
    assert f["data"]["limits"]["run_timeout"] == "hour" and f["errors"][0]["file"] == "config.yaml"
    assert f["errors"][0]["line"] == next(i for i, row in enumerate(text.splitlines(), 1)
                                             if row.lstrip().startswith("run_timeout:"))
    assert "run_timeout" in f["errors"][0]["message"]
    assert [x["run_id"] for x in client.get("/projects/alpha/runs").json()["runs"]] == [run_id]  # runs_dir from config

    (a / "workflows" / "mcp.yaml").write_text("version: 1\nservers:\n  web: { url: https://x.example.com }\n")
    assert client.get("/projects/alpha/files/mcp.yaml").status_code == 404  # owner-only: not served (api.md)
    cfg.write_text(text)
    assert client.get("/projects/alpha").json()["errors"][0]["file"] == "mcp.yaml"  # its errors are the project's


def test_frontmatter_duplicate_key_first_line(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("---\nversion: 1\nname: a\nname: b\n---\nbody\n")
    with pytest.raises(LoadError) as e:
        read_frontmatter(p, "agents/a.md")
    assert str(e.value) == "agents/a.md, line 4: duplicate key 'name' (first on line 3)"


def test_run_output_files(wf, tmp_path):
    """File and files outputs map uploaded run files, never the report."""
    images = tmp_path / "images"
    images.mkdir()
    for n in ("a.png", "b.png"):
        (images / n).write_bytes(png(4, 3))
    p = scenario(wf, """\
version: 1
name: picture
description: output files
inputs: {refs: {type: files, default: []}}
outputs: {image: {type: file}, gallery: {type: files}}
steps:
  - id: photo
    image: {model: gemini-image, prompt: a cup}
  - id: out
    output: {image: "{{ steps.photo.file }}", gallery: "{{ inputs.refs }}"}
""", "picture")
    made, _ = run(p, {"refs": [images / "a.png", images / "b.png"]})
    paths = api.run_output_files(wf.parent, made.rec.dir.name)
    assert paths["image"].startswith("steps/") and set(paths) == {"image", "gallery-1", "gallery-2"}
    assert "report" not in paths
    plain, _ = run(scenario(wf, """\
version: 1
name: plain
description: no files
steps: [{id: value, set: {text: "'tea'"}}]
""", "plain"))
    assert api.run_output_files(wf.parent, plain.rec.dir.name) == {}
    assert api.run_output_files(wf.parent, "20261002-101512-demo-0000") == {}
    assert api.run_output_files(wf.parent, "wrong") == {}
