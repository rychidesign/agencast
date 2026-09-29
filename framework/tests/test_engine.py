"""Run with a fake provider: error classes and their behavior (scenario.md §6),
steps, run record (run-record.md), callback."""
import hashlib
import hmac
import json
import re
import base64
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from conftest import add_image_model, events, model_ids, run, scenario

from agencast import AgencastError, engine, providers
from agencast.engine import dry_run, run_scenario
from agencast.fake import Fake
from agencast.validate import validate

HEAD = "version: 1\nname: NAME\ndescription: Test scenario\n"
ASK = HEAD + """
outputs: { text: { type: string } }
steps:
  - id: write
    RETRY
    ask: { agent: copywriter, prompt: "Say hello" SCHEMA }
  - id: out
    output: { text: "{{ steps.write.OUT }}" }
"""


def ask_scenario(wf, retry=None, schema=False, alias=None):
    text = ASK.replace("RETRY", f"retry: {retry}" if retry is not None else "")
    text = text.replace("SCHEMA", ", schema: { text: string }" if schema else "").replace("OUT", "text")
    if alias:
        f = wf / "agents" / "copywriter.md"
        f.write_text(f.read_text().replace("model: smart", f"model: {alias}"))
    return scenario(wf, text)


def err(r):
    return (r.error or {}).get("class"), (r.error or {}).get("message", "")


# --- success and record --------------------------------------------------------------------

def test_record_layout_and_events(wf):
    r, fake = run(wf / "scenarios" / "ig-post.yaml", {"topic": "coffee"},
                  __import__("yaml").safe_load(open(Path(__file__).resolve().parents[2] / "examples/showcase/fake/ig-post.yaml")))
    assert r.status == "succeeded", r.error
    d = r.rec.dir
    assert re.fullmatch(r"\d{8}-\d{6}-ig-post-[0-9a-f]{4}", r.run_id)
    for f in ("plan.md", "inputs.json", "events.jsonl", "summary.md", "callback.json",
              "steps/01-copy/prompt.md", "steps/01-copy/calls/01.request.json", "steps/01-copy/calls/01.response.json",
              "steps/01-copy/output.json", "steps/02-tone_check/output.json", "steps/07-photo/image.png",
              "steps/07-photo/output.json", "steps/08-out/output.json"):
        assert (d / f).is_file(), f
    assert not (d / "steps/03-stop").exists()  # a skipped step has no directory
    types = [e["type"] for e in events(r)]
    assert types[0] == "run_started" and types[-1] == "run_finished"
    assert {"step_started", "step_finished", "step_skipped", "model_call", "jev_call", "image_saved",
            "file_uploaded"} <= set(types)
    for e in events(r):
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", e["ts"])
    started = events(r, "run_started")[0]
    assert re.fullmatch(re.escape(r.run_id) + r"-[0-9a-f]{32}", started["storage_prefix"])
    skipped = events(r, "step_skipped")[0]
    assert skipped == {**skipped, "step": "stop", "reason_code": "when", "default_used": False,
                       "reason": "when: steps.tone_check.on_brand < 0.7 → false"}
    calls = events(r, "model_call")
    assert [c["structured_output"] for c in calls] == ["native_schema", "tool_wrapper", None]
    assert calls[0]["usage"] == {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.0001}
    jev = events(r, "jev_call")[0]
    assert jev["answers"] == {"on_brand": 0.91} and jev["response_model"] == "typesafe/jev-fake"
    # no base64 or reasoning_details anywhere in the record
    for f in d.rglob("*"):
        if f.suffix in (".json", ".jsonl", ".md"):
            text = f.read_text()
            assert "base64," not in text and "fake-signature" not in text, f
    assert "<file: steps/07-photo/image.png" in (d / "steps/07-photo/calls/01.response.json").read_text()
    cb = json.loads((d / "callback.json").read_text())
    assert cb["status"] == "succeeded" and cb["outputs"]["hashtags"] == ["#lumen", "#coffee", "#morning"]
    assert cb["outputs"]["image"].startswith("file://") and started["storage_prefix"] in cb["outputs"]["image"]
    assert json.loads((d / "steps/07-photo/output.json").read_text()) == {"file": "steps/07-photo/image.png"}
    summary = (d / "summary.md").read_text()
    assert summary.startswith("# test" if False else "# ig-post — success")
    assert "| 3 | stop | fail | skipped |" in summary and "on_brand = 0.91" in summary
    fin = events(r, "run_finished")[0]
    assert fin["status"] == "succeeded" and fin["image_cost_usd"] == 0.04 and fin["error"] is None


