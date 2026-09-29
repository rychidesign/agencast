"""API based on GUI findings, part 2 (agencast 0.8.0, api.md “Batch, preview and additions”): batch operations,
preview without writes, whole steps, fresh run state, lightweight fingerprints, file errors, new file descriptions,
model alias usage and allowed config.yaml fields."""
import json
import time

import httpx
import pytest
from conftest import TOKEN
from test_edit import BRANCHES, ids
from test_gui_api import held_lock

from agencast import ConfigErrors, api, server
from agencast.fake import Fake
from agencast.loader import load_yaml

RENAME = """\
version: 1
name: rename
description: Rename a referenced step
inputs:
  topic: { type: string, default: café }
outputs:
  text: { type: string }
steps:
  - id: write
    ask: { agent: writer, prompt: "Topic {{ inputs.topic }}" }
  # comment: steps.write.text is referenced below
  - id: revise
    when: steps.write.text != ""
    ask: { agent: writer, prompt: "Edit: {{ steps.write.text }} (steps.write.text outside the template stays unchanged)" }
    default: { text: "" }
  - id: result
    output:
      text: "{{ steps.revise.text }} {{steps.write.text}}"
"""


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "p"
    api.new_project(root)
    for name, text in (("branches", BRANCHES), ("rename", RENAME)):
        assert api.write_file(root, f"scenarios/{name}.yaml", None, text)["errors"] == []
    return root


def text_of(root, name):
    return (root / "workflows" / "scenarios" / f"{name}.yaml").read_text()


def tag_of(root, name):
    return api.read_file(root, f"scenarios/{name}.yaml")["etag"]


def test_rename_read_step_in_one_batch(proj):
    tag = tag_of(proj, "rename")
    with pytest.raises(ConfigErrors):  # not possible one operation at a time (API findings 10)
        api.update_step(proj, "rename", tag, ["steps", 0], {"id": "draft"})
    with pytest.raises(ConfigErrors) as e:  # without rename_refs, references remain broken — a result error, not an operation error
        api.batch(proj, "rename", tag, [{"op": "rename_step", "address": ["steps", 0], "new_id": "draft",
                                            "rename_refs": False}])
    assert not isinstance(e.value, api.OpError)
    r = api.batch(proj, "rename", tag, [{"op": "rename_step", "address": ["steps", 0], "new_id": "draft"}])
    assert r["errors"] == []
    text = text_of(proj, "rename")
    assert text == RENAME.replace("id: write", "id: draft").replace(
        'when: steps.write.text != ""', 'when: steps.draft.text != ""').replace(
        '{ agent: writer, prompt: "Edit: {{ steps.write.text }} (steps.write.text outside the template stays unchanged)" }',
        '{agent: writer, prompt: "Edit: {{ steps.draft.text }} (steps.write.text outside the template stays unchanged)"}').replace(
        "{{steps.write.text}}", "{{steps.draft.text}}")  # comment and text outside the template unchanged ({ a } → {a}: api.md)
    assert r["etag"] == tag_of(proj, "rename")


def test_batch_atomic_sequential_addresses_and_op_index(proj):
    tag = tag_of(proj, "rename")
    before = text_of(proj, "rename")
    # delete a referenced step + update its consumer; the second address applies to the state after the first operation
    r = api.batch(proj, "rename", tag, [
        {"op": "delete_step", "address": ["steps", 1]},
        {"op": "update_step", "address": ["steps", 1], "fields": {"output": {"text": "{{ steps.write.text }}"}}}])
    assert [s["id"] for s in load_yaml(text_of(proj, "rename"), "")["steps"]] == ["write", "result"]
    # error in operation n → nothing is written, OpError with index
    cur = text_of(proj, "rename")
    bad_ops = [
        ([{"op": "add_step", "step": {"id": "x", "fail": "x"}}, {"op": "delete_step", "address": ["steps", 9]}], 1,
         "index 9"),
        ([{"op": "change"}], 0, "unknown operation"),
        ([{"op": "move_step", "address": ["steps", 0]}], 0, "missing field to"),
        ([{"op": "delete_step", "address": ["steps", 0], "extra": 1}], 0, "unknown field extra"),
        (["not-an-object"], 0, "unknown operation"), ([{"op": ["list"]}], 0, "unknown operation")]
    for ops, n, msg in bad_ops:
        with pytest.raises(api.OpError) as e:
            api.batch(proj, "rename", r["etag"], ops)
        assert e.value.op == n and msg in e.value.errors[0] and e.value.errors[0].startswith(f"ops[{n}]")
    with pytest.raises(ConfigErrors, match="ops: must be a list of operations"):
        api.batch(proj, "rename", r["etag"], {"op": "delete_step"})
    with pytest.raises(api.Conflict):
        api.batch(proj, "rename", tag, [])
    assert text_of(proj, "rename") == cur != before


