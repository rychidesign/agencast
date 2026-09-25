"""Běh s falešným poskytovatelem: třídy chyb a jejich chování (scenario.md §6),
kroky, záznam běhu (run-record.md), callback."""
import hashlib
import hmac
import json
import re

import httpx
import pytest
from conftest import events, run, scenario

from maw.engine import dry_run
from maw.validate import validate

HEAD = "version: 1\nname: NAME\ndescription: Testovací scénář\n"
ASK = HEAD + """
outputs: { text: { type: string } }
steps:
  - id: napis
    RETRY
    ask: { agent: copywriter, prompt: "Pozdrav" SCHEMA }
  - id: out
    output: { text: "{{ steps.napis.OUT }}" }
"""


def ask_scenario(wf, retry=None, schema=False, alias=None):
    text = ASK.replace("RETRY", f"retry: {retry}" if retry is not None else "")
    text = text.replace("SCHEMA", ", schema: { text: string }" if schema else "").replace("OUT", "text")
    if alias:
        f = wf / "agents" / "copywriter.md"
        f.write_text(f.read_text().replace("model: chytry", f"model: {alias}"))
    return scenario(wf, text)


def err(r):
    return (r.error or {}).get("class"), (r.error or {}).get("message", "")


# --- úspěch a záznam --------------------------------------------------------------------

def test_record_layout_and_events(wf):
    r, fake = run(wf / "scenarios" / "ig-post.yaml", {"tema": "káva"},
                  __import__("yaml").safe_load(open(__file__.replace("test_engine.py", "golden/ig-post.yaml"))))
    assert r.status == "succeeded", r.error
    d = r.rec.dir
    assert re.fullmatch(r"\d{8}-\d{6}-ig-post-[0-9a-f]{4}", r.run_id)
    for f in ("plan.md", "inputs.json", "events.jsonl", "summary.md", "callback.json",
              "steps/01-copy/prompt.md", "steps/01-copy/calls/01.request.json", "steps/01-copy/calls/01.response.json",
              "steps/01-copy/output.json", "steps/02-kontrola/output.json", "steps/07-foto/image.png",
              "steps/07-foto/output.json", "steps/08-out/output.json"):
        assert (d / f).is_file(), f
    assert not (d / "steps/03-stop").exists()  # přeskočený krok nemá složku
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
                       "reason": "when: steps.kontrola.on_brand < 0.7 → false"}
    calls = events(r, "model_call")
    assert [c["structured_output"] for c in calls] == ["native_schema", "tool_wrapper", None]
    assert calls[0]["usage"] == {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.0001}
    jev = events(r, "jev_call")[0]
    assert jev["answers"] == {"on_brand": 0.91} and jev["response_model"] == "typesafe/jev-fake"
    # base64 ani reasoning_details v záznamu nikde
    for f in d.rglob("*"):
        if f.suffix in (".json", ".jsonl", ".md"):
            text = f.read_text()
            assert "base64," not in text and "falešný-podpis" not in text, f
    assert "<soubor: steps/07-foto/image.png" in (d / "steps/07-foto/calls/01.response.json").read_text()
    cb = json.loads((d / "callback.json").read_text())
    assert cb["status"] == "succeeded" and cb["outputs"]["hashtags"] == ["#thtd", "#kava", "#rano"]
    assert cb["outputs"]["image"].startswith("file://") and started["storage_prefix"] in cb["outputs"]["image"]
    assert json.loads((d / "steps/07-foto/output.json").read_text()) == {"file": "steps/07-foto/image.png"}
    summary = (d / "summary.md").read_text()
    assert summary.startswith("# test" if False else "# ig-post — úspěch")
    assert "| 3 | stop | fail | přeskočeno |" in summary and "on_brand = 0,91" in summary
    fin = events(r, "run_finished")[0]
    assert fin["status"] == "succeeded" and fin["image_cost_usd"] == 0.04 and fin["error"] is None


def test_ask_text_and_system_prompt_with_skill(wf):
    r, fake = run(ask_scenario(wf), script={"napis": {"text": "Ahoj!"}})
    assert r.status == "succeeded" and r.outputs == {"text": "Ahoj!"}
    body = fake.calls[0][2]
    system = body["messages"][0]["content"]
    assert system.startswith("Jsi copywriter") and "## Skill: thtd-hlas" in system
    assert body["messages"][1] == {"role": "user", "content": "Pozdrav"}
    assert "response_format" not in body and body["usage"] == {"include": True}