def test_ask_text_and_system_prompt_with_skill(wf):
    r, fake = run(ask_scenario(wf), script={"write": {"text": "Hello!"}})
    assert r.status == "succeeded" and r.outputs == {"text": "Hello!"}
    body = fake.calls[0][2]
    system = body["messages"][0]["content"]
    assert system.startswith("You are the copywriter") and "## Skill: lumen-voice" in system
    assert body["messages"][1] == {"role": "user", "content": "Say hello"}
    assert "response_format" not in body and body["usage"] == {"include": True}


def test_dry_run_only_plan(wf):
    p = validate(wf / "scenarios" / "ig-post.yaml", check_models=False)
    rec = dry_run(p, {"topic": "x"})
    assert sorted(f.name for f in rec.dir.iterdir()) == ["inputs.json", "plan.md"]
    plan = (rec.dir / "plan.md").read_text()
    assert "| 1 | copy | ask |" in plan and "anthropic/claude-haiku-4.5" in plan and "4:5" in plan


# --- error classes ---------------------------------------------------------------------------

def test_transient_retried_then_ok(wf):
    r, fake = run(ask_scenario(wf), script={"write": [{"status": 429}, {"status": 502}, {"text": "ok"}]})
    assert r.status == "succeeded"
    errs = events(r, "error")
    assert [(e["class"], e["will_retry"], e["http_status"]) for e in errs] == \
        [("transient", True, 429), ("transient", True, 502)]
    assert [c["attempt"] for c in events(r, "model_call")] == [1, 2, 3]
    assert sorted(p.name for p in (r.rec.dir / "steps/01-write/calls").iterdir())[-1] == "03.response.json"


def test_transient_exhausted(wf):
    r, _ = run(ask_scenario(wf, retry=1), script={"write": {"status": 503}})
    assert err(r)[0] == "transient" and r.error["step"] == "write"
    assert len(events(r, "model_call")) == 2 and events(r, "error")[-1]["will_retry"] is False


def test_200_with_finish_reason_error_is_transient(wf):
    r, _ = run(ask_scenario(wf), script={"write": [{"finish_reason": "error"}, {"text": "ok"}]})
    assert r.status == "succeeded"
    assert events(r, "error")[0]["message"] == "provider returned HTTP 200 with finish_reason: error"


def test_200_with_error_body_is_transient(wf):
    body = {"error": {"code": 502, "message": "upstream"}}
    r, _ = run(ask_scenario(wf, retry=0), script={"write": {"body": body}})
    assert err(r) == ("transient", "HTTP 200 (error.code 502): upstream")


@pytest.mark.parametrize("spec,cls,msg", [
    ({"finish_reason": "length"}, "config", "max_tokens"),
    ({"finish_reason": "content_filter"}, "content", "filter"),
    ({"refusal": "I cannot."}, "content", "model refused: I cannot."),
    ({"status": 402}, "budget", "credit exhausted"),
    ({"status": 400}, "config", "HTTP 400"),
    ({"status": 401}, "config", "HTTP 401"),
    ({"status": 403, "error": "flagged by moderation"}, "content", "moderation"),
    ({"status": 403, "error": "key disabled"}, "config", "HTTP 403"),
])
def test_not_retried_classes(wf, spec, cls, msg):
    r, _ = run(ask_scenario(wf), script={"write": spec})
    assert err(r)[0] == cls and msg in err(r)[1]
    assert len(events(r, "model_call")) == 1


def test_empty_content_is_transient(wf):
    r, _ = run(ask_scenario(wf, retry=0), script={"write": {"text": "  "}})
    assert err(r) == ("transient", "empty response without refusal (HTTP 200)")


def test_missing_cost_retried_then_budget(wf):
    r, _ = run(ask_scenario(wf, retry=1), script={"write": {"text": "ok", "cost": None}})
    assert err(r) == ("budget", "unknown cost (response has no usage.cost)")
    assert [e["class"] for e in events(r, "error")] == ["transient", "budget"]
    assert events(r, "model_call")[0]["usage"]["cost_usd"] is None
    assert any("returned no cost" in w for w in r.warnings)


