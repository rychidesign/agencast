"""Images as inputs and as a variable (0.18.0): `file`/`files` inputs from a path, metadata read with a dot,
`images:` on ask/task, `files` output, staging into runs/<id>/inputs/ (scenario.md Type file, run-record.md)."""
import json
import struct
from pathlib import Path

import pytest
from conftest import events, run, scenario
from test_task import setup

from agencast import ConfigErrors, api
from agencast.engine import dry_run
from agencast.expressions import ExprError, FileRef, evaluate, infer
from agencast.fake import Fake, png
from agencast.providers import image_size, probe_image
from agencast.validate import check_models_list, resolve_inputs, validate

HEAD = "version: 1\nname: NAME\ndescription: x\n"


def box(t: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + t + payload


AVIF = box(b"ftyp", b"avif\0\0\0\0") + box(b"meta", b"\0\0\0\0" + box(b"iprp", box(b"ipco", box(
    b"ispe", b"\0\0\0\0" + struct.pack(">II", 300, 200)))))
GIF = b"GIF89a" + struct.pack("<HH", 5, 7) + b"\0" * 6


def app1(payload: bytes) -> bytes:
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def jpeg(orientation: int | None, xmp: bool = False) -> bytes:
    sof = b"\xff\xc0" + struct.pack(">H", 11) + b"\x08" + struct.pack(">HH", 480, 640) + b"\x01\x01\x11\x00"
    xmp_seg = app1(b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta/>") if xmp else b""  # a later non-Exif APP1
    if orientation is None:
        return b"\xff\xd8" + xmp_seg + sof
    tiff = b"MM\x00\x2a\x00\x00\x00\x08" + struct.pack(">H", 1) + struct.pack(">HHI", 0x0112, 3, 1) \
        + struct.pack(">HH", orientation, 0) + b"\0\0\0\0"
    return b"\xff\xd8" + app1(b"Exif\x00\x00" + tiff) + xmp_seg + sof


@pytest.mark.parametrize("data,want", [
    (png(4, 3), ("png", 4, 3)), (GIF, ("gif", 5, 7)), (AVIF, ("avif", 300, 200)),
    (jpeg(None), ("jpeg", 640, 480)), (jpeg(1), ("jpeg", 640, 480)), (jpeg(6), ("jpeg", 480, 640)),
    (jpeg(6, xmp=True), ("jpeg", 480, 640)), (jpeg(None, xmp=True), ("jpeg", 640, 480)),
])
def test_probe_formats_and_exif_orientation(data, want):
    assert probe_image(data) == want


def test_probe_rejects_other_files():
    assert probe_image(b"<svg xmlns='http://www.w3.org/2000/svg'/>") is None
    assert image_size(b"GIF89a") == (None, None) and image_size(box(b"ftyp", b"avif")) == (None, None)


# --- file as a variable -----------------------------------------------------------------------

PHOTO = FileRef("inputs/photo.png", 4, 3, "png")
CTX = {"inputs": {"photo": PHOTO, "refs": [PHOTO, FileRef("inputs/refs-2.jpg", 6, 9, "jpeg")]}, "steps": {}}


def test_file_metadata_with_dot_and_brackets():
    assert evaluate("inputs.photo.width > inputs.photo.height", CTX) is True
    assert evaluate('inputs.refs[1]["format"] + str(inputs.refs[1].height)', CTX) == "jpeg9"
    assert evaluate("len(inputs.refs)", CTX) == 2 and evaluate("inputs.refs[0] == inputs.photo", CTX) is True
    assert FileRef("a.png", 1, 1, "png") == FileRef("a.png")  # metadata do not take part in ==
    with pytest.raises(ExprError, match="is file — has no key 'size' \\(available: width, height, format\\)"):
        evaluate("inputs.photo.size", CTX)
    with pytest.raises(ExprError, match="width of steps/x.svg is unknown"):
        evaluate("steps.x.file.width", {"inputs": {}, "steps": {"x": {"file": FileRef("steps/x.svg")}}})


def test_file_metadata_static_types():
    inputs, res = {"photo": "file", "refs": ["file"]}, lambda k: {"gen": {"file": "file"}}[k]
    assert infer("inputs.photo.width / inputs.refs[0].height", inputs, res) == "number"
    assert infer('inputs.refs[1]["format"]', inputs, res) == "string"
    assert infer("[inputs.photo, steps.gen.file]", inputs, res) == ["file"]
    with pytest.raises(ExprError, match="has no key 'size'"):
        infer("inputs.photo.size", inputs, res)
    with pytest.raises(ExprError, match="cannot add number \\+ string"):
        infer("inputs.photo.width + inputs.photo.format", inputs, res)


# --- inputs -------------------------------------------------------------------------------------

@pytest.fixture
def photos(tmp_path) -> Path:
    d = tmp_path / "photos"
    d.mkdir()
    (d / "a.png").write_bytes(png(4, 3))
    (d / "b.jpg").write_bytes(jpeg(6))
    (d / "c.avif").write_bytes(AVIF)
    (d / "notes.txt").write_text("not an image")
    return d


SPEC = {"inputs": {"photo": {"type": "file", "required": True}, "refs": {"type": "files", "default": []}}}


def test_resolve_inputs_paths(photos):
    got = resolve_inputs(SPEC, {"photo": photos / "a.png", "refs": [photos / "b.jpg", photos / "c.avif"]})
    assert got == {"photo": photos / "a.png", "refs": [photos / "b.jpg", photos / "c.avif"]}
    text = resolve_inputs(SPEC, {"photo": str(photos / "a.png"), "refs": json.dumps([str(photos / "b.jpg")])},
                          from_text=True)
    assert text == {"photo": photos / "a.png", "refs": [photos / "b.jpg"]}
    assert resolve_inputs(SPEC, {"photo": str(photos / "a.png"), "refs": str(photos / "c.avif")}, from_text=True)["refs"] \
        == [photos / "c.avif"]


@pytest.mark.parametrize("given,from_text,msg", [
    ({"photo": "/etc/passwd"}, False, "pass a path from the CLI"),          # a JSON string is never a path
    ({"photo": {"upload_id": "x"}}, False, "pass a path from the CLI"),
    ({"photo": "missing.png"}, True, "file missing.png does not exist"),
    ({"photo": "notes.txt"}, True, "is not a supported image"),
    ({"photo": ["a.png"]}, True, "must be one image path, got a list of 1"),
    ({"photo": "a.png", "refs": "[]"}, True, "must be 1–16 image paths, got a list of 0"),
    ({"photo": "a.png", "refs": json.dumps(["a.png"] * 17)}, True, "got a list of 17"),
])
def test_resolve_inputs_errors(photos, monkeypatch, given, from_text, msg):
    monkeypatch.chdir(photos)
    with pytest.raises(ConfigErrors) as e:
        resolve_inputs(SPEC, given, from_text=from_text)
    assert msg in "\n".join(e.value.errors), e.value.errors


def test_resolve_inputs_size_limit(photos, monkeypatch):
    monkeypatch.setattr("agencast.validate.MAX_FILE_BYTES", 10)
    with pytest.raises(ConfigErrors, match="maximum 10 B"):
        resolve_inputs(SPEC, {"photo": photos / "a.png"})


def test_resolve_inputs_twice_keeps_applied_default(photos, wf):
    """cli.py and server.py resolve first, api.run / api.dry_run again: the `files` default [] must pass."""
    first = resolve_inputs(SPEC, {"photo": str(photos / "a.png")}, from_text=True)
    assert resolve_inputs(SPEC, first) == first == {"photo": photos / "a.png", "refs": []}
    p = validate(scenario(wf, ASK), check_models=False)
    assert (api.dry_run(p, first).dir / "inputs.json").is_file()
    r = api.run(p, first, fake=Fake({"write": {"text": "ok"}}, ["anthropic/claude-haiku-4.5"]))
    assert r.status == "succeeded", r.error


def test_vision_check_needs_image_input():
    cfg = {"models": {"smart": {"id": "m1"}}}
    m = {"id": "m1", "output_modalities": ["text"], "supported_parameters": []}
    assert "does not accept image input" in check_models_list(cfg, {"smart": {"vision"}}, [{**m, "input_modalities": ["text"]}])[0]
    assert check_models_list(cfg, {"smart": {"vision"}}, [m]) == []  # old cache without the key = unknown, skipped
    assert check_models_list(cfg, {"smart": {"vision"}}, [{**m, "input_modalities": ["text", "image"]}]) == []


# --- validate ---------------------------------------------------------------------------------

def errors(wf, text) -> str:
    try:
        validate(scenario(wf, text), check_models=False)
    except ConfigErrors as e:
        return "\n".join(e.errors)
    return ""


INPUTS = "inputs: { photo: { type: file, required: true }, refs: { type: files, default: [] }, t: { type: string, default: x } }\n"


@pytest.mark.parametrize("body,msg", [
    ('steps: [{ id: a, ask: { agent: copywriter, prompt: x, images: ["{{ inputs.photo }}", "{{ inputs.refs }}"] } }]', ""),
    ('steps: [{ id: a, ask: { agent: copywriter, prompt: x, images: "{{ inputs.refs }}" } }]', ""),
    ('steps: [{ id: a, ask: { agent: copywriter, prompt: x, images: ["{{ inputs.t }}"] } }]', "got string"),
    ('steps: [{ id: a, ask: { agent: copywriter, prompt: x, images: ["x {{ inputs.photo }}"] } }]', "got string"),
    ('steps: [{ id: a, ask: { agent: copywriter, prompt: x, images: ["photo.png"] } }]', "got string"),
    ('steps: [{ id: a, set: { l: "[inputs.t]" } }, { id: b, ask: { agent: copywriter, prompt: x, images: "{{ steps.a.l }}" } }]',
     "got a list of string"),
    ('steps: [{ id: a, ask: { agent: copywriter, prompt: x, images: [] } }]', "images"),
    ('steps: [{ id: a, set: { w: "inputs.photo.width > inputs.refs[0].height", f: "inputs.refs[0].format" } }]', ""),
    ('steps: [{ id: a, set: { w: "inputs.photo.size" } }]', "has no key 'size'"),
    ('outputs: { g: { type: files } }\nsteps: [{ id: o, output: { g: "{{ inputs.refs }}" } }]', ""),
    ('outputs: { g: { type: files } }\nsteps: [{ id: o, output: { g: "{{ inputs.photo }}" } }]', "files output must be"),
    ('outputs: { g: { type: files } }\nsteps: [{ id: s, set: { l: "[inputs.t]" } }, { id: o, output: { g: "{{ steps.s.l }}" } }]',
     "not a list of string"),
    ('outputs: { g: { type: file } }\nsteps: [{ id: o, output: { g: "{{ inputs.photo }}" } }]', ""),
    ('inputs: { p: { type: file, default: x } }\nsteps: [{ id: a, fail: x }]', "does not match type file"),
])
def test_validate_images(wf, body, msg):
    got = errors(wf, HEAD + (INPUTS if not body.startswith("inputs:") else "") + body)
    assert (msg in got) if msg else (got == ""), got


def test_validate_call_passes_files(wf):
    scenario(wf, HEAD + "callable: true\ninputs: { pics: { type: files, required: true } }\n"
                        "outputs: { n: { type: number } }\nsteps: [{ id: c, set: { n: len(inputs.pics) } }, "
                        "{ id: o, output: { n: '{{ steps.c.n }}' } }]", "gallery")
    assert errors(wf, HEAD + INPUTS + 'steps: [{ id: a, call: { scenario: gallery, inputs: { pics: "{{ inputs.refs }}" } } }]') == ""
    got = errors(wf, HEAD + INPUTS + "steps: [{ id: s, set: { l: '[inputs.t]' } }, "
                                     '{ id: a, call: { scenario: gallery, inputs: { pics: "{{ steps.s.l }}" } } }]')
    assert "input has type files, value is a list of string" in got, got


# --- run --------------------------------------------------------------------------------------

ASK = HEAD + INPUTS + """
outputs: { text: { type: string }, photo: { type: file }, gallery: { type: files }, raw: { type: list }, wide: { type: boolean } }
steps:
  - id: shape
    set: { wide: "inputs.photo.width > inputs.photo.height", n: "len(inputs.refs)" }
  - id: write
    ask:
      agent: copywriter
      prompt: "Describe image 1; there are {{ steps.shape.n }} more."
      images: ["{{ inputs.photo }}", "{{ inputs.refs }}"]
  - id: out
    output:
      text: "{{ steps.write.text }}"
      photo: "{{ inputs.photo }}"
      gallery: "{{ inputs.refs }}"
      raw: "{{ inputs.refs }}"
      wide: "{{ steps.shape.wide }}"
"""


def test_ask_with_images_staged_sent_and_redacted(wf, photos):
    r, fake = run(scenario(wf, ASK), {"photo": photos / "a.png", "refs": [photos / "b.jpg", photos / "a.png"]},
                  script={"write": {"text": "A tiny gray image."}})
    assert r.status == "succeeded", r.error
    d = r.rec.dir
    assert r.values["inputs"]["photo"] == FileRef("inputs/photo.png") and r.values["inputs"]["photo"].width == 4
    assert [f.path for f in r.values["inputs"]["refs"]] == ["inputs/refs-1.jpg", "inputs/refs-2.png"]
    assert (d / "inputs/photo.png").read_bytes() == png(4, 3) and (d / "inputs/refs-1.jpg").is_file()
    assert r.values["steps"]["shape"] == {"wide": True, "n": 2}
    content = fake.calls[0][2]["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "Describe image 1; there are 2 more."}
    assert [c["text"] for c in content[1::2]] == ["Image 1 (photo.png, 4×3):", "Image 2 (refs-1.jpg, 480×640):",
                                                   "Image 3 (refs-2.png, 4×3):"]
    assert content[2]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[4]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    req = (d / "steps/02-write/calls/01.request.json").read_text()
    assert req.count(f"<file: inputs/photo.png, {len(png(4, 3))} B>") == 2  # identical bytes: the first path names both
    assert "<file: inputs/refs-1.jpg" in req
    assert "# Images\n\n- <file: inputs/photo.png" in (d / "steps/02-write/prompt.md").read_text()
    assert (d / "steps/02-write/prompt.md").read_text().count("- <file: ") == 3  # one line per image sent
    for f in d.rglob("*"):
        if f.suffix in (".json", ".jsonl", ".md"):
            text = f.read_text()
            assert "base64," not in text and str(photos) not in text, f  # never base64, never a host path
    assert json.loads((d / "inputs.json").read_text()) == {
        "photo": "inputs/photo.png", "refs": ["inputs/refs-1.jpg", "inputs/refs-2.png"], "t": "x"}
    cb = json.loads((d / "callback.json").read_text())["outputs"]
    assert cb["photo"].endswith("/photo.png") and cb["wide"] is True
    assert [u.rsplit("/", 1)[1] for u in cb["gallery"]] == ["gallery-1.jpg", "gallery-2.png"]
    assert cb["raw"] == ["inputs/refs-1.jpg", "inputs/refs-2.png"]  # a file inside a list output = its path
    assert [e["output"] for e in events(r, "file_uploaded")][:3] == ["photo", "gallery-1", "gallery-2"]  # then report


def test_avif_is_an_input_but_cannot_be_sent_to_a_model(wf, photos):
    p = scenario(wf, HEAD + "inputs: { photo: { type: file, required: true } }\noutputs: { same: { type: file } }\n"
                            'steps: [{ id: o, output: { same: "{{ inputs.photo }}" } }]')
    r, _ = run(p, {"photo": photos / "c.avif"})
    assert r.status == "succeeded" and r.values["inputs"]["photo"] == FileRef("inputs/photo.avif"), r.error
    assert r.values["inputs"]["photo"].width == 300 and r.outputs["same"].endswith("/same.avif")
    p = scenario(wf, HEAD + "inputs: { photo: { type: file, required: true } }\n"
                            'steps: [{ id: a, ask: { agent: copywriter, prompt: x, images: ["{{ inputs.photo }}"] } }]')
    r, fake = run(p, {"photo": photos / "c.avif"})
    assert r.error["class"] == "config" and "inputs/photo.avif (image/avif) cannot be sent to a model" in r.error["message"]
    assert not fake.calls


def test_ask_without_images_sends_plain_text(wf, photos):
    p = scenario(wf, HEAD + INPUTS + 'steps: [{ id: a, ask: { agent: copywriter, prompt: "Hi {{ inputs.photo }}" } }]')
    r, fake = run(p, {"photo": photos / "a.png"})
    assert r.status == "succeeded", r.error
    assert fake.calls[0][2]["messages"][1] == {"role": "user", "content": "Hi inputs/photo.png"}


def test_images_null_from_default_is_skipped_and_text_is_expression_error(wf, photos):
    p = scenario(wf, HEAD + INPUTS + """
steps:
  - id: gen
    when: 'false'
    default: { file: null }
    image: { model: gemini-image, prompt: x }
  - id: a
    ask: { agent: copywriter, prompt: x, images: ["{{ steps.gen.file }}", "{{ inputs.photo }}"] }
""")
    r, fake = run(p, {"photo": photos / "a.png"})
    assert r.status == "succeeded", r.error
    assert [c["text"] for c in fake.calls[0][2]["messages"][1]["content"][1::2]] == ["Image 1 (photo.png, 4×3):"]


def test_dry_run_plans_paths_without_copying(wf, photos):
    p = validate(scenario(wf, ASK), check_models=False)
    rec = dry_run(p, resolve_inputs(p.scenario, {"photo": photos / "a.png", "refs": [photos / "b.jpg"]}))
    assert json.loads((rec.dir / "inputs.json").read_text()) == {"photo": "inputs/photo.png", "refs": ["inputs/refs-1.jpg"], "t": "x"}
    assert not (rec.dir / "inputs").exists() and str(photos) not in (rec.dir / "inputs.json").read_text()


def test_task_with_images(wf, photos):
    setup(wf)  # agent `tester` with the fake MCP server (test_task)
    p = scenario(wf, HEAD + "inputs: { photo: { type: file, required: true } }\n"
                            'steps: [{ id: t, task: { agent: tester, prompt: "Complete the task", images: ["{{ inputs.photo }}"] } }]')
    r, fake = run(p, {"photo": photos / "a.png"}, script={"t": {"text": "Done."}})
    assert r.status == "succeeded", r.error
    content = fake.calls[0][2]["messages"][1]["content"]
    assert content[0]["text"] == "Complete the task" and content[1]["text"] == "Image 1 (photo.png, 4×3):"
    req = (r.rec.dir / "steps/01-t/calls/01.request.json").read_text()
    assert "<file: inputs/photo.png" in req and "base64," not in req