def test_dry_run_only_plan(wf):
    p = validate(wf / "scenarios" / "ig-post.yaml", check_models=False)
    rec = dry_run(p, {"tema": "x"})
    assert sorted(f.name for f in rec.dir.iterdir()) == ["inputs.json", "plan.md"]
    plan = (rec.dir / "plan.md").read_text()
    assert "| 1 | copy | ask |" in plan and "anthropic/claude-haiku-4.5" in plan and "4:5" in plan


# --- třídy chyb ---------------------------------------------------------------------------

def test_transient_retried_then_ok(wf):
    r, fake = run(ask_scenario(wf), script={"napis": [{"status": 429}, {"status": 502}, {"text": "ok"}]})
    assert r.status == "succeeded"
    errs = events(r, "error")
    assert [(e["class"], e["will_retry"], e["http_status"]) for e in errs] == \
        [("transient", True, 429), ("transient", True, 502)]
    assert [c["attempt"] for c in events(r, "model_call")] == [1, 2, 3]
    assert sorted(p.name for p in (r.rec.dir / "steps/01-napis/calls").iterdir())[-1] == "03.response.json"


def test_transient_exhausted(wf):
    r, _ = run(ask_scenario(wf, retry=1), script={"napis": {"status": 503}})
    assert err(r)[0] == "transient" and r.error["step"] == "napis"
    assert len(events(r, "model_call")) == 2 and events(r, "error")[-1]["will_retry"] is False


def test_200_with_finish_reason_error_is_transient(wf):
    r, _ = run(ask_scenario(wf), script={"napis": [{"finish_reason": "error"}, {"text": "ok"}]})
    assert r.status == "succeeded"
    assert events(r, "error")[0]["message"] == "poskytovatel vrátil HTTP 200 s finish_reason: error"


def test_200_with_error_body_is_transient(wf):
    body = {"error": {"code": 502, "message": "upstream"}}
    r, _ = run(ask_scenario(wf, retry=0), script={"napis": {"body": body}})
    assert err(r) == ("transient", "HTTP 200 (error.code 502): upstream")


@pytest.mark.parametrize("spec,cls,msg", [
    ({"finish_reason": "length"}, "config", "max_tokens"),
    ({"finish_reason": "content_filter"}, "content", "filtr"),
    ({"refusal": "Nemohu."}, "content", "model odmítl: Nemohu."),
    ({"status": 402}, "budget", "došel kredit"),
    ({"status": 400}, "config", "HTTP 400"),
    ({"status": 401}, "config", "HTTP 401"),
    ({"status": 403, "error": "flagged by moderation"}, "content", "moderation"),
    ({"status": 403, "error": "key disabled"}, "config", "HTTP 403"),
])
def test_not_retried_classes(wf, spec, cls, msg):
    r, _ = run(ask_scenario(wf), script={"napis": spec})
    assert err(r)[0] == cls and msg in err(r)[1]
    assert len(events(r, "model_call")) == 1


def test_empty_content_is_transient(wf):
    r, _ = run(ask_scenario(wf, retry=0), script={"napis": {"text": "  "}})
    assert err(r) == ("transient", "prázdná odpověď bez odmítnutí (HTTP 200)")


def test_missing_cost_retried_then_budget(wf):
    r, _ = run(ask_scenario(wf, retry=1), script={"napis": {"text": "ok", "cost": None}})
    assert err(r) == ("budget", "cena neznámá (odpověď nemá usage.cost)")
    assert [e["class"] for e in events(r, "error")] == ["transient", "budget"]
    assert events(r, "model_call")[0]["usage"]["cost_usd"] is None
    assert any("nevrátil cenu" in w for w in r.warnings)