@pytest.mark.parametrize("script,status", [
    ({"propose": [{"status": 429, "error": "Rate limit exceeded"}, {"json": {"names": ["Oatsy", "Frost Oat"]}}]},
     "succeeded"),
    ({"propose": [{"status": 400, "error": "Invalid request"}]}, "failed"),
])
def test_http_error_without_usage_no_cost_warning(wf, script, status):
    """BUGS.md #1: an error response (429, 400) has no usage and costs nothing — no cost warning is needed."""
    r, _ = run(wf / "scenarios" / "tutorial-04-parallel.yaml", {"product": "ice cream"}, script)
    assert r.status == status and r.warnings == []


def test_schema_cascade_goes_level_down_with_feedback(wf):
    script = {"write": [{"text": "this is not JSON"}, {"json": {"text": 5}}, {"json": {"text": "ok"}}]}
    r, fake = run(ask_scenario(wf, schema=True), script=script)
    assert r.status == "succeeded" and r.outputs == {"text": "ok"}
    assert [c["structured_output"] for c in events(r, "model_call")] == ["native_schema", "tool_wrapper", "prompt"]
    assert [e["class"] for e in events(r, "error")] == ["schema", "schema"]
    second, third = fake.calls[1][2], fake.calls[2][2]
    assert second["tools"][0]["function"]["name"] == "_submit_output" and "response_format" not in second
    # feedback: previous model response (with unchanged reasoning_details) + error
    assert second["messages"][2]["role"] == "assistant" and second["messages"][2]["reasoning_details"]
    assert "response is not JSON" in second["messages"][3]["content"]
    assert "Respond only with a JSON object matching this JSON Schema" in third["messages"][0]["content"]
    req = (r.rec.dir / "steps/01-write/calls/02.request.json").read_text()
    assert "<omitted: reasoning_details" in req and "fake-signature" not in req
    assert "Respond only with a JSON object" in (r.rec.dir / "steps/01-write/prompt.md").read_text()


def test_schema_starts_at_alias_level(wf):
    r, fake = run(ask_scenario(wf, schema=True, alias="fast"))
    assert r.status == "succeeded" and fake.calls[0][2]["tool_choice"]["function"]["name"] == "_submit_output"


def test_schema_exhausted(wf):
    r, _ = run(ask_scenario(wf, schema=True, retry=1), script={"write": {"json": {"other": 1}}})
    assert err(r)[0] == "schema" and "does not match schema" in err(r)[1]


def test_expression_error_not_retried(wf):
    p = scenario(wf, HEAD + """
steps:
  - id: k
    jev: { state: x, questions: { q: { type: noul, instructions: y } } }
  - id: s
    set: { c: steps.k.details.q.confidence }
""")
    r, _ = run(p)
    assert err(r)[0] == "expression" and "'steps.k.details.q' has no key 'confidence' (available: —)" in err(r)[1]
    assert r.error["step"] == "s"


def test_jev_missing_answer_is_transient(wf):
    p = scenario(wf, HEAD + "steps: [{ id: k, retry: 0, jev: { state: x, questions: { q: { type: noul, instructions: y } } } }]")
    r, _ = run(p, script={"k": {"body": {"model": "jev", "answers": {}, "usage": {"cost": 0.0}}}})
    assert err(r)[0] == "transient" and "question 'q'" in err(r)[1]


def test_jev_request_shape_and_json_safe_state(wf):
    p = scenario(wf, HEAD + """
inputs: { t: { type: string, default: 'a "b" {c}' } }
steps:
  - id: s
    set: { l: '["x", "y"]' }
  - id: k
    jev:
      state: "{{ steps.s.l }}"
      questions:
        q: { type: choice, instructions: "Topic {{ inputs.t }}", criteria: { a: A, b: "{{ inputs.t }}" } }
  - id: z
    set: { v: 'steps.k.q + "/" + str(steps.k.details.q.probabilities.a)' }
""")
    r, fake = run(p)
    body = fake.calls[0][2]
    assert body == {"model": "jev-1.13", "state": '["x", "y"]', "questions": {"q": {
        "type": "choice", "instructions": 'Topic a "b" {c}', "criteria": {"a": "A", "b": 'a "b" {c}'}}}}
    assert r.values["steps"]["z"]["v"] == "a/1.0"


# --- image --------------------------------------------------------------------------------

