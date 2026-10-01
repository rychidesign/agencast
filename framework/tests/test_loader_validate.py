"""Loader (YAML 1.2 core, versions, spec schemas) and static validation checks (scenario.md §7)."""
import pytest
from conftest import add_image_model, scenario

from agencast import ConfigErrors
from agencast.loader import SPEC_SCHEMAS, LoadError, load_dotenv, load_yaml
from agencast.validate import resolve_inputs, validate


# --- YAML 1.2 core ------------------------------------------------------------------

def test_yaml_12_core():
    assert load_yaml("a: 4:5\nb: yes\nc: on\nd: off\ne: no\nf: 2026-09-25\ng: TRUE\nh: 010\ni: 0x1f\nj: .5\nk: ~", "x") == \
        {"a": "4:5", "b": "yes", "c": "on", "d": "off", "e": "no", "f": "2026-09-25", "g": True, "h": 10, "i": 31,
         "j": 0.5, "k": None}


def test_yaml_duplicate_key_has_line():
    with pytest.raises(LoadError, match=r"f.yaml, line 3: duplicate key 'a' \(first on line 1\)"):
        load_yaml("a: 1\nb: 2\na: 3", "f.yaml")


@pytest.mark.parametrize("text,line,problem", [
    ("id: a\nwhen: {{ steps.k.x }} < 0.5\n", 2, "expected <block end>, but found '<scalar>'"),
    ("description: Step: check\nx: 1\n", 1, "mapping values are not allowed here"),
])
def test_yaml_syntax_error_english_hint(text, line, problem):
    """BUGS.md #4: English hint with a line number; parser message on the second line."""
    with pytest.raises(LoadError) as e:
        load_yaml(text, "f.yaml")
    assert str(e.value) == (f"f.yaml, line {line}: cannot read YAML — a value containing {{, [, ': ' or ' #' must be "
                            f"quoted (scenario.md §5 'YAML pitfalls')\n  {problem}")


def test_yaml_on_as_case_key_is_text(wf):
    """`cases: { yes: …, on: … }` — keys are strings (YAML 1.2), not booleans."""
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
    monkeypatch.delenv("AGENCAST_TEST_X", raising=False)
    (tmp_path / ".env").write_bytes(b"# comment\r\nAGENCAST_TEST_X=\"abc\"\r\n")
    load_dotenv(tmp_path / ".env")
    import os
    assert os.environ["AGENCAST_TEST_X"] == "abc"


def test_schemas_come_from_spec():
    assert SPEC_SCHEMAS.parts[-3:] == ("docs", "spec", "schema") and (SPEC_SCHEMAS / "scenario.schema.json").is_file()


# --- versions (R8, §5.9 item 6) ---------------------------------------------------------------

def test_unknown_version_rejected(wf):
    p = scenario(wf, "version: 2\nname: NAME\ndescription: x\nsteps: [{ id: a, fail: x }]\n")
    with pytest.raises(ConfigErrors, match="unknown format version 2"):
        validate(p, check_models=False)
    p = scenario(wf, "name: NAME\ndescription: x\nsteps: [{ id: a, fail: x }]\n")
    with pytest.raises(ConfigErrors, match="missing field version"):
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
    with pytest.raises(ConfigErrors, match="agents/copywriter.md: unknown format version 7"):
        validate(p, check_models=False)


def test_agent_model_id_instead_of_alias(wf):
    """BUGS.md #3: a model ID in an agent → alias error, not the schema regex."""
    f = wf / "agents" / "copywriter.md"
    f.write_text(f.read_text().replace("model: smart", "model: anthropic/claude-haiku-4.5"))
    got = errors(wf, HEAD + "steps: [{ id: a, ask: { agent: copywriter, prompt: x } }]")
    assert got.startswith("agents/copywriter.md: model 'anthropic/claude-haiku-4.5' is not an alias in config.yaml "
                          "(aliases: smart, ") and "\n" not in got, got


# --- validate ---------------------------------------------------------------------------

def errors(wf, text, **kw):
    try:
        validate(scenario(wf, text), check_models=False)
    except ConfigErrors as e:
        return "\n".join(e.errors)
    return ""


HEAD = "version: 1\nname: NAME\ndescription: x\n"


