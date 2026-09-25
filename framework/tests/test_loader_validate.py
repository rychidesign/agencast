"""Loader (YAML 1.2 core, verze, schémata ze spec) a statické kontroly validate (scenario.md §7)."""
import pytest
from conftest import scenario

from maw import ConfigErrors
from maw.loader import SPEC_SCHEMAS, LoadError, load_dotenv, load_yaml
from maw.validate import resolve_inputs, validate


# --- YAML 1.2 core ------------------------------------------------------------------

def test_yaml_12_core():
    assert load_yaml("a: 4:5\nb: yes\nc: on\nd: off\ne: no\nf: 2026-09-25\ng: TRUE\nh: 010\ni: 0x1f\nj: .5\nk: ~", "x") == \
        {"a": "4:5", "b": "yes", "c": "on", "d": "off", "e": "no", "f": "2026-09-25", "g": True, "h": 10, "i": 31,
         "j": 0.5, "k": None}


def test_yaml_duplicate_key_has_line():
    with pytest.raises(LoadError, match=r"f.yaml, řádek 3: duplicitní klíč 'a' \(poprvé na řádku 1\)"):
        load_yaml("a: 1\nb: 2\na: 3", "f.yaml")


@pytest.mark.parametrize("text,line,problem", [
    ("id: a\nwhen: {{ steps.k.x }} < 0.5\n", 2, "expected <block end>, but found '<scalar>'"),
    ("description: Krok: ověř\nx: 1\n", 1, "mapping values are not allowed here"),
])
def test_yaml_syntax_error_czech_hint(text, line, problem):
    """BUGS.md #4: česká věta s radou a řádkem, hláška parseru jako druhý řádek."""
    with pytest.raises(LoadError) as e:
        load_yaml(text, "f.yaml")
    assert str(e.value) == (f"f.yaml, řádek {line}: YAML nejde přečíst — hodnota s {{, [, ': ' nebo ' #' patří "
                            f"do uvozovek (scenario.md §5 „Pozor na YAML“)\n  {problem}")


def test_yaml_on_as_case_key_is_text(wf):
    """`cases: { yes: …, on: … }` — klíče jsou text (YAML 1.2), ne booleany."""
    p = scenario(wf, """
        version: 1
        name: NAME
        description: x
        inputs: { v: { type: string, default: "yes" } }
        steps:
          - id: s
            switch:
              value: inputs.v
              cases:
                yes: [{ id: a, set: { x: 1 } }]
                on: [{ id: b, set: { x: 2 } }]
              default: []
    """)
    assert list(validate(p, check_models=False).scenario["steps"][0]["switch"]["cases"]) == ["yes", "on"]


def test_dotenv_crlf(tmp_path, monkeypatch):
    monkeypatch.delenv("MAW_TEST_X", raising=False)
    (tmp_path / ".env").write_bytes(b"# komentar\r\nMAW_TEST_X=\"abc\"\r\n")
    load_dotenv(tmp_path / ".env")
    import os
    assert os.environ["MAW_TEST_X"] == "abc"


def test_schemas_come_from_spec():
    assert SPEC_SCHEMAS.parts[-3:] == ("docs", "spec", "schema") and (SPEC_SCHEMAS / "scenario.schema.json").is_file()


# --- verze (R8, §5.9 bod 6) ---------------------------------------------------------------

def test_unknown_version_rejected(wf):
    p = scenario(wf, "version: 2\nname: NAME\ndescription: x\nsteps: [{ id: a, fail: x }]\n")
    with pytest.raises(ConfigErrors, match="neznámá verze formátu 2"):
        validate(p, check_models=False)
    p = scenario(wf, "name: NAME\ndescription: x\nsteps: [{ id: a, fail: x }]\n")
    with pytest.raises(ConfigErrors, match="chybí pole version"):
        validate(p, check_models=False)