IMG = HEAD + """
steps:
  - id: photo
    RETRY
    image: { model: gemini-image, prompt: "Coffee", aspect_ratio: "4:5" }
"""


def test_image_aspect_ok_and_request(wf):
    r, fake = run(scenario(wf, IMG.replace("RETRY", "")))
    assert r.status == "succeeded"
    body = fake.calls[0][2]
    assert body["modalities"] == ["image", "text"] and body["image_config"] == {"aspect_ratio": "4:5"}
    saved = events(r, "image_saved")[0]
    assert saved["width"] / saved["height"] == 0.8 and saved["media_type"] == "image/png"


def test_image_aspect_mismatch_is_config(wf):
    r, _ = run(scenario(wf, IMG.replace("RETRY", "")), script={"photo": {"image": {"width": 1408, "height": 768}}})
    assert err(r)[0] == "config" and "does not support aspect_ratio 4:5: image is 1408×768" in err(r)[1]
    assert len(events(r, "model_call")) == 1


def test_image_missing_becomes_content(wf):
    r, _ = run(scenario(wf, IMG.replace("RETRY", "retry: 1")), script={"photo": {"finish_reason": "stop", "body": {
        "id": "g", "model": "m", "choices": [{"finish_reason": "stop", "message": {"content": "missing"}}],
        "usage": {"cost": 0.01}}}})
    assert err(r) == ("content", "model returned no image")
    assert [(e["class"], e["will_retry"]) for e in events(r, "error")] == [("transient", True), ("content", False)]


def test_image_refusal_is_content(wf):
    r, _ = run(scenario(wf, IMG.replace("RETRY", "")), script={"photo": {"refusal": "person"}})
    assert err(r)[0] == "content" and len(events(r, "model_call")) == 1


def test_images_body_and_response_shapes():
    assert providers.images_body("openai/gpt-image-2", "cup", "1:1", "low") == {
        "model": "openai/gpt-image-2", "prompt": "cup", "aspect_ratio": "1:1", "quality": "low"}
    data = base64.b64encode(b"\x89PNG\r\n\x1a\nheader").decode()
    meta, value, error = providers.parse_images(200, {"data": [{"b64_json": data}], "usage": {"cost": 0.02}}, {})
    assert value == (b"\x89PNG\r\n\x1a\nheader", "image/png") and meta["usage"]["cost_usd"] == 0.02 and error is None
    webp = (b"RIFF\0\0\0\0WEBPVP8X\x0a\0\0\0\0\0\0\0" +
            (63).to_bytes(3, "little") + (63).to_bytes(3, "little"))
    _, value, error = providers.parse_images(200, {"data": [{"b64_json": base64.b64encode(webp).decode()}],
                                                   "usage": {"cost": 0.02}}, {})
    assert value == (webp, "image/webp") and providers.image_size(webp) == (64, 64) and error is None


def test_images_live_response_fixture_shape():
    fixture = json.loads((Path(__file__).parent / "fixtures/openrouter-images-response.json").read_text())
    assert set(fixture) == {"created", "data", "usage"}
    assert fixture["data"][0]["media_type"] == "image/png" and fixture["usage"]["cost"] > 0
    fixture["data"][0]["b64_json"] = base64.b64encode(b"\x89PNG\r\n\x1a\nheader").decode()
    meta, value, error = providers.parse_images(200, fixture, {})
    assert value[1] == "image/png" and meta["usage"]["cost_usd"] == fixture["usage"]["cost"] and error is None


@pytest.mark.parametrize("status,headers,cls,retry_after", [
    (502, {}, "transient", None), (429, {"retry-after": "3"}, "transient", 3.0),
    (400, {}, "config", None), (401, {}, "config", None), (404, {}, "config", None), (403, {}, "content", None),
])
def test_parse_images_errors(status, headers, cls, retry_after):
    body = {"error": {"code": status, "message": "content_policy_violation" if status == 403 else "try again"}}
    _, _, error = providers.parse_images(status, body, headers)
    assert error.cls == cls and error.retry_after == retry_after


def test_parse_images_empty_and_unsupported_format():
    _, _, empty = providers.parse_images(200, {"data": []}, {})
    assert (empty.cls, empty.final) == ("transient", "content")
    encoded = base64.b64encode(b"not an image").decode()
    _, _, unsupported = providers.parse_images(200, {"data": [{"b64_json": encoded}]}, {})
    assert (unsupported.cls, unsupported.message) == ("content", "unsupported image format")