@pytest.mark.parametrize("body,msg", [
    ("steps: [{ id: a, ask: { agent: copywriter, prompt: x, modle: y } }]", "unknown field 'modle'"),
    ("steps: [{ id: a, fail: x, retry: 1 }]", "unknown field 'retry'"),
    ("steps: [{ id: a, fail: x, set: { y: 1 } }]", "exactly one type"),
    ("steps: [{ id: and, fail: x }]", "reserved word"),
    ("steps: [{ id: a, set: { x: 1 } }, { id: a, set: { y: 1 } }]", "id is not unique"),
    ("steps: [{ id: a, ask: { agent: nobody, prompt: x } }]", "agent 'nobody' does not exist"),
    ("steps: [{ id: a, ask: { agent: copywriter, prompt: x, schema: { a: 5 } } }]", "schema format: string, number"),
    ("steps: [{ id: a, image: { model: unknown, prompt: x } }]", "'unknown' is not an alias in config.yaml"),
    ("steps: [{ id: a, when: steps.b.x > 1, set: { x: 1 } }, { id: b, set: { x: 1 } }]", "step 'b' comes later"),
    ("steps: [{ id: a, set: { x: steps.missing.y } }]", "step 'missing' does not exist"),
    ("steps: [{ id: a, when: 'true', set: { x: 1 } }, { id: b, set: { y: steps.a.x } }]", "may not run (has when)"),
    ("steps: [{ id: a, set: { x: 1 } }, { id: b, set: { y: steps.a.z } }]", "'steps.a' has no key 'z'"),
    ('steps: [{ id: a, set: { x: 1 } }, { id: b, when: steps.a.x < "0.7", fail: x }]', "comparing number with string"),
    ("steps: [{ id: a, when: 1 + 1, fail: x }]", "expression must return true/false, got number"),
    ("steps: [{ id: a, set: { x: 'True == false' } }]", "unknown name 'True'"),
    ("steps: [{ id: a, set: { x: 'open(\"f\")' } }]", "function 'open' is not allowed"),
    ('steps: [{ id: a, set: { x: "{{ inputs.y }}" } }]', "template {{ }} is not allowed here"),
    ('steps: [{ id: a, image: { model: gemini-image, prompt: x, aspect_ratio: "{{ inputs.r }}" } }]', "has no key 'r'"),
    ("steps: [{ id: a, fail: x }, { id: b, fail: y }]", "unreachable"),
    ("steps: [{ id: a, fail: 'x {{ inputs.missing }}' }]", "'inputs' has no key 'missing'"),
    ("steps: [{ id: a, task: { agent: publisher, prompt: x } }]", "cannot run an agent with server 'instagram'"),
    ("steps: [{ id: a, call: { scenario: other } }]", "scenario 'other' does not exist"),
    ("steps: [{ id: a, set: { x: 1 }, default: { y: 1 } }]", "missing: x"),
    ("steps: [{ id: a, jev: { state: x, questions: { q: { type: noul, instructions: y } } }, default: {} }]", "missing: q"),
    ("steps: [{ id: a, set: { x: 1 }, default: { x: text } }]", "default.x"),
    ("steps: [{ id: a, output: { x: 1 } }]", "scenario without outputs cannot have an output step"),
    ("outputs: { x: { type: string } }\nsteps: [{ id: a, set: { x: 1 } }]", "last step is not output"),
    ("outputs: { x: { type: string } }\nsteps: [{ id: o, output: { y: a } }]", "missing outputs declared in the header: x"),
    ("outputs: { x: { type: file } }\nsteps: [{ id: o, output: { x: /home/x/.env } }]", "file output"),
    ("outputs: { x: { type: number } }\nsteps: [{ id: o, output: { x: text } }]", "output has type number"),
    ("outputs: { x: { type: string } }\nsteps: [{ id: o, output: { x: a } }, { id: p, set: { y: 1 } }]",
     "only as the last step"),
    ("steps: [{ id: p, parallel: { a: [{ id: x, output: { y: 1 } }], b: [{ id: y, fail: z }] } }]",
     "output must not be inside a"),
    ("steps:\n  - id: p\n    parallel:\n      a: [{ id: x, set: { v: 1 } }]\n      b: [{ id: y, set: { w: steps.x.v } }]",
     "is in another parallel branch"),
    ("steps:\n  - id: s\n    switch: { value: '\"a\"', cases: { a: [{ id: x, set: { v: 1 } }] }, default: [] }\n"
     "  - id: z\n    set: { w: steps.x.v }", "is in a switch branch"),
    ("steps: [{ id: s, switch: { value: '1', cases: { a: [] }, default: [] } }]", "must contain at least 1"),
    ("steps: [{ id: s, switch: { value: '1', cases: { a: [{ id: x, set: { v: 1 } }] }, default: [] } }]",
     "expression must return string, got number"),
    ("steps: [{ id: s, switch: { value: '\"a\"', cases: { a: [{ id: x, set: { v: 1 } }] } } }]",
     "missing required field 'default'"),
    ("steps: [{ id: s, set: { v: null } }, { id: f, fail: 'x {{ steps.s.v }}' }]", "always null"),
    ("steps: [{ id: p, parallel: { a: [{ id: x, fail: z }], b: [{ id: y, fail: z }] } }, { id: z, set: { w: steps.p.x } }]",
     "(parallel) has no output"),
    ("inputs: { t: { type: string, required: true, default: x } }\nsteps: [{ id: a, fail: x }]", "either required"),
    ("inputs: { t: { type: integer, default: 1.5 } }\nsteps: [{ id: a, fail: x }]", "does not match type integer"),
    ("steps: [{ id: a, budget_usd: 5, ask: { agent: copywriter, prompt: x } }]", "exceeds limits.budget_usd of agent"),
    ("description: '{{ x }}'\nsteps: [{ id: a, fail: x }]", None),  # duplicate key description
])
def test_validate_errors(wf, body, msg):
    got = errors(wf, HEAD + body)
    assert (msg or "duplicate key") in got, got