def test_unknown_agent_version_rejected(wf):
    f = wf / "agents" / "copywriter.md"
    f.write_text(f.read_text().replace("version: 1", "version: 7"))
    p = scenario(wf, """
        version: 1
        name: NAME
        description: x
        steps: [{ id: a, ask: { agent: copywriter, prompt: x } }]
    """)
    with pytest.raises(ConfigErrors, match="agents/copywriter.md: neznámá verze formátu 7"):
        validate(p, check_models=False)


def test_agent_model_id_instead_of_alias(wf):
    """BUGS.md #3: konkrétní id modelu v agentovi → hláška o aliasu, ne regex ze schématu."""
    f = wf / "agents" / "copywriter.md"
    f.write_text(f.read_text().replace("model: chytry", "model: anthropic/claude-haiku-4.5"))
    got = errors(wf, HEAD + "steps: [{ id: a, ask: { agent: copywriter, prompt: x } }]")
    assert got.startswith("agents/copywriter.md: model 'anthropic/claude-haiku-4.5' není alias v config.yaml "
                          "(aliasy: chytry, ") and "\n" not in got, got


# --- validate ---------------------------------------------------------------------------

def errors(wf, text, **kw):
    try:
        validate(scenario(wf, text), check_models=False)
    except ConfigErrors as e:
        return "\n".join(e.errors)
    return ""


HEAD = "version: 1\nname: NAME\ndescription: x\n"