def test_image_api_generates_file_cost_and_image_budget(wf):
    add_image_model(wf)
    cfg = __import__("yaml").safe_load((wf / "config.yaml").read_text())
    cfg["limits"]["run_image_budget_usd"] = 0.03
    (wf / "config.yaml").write_text(__import__("yaml").safe_dump(cfg, allow_unicode=True, sort_keys=False))
    p = scenario(wf, HEAD + 'steps: [{ id: photo, image: { model: gpt-image, prompt: "Coffee", aspect_ratio: "1:1" } }]')
    r, fake = run(p)
    assert r.status == "succeeded", r.error
    assert fake.calls[0][1:] == ("images", {"model": "openai/gpt-image-2", "prompt": "Coffee",
                                               "aspect_ratio": "1:1", "quality": "low"})
    assert r.values["steps"]["photo"]["file"].path.endswith("/image.png")
    assert (r.rec.dir / r.values["steps"]["photo"]["file"].path).is_file()
    call = events(r, "model_call")[0]
    assert call["usage"]["cost_usd"] == r.image_cost == 0.04 and call["timeout_s"] == 180
    assert call["budget_exceeded_usd"] == 0.01
    assert events(r, "run_finished")[0]["image_cost_usd"] == 0.04


def test_image_api_aspect_ratio_mismatch_is_config(wf):
    add_image_model(wf)
    p = scenario(wf, HEAD + 'steps: [{ id: photo, image: { model: gpt-image, prompt: x, aspect_ratio: "1:1" } }]')
    r, _ = run(p, script={"photo": {"image": {"width": 128, "height": 64}}})
    assert err(r)[0] == "config" and "model does not support aspect_ratio 1:1" in err(r)[1]


# --- budget and time ----------------------------------------------------------------------------

def test_run_budget_checked_before_call(wf):
    cfg = wf / "config.yaml"
    cfg.write_text(cfg.read_text().replace("run_budget_usd: 1.00", "run_budget_usd: 0.0001"))
    p = scenario(wf, HEAD + """
steps:
  - { id: a, on_error: continue, default: { text: x }, ask: { agent: copywriter, prompt: x } }
  - { id: b, on_error: continue, default: { text: x }, ask: { agent: copywriter, prompt: y } }
""")
    r, fake = run(p, script={"a": {"text": "ok", "cost": 0.0003}})
    assert len(fake.calls) == 1                         # the second call did not start
    assert err(r)[0] == "budget" and r.error["step"] == "b" and "run (run_budget_usd) exhausted" in err(r)[1]
    assert any("exceeded by 0.0002 USD" in w for w in r.warnings)  # the call exceeding the budget completes
    assert events(r, "model_call")[0]["budget_exceeded_usd"] == 0.0002


def test_step_budget_and_continue(wf):
    p = scenario(wf, HEAD + """
steps:
  - id: a
    budget_usd: 0.0001
    on_error: continue
    default: { text: "fallback" }
    ask: { agent: copywriter, prompt: x }
  - id: b
    set: { t: steps.a.text }
""")
    r, fake = run(p, script={"a": [{"finish_reason": "error", "cost": 0.0002}]})
    assert r.status == "succeeded" and r.values["steps"]["b"]["t"] == "fallback"
    fin = [e for e in events(r, "step_finished") if e["step"] == "a"][0]
    assert fin["status"] == "failed" and fin["continued"] is True
    assert any("on_error: continue" in w for w in r.warnings) and len(fake.calls) == 1


def test_step_timeout(wf):
    p = scenario(wf, HEAD + "steps: [{ id: a, timeout: 1s, ask: { agent: copywriter, prompt: x } }]")
    r, _ = run(p, script={"a": {"sleep": 3}})
    assert err(r) == ("timeout", "timeout exceeded for step (1s)")