def test_schema_cascade_goes_level_down_with_feedback(wf):
    script = {"napis": [{"text": "tohle není JSON"}, {"json": {"text": 5}}, {"json": {"text": "ok"}}]}
    r, fake = run(ask_scenario(wf, schema=True), script=script)
    assert r.status == "succeeded" and r.outputs == {"text": "ok"}
    assert [c["structured_output"] for c in events(r, "model_call")] == ["native_schema", "tool_wrapper", "prompt"]
    assert [e["class"] for e in events(r, "error")] == ["schema", "schema"]
    second, third = fake.calls[1][2], fake.calls[2][2]
    assert second["tools"][0]["function"]["name"] == "_submit_output" and "response_format" not in second
    # zpětná vazba: předchozí odpověď modelu (s reasoning_details beze změny) + chyba
    assert second["messages"][2]["role"] == "assistant" and second["messages"][2]["reasoning_details"]
    assert "odpověď není JSON" in second["messages"][3]["content"]
    assert "Odpověz jen JSON objektem podle tohoto JSON Schema" in third["messages"][0]["content"]
    req = (r.rec.dir / "steps/01-napis/calls/02.request.json").read_text()
    assert "<vynecháno: reasoning_details" in req and "falešný-podpis" not in req
    assert "Odpověz jen JSON objektem" in (r.rec.dir / "steps/01-napis/prompt.md").read_text()


def test_schema_starts_at_alias_level(wf):
    r, fake = run(ask_scenario(wf, schema=True, alias="rychly"))
    assert r.status == "succeeded" and fake.calls[0][2]["tool_choice"]["function"]["name"] == "_submit_output"


def test_schema_exhausted(wf):
    r, _ = run(ask_scenario(wf, schema=True, retry=1), script={"napis": {"json": {"jine": 1}}})
    assert err(r)[0] == "schema" and "nesedí na schema" in err(r)[1]


def test_expression_error_not_retried(wf):
    p = scenario(wf, HEAD + """
steps:
  - id: k
    jev: { state: x, questions: { q: { type: noul, instructions: y } } }
  - id: s
    set: { c: steps.k.details.q.confidence }
""")
    r, _ = run(p)
    assert err(r)[0] == "expression" and "'steps.k.details.q' nemá klíč 'confidence' (dostupné: —)" in err(r)[1]
    assert r.error["step"] == "s"


def test_jev_missing_answer_is_transient(wf):
    p = scenario(wf, HEAD + "steps: [{ id: k, retry: 0, jev: { state: x, questions: { q: { type: noul, instructions: y } } } }]")
    r, _ = run(p, script={"k": {"body": {"model": "jev", "answers": {}, "usage": {"cost": 0.0}}}})
    assert err(r)[0] == "transient" and "otázku 'q'" in err(r)[1]


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
        q: { type: choice, instructions: "Téma {{ inputs.t }}", criteria: { a: A, b: "{{ inputs.t }}" } }
  - id: z
    set: { v: 'steps.k.q + "/" + str(steps.k.details.q.probabilities.a)' }
""")
    r, fake = run(p)
    body = fake.calls[0][2]
    assert body == {"model": "jev-1.13", "state": '["x", "y"]', "questions": {"q": {
        "type": "choice", "instructions": 'Téma a "b" {c}', "criteria": {"a": "A", "b": 'a "b" {c}'}}}}
    assert r.values["steps"]["z"]["v"] == "a/1.0"


# --- obrázek --------------------------------------------------------------------------------

IMG = HEAD + """
steps:
  - id: foto
    RETRY
    image: { model: gemini-image, prompt: "Káva", aspect_ratio: "4:5" }
"""


def test_image_aspect_ok_and_request(wf):
    r, fake = run(scenario(wf, IMG.replace("RETRY", "")))
    assert r.status == "succeeded"
    body = fake.calls[0][2]
    assert body["modalities"] == ["image", "text"] and body["image_config"] == {"aspect_ratio": "4:5"}
    saved = events(r, "image_saved")[0]
    assert saved["width"] / saved["height"] == 0.8 and saved["media_type"] == "image/png"


def test_image_aspect_mismatch_is_config(wf):
    r, _ = run(scenario(wf, IMG.replace("RETRY", "")), script={"foto": {"image": {"width": 1408, "height": 768}}})
    assert err(r)[0] == "config" and "nepodporuje aspect_ratio 4:5: obrázek má 1408×768" in err(r)[1]
    assert len(events(r, "model_call")) == 1


def test_image_missing_becomes_content(wf):
    r, _ = run(scenario(wf, IMG.replace("RETRY", "retry: 1")), script={"foto": {"finish_reason": "stop", "body": {
        "id": "g", "model": "m", "choices": [{"finish_reason": "stop", "message": {"content": "nic"}}],
        "usage": {"cost": 0.01}}}})
    assert err(r) == ("content", "model nevrátil obrázek")
    assert [(e["class"], e["will_retry"]) for e in events(r, "error")] == [("transient", True), ("content", False)]


def test_image_refusal_is_content(wf):
    r, _ = run(scenario(wf, IMG.replace("RETRY", "")), script={"foto": {"refusal": "osoba"}})
    assert err(r)[0] == "content" and len(events(r, "model_call")) == 1


# --- rozpočet a čas ----------------------------------------------------------------------------

def test_run_budget_checked_before_call(wf):
    cfg = wf / "config.yaml"
    cfg.write_text(cfg.read_text().replace("run_budget_usd: 1.00", "run_budget_usd: 0.0001"))
    p = scenario(wf, HEAD + """