def test_incomplete_step_and_new_branch_in_one_batch(proj):
    tag = tag_of(proj, "rename")
    new = [{"op": "add_step", "after": ["steps", 0], "step": {"id": "new", "ask": {}}}]
    with pytest.raises(ConfigErrors):  # an empty ask alone fails (validation is unchanged)
        api.batch(proj, "rename", tag, new)
    r = api.batch(proj, "rename", tag, new + [
        {"op": "update_step", "address": ["steps", 1], "fields": {"ask": {"agent": "writer", "prompt": "New"}}}])
    assert r["errors"] == [] and load_yaml(text_of(proj, "rename"), "")["steps"][1]["id"] == "new"

    par = ["steps", 0, "switch", "cases", "café", 0]
    tag = tag_of(proj, "branches")
    with pytest.raises(ConfigErrors):  # an empty branch alone fails
        api.batch(proj, "branches", tag, [{"op": "add_branch", "address": par, "name": "d"}])
    r = api.batch(proj, "branches", tag, [
        {"op": "add_branch", "address": par, "name": "d"},
        {"op": "add_step", "after": [*par, "parallel", "d"], "step": {"id": "d0", "fail": "D"}},
        {"op": "add_branch", "address": ["steps", 0], "name": "thé", "steps": [{"id": "c0", "fail": "Tea"}]}])
    tree = api.describe_scenario(proj, "branches")
    assert tree and ("d0", [*par, "parallel", "d", 0]) in ids(tree["steps"])
    assert list(tree["steps"][0]["cases"]) == ["café", "thé"]
    for op, msg in (
        ({"address": par, "name": "a"}, "no branch/case with this name may already exist"),
        ({"address": ["steps", 1], "name": "x"}, "branches can only be added to parallel or switch"),
    ):
        with pytest.raises(api.OpError, match=msg):
            api.batch(proj, "branches", r["etag"], [{"op": "add_branch", **op}])


def test_replace_step_with_null(proj):
    r = api.write_file(proj, "scenarios/image.yaml", None, (
        "version: 1\nname: image\ndescription: Image\noutputs:\n  text: { type: string }\nsteps:\n"
        "  - id: photo\n    image: { model: gemini-image, prompt: Coffee }\n"
        "  - id: result\n    output: { text: done }\n"))
    step = {"id": "photo", "when": "false", "image": {"model": "gemini-image", "prompt": "Tea"}, "default": {"file": None}}
    with pytest.raises(ConfigErrors):  # merge patch cannot write null — it deletes the key, leaving default incomplete
        api.update_step(proj, "image", r["etag"], ["steps", 0], {"default": {"file": None}, "when": "false"})
    r = api.replace_step(proj, "image", r["etag"], ["steps", 0], step)
    assert r["errors"] == [] and load_yaml(text_of(proj, "image"), "")["steps"][0] == step
    # 19: the image.model alias is “in use”
    d = api.describe_project(proj)
    assert d["links"]["scenario_model"] == [["image", "gemini-image"]]
    assert d["models_used"] == {"smart": ["agents/writer.md"], "fast": [], "gemini-image": ["scenarios/image.yaml"]}


def test_render_without_write(proj):
    p = proj / "workflows" / "scenarios" / "rename.yaml"
    before = p.read_bytes()
    tag = tag_of(proj, "rename")
    out = api.render(proj, "rename", None, [
        {"op": "add_step", "after": ["steps", 0], "step": {"id": "new", "ask": {"agent": "writer"}}},
        {"op": "set_header", "fields": {"description": "New description"}}])
    assert p.read_bytes() == before
    assert "# comment: steps.write.text is referenced below\n" in out["text"] and "description: New description\n" in out["text"]
    assert [(s["id"], s["address"]) for s in out["tree"]][:2] == [("write", ["steps", 0]), ("new", ["steps", 1])]
    assert any("new" in e for e in out["errors"])  # draft state error, not 422
    assert api.render(proj, "rename", tag, [])["text"] == before.decode()
    with pytest.raises(api.Conflict):
        api.render(proj, "rename", "stale", [])
    with pytest.raises(api.OpError):
        api.render(proj, "rename", None, [{"op": "delete_step", "address": ["steps", 7]}])
    with pytest.raises(api.NotFound):
        api.render(proj, "absent", None, [])


