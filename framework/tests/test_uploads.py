"""POST …/uploads (api.md Uploads, 0.18.0): image upload for file/files inputs over HTTP — single-project
webhook and registry mode, token before the body, limits, upload ids in runs and dry runs, expiry."""
import json
import os
import time

import pytest
from conftest import SECRET, TOKEN, scenario, serve
from test_webhook import Receiver, finished, start

from agencast import api
from agencast.fake import Fake, png
from agencast.server import Projects

PIC = ("version: 1\nname: NAME\ndescription: x\n"
       "inputs: { photo: { type: file, required: true }, refs: { type: files, default: [] } }\n"
       "outputs: { same: { type: file }, wide: { type: boolean }, n: { type: number } }\n"
       "steps:\n"
       "  - id: s\n    set: { wide: 'inputs.photo.width > inputs.photo.height', n: len(inputs.refs) }\n"
       "  - id: o\n    output: { same: '{{ inputs.photo }}', wide: '{{ steps.s.wide }}', n: '{{ steps.s.n }}' }\n")


@pytest.fixture
def hook_server(wf, monkeypatch):
    monkeypatch.setenv("WEBHOOK_TOKEN", TOKEN)
    monkeypatch.setenv("CALLBACK_SECRET", SECRET)
    scenario(wf, PIC, "pic")
    hook, srv, client = start(wf)
    yield hook, client
    client.close()
    srv.shutdown()
    srv.server_close()


def test_upload_then_run_with_upload_ids(wf, hook_server):
    hook, client = hook_server
    r = client.post("/uploads", content=png(4, 3))
    assert r.status_code == 201, r.text
    up = r.json()
    assert up == {"upload_id": up["upload_id"], "format": "png", "width": 4, "height": 3, "bytes": len(png(4, 3))}
    assert up["upload_id"].startswith("up_") and len(up["upload_id"]) == 35
    assert (hook.uploads / f"{up['upload_id']}.png").read_bytes() == png(4, 3)
    other = client.post("/uploads", content=png(2, 5)).json()["upload_id"]
    rcv = Receiver()
    r = client.post("/runs", json={"scenario": "pic", "callback_url": rcv.url,
                                   "inputs": {"photo": {"upload_id": up["upload_id"]},
                                              "refs": [{"upload_id": other}, {"upload_id": up["upload_id"]}]}})
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]
    cb = rcv.wait()[0]
    finished(hook, run_id)
    assert cb["status"] == "succeeded" and cb["outputs"]["wide"] is True and cb["outputs"]["n"] == 2
    assert cb["outputs"]["same"].endswith("/same.png")
    d = hook.runs / run_id
    assert (d / "inputs/photo.png").read_bytes() == png(4, 3) and (d / "inputs/refs-1.png").read_bytes() == png(2, 5)
    assert json.loads((d / "inputs.json").read_text())["refs"] == ["inputs/refs-1.png", "inputs/refs-2.png"]
    text = (d / "events.jsonl").read_text() + (d / "summary.md").read_text()
    assert "_uploads" not in text and "upload_id" not in text  # the record knows only its own copies
    assert (hook.uploads / f"{up['upload_id']}.png").is_file()  # reusable after the run


@pytest.mark.parametrize("body,auth,status,msg", [
    (png(4, 3), "", 401, "token"),
    (b"<svg/>", None, 422, "not a supported image"),
    (b"", None, 422, "not a supported image"),
    (b"GIF89a", None, 422, "cannot read the image dimensions"),  # a header too short for the dimensions
])
def test_upload_rejections(hook_server, body, auth, status, msg):
    _, client = hook_server
    headers = {"Authorization": auth} if auth is not None else {}
    r = client.post("/uploads", content=body, headers=headers)
    assert r.status_code == status and msg in r.json()["error"], r.text


def test_upload_size_limit_checked_before_reading(hook_server, monkeypatch):
    _, client = hook_server
    monkeypatch.setattr("agencast.server.MAX_FILE_BYTES", 10)
    r = client.post("/uploads", content=png(4, 3))
    assert r.status_code == 422 and "maximum 10 B" in r.json()["error"]
    r = client.post("/uploads", content=png(4, 3), headers={"Authorization": ""})
    assert r.status_code == 401, r.text  # the token comes first: 422 "maximum 10 B" would mean the body was read


