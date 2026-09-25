"""Krok call (scenario.md call, DESIGN §5.3): vnořený scénář ve stejném běhu,
kontrakt inputs/outputs, callable, cykly a hloubka, sdílený rozpočet."""
import json
from pathlib import Path

import pytest
from conftest import events, run, scenario

from maw import ConfigErrors
from maw.loader import read_yaml
from maw.validate import validate

GOLDEN = Path(__file__).parent / "golden" / "ukazka-call.yaml"

CALLEE = """
version: 1
name: NAME
description: Volaný scénář
callable: CALLABLE
inputs:
  text: { type: string, required: true }
  n: { type: number, default: 1 }
outputs:
  delka: { type: number }
  text: { type: string }
steps:
  - id: spocitej
    set: { delka: len(inputs.text) + inputs.n }
  - id: STOP
    when: inputs.n > 5
    fail: "moc velké n: {{ inputs.n }}"
  - id: out
    output: { delka: "{{ steps.spocitej.delka }}", text: "{{ inputs.text }}" }
"""


def callee(wf, name="volany", callable_=True):
    return scenario(wf, CALLEE.replace("CALLABLE", str(callable_).lower()).replace("STOP", "stop"), name)


def caller(wf, call_body, rest="", name="test", extra_inputs=""):
    return scenario(wf, f"""
        version: 1
        name: NAME
        description: Volající scénář
        inputs:
          tema: {{ type: string, default: kava }}
          {extra_inputs}
        steps:
          - id: navrh
            {call_body}
        {rest}
        """, name)


def config_errors(path) -> str:
    with pytest.raises(ConfigErrors) as e:
        run(path)
    return "\n".join(e.value.errors)


# --- zlatý referenční scénář ------------------------------------------------------------------

def test_golden_call_record_and_outputs(wf):
    r, fake = run(wf / "scenarios" / "ukazka-call.yaml", {"tema": "káva"}, read_yaml(GOLDEN))
    assert r.status == "succeeded", r.error
    d = r.rec.dir
    for f in ("steps/02-ton/inputs.json", "steps/02-ton/output.json",
              "steps/02-ton/steps/01-kontrola/calls/01.request.json", "steps/02-ton/steps/03-out/output.json"):
        assert (d / f).is_file(), f
    assert json.loads((d / "steps/02-ton/inputs.json").read_text()) == {
        "text": "Ranní káva, co tě nakopne. Dáš si?", "prah": 0.7}
    assert json.loads((d / "steps/02-ton/output.json").read_text()) == {"on_brand": 0.91, "v_poradku": True}
    steps = [e.get("step") for e in events(r, "step_started")]
    assert steps == ["copy", "ton", "ton/kontrola", "ton/vysledek", "ton/out", "out"]
    assert events(r, "jev_call")[0]["request_file"] == "steps/02-ton/steps/01-kontrola/calls/01.request.json"
    assert [c[0] for c in fake.calls] == ["copy", "ton/kontrola"]
    ton = next(e for e in events(r, "step_finished") if e["step"] == "ton")
    assert ton["cost_usd"] == 0.0001 and ton["kind"] == "call"  # cena jev volání uvnitř
    assert r.cost == pytest.approx(0.0002)
    assert json.loads((d / "callback.json").read_text())["outputs"] == {
        "caption": "Ranní káva, co tě nakopne. Dáš si?", "on_brand": 0.91}
    assert [e["type"] for e in events(r)].count("run_started") == 1  # call nezakládá nový běh
    assert "scénář kontrola-tonu" in (d / "plan.md").read_text()


def test_nested_error_is_error_of_call_step(wf):
    callee(wf)
    r, _ = run(caller(wf, 'call: { scenario: volany, inputs: { text: "{{ inputs.tema }}", n: 9 } }'))
    assert r.status == "failed"
    assert r.error["class"] == "fail" and r.error["step"] == "navrh/stop" and r.error["message"] == "moc velké n: 9"
    fin = {e["step"]: e["status"] for e in events(r, "step_finished")}
    assert fin["navrh/stop"] == "failed" and fin["navrh"] == "failed"
    assert json.loads((r.rec.dir / "callback.json").read_text())["error"]["step"] == "navrh/stop"


