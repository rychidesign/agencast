"""The call step (scenario.md call, DESIGN §5.3): nested scenario in the same run,
inputs/outputs contract, callable, cycles and depth, shared budget."""
import json
from pathlib import Path

import pytest
from conftest import events, run, scenario

from agencast import ConfigErrors
from agencast.loader import read_yaml
from agencast.validate import validate

GOLDEN = Path(__file__).resolve().parents[2] / "examples" / "showcase" / "fake" / "demo-call.yaml"

CALLEE = """
version: 1
name: NAME
description: Called scenario
callable: CALLABLE
inputs:
  text: { type: string, required: true }
  n: { type: number, default: 1 }
outputs:
  length: { type: number }
  text: { type: string }
steps:
  - id: calculate
    set: { length: len(inputs.text) + inputs.n }
  - id: STOP
    when: inputs.n > 5
    fail: "n is too large: {{ inputs.n }}"
  - id: out
    output: { length: "{{ steps.calculate.length }}", text: "{{ inputs.text }}" }
"""


def callee(wf, name="callee", callable_=True):
    return scenario(wf, CALLEE.replace("CALLABLE", str(callable_).lower()).replace("STOP", "stop"), name)


def caller(wf, call_body, rest="", name="test", extra_inputs=""):
    return scenario(wf, f"""
        version: 1
        name: NAME
        description: Calling scenario
        inputs:
          topic: {{ type: string, default: coffee }}
          {extra_inputs}
        steps:
          - id: draft
            {call_body}
        {rest}
        """, name)


def config_errors(path) -> str:
    with pytest.raises(ConfigErrors) as e:
        run(path)
    return "\n".join(e.value.errors)


# --- golden reference scenario ------------------------------------------------------------------

def test_golden_call_record_and_outputs(wf):
    r, fake = run(wf / "scenarios" / "demo-call.yaml", {"topic": "coffee"}, read_yaml(GOLDEN))
    assert r.status == "succeeded", r.error
    d = r.rec.dir
    for f in ("steps/02-tone/inputs.json", "steps/02-tone/output.json",
              "steps/02-tone/steps/01-check/calls/01.request.json", "steps/02-tone/steps/03-out/output.json"):
        assert (d / f).is_file(), f
    assert json.loads((d / "steps/02-tone/inputs.json").read_text()) == {
        "text": "Morning coffee that gets you going. Want one?", "threshold": 0.7}
    assert json.loads((d / "steps/02-tone/output.json").read_text()) == {"on_brand": 0.91, "passed": True}
    steps = [e.get("step") for e in events(r, "step_started")]
    assert steps == ["copy", "tone", "tone/check", "tone/result", "tone/out", "out"]
    assert events(r, "jev_call")[0]["request_file"] == "steps/02-tone/steps/01-check/calls/01.request.json"
    assert [c[0] for c in fake.calls] == ["copy", "tone/check"]
    tone = next(e for e in events(r, "step_finished") if e["step"] == "tone")
    assert tone["cost_usd"] == 0.0001 and tone["kind"] == "call"  # cost of the nested jev call
    assert r.cost == pytest.approx(0.0002)
    assert json.loads((d / "callback.json").read_text())["outputs"] == {
        "caption": "Morning coffee that gets you going. Want one?", "on_brand": 0.91}
    assert [e["type"] for e in events(r)].count("run_started") == 1  # call does not create a new run
    assert "scenario tone-check" in (d / "plan.md").read_text()


def test_nested_error_is_error_of_call_step(wf):
    callee(wf)
    r, _ = run(caller(wf, 'call: { scenario: callee, inputs: { text: "{{ inputs.topic }}", n: 9 } }'))
    assert r.status == "failed"
    assert r.error["class"] == "fail" and r.error["step"] == "draft/stop" and r.error["message"] == "n is too large: 9"
    fin = {e["step"]: e["status"] for e in events(r, "step_finished")}
    assert fin["draft/stop"] == "failed" and fin["draft"] == "failed"
    assert json.loads((r.rec.dir / "callback.json").read_text())["error"]["step"] == "draft/stop"


def test_on_error_continue_on_call_uses_default(wf):
    callee(wf)
    r, _ = run(caller(wf, 'on_error: continue\n            default: { length: 0, text: "" }\n'
                          '            call: { scenario: callee, inputs: { text: x, n: 9 } }',
                      "  - id: after\n            set: { d: steps.draft.length }"))
    assert r.status == "succeeded", r.error
    assert r.values["steps"]["after"] == {"d": 0}
    assert any("step draft failed (fail" in w for w in r.warnings)


def test_outputs_and_defaults_of_callee(wf):
    callee(wf)
    r, _ = run(caller(wf, 'call: { scenario: callee, inputs: { text: "{{ inputs.topic }}" } }',
                      "  - id: after\n            set: { d: steps.draft.length, t: steps.draft.text }"))
    assert r.status == "succeeded", r.error
    assert r.values["steps"]["after"] == {"d": 7, "t": "coffee"}  # n = default 1
    assert json.loads((r.rec.dir / "steps/01-draft/inputs.json").read_text()) == {"text": "coffee", "n": 1}


def test_shared_run_budget(wf):
    (wf / "config.yaml").write_text((wf / "config.yaml").read_text().replace("run_budget_usd: 1.00",
                                                                             "run_budget_usd: 0.0001"))
    r, _ = run(wf / "scenarios" / "demo-call.yaml", {"topic": "coffee"})
    assert r.status == "failed" and r.error["class"] == "budget" and r.error["step"] == "tone/check"
    assert "run" in r.error["message"]