def test_template_in_expression_one_error(wf):
    """BUGS.md #2: `{{ }}` in an expression (set, when) = one message with a caret, no AST Set node errors."""
    got = errors(wf, HEAD + "steps: [{ id: a, when: '{{ inputs.y }}', set: { x: '{{ inputs.y }}' } }]")
    assert got.count("template {{ }} is not allowed here") == 2 and "Set" not in got, got
    assert "\n  {{ inputs.y }}\n  ^" in got


def test_switch_cases_must_be_jev_criteria(wf):
    got = errors(wf, HEAD + """
steps:
  - id: k
    jev:
      state: x
      questions:
        kind: { type: choice, instructions: y, criteria: { product: a, action: b } }
  - id: s
    switch:
      value: steps.k.kind
      cases: { product: [{ id: a, fail: x }], discount: [{ id: b, fail: y }] }
      default: []
""")
    assert "discount is not among the criteria choices for question 'kind'" in got


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
    assert "does not match the file name" in errors(wf, "version: 1\nname: other\ndescription: x\nsteps: [{ id: a, fail: x }]")


def test_subfolders_ignored(wf):
    for d in ("scenarios", "agents"):
        (wf / d / "archive").mkdir()
        (wf / d / "archive" / "broken.yaml").write_text("this: [not valid")
    assert errors(wf, HEAD + "steps: [{ id: a, fail: x }]") == ""


def test_scenario_in_subfolder_not_runnable(wf):
    (wf / "scenarios" / "archive").mkdir()
    p = wf / "scenarios" / "archive" / "stale.yaml"
    p.write_text(HEAD.replace("NAME", "stale") + "steps: [{ id: a, fail: x }]")
    with pytest.raises(ConfigErrors, match="only scenarios stored directly in the folder can run: workflows/scenarios/"):
        validate(p, check_models=False)


def test_missing_file_in_subfolder_hint(wf):
    (wf / "agents" / "archive").mkdir()
    (wf / "agents" / "copywriter.md").rename(wf / "agents" / "archive" / "copywriter.md")
    (wf / "scenarios" / "archive").mkdir()
    (wf / "scenarios" / "archive" / "other.yaml").write_text("x")
    got = errors(wf, HEAD + "steps: [{ id: a, ask: { agent: copywriter, prompt: x } },"
                            " { id: b, call: { scenario: other } }]")
    assert "agent 'copywriter' does not exist (agents/copywriter.md) " \
           "(file is in subfolder agents/archive/, subfolders are not read)" in got, got
    assert "scenario 'other' does not exist (scenarios/other.yaml) " \
           "(file is in subfolder scenarios/archive/, subfolders are not read)" in got, got


def test_config_secret_not_printed(wf):
    cfg = wf / "config.yaml"
    cfg.write_text(cfg.read_text().replace("api_key_env: OPENROUTER_API_KEY", "api_key_env: sk-or-v1-SECRET123"))
    got = errors(wf, HEAD + "steps: [{ id: a, fail: x }]")
    assert "openrouter.api_key_env: value does not match pattern" in got and "SECRET" not in got


def test_config_same_env_twice(wf):
    cfg = wf / "config.yaml"
    cfg.write_text(cfg.read_text().replace("token_env: WEBHOOK_TOKEN", "token_env: OPENROUTER_API_KEY"))
    assert "use the same variable OPENROUTER_API_KEY" in errors(wf, HEAD + "steps: [{ id: a, fail: x }]")