def test_on_error_continue_on_call_uses_default(wf):
    callee(wf)
    r, _ = run(caller(wf, 'on_error: continue\n            default: { delka: 0, text: "" }\n'
                          '            call: { scenario: volany, inputs: { text: x, n: 9 } }',
                      "  - id: po\n            set: { d: steps.navrh.delka }"))
    assert r.status == "succeeded", r.error
    assert r.values["steps"]["po"] == {"d": 0}
    assert any("krok navrh selhal (fail" in w for w in r.warnings)


def test_outputs_and_defaults_of_callee(wf):
    callee(wf)
    r, _ = run(caller(wf, 'call: { scenario: volany, inputs: { text: "{{ inputs.tema }}" } }',
                      "  - id: po\n            set: { d: steps.navrh.delka, t: steps.navrh.text }"))
    assert r.status == "succeeded", r.error
    assert r.values["steps"]["po"] == {"d": 5, "t": "kava"}  # n = default 1
    assert json.loads((r.rec.dir / "steps/01-navrh/inputs.json").read_text()) == {"text": "kava", "n": 1}


def test_shared_run_budget(wf):
    (wf / "config.yaml").write_text((wf / "config.yaml").read_text().replace("run_budget_usd: 1.00",
                                                                             "run_budget_usd: 0.0001"))
    r, _ = run(wf / "scenarios" / "ukazka-call.yaml", {"tema": "káva"})
    assert r.status == "failed" and r.error["class"] == "budget" and r.error["step"] == "ton/kontrola"
    assert "běhu" in r.error["message"]


def test_call_own_budget_is_covered_by_its_on_error(wf):
    callee_text = CALLEE.replace("callable: CALLABLE", "callable: true").replace("STOP", "stop")
    callee_text = callee_text.replace("  - id: out", """  - id: j
    jev: { state: x, questions: { q: { type: noul, instructions: y } } }
  - id: j2
    jev: { state: x, questions: { q: { type: noul, instructions: y } } }
  - id: out""")
    scenario(wf, callee_text, "volany")
    r, _ = run(caller(wf, 'budget_usd: 0.0001\n            on_error: continue\n            default: { delka: 0, text: "" }\n'
                          '            call: { scenario: volany, inputs: { text: x } }'))
    assert r.status == "succeeded", r.error
    assert any("krok navrh selhal (budget" in w for w in r.warnings)


def test_runtime_input_type_mismatch_is_expression(wf):
    callee(wf)
    r, _ = run(caller(wf, 'call: { scenario: volany, inputs: { text: x, n: "{{ inputs.data.a }}" } }',
                      extra_inputs="data: { type: object, default: { a: text } }"))
    assert r.error["class"] == "expression" and "call.inputs.n" in r.error["message"], r.error
    assert r.error["step"] == "navrh"


def test_file_passes_through_call_and_uploads_once(wf):
    scenario(wf, """
        version: 1
        name: NAME
        description: Fotka
        callable: true
        outputs: { foto: { type: file } }
        steps:
          - id: img
            image: { model: gemini-image, prompt: kava, aspect_ratio: "4:5" }
          - id: out
            output: { foto: "{{ steps.img.file }}" }
        """, "fotka")
    scenario(wf, """
        version: 1
        name: NAME
        description: Použije fotku
        callable: true
        inputs: { obr: { type: file, required: true } }
        outputs: { obr: { type: file } }
        steps:
          - id: out
            output: { obr: "{{ inputs.obr }}" }
        """, "predej")
    path = scenario(wf, """
        version: 1
        name: NAME
        description: Hlavní
        outputs: { image: { type: file } }
        steps:
          - id: f
            call: { scenario: fotka }
          - id: p
            call: { scenario: predej, inputs: { obr: "{{ steps.f.foto }}" } }
          - id: out
            output: { image: "{{ steps.p.obr }}" }
        """)
    r, _ = run(path)
    assert r.status == "succeeded", r.error
    assert (r.rec.dir / "steps/01-f/steps/01-img/image.png").is_file()
    up = events(r, "file_uploaded")
    assert [u["output"] for u in up] == ["image", "report"]  # vnořené výstupy se nenahrávají
    assert up[0]["path"] == "steps/01-f/steps/01-img/image.png"
    assert json.loads((r.rec.dir / "steps/01-f/output.json").read_text()) == {"foto": "steps/01-f/steps/01-img/image.png"}