def test_file_errors_new_files_and_config(proj):
    # 17: files/ returns file validation errors like GET /projects/<p>
    text = RENAME.replace("{{steps.write.text}}", "{{ steps.missing.text }}")
    # write_file rejects new errors → edit manually outside the API
    (proj / "workflows" / "scenarios" / "rename.yaml").write_text(text)
    f = api.read_file(proj, "scenarios/rename.yaml")
    d = api.describe_project(proj)
    want = next(s["errors"] for s in d["scenarios"] if s["name"] == "rename")
    assert f["errors"] == want and any("missing" in e for e in want)
    assert api.read_file(proj, "agents/writer.md")["errors"] == []
    assert api.file_etag(proj, "scenarios/rename.yaml") == f["etag"]
    with pytest.raises(api.NotFound):
        api.file_etag(proj, "scenarios/absent.yaml")
    # 18: description and model of a new agent and scenario
    api.new_agent(proj, "new", "Description: with a colon and \"quotes\"", "fast")
    fm = api.read_file(proj, "agents/new.md")["frontmatter"]
    assert fm["description"] == "Description: with a colon and \"quotes\"" and fm["model"] == "fast"
    with pytest.raises(ConfigErrors, match="is not an alias from config.yaml"):
        api.new_agent(proj, "other", model="absent")
    api.new_scenario(proj, "new", "What the scenario does")
    assert api.read_file(proj, "scenarios/new.yaml")["data"]["description"] == "What the scenario does"
    with pytest.raises(ConfigErrors, match="description"):
        api.new_scenario(proj, "third", 5)  # type: ignore[arg-type]
    # 20: runs_dir and openrouter.jev_model are allowed, base_url is not
    c = api.read_file(proj, "config.yaml")
    r = api.set_config(proj, c["etag"], {"runs_dir": "./run-records", "openrouter": {"jev_model": "jev-1.14"}})
    data = api.read_file(proj, "config.yaml")["data"]
    assert data["runs_dir"] == "./run-records" and data["openrouter"]["jev_model"] == "jev-1.14"
    with pytest.raises(ConfigErrors, match="base_url"):
        api.set_config(proj, r["etag"], {"openrouter": {"base_url": "https://openrouter.ai/api/v2"}})


def test_fresh_run_state(proj, monkeypatch):
    """15: queued immediately after 202; acquired directory: queued without a lock, running with one; dry_run only without run.lock."""
    monkeypatch.setenv("WEBHOOK_TOKEN", TOKEN)
    monkeypatch.setenv("CALLBACK_SECRET", "s")
    hook = server.Webhook(proj / "workflows", fake=Fake(None))  # without start(): no worker processes the queue
    s, body = hook.accept(f"Bearer {TOKEN}", json.dumps({"scenario": "rename"}).encode(), gui=True)
    assert s == 202
    run_id = body["run_id"]
    assert api.run_detail(proj, run_id) == {"run_id": run_id, "status": "queued", "state": "queued",
                                            "scenario": "rename", "queue_position": 1}
    d = proj / "runs" / run_id
    d.mkdir()  # worker created the directory, but has not acquired the lock yet
    for detail in (api.run_detail(proj, run_id), api.runs_list(proj)[0]):
        assert detail and detail["state"] == "queued" and detail["status"] == "queued" and detail["queue_position"] == 1
    (d / "run.lock").touch()
    (d / "plan.md").write_text("# plan\n")
    assert api.run_detail(proj, run_id)["state"] == "queued"  # type: ignore[index]
    with held_lock(d):
        assert api.run_detail(proj, run_id)["state"] == "running"  # type: ignore[index]
    (proj / "runs" / "_queue" / f"{run_id}.json").unlink()  # server stopped and someone deleted the queue
    assert api.runs_list(proj)[0]["state"] == "interrupted"  # plan.md + run.lock = live run, not a dry run
    dry = api.dry_run(api.load("rename", project_root=proj, offline=True), {}).dir
    assert api.run_detail(proj, dry.name)["state"] == "dry_run"  # type: ignore[index]