def test_models_checked_against_models_list(wf):
    from agencast.fake import Fake
    p = scenario(wf, HEAD + "steps: [{ id: a, image: { model: smart, prompt: x } }]")
    fake = Fake(None, ["anthropic/claude-haiku-4.5"])  # gemini models are absent from /models
    with pytest.raises(ConfigErrors) as e:
        validate(p, transport=fake.transport())
    assert "does not support image output" in str(e.value)
    cfg = wf / "config.yaml"
    cfg.write_text(cfg.read_text().replace("claude-haiku-4.5", "claude-haiku-4-5"))
    with pytest.raises(ConfigErrors, match="is not in GET /models"):
        validate(p, transport=fake.transport())


def test_images_api_model_and_aspect_ratio_validation(wf):
    from agencast.fake import Fake

    add_image_model(wf)
    p = scenario(wf, HEAD + 'steps: [{ id: a, image: { model: gpt-image, prompt: x, aspect_ratio: "1:1" } }]')
    assert validate(p, transport=Fake(None, [], ["openai/gpt-image-2"]).transport())
    p.write_text(HEAD.replace("NAME", p.stem) + 'steps: [{ id: a, image: { model: gpt-image, prompt: x, aspect_ratio: "5:4" } }]')
    with pytest.raises(ConfigErrors, match="does not support aspect_ratio 5:4"):
        validate(p, transport=Fake(None, [], ["openai/gpt-image-2"]).transport())
    with pytest.raises(ConfigErrors, match="is not in GET /images/models"):
        validate(p, transport=Fake(None, [], ["openai/other-image"]).transport())


def test_chat_image_model_only_in_images_api_suggests_config(wf):
    from agencast.fake import Fake

    add_image_model(wf, quality=None)
    cfg_path = wf / "config.yaml"
    cfg = __import__("yaml").safe_load(cfg_path.read_text())
    cfg["models"]["gpt-image"]["api"] = "chat"
    cfg_path.write_text(__import__("yaml").safe_dump(cfg, allow_unicode=True, sort_keys=False))
    p = scenario(wf, HEAD + "steps: [{ id: a, image: { model: gpt-image, prompt: x } }]")
    with pytest.raises(ConfigErrors, match=r"openai/gpt-image-2.*is only available in the Images API — set models.gpt-image.api: images"):
        validate(p, transport=Fake(None, ["anthropic/claude-haiku-4.5"], ["openai/gpt-image-2"]).transport())


def test_quality_requires_images_api(wf):
    add_image_model(wf)
    cfg_path = wf / "config.yaml"
    cfg = __import__("yaml").safe_load(cfg_path.read_text())
    cfg["models"]["gpt-image"]["api"] = "chat"
    cfg_path.write_text(__import__("yaml").safe_dump(cfg, allow_unicode=True, sort_keys=False))
    p = scenario(wf, HEAD + "steps: [{ id: a, fail: done }]")
    with pytest.raises(ConfigErrors, match=r"config.yaml.*models.gpt-image.api: expected \"images\""):
        validate(p, check_models=False)


def test_all_errors_at_once(wf):
    got = errors(wf, HEAD + "steps: [{ id: a, set: { x: steps.b.y } }, { id: c, when: '1', fail: x }]")
    assert "step 'b' does not exist" in got and "expression must return true/false" in got


# --- inputs ----------------------------------------------------------------------------

def test_inputs():
    sc = {"inputs": {"t": {"type": "string", "required": True}, "n": {"type": "integer", "default": 2},
                     "b": {"type": "boolean", "default": False}, "l": {"type": "list", "default": []}}}
    assert resolve_inputs(sc, {"t": "4:5", "n": "3", "b": "true", "l": '["a"]'}, from_text=True) == \
        {"t": "4:5", "n": 3, "b": True, "l": ["a"]}
    with pytest.raises(ConfigErrors) as e:
        resolve_inputs(sc, {"n": "x", "z": "1"}, from_text=True)
    assert {"missing required input 't' (string)", "unknown input 'z' (scenario has: t, n, b, l)",
            "input 'n' must be integer, got string"} <= set(e.value.errors)
    with pytest.raises(ConfigErrors, match="an upload_id from POST"):  # a JSON string is never a host path
        resolve_inputs({"inputs": {"f": {"type": "file", "required": True}}}, {"f": "/etc/passwd"})