# --- validate --------------------------------------------------------------------------------

def test_call_to_not_callable_is_config(wf):
    callee(wf, callable_=False)
    assert "nemá callable: true" in config_errors(caller(wf, "call: { scenario: volany, inputs: { text: x } }"))


def test_call_contract_errors(wf):
    callee(wf)
    got = config_errors(caller(wf, "call: { scenario: volany, inputs: { navic: 1, n: x } }",
                               "  - id: po\n            set: { d: steps.navrh.nic }"))
    assert "nemá vstupy: navic" in got
    assert "chybí povinné vstupy scénáře 'volany': text" in got
    assert "call.inputs.n: vstup má typ number, hodnota je string" in got
    assert "'steps.navrh' nemá klíč 'nic'" in got


def test_file_input_only_from_file(wf):
    scenario(wf, """
        version: 1
        name: NAME
        description: x
        callable: true
        inputs: { obr: { type: file, required: true } }
        steps: [{ id: a, set: { x: 1 } }]
        """, "predej")
    assert "vstup má typ file, hodnota je string" in config_errors(
        caller(wf, 'call: { scenario: predej, inputs: { obr: "/home/x/.env" } }'))


def test_errors_in_callee_are_reported_with_its_file(wf):
    scenario(wf, CALLEE.replace("callable: CALLABLE", "callable: true").replace("STOP", "stop")
             .replace("len(inputs.text)", "len(inputs.nic)"), "volany")
    assert "volany.yaml: krok \"spocitej\"" in config_errors(caller(wf, "call: { scenario: volany, inputs: { text: x } }"))


def test_cycle_is_config(wf):
    for a, b in (("a", "b"), ("b", "a")):
        scenario(wf, f"""
            version: 1
            name: NAME
            description: x
            callable: true
            steps: [{{ id: s, call: {{ scenario: {b} }} }}]
            """, a)
    assert "cyklus call: a → b → a" in config_errors(wf / "scenarios" / "a.yaml")
    scenario(wf, "version: 1\nname: NAME\ndescription: x\ncallable: true\nsteps: [{ id: s, call: { scenario: sam } }]\n",
             "sam")
    assert "cyklus call: sam → sam" in config_errors(wf / "scenarios" / "sam.yaml")


def test_depth_limit_is_config(wf):
    for a, b in (("a", "b"), ("b", "c")):
        scenario(wf, f"version: 1\nname: NAME\ndescription: x\ncallable: true\n"
                     f"steps: [{{ id: s, call: {{ scenario: {b} }} }}]\n", a)
    scenario(wf, "version: 1\nname: NAME\ndescription: x\ncallable: true\nsteps: [{ id: s, set: { x: 1 } }]\n", "c")
    run(wf / "scenarios" / "a.yaml")  # hloubka 2 ≤ výchozí 3
    (wf / "config.yaml").write_text((wf / "config.yaml").read_text().replace("run_timeout: 1h",
                                                                             "run_timeout: 1h\n  max_call_depth: 1"))
    assert "hloubka call 2 je nad limits.max_call_depth (1): a → b → c" in config_errors(wf / "scenarios" / "a.yaml")


def test_callable_scenario_runs_standalone(wf):
    p = validate(wf / "scenarios" / "kontrola-tonu.yaml", check_models=False)
    assert p.scenario["callable"] is True