@pytest.mark.parametrize("body,msg", [
    ("steps: [{ id: a, ask: { agent: copywriter, prompt: x, modle: y } }]", "neznámé pole 'modle'"),
    ("steps: [{ id: a, fail: x, retry: 1 }]", "neznámé pole 'retry'"),
    ("steps: [{ id: a, fail: x, set: { y: 1 } }]", "právě jeden typ"),
    ("steps: [{ id: and, fail: x }]", "vyhrazené slovo"),
    ("steps: [{ id: a, set: { x: 1 } }, { id: a, set: { y: 1 } }]", "id není unikátní"),
    ("steps: [{ id: a, ask: { agent: nikdo, prompt: x } }]", "agent 'nikdo' neexistuje"),
    ("steps: [{ id: a, image: { model: neznamy, prompt: x } }]", "'neznamy' není alias v config.yaml"),
    ("steps: [{ id: a, when: steps.b.x > 1, set: { x: 1 } }, { id: b, set: { x: 1 } }]", "krok 'b' je až níž"),
    ("steps: [{ id: a, set: { x: steps.nic.y } }]", "krok 'nic' neexistuje"),
    ("steps: [{ id: a, when: 'true', set: { x: 1 } }, { id: b, set: { y: steps.a.x } }]", "nemusí proběhnout (má when)"),
    ("steps: [{ id: a, set: { x: 1 } }, { id: b, set: { y: steps.a.z } }]", "'steps.a' nemá klíč 'z'"),
    ('steps: [{ id: a, set: { x: 1 } }, { id: b, when: steps.a.x < "0.7", fail: x }]', "porovnání number s string"),
    ("steps: [{ id: a, when: 1 + 1, fail: x }]", "výraz musí dát true/false, dá number"),
    ("steps: [{ id: a, set: { x: 'True == false' } }]", "neznámé jméno 'True'"),
    ("steps: [{ id: a, set: { x: 'open(\"f\")' } }]", "funkce 'open' není povolená"),
    ('steps: [{ id: a, set: { x: "{{ inputs.y }}" } }]', "šablona {{ }} tu není povolená"),
    ('steps: [{ id: a, image: { model: gemini-image, prompt: x, aspect_ratio: "{{ inputs.r }}" } }]', "neodpovídá tvaru"),
    ("steps: [{ id: a, fail: x }, { id: b, fail: y }]", "nedosažitelný"),
    ("steps: [{ id: a, fail: 'x {{ inputs.nic }}' }]", "'inputs' nemá klíč 'nic'"),
    ("steps: [{ id: a, task: { agent: publisher, prompt: x } }]", "nesmí spustit agenta se serverem 'instagram'"),
    ("steps: [{ id: a, call: { scenario: jiny } }]", "scénář 'jiny' neexistuje"),
    ("steps: [{ id: a, set: { x: 1 }, default: { y: 1 } }]", "chybí: x"),
    ("steps: [{ id: a, jev: { state: x, questions: { q: { type: noul, instructions: y } } }, default: {} }]", "chybí: q"),
    ("steps: [{ id: a, set: { x: 1 }, default: { x: text } }]", "default.x"),
    ("steps: [{ id: a, output: { x: 1 } }]", "scénář bez outputs nesmí mít krok output"),
    ("outputs: { x: { type: string } }\nsteps: [{ id: a, set: { x: 1 } }]", "poslední krok není output"),
    ("outputs: { x: { type: string } }\nsteps: [{ id: o, output: { y: a } }]", "chybí výstupy z hlavičky: x"),
    ("outputs: { x: { type: file } }\nsteps: [{ id: o, output: { x: /home/x/.env } }]", "výstup typu file"),
    ("outputs: { x: { type: number } }\nsteps: [{ id: o, output: { x: text } }]", "výstup má typ number"),
    ("outputs: { x: { type: string } }\nsteps: [{ id: o, output: { x: a } }, { id: p, set: { y: 1 } }]",
     "jen jako poslední krok"),
    ("steps: [{ id: p, parallel: { a: [{ id: x, output: { y: 1 } }], b: [{ id: y, fail: z }] } }]",
     "output nesmí být uvnitř větve"),
    ("steps:\n  - id: p\n    parallel:\n      a: [{ id: x, set: { v: 1 } }]\n      b: [{ id: y, set: { w: steps.x.v } }]",
     "je v jiné větvi parallel"),
    ("steps:\n  - id: s\n    switch: { value: '\"a\"', cases: { a: [{ id: x, set: { v: 1 } }] }, default: [] }\n"
     "  - id: z\n    set: { w: steps.x.v }", "je ve větvi switch"),
    ("steps: [{ id: s, switch: { value: '1', cases: { a: [] }, default: [] } }]", "musí mít aspoň 1"),
    ("steps: [{ id: s, switch: { value: '1', cases: { a: [{ id: x, set: { v: 1 } }] }, default: [] } }]",
     "výraz musí dát string, dá number"),
    ("steps: [{ id: s, switch: { value: '\"a\"', cases: { a: [{ id: x, set: { v: 1 } }] } } }]",
     "chybí povinné pole 'default'"),
    ("steps: [{ id: s, set: { v: null } }, { id: f, fail: 'x {{ steps.s.v }}' }]", "vždy null"),
    ("steps: [{ id: p, parallel: { a: [{ id: x, fail: z }], b: [{ id: y, fail: z }] } }, { id: z, set: { w: steps.p.x } }]",
     "(parallel) nemá výstup"),
    ("inputs: { t: { type: string, required: true, default: x } }\nsteps: [{ id: a, fail: x }]", "buď required"),
    ("inputs: { t: { type: integer, default: 1.5 } }\nsteps: [{ id: a, fail: x }]", "neodpovídá type integer"),
    ("steps: [{ id: a, budget_usd: 5, ask: { agent: copywriter, prompt: x } }]", "víc než limits.budget_usd agenta"),
    ("description: '{{ x }}'\nsteps: [{ id: a, fail: x }]", None),  # duplicitní klíč description
])
def test_validate_errors(wf, body, msg):
    got = errors(wf, HEAD + body)
    assert (msg or "duplicitní klíč") in got, got


def test_template_in_expression_one_error(wf):
    """BUGS.md #2: `{{ }}` ve výrazu (set, when) = jedna hláška se stříškou, nic o AST uzlu Set."""
    got = errors(wf, HEAD + "steps: [{ id: a, when: '{{ inputs.y }}', set: { x: '{{ inputs.y }}' } }]")
    assert got.count("šablona {{ }} tu není povolená") == 2 and "Set" not in got, got
    assert "\n  {{ inputs.y }}\n  ^" in got