def test_read_timeout_is_transient_and_capped(wf):
    """ISSUES 34: call read timeout = min(remaining step time, 120 s chat / 30 s Jev); expiration → transient + retry."""
    p = scenario(wf, HEAD + """
steps:
  - { id: a, timeout: 10s, ask: { agent: copywriter, prompt: x } }
  - { id: b, timeout: 5m, ask: { agent: copywriter, prompt: x } }
  - { id: j, timeout: 5m, jev: { state: x, questions: { q: { type: noul, instructions: y } } } }
""")
    fake, sent = Fake(None, model_ids(wf)), []
    handle = fake.handle

    def hang_once(request):
        if request.url.path.endswith("/models"):
            return handle(request)
        sent.append(request.extensions["timeout"]["read"])
        if len(sent) == 1:
            raise httpx.ReadTimeout("stalled connection", request=request)
        return handle(request)

    fake.handle = hang_once
    pr = validate(p, transport=fake.transport())
    r = run_scenario(pr, {}, fake=fake)
    assert r.status == "succeeded", r.error
    e = events(r, "error")[0]
    assert (e["step"], e["class"], e["will_retry"]) == ("a", "transient", True) and "ReadTimeout" in e["message"]
    calls = {(c["step"], c["attempt"]): c["timeout_s"] for c in events(r) if c["type"] in ("model_call", "jev_call")}
    assert calls["a", 2] <= calls["a", 1] <= 10                      # remaining step time (independent of speed)
    assert calls["b", 1] == 120 and calls["j", 1] == 30              # chat / Jev cap
    assert sent[0] == calls["a", 1] and sent[-1] == 30               # httpx received the same timeout


def test_run_timeout_not_overridden_by_continue(wf):
    cfg = wf / "config.yaml"
    cfg.write_text(cfg.read_text().replace("run_timeout: 1h", "run_timeout: 1s"))
    p = scenario(wf, HEAD + """
steps:
  - { id: a, on_error: continue, default: { text: x }, ask: { agent: copywriter, prompt: x } }
  - { id: b, set: { v: 1 } }
""")
    r, _ = run(p, script={"a": {"sleep": 3}})
    assert err(r) == ("timeout", "timeout exceeded for run (run_timeout 1s)")
    assert "b" not in r.values["steps"]


# --- when, set, fail, switch, parallel -----------------------------------------------------------

def test_when_default_and_null_from_default(wf):
    p = scenario(wf, HEAD + """
outputs: { image: { type: file }, t: { type: string } }
steps:
  - id: photo
    when: 1 > 2
    default: { file: null }
    image: { model: gemini-image, prompt: x }
  - id: out
    output: { image: "{{ steps.photo.file }}", t: "file: {{ steps.photo.file }}" }
""")
    r, fake = run(p)
    assert r.status == "succeeded" and not fake.calls
    assert r.outputs == {"image": None, "t": "file: null"}
    assert events(r, "step_skipped")[0]["default_used"] is True


def test_fail_step(wf):
    p = scenario(wf, HEAD + """
inputs: { x: { type: number, default: 0.42 } }
steps:
  - { id: stop, when: inputs.x < 0.7, fail: "Does not match (on_brand = {{ inputs.x }})" }
""")
    r, _ = run(p)
    assert r.error == {"class": "fail", "step": "stop", "message": "Does not match (on_brand = 0.42)"}
    summary = (r.rec.dir / "summary.md").read_text()
    assert "— failed" in summary and "Run ended at step stop." in summary
    assert json.loads((r.rec.dir / "callback.json").read_text())["error"]["class"] == "fail"


SWITCH = HEAD + """
inputs: { v: { type: string, default: VALUE } }
steps:
  - id: s
    switch:
      value: inputs.v
      cases:
        a: [{ id: xa, set: { r: '"A"' }, default: { r: "-" } }]
        b: [{ id: xb, set: { r: '"B"' }, default: { r: "-" } }]
      default: [{ id: xd, set: { r: '"D"' }, default: { r: "-" } }]
  - id: z
    set: { r: 'steps.xa.r + steps.xb.r + steps.xd.r' }
"""


def test_switch_branches(wf):
    r, _ = run(scenario(wf, SWITCH.replace("VALUE", "b")))
    assert r.values["steps"]["z"]["r"] == "-B-"
    skipped = {e["step"]: e for e in events(r, "step_skipped")}
    assert skipped["xa"]["reason"] == 'switch: s = "b"' and skipped["xa"]["reason_code"] == "switch"
    assert [e for e in events(r, "step_started") if e["step"] == "xb"][0]["branch"] == "b"
    r, _ = run(scenario(wf, SWITCH.replace("VALUE", "other"), name="t2"))
    assert r.values["steps"]["z"]["r"] == "--D"