steps:
  - { id: a, on_error: continue, default: { text: x }, ask: { agent: copywriter, prompt: x } }
  - { id: b, on_error: continue, default: { text: x }, ask: { agent: copywriter, prompt: y } }
""")
    r, fake = run(p, script={"a": {"text": "ok", "cost": 0.0003}})
    assert len(fake.calls) == 1                         # druhé volání se nespustilo
    assert err(r)[0] == "budget" and r.error["step"] == "b" and "běhu (run_budget_usd) vyčerpán" in err(r)[1]
    assert any("překročen o 0.0002 USD" in w for w in r.warnings)  # volání, které překročí, se dokončí
    assert events(r, "model_call")[0]["budget_exceeded_usd"] == 0.0002


def test_step_budget_and_continue(wf):
    p = scenario(wf, HEAD + """
steps:
  - id: a
    budget_usd: 0.0001
    on_error: continue
    default: { text: "výchozí" }
    ask: { agent: copywriter, prompt: x }
  - id: b
    set: { t: steps.a.text }
""")
    r, fake = run(p, script={"a": [{"finish_reason": "error", "cost": 0.0002}]})
    assert r.status == "succeeded" and r.values["steps"]["b"]["t"] == "výchozí"
    fin = [e for e in events(r, "step_finished") if e["step"] == "a"][0]
    assert fin["status"] == "failed" and fin["continued"] is True
    assert any("on_error: continue" in w for w in r.warnings) and len(fake.calls) == 1


def test_step_timeout(wf):
    p = scenario(wf, HEAD + "steps: [{ id: a, timeout: 1s, ask: { agent: copywriter, prompt: x } }]")
    r, _ = run(p, script={"a": {"sleep": 3}})
    assert err(r) == ("timeout", "překročen časový limit kroku (1s)")


def test_run_timeout_not_overridden_by_continue(wf):
    cfg = wf / "config.yaml"
    cfg.write_text(cfg.read_text().replace("run_timeout: 1h", "run_timeout: 1s"))
    p = scenario(wf, HEAD + """
steps:
  - { id: a, on_error: continue, default: { text: x }, ask: { agent: copywriter, prompt: x } }
  - { id: b, set: { v: 1 } }
""")
    r, _ = run(p, script={"a": {"sleep": 3}})
    assert err(r) == ("timeout", "překročen časový limit běhu (run_timeout 1s)")
    assert "b" not in r.values["steps"]


# --- when, set, fail, switch, parallel -----------------------------------------------------------

def test_when_default_and_null_from_default(wf):
    p = scenario(wf, HEAD + """
outputs: { image: { type: file }, t: { type: string } }
steps:
  - id: foto
    when: 1 > 2
    default: { file: null }
    image: { model: gemini-image, prompt: x }
  - id: out
    output: { image: "{{ steps.foto.file }}", t: "soubor: {{ steps.foto.file }}" }
""")
    r, fake = run(p)
    assert r.status == "succeeded" and not fake.calls
    assert r.outputs == {"image": None, "t": "soubor: null"}
    assert events(r, "step_skipped")[0]["default_used"] is True


def test_fail_step(wf):
    p = scenario(wf, HEAD + """
inputs: { x: { type: number, default: 0.42 } }
steps:
  - { id: stop, when: inputs.x < 0.7, fail: "Nesedí (on_brand = {{ inputs.x }})" }