def test_http_batch_render_head(registry_server):
    _, client, a, _ = registry_server
    assert api.write_file(a, "scenarios/rename.yaml", None, RENAME)["errors"] == []
    tag = client.get("/projects/alpha/scenarios/rename").json()["etag"]
    # lightweight fingerprint: HEAD with ETag header, GET ?etag_only=1
    h = client.head("/projects/alpha/files/scenarios/rename.yaml")
    assert h.status_code == 200 and h.headers["etag"] == f'"{tag}"' and h.content == b""
    assert client.get("/projects/alpha/files/scenarios/rename.yaml?etag_only=1").json() == {"etag": tag}
    assert client.head("/projects/alpha/files/scenarios/absent.yaml").status_code == 404
    assert client.head("/projects/alpha/files/.env").status_code == 404
    assert httpx.head(f"{client.base_url}/projects/alpha/files/config.yaml").status_code == 401
    # render: nothing is written, errors as objects
    r = client.post("/projects/alpha/scenarios/rename/render", json={"ops": [
        {"op": "rename_step", "address": ["steps", 0], "new_id": "draft", "rename_refs": False}]})
    assert r.status_code == 200 and set(r.json()) == {"text", "tree", "errors"}
    assert r.json()["tree"][0]["id"] == "draft" and r.json()["errors"][0]["file"] == "scenarios/rename.yaml"
    assert client.head("/projects/alpha/files/scenarios/rename.yaml").headers["etag"] == f'"{tag}"'
    raw = client.post("/projects/alpha/scenarios/rename/render", json={"text": RENAME})
    assert raw.status_code == 200 and set(raw.json()) == {"tree", "errors"}
    assert raw.json()["tree"][0]["id"] == "write" and raw.json()["errors"] == []
    checked = client.post("/projects/alpha/validate", json={"path": "scenarios/rename.yaml", "text": RENAME})
    assert checked.status_code == 200 and checked.json()["tree"][0]["id"] == "write"
    assert checked.json()["errors"] == []
    assert (a / "workflows" / "scenarios" / "rename.yaml").read_text() == RENAME
    # batch: 422 with operation index, 409, 200
    r = client.post("/projects/alpha/scenarios/rename/batch", json={"etag": tag, "ops": [
        {"op": "set_header", "fields": {"description": "x"}}, {"op": "delete_step", "address": ["steps", 5]}]})
    assert r.status_code == 422 and r.json()["op"] == 1 and r.json()["errors"][0]["message"].startswith("ops[1]")
    r = client.post("/projects/alpha/scenarios/rename/batch", json={"etag": tag, "ops": [
        {"op": "rename_step", "address": ["steps", 0], "new_id": []}]})
    assert r.status_code == 422 and r.json()["errors"][0] | {"message": ""} == {
        "message": "", "step": "write", "field": "new_id"}
    r = client.post("/projects/alpha/scenarios/rename/batch", json={"etag": tag, "ops": [
        {"op": "add_step", "after": ["steps", 9], "step": {"id": "new", "fail": "error"}}]})
    assert r.status_code == 422 and r.json()["errors"][0]["step"] == "new"
    assert client.post("/projects/alpha/scenarios/rename/batch", json={"etag": "x", "ops": []}).status_code == 409
    r = client.post("/projects/alpha/scenarios/rename/batch", json={"etag": tag, "ops": [
        {"op": "rename_step", "address": ["steps", 0], "new_id": "draft"}]})
    assert r.status_code == 200 and r.json()["errors"] == []
    # PUT …/steps/<address> = whole step
    r = client.put("/projects/alpha/scenarios/rename/steps/0", json={"etag": r.json()["etag"], "step": {
        "id": "draft", "ask": {"agent": "writer", "prompt": "Different"}}})
    assert r.status_code == 200 and "prompt: Different" in (a / "workflows" / "scenarios" / "rename.yaml").read_text()
    # POST scenarios/agents with description and model
    r = client.post("/projects/alpha/agents", json={"name": "designer", "description": "Draws", "model": "gemini-image"})
    assert r.status_code == 200
    assert client.post("/projects/alpha/agents", json={"name": "x", "model": "absent"}).status_code == 422
    body = client.get("/projects/alpha").json()
    assert body["models_used"]["gemini-image"] == ["agents/designer.md"] and body["links"]["scenario_model"] == []
    # files/ with file validation errors (objects as in GET /projects/<p>)
    f = a / "workflows" / "scenarios" / "rename.yaml"
    f.write_text(f.read_text().replace("prompt: Different", 'prompt: "{{ steps.missing.text }}"'))
    errs = client.get("/projects/alpha/files/scenarios/rename.yaml").json()["errors"]
    assert errs and errs == next(s["errors"] for s in client.get("/projects/alpha").json()["scenarios"]
                                 if s["name"] == "rename")


def test_http_fresh_run_is_never_dry_run(registry_server):
    """15 via HTTP: only queued/running/succeeded from 202 until the run finishes."""
    _, client, _, _ = registry_server
    run_id = client.post("/projects/alpha/runs", json={"scenario": "demo"}).json()["run_id"]
    seen = set()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        states = {client.get(f"/projects/alpha/runs/{run_id}").json()["state"],
                  next(x["state"] for x in client.get("/projects/alpha/runs").json()["runs"] if x["run_id"] == run_id)}
        seen |= states
        if states == {"succeeded"}:
            break
        time.sleep(0.01)
    assert "succeeded" in seen and seen <= {"queued", "running", "succeeded"}