def test_switch_non_string_is_expression(wf):
    p = scenario(wf, HEAD + """
steps:
  - { id: k, jev: { state: x, questions: { q: { type: noul, instructions: y } } } }
  - id: s
    switch: { value: 'steps.k.details.q.x', cases: { a: [{ id: a1, fail: x }] }, default: [] }
""")
    r, _ = run(p, script={"k": {"body": {"model": "j", "answers": {"q": {"type": "noul", "noul": 0.5, "x": None}},
                                         "usage": {"cost": 0}}}})
    assert err(r)[0] == "expression" and "switch.value must return text" in err(r)[1]


PARALLEL = HEAD + """
steps:
  - id: p
    parallel:
      fast:
        - { id: r1, ask: { agent: copywriter, prompt: quickly } }
      slow:
        - { id: s1, ask: { agent: copywriter, prompt: slowly } }
        - { id: s2, set: { v: steps.s1.text } }
  - id: z
    set: { v: 'steps.r1.text + steps.s2.v' }
"""


def test_parallel_ok(wf):
    r, _ = run(scenario(wf, PARALLEL), script={"r1": {"text": "A"}, "s1": {"text": "B"}})
    assert r.status == "succeeded" and r.values["steps"]["z"]["v"] == "AB"
    fin = [e for e in events(r, "step_finished") if e["step"] == "p"][0]
    assert fin["cost_usd"] == pytest.approx(0.0002)
    assert {e["step"]: e.get("branch") for e in events(r, "step_started")}["s1"] == "slow"


def test_parallel_failure_cancels_other_branch(wf):
    r, _ = run(scenario(wf, PARALLEL), script={"r1": {"status": 400}, "s1": {"sleep": 5, "text": "B"}})
    assert r.error["step"] == "r1" and r.error["class"] == "config"
    fin = {e["step"]: e["status"] for e in events(r, "step_finished")}
    assert fin == {"r1": "failed", "s1": "cancelled", "p": "failed"}
    assert [(e["step"], e["reason_code"]) for e in events(r, "step_skipped")] == [("s2", "cancelled")]
    assert "z" not in r.values["steps"]


def test_parallel_skipped_with_when(wf):
    r, fake = run(scenario(wf, PARALLEL.replace("  - id: p\n", "  - id: p\n    when: 1 > 2\n")
                           .replace("  - id: z\n    set: { v: 'steps.r1.text + steps.s2.v' }\n", "")))
    assert r.status == "succeeded" and not fake.calls
    assert [e["step"] for e in events(r, "step_skipped")] == ["p", "r1", "s1", "s2"]


# --- secret values and callback -------------------------------------------------------------

def test_secrets_masked_everywhere(wf, monkeypatch):
    monkeypatch.setenv("CALLBACK_SECRET", "super-secret-password-123")
    r, _ = run(ask_scenario(wf), script={"write": {"text": "the key is super-secret-password-123"}})
    assert r.status == "succeeded"
    for f in r.rec.dir.rglob("*"):
        if f.is_file() and f.suffix != ".png":
            assert "super-secret-password-123" not in f.read_text(), f
    assert "<secret: CALLBACK_SECRET>" in (r.rec.dir / "callback.json").read_text()
    assert any("CALLBACK_SECRET" in w for w in r.warnings)


def test_callback_signed(wf, monkeypatch):
    monkeypatch.setenv("CALLBACK_SECRET", "signature-123456")
    got = []

    def handler(req):
        got.append(req)
        return httpx.Response(200)
    r, _ = run(ask_scenario(wf), script={"write": {"text": "ok"}}, callback_url="https://n8n.example.com/w/1?t=x",
               request_key="k-1", callback_transport=httpx.MockTransport(handler))
    assert len(got) == 1
    req = got[0]
    assert req.headers["x-run-id"] == r.run_id
    assert req.headers["x-signature"] == "sha256=" + hmac.new(b"signature-123456", req.content, hashlib.sha256).hexdigest()
    body = json.loads(req.content)
    assert body == json.loads((r.rec.dir / "callback.json").read_text())
    assert body["request_key"] == "k-1" and body["outputs"] == {"text": "ok"}
    assert body["report_url"].startswith("file://") and body["report_url"].endswith("/report.html")
    sent = events(r, "callback_sent")[0]
    assert sent["url"] == "https://n8n.example.com/w/1" and sent["http_status"] == 200