def test_call_own_budget_is_covered_by_its_on_error(wf):
    callee_text = CALLEE.replace("callable: CALLABLE", "callable: true").replace("STOP", "stop")
    callee_text = callee_text.replace("  - id: out", """  - id: j
    jev: { state: x, questions: { q: { type: noul, instructions: y } } }
  - id: j2
    jev: { state: x, questions: { q: { type: noul, instructions: y } } }
  - id: out""")
    scenario(wf, callee_text, "callee")
    r, _ = run(caller(wf, 'budget_usd: 0.0001\n            on_error: continue\n            default: { length: 0, text: "" }\n'
                          '            call: { scenario: callee, inputs: { text: x } }'))
    assert r.status == "succeeded", r.error
    assert any("step draft failed (budget" in w for w in r.warnings)


def test_runtime_input_type_mismatch_is_expression(wf):
    callee(wf)
    r, _ = run(caller(wf, 'call: { scenario: callee, inputs: { text: x, n: "{{ inputs.data.a }}" } }',
                      extra_inputs="data: { type: object, default: { a: text } }"))
    assert r.error["class"] == "expression" and "call.inputs.n" in r.error["message"], r.error
    assert r.error["step"] == "draft"


def test_file_passes_through_call_and_uploads_once(wf):
    scenario(wf, """
        version: 1
        name: NAME
        description: Photo
        callable: true
        outputs: { photo: { type: file } }
        steps:
          - id: img
            image: { model: gemini-image, prompt: coffee, aspect_ratio: "4:5" }
          - id: out
            output: { photo: "{{ steps.img.file }}" }
        """, "photo")
    scenario(wf, """
        version: 1
        name: NAME
        description: Use the photo
        callable: true
        inputs: { image: { type: file, required: true } }
        outputs: { image: { type: file } }
        steps:
          - id: out
            output: { image: "{{ inputs.image }}" }
        """, "forward")
    path = scenario(wf, """
        version: 1
        name: NAME
        description: Main
        outputs: { image: { type: file } }
        steps:
          - id: f
            call: { scenario: photo }
          - id: p
            call: { scenario: forward, inputs: { image: "{{ steps.f.photo }}" } }
          - id: out
            output: { image: "{{ steps.p.image }}" }
        """)
    r, _ = run(path)
    assert r.status == "succeeded", r.error
    assert (r.rec.dir / "steps/01-f/steps/01-img/image.png").is_file()
    up = events(r, "file_uploaded")
    assert [u["output"] for u in up] == ["image", "report"]  # nested outputs are not uploaded
    assert up[0]["path"] == "steps/01-f/steps/01-img/image.png"
    assert json.loads((r.rec.dir / "steps/01-f/output.json").read_text()) == {"photo": "steps/01-f/steps/01-img/image.png"}


# --- validate --------------------------------------------------------------------------------

def test_call_to_not_callable_is_config(wf):
    callee(wf, callable_=False)
    assert "has no callable: true" in config_errors(caller(wf, "call: { scenario: callee, inputs: { text: x } }"))


def test_call_contract_errors(wf):
    callee(wf)
    got = config_errors(caller(wf, "call: { scenario: callee, inputs: { extra: 1, n: x } }",
                               "  - id: after\n            set: { d: steps.draft.missing }"))
    assert "has no inputs named: extra" in got
    assert "missing required inputs for scenario 'callee': text" in got
    assert "call.inputs.n: input has type number, value is string" in got
    assert "'steps.draft' has no key 'missing'" in got


def test_file_input_only_from_file(wf):
    scenario(wf, """
        version: 1
        name: NAME
        description: x
        callable: true
        inputs: { image: { type: file, required: true } }
        steps: [{ id: a, set: { x: 1 } }]
        """, "forward")
    assert "input has type file, value is string" in config_errors(
        caller(wf, 'call: { scenario: forward, inputs: { image: "/home/x/.env" } }'))


def test_errors_in_callee_are_reported_with_its_file(wf):
    scenario(wf, CALLEE.replace("callable: CALLABLE", "callable: true").replace("STOP", "stop")
             .replace("len(inputs.text)", "len(inputs.missing)"), "callee")
    assert "callee.yaml: step \"calculate\"" in config_errors(caller(wf, "call: { scenario: callee, inputs: { text: x } }"))


def test_cycle_is_config(wf):
    for a, b in (("a", "b"), ("b", "a")):
        scenario(wf, f"""
            version: 1
            name: NAME
            description: x
            callable: true
            steps: [{{ id: s, call: {{ scenario: {b} }} }}]
            """, a)
    assert "call cycle: a → b → a" in config_errors(wf / "scenarios" / "a.yaml")
    scenario(wf, "version: 1\nname: NAME\ndescription: x\ncallable: true\nsteps: [{ id: s, call: { scenario: self } }]\n",
             "self")
    assert "call cycle: self → self" in config_errors(wf / "scenarios" / "self.yaml")


def test_depth_limit_is_config(wf):
    for a, b in (("a", "b"), ("b", "c")):
        scenario(wf, f"version: 1\nname: NAME\ndescription: x\ncallable: true\n"
                     f"steps: [{{ id: s, call: {{ scenario: {b} }} }}]\n", a)
    scenario(wf, "version: 1\nname: NAME\ndescription: x\ncallable: true\nsteps: [{ id: s, set: { x: 1 } }]\n", "c")
    run(wf / "scenarios" / "a.yaml")  # depth 2 ≤ default 3
    (wf / "config.yaml").write_text((wf / "config.yaml").read_text().replace("run_timeout: 1h",
                                                                             "run_timeout: 1h\n  max_call_depth: 1"))
    assert "call depth 2 exceeds limits.max_call_depth (1): a → b → c" in config_errors(wf / "scenarios" / "a.yaml")


def test_callable_scenario_runs_standalone(wf):
    p = validate(wf / "scenarios" / "tone-check.yaml", check_models=False)
    assert p.scenario["callable"] is True