def test_switch_cases_must_be_jev_criteria(wf):
    got = errors(wf, HEAD + """
steps:
  - id: k
    jev:
      state: x
      questions:
        druh: { type: choice, instructions: y, criteria: { produkt: a, akce: b } }
  - id: s
    switch:
      value: steps.k.druh
      cases: { produkt: [{ id: a, fail: x }], sleva: [{ id: b, fail: y }] }
      default: []
""")
    assert "sleva není mezi možnostmi criteria otázky 'druh'" in got


def test_reference_inside_same_branch_needs_no_default(wf):
    assert errors(wf, HEAD + """
steps:
  - id: s
    switch:
      value: '"a"'
      cases:
        a:
          - { id: x, set: { v: 1 } }
          - { id: y, set: { w: steps.x.v } }
      default: []
""") == ""


def test_name_must_match_file(wf):
    assert "se neshoduje se jménem souboru" in errors(wf, "version: 1\nname: jine\ndescription: x\nsteps: [{ id: a, fail: x }]")


def test_subfolder_rejected(wf):
    (wf / "scenarios" / "sub").mkdir()
    assert "podsložky se nečtou" in errors(wf, HEAD + "steps: [{ id: a, fail: x }]")


def test_config_secret_not_printed(wf):
    cfg = wf / "config.yaml"
    cfg.write_text(cfg.read_text().replace("api_key_env: OPENROUTER_API_KEY", "api_key_env: sk-or-v1-TAJNE123"))
    got = errors(wf, HEAD + "steps: [{ id: a, fail: x }]")
    assert "openrouter.api_key_env: hodnota neodpovídá tvaru" in got and "TAJNE" not in got


def test_config_same_env_twice(wf):
    cfg = wf / "config.yaml"
    cfg.write_text(cfg.read_text().replace("token_env: WEBHOOK_TOKEN", "token_env: OPENROUTER_API_KEY"))
    assert "používají stejnou proměnnou OPENROUTER_API_KEY" in errors(wf, HEAD + "steps: [{ id: a, fail: x }]")


def test_models_checked_against_models_list(wf):
    from maw.fake import Fake
    p = scenario(wf, HEAD + "steps: [{ id: a, image: { model: chytry, prompt: x } }]")
    fake = Fake(None, ["anthropic/claude-haiku-4.5"])  # gemini modely v /models chybí
    with pytest.raises(ConfigErrors) as e:
        validate(p, transport=fake.transport())
    assert "neumí výstup obrázku" in str(e.value)
    cfg = wf / "config.yaml"
    cfg.write_text(cfg.read_text().replace("claude-haiku-4.5", "claude-haiku-4-5"))
    with pytest.raises(ConfigErrors, match="není v GET /models"):
        validate(p, transport=fake.transport())


def test_all_errors_at_once(wf):
    got = errors(wf, HEAD + "steps: [{ id: a, set: { x: steps.b.y } }, { id: c, when: '1', fail: x }]")
    assert "krok 'b' neexistuje" in got and "výraz musí dát true/false" in got


# --- vstupy ----------------------------------------------------------------------------

def test_inputs():
    sc = {"inputs": {"t": {"type": "string", "required": True}, "n": {"type": "integer", "default": 2},
                     "b": {"type": "boolean", "default": False}, "l": {"type": "list", "default": []}}}
    assert resolve_inputs(sc, {"t": "4:5", "n": "3", "b": "true", "l": '["a"]'}, from_text=True) == \
        {"t": "4:5", "n": 3, "b": True, "l": ["a"]}
    with pytest.raises(ConfigErrors) as e:
        resolve_inputs(sc, {"n": "x", "z": "1"}, from_text=True)
    assert {"chybí povinný vstup 't' (string)", "neznámý vstup 'z' (scénář má: t, n, b, l)",
            "vstup 'n' má být integer, dostal string"} <= set(e.value.errors)
    with pytest.raises(ConfigErrors, match="jen přes call"):
        resolve_inputs({"inputs": {"f": {"type": "file", "required": True}}}, {"f": "/etc/passwd"})