def test_callback_failure_does_not_change_status(wf, monkeypatch):
    monkeypatch.setenv("CALLBACK_SECRET", "signature-123456")
    r, _ = run(ask_scenario(wf), script={"write": {"text": "ok"}}, callback_url="https://n8n.example.com/w",
               callback_transport=httpx.MockTransport(lambda req: httpx.Response(500)))
    assert r.status == "succeeded" and r.callback_failed
    assert [e["attempt"] for e in events(r, "callback_sent")] == [1, 2, 3]
    assert events(r)[-1]["type"] == "callback_failed"
    assert "Callback not delivered" in (r.rec.dir / "summary.md").read_text()


def test_callback_requires_https_and_secret(wf, monkeypatch):
    from agencast import ConfigErrors
    monkeypatch.delenv("CALLBACK_SECRET", raising=False)
    with pytest.raises(ConfigErrors) as e:
        run(ask_scenario(wf), callback_url="http://n8n.example.com/w")
    assert "https://" in str(e.value) and "CALLBACK_SECRET" in str(e.value)


# --- concurrent runs (ISSUES 39) ------------------------------------------------------------

class _FrozenNow(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 9, 26, 12, 0, 0, tzinfo=tz)


def _same_suffix(monkeypatch, suffixes):
    """run_id in the same second with suffixes from `suffixes` (other token_hex calls unchanged)."""
    real, it = engine.secrets.token_hex, iter(suffixes)
    monkeypatch.setattr(engine, "datetime", _FrozenNow)
    monkeypatch.setattr(engine.secrets, "token_hex", lambda n=None: next(it) if n == 2 else real(n))


def test_run_id_collision_retries_with_new_suffix(wf, monkeypatch):
    """ISSUES 35: a second run in the same second with the same suffix gets a different ID; both records are created."""
    _same_suffix(monkeypatch, ["aaaa", "aaaa", "bbbb"])
    path = ask_scenario(wf)
    r1, _ = run(path)
    r2, _ = run(path)
    assert (r1.run_id, r2.run_id) == ("20260926-120000-test-aaaa", "20260926-120000-test-bbbb")
    assert all((wf.parent / "runs" / r.run_id / "events.jsonl").is_file() for r in (r1, r2))


def test_run_id_collision_gives_up_after_five_tries(wf, monkeypatch):
    _same_suffix(monkeypatch, ["aaaa"] * 6)
    path = ask_scenario(wf)
    run(path)
    with pytest.raises(AgencastError, match="5× run_id collisions") as e:
        run(path)
    assert e.value.cls == "internal"


def test_models_cache_atomic_and_corrupt_is_ignored(tmp_path, monkeypatch):
    """/models cache: corrupt JSON = no cache; write via a temporary file + os.replace."""
    calls = []

    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"data": [{"id": "a/b"}]})
    real_client = httpx.Client
    monkeypatch.setattr(providers.httpx, "Client",
                        lambda **kw: real_client(**{**kw, "transport": httpx.MockTransport(handle)}))
    (tmp_path / "_models.json").write_text('{"base_url": "https://x", "fetch')  # partial write
    assert [m["id"] for m in providers.list_models("https://x", tmp_path)] == ["a/b"]
    assert json.loads((tmp_path / "_models.json").read_text())["base_url"] == "https://x"
    assert [p.name for p in tmp_path.iterdir()] == ["_models.json"]  # no leftover .tmp
    providers.list_models("https://x", tmp_path)
    assert len(calls) == 1  # second call uses cache


def test_images_models_have_separate_cache(tmp_path, monkeypatch):
    calls = []

    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"data": [{"id": "openai/gpt-image-2",
            "architecture": {"output_modalities": ["image"]},
            "supported_parameters": {"aspect_ratio": {"values": ["1:1"]}}}]})
    real_client = httpx.Client
    monkeypatch.setattr(providers.httpx, "Client",
                        lambda **kw: real_client(**{**kw, "transport": httpx.MockTransport(handle)}))
    models = providers.list_image_models("https://x/api/v1", tmp_path)
    assert models[0]["supported_parameters"]["aspect_ratio"]["values"] == ["1:1"]
    assert (tmp_path / "_images_models.json").is_file()
    providers.list_image_models("https://x/api/v1", tmp_path)
    assert calls == ["/api/v1/images/models"]