""")
    r, _ = run(p)
    assert r.error == {"class": "fail", "step": "stop", "message": "Nesedí (on_brand = 0.42)"}
    summary = (r.rec.dir / "summary.md").read_text()
    assert "— chyba" in summary and "Běh skončil v kroku stop." in summary
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
    r, _ = run(scenario(wf, SWITCH.replace("VALUE", "jine"), name="t2"))
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
    assert err(r)[0] == "expression" and "switch.value musí dát text" in err(r)[1]


PARALLEL = HEAD + """
steps:
  - id: p
    parallel:
      rychla:
        - { id: r1, ask: { agent: copywriter, prompt: rychle } }
      pomala:
        - { id: s1, ask: { agent: copywriter, prompt: pomalu } }
        - { id: s2, set: { v: steps.s1.text } }
  - id: z
    set: { v: 'steps.r1.text + steps.s2.v' }
"""


def test_parallel_ok(wf):
    r, _ = run(scenario(wf, PARALLEL), script={"r1": {"text": "A"}, "s1": {"text": "B"}})
    assert r.status == "succeeded" and r.values["steps"]["z"]["v"] == "AB"
    fin = [e for e in events(r, "step_finished") if e["step"] == "p"][0]
    assert fin["cost_usd"] == pytest.approx(0.0002)
    assert {e["step"]: e.get("branch") for e in events(r, "step_started")}["s1"] == "pomala"


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


# --- tajné hodnoty a callback -------------------------------------------------------------

def test_secrets_masked_everywhere(wf, monkeypatch):
    monkeypatch.setenv("CALLBACK_SECRET", "super-tajne-heslo-123")
    r, _ = run(ask_scenario(wf), script={"napis": {"text": "klíč je super-tajne-heslo-123"}})
    assert r.status == "succeeded"
    for f in r.rec.dir.rglob("*"):
        if f.is_file() and f.suffix != ".png":
            assert "super-tajne-heslo-123" not in f.read_text(), f
    assert "<tajné: CALLBACK_SECRET>" in (r.rec.dir / "callback.json").read_text()
    assert any("CALLBACK_SECRET" in w for w in r.warnings)


def test_callback_signed(wf, monkeypatch):
    monkeypatch.setenv("CALLBACK_SECRET", "podpis-123456")
    got = []

    def handler(req):
        got.append(req)
        return httpx.Response(200)
    r, _ = run(ask_scenario(wf), script={"napis": {"text": "ok"}}, callback_url="https://n8n.example.com/w/1?t=x",
               request_key="k-1", callback_transport=httpx.MockTransport(handler))
    assert len(got) == 1
    req = got[0]
    assert req.headers["x-run-id"] == r.run_id
    assert req.headers["x-signature"] == "sha256=" + hmac.new(b"podpis-123456", req.content, hashlib.sha256).hexdigest()
    body = json.loads(req.content)
    assert body == json.loads((r.rec.dir / "callback.json").read_text())
    assert body["request_key"] == "k-1" and body["outputs"] == {"text": "ok"}
    assert body["report_url"].startswith("file://") and body["report_url"].endswith("/report.html")
    sent = events(r, "callback_sent")[0]
    assert sent["url"] == "https://n8n.example.com/w/1" and sent["http_status"] == 200


def test_callback_failure_does_not_change_status(wf, monkeypatch):
    monkeypatch.setenv("CALLBACK_SECRET", "podpis-123456")
    r, _ = run(ask_scenario(wf), script={"napis": {"text": "ok"}}, callback_url="https://n8n.example.com/w",
               callback_transport=httpx.MockTransport(lambda req: httpx.Response(500)))
    assert r.status == "succeeded" and r.callback_failed
    assert [e["attempt"] for e in events(r, "callback_sent")] == [1, 2, 3]
    assert events(r)[-1]["type"] == "callback_failed"
    assert "Callback nedoručen" in (r.rec.dir / "summary.md").read_text()


def test_callback_requires_https_and_secret(wf, monkeypatch):
    from maw import ConfigErrors
    monkeypatch.delenv("CALLBACK_SECRET", raising=False)
    with pytest.raises(ConfigErrors) as e:
        run(ask_scenario(wf), callback_url="http://n8n.example.com/w")
    assert "https://" in str(e.value) and "CALLBACK_SECRET" in str(e.value)