def test_using_an_upload_refreshes_its_age(hook_server):
    hook, client = hook_server
    uid = client.post("/uploads", content=png(4, 3)).json()["upload_id"]
    f = hook.uploads / f"{uid}.png"
    os.utime(f, (time.time() - 2 * 86400,) * 2)
    r = client.post("/runs", json={"scenario": "pic", "callback_url": "https://x.example.com/cb",
                                   "inputs": {"photo": {"upload_id": uid}}, "request_key": "k1"})
    assert r.status_code in (202, 422), r.text  # resolved by check() either way
    assert time.time() - f.stat().st_mtime < 60  # touched: a sweep during a dry run cannot delete it


def test_run_input_must_be_an_upload_id(hook_server):
    _, client = hook_server
    rcv = Receiver()

    def post(photo):
        return client.post("/runs", json={"scenario": "pic", "callback_url": rcv.url, "inputs": {"photo": photo}})
    r = post("/etc/passwd")
    assert r.status_code == 422 and "an upload_id from POST" in r.json()["details"][0], r.text
    r = post({"upload_id": "up_" + "0" * 32})
    assert r.status_code == 422 and "not found" in r.json()["details"][0]
    r = post({"upload_id": "../../.env"})
    assert r.status_code == 422 and 'expected {"upload_id"' in r.json()["details"][0]
    r = post({"upload_id": "up_" + "0" * 32, "path": "x"})
    assert r.status_code == 422 and 'expected {"upload_id"' in r.json()["details"][0]
    assert not rcv.got


def test_sweep_keeps_queued_and_recent_uploads(hook_server):
    hook, client = hook_server
    old_free = hook.uploads / ("up_" + "a" * 32 + ".png")
    old_used = hook.uploads / ("up_" + "b" * 32 + ".png")
    hook.uploads.mkdir(exist_ok=True)
    for f in (old_free, old_used):
        f.write_bytes(png(1, 1))
        os.utime(f, (time.time() - 2 * 86400,) * 2)
    (hook.qdir / "20990101-000000-pic-abcd.json").write_text(json.dumps(
        {"run_id": "20990101-000000-pic-abcd", "scenario": "pic", "queued_ns": 1,
         "inputs": {"photo": {"upload_id": old_used.stem}}}))
    fresh = client.post("/uploads", content=png(4, 3)).json()["upload_id"]
    assert not old_free.exists() and old_used.exists() and (hook.uploads / f"{fresh}.png").exists()


def test_registry_upload_and_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("CALLBACK_SECRET", SECRET)
    a = tmp_path / "alpha"
    api.new_project(a)
    scenario(a / "workflows", PIC.replace("outputs: { same: { type: file }, wide: { type: boolean }, n: { type: number } }",
                                          "outputs: { wide: { type: boolean }, n: { type: number } }")
             .replace("same: '{{ inputs.photo }}', ", ""), "pic")
    projects = Projects(token=TOKEN, fake=lambda: Fake(None))
    projects.start()
    srv, client = serve(projects=projects)
    try:
        assert client.post("/uploads", content=png(4, 3)).status_code == 404  # registry mode: per project
        assert client.post("/projects/alpha/uploads", content=png(4, 3), headers={"Authorization": "x"}).status_code == 401
        assert client.post("/projects/nope/uploads", content=png(4, 3)).status_code == 404
        up = client.post("/projects/alpha/uploads", content=png(6, 4)).json()
        assert up["width"] == 6 and (a / "runs/_uploads" / f"{up['upload_id']}.png").is_file()
        r = client.post("/projects/alpha/runs", json={"scenario": "pic", "dry_run": True,
                                                      "inputs": {"photo": {"upload_id": up["upload_id"]}}})
        assert r.status_code == 200, r.text
        dry = r.json()["run_id"]
        run_dir = a / "runs" / dry
        assert json.loads((run_dir / "inputs.json").read_text()) == {"photo": "inputs/photo.png", "refs": []}
        assert not (run_dir / "inputs").exists()
        r = client.post("/projects/alpha/runs", json={"scenario": "pic", "inputs": {"photo": {"upload_id": up["upload_id"]}}})
        assert r.status_code == 202, r.text
        finished(projects.hooks[a], r.json()["run_id"])
        cb = json.loads((a / "runs" / r.json()["run_id"] / "callback.json").read_text())
        assert cb["status"] == "succeeded" and cb["outputs"] == {"wide": True, "n": 0}
        ids = {x["run_id"] for x in client.get("/projects/alpha/runs").json()["runs"]}
        assert ids == {dry, r.json()["run_id"]}  # _uploads is not a run
    finally:
        client.close()
        srv.shutdown()
        srv.server_close()
