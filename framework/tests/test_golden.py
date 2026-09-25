"""Konformační sada (DESIGN §5.6, §5.9 bod 3): každý scénář, agent a skill ve
workflows/ a každá ukázka v docs/spec/ musí projít validate a scénáře doběhnout
s falešným poskytovatelem. Přidání scénáře do workflows/ = přidání testu.

Skriptované odpovědi pro zlatý scénář: tests/golden/<jméno>.yaml (volitelné;
bez nich musí běh skončit úspěchem nebo záměrným `fail`).
"""
import re
import shutil
from pathlib import Path

import pytest
from conftest import CONFIG, REPO, WORKFLOWS, run

from maw.expressions import parse, parse_path, template_parts
from maw.loader import (load_yaml, nested_lists, read_frontmatter, read_yaml, scenario_schema_errors, schema_errors,
                        version_error)
from maw.validate import load_agent, load_config, load_skill

GOLDEN = Path(__file__).parent / "golden"
SPEC = REPO / "docs" / "spec"


@pytest.mark.parametrize("path", sorted((WORKFLOWS / "scenarios").glob("*.yaml")), ids=lambda p: p.stem)
def test_workflow_scenario_runs_with_fake(wf, path):
    script = read_yaml(GOLDEN / path.name) if (GOLDEN / path.name).is_file() else None
    r, _ = run(wf / "scenarios" / path.name, _sample_inputs(read_yaml(path)), script)
    if script:
        assert r.status == "succeeded", r.error
    else:
        assert r.status == "succeeded" or r.error["class"] == "fail", r.error


def _sample_inputs(sc):
    samples = {"string": "test", "number": 1, "integer": 1, "boolean": True, "list": [], "object": {}}
    return {k: samples[v["type"]] for k, v in (sc.get("inputs") or {}).items() if v.get("required")}


@pytest.mark.parametrize("path", sorted((WORKFLOWS / "agents").glob("*.md")), ids=lambda p: p.stem)
def test_workflow_agent_valid(wf, path):
    errs = []
    cfg = load_config(wf, errs)
    assert load_agent(wf, path.stem, cfg, errs) and not errs, errs


@pytest.mark.parametrize("path", sorted((WORKFLOWS / "skills").glob("*/SKILL.md")), ids=lambda p: p.parent.name)
def test_workflow_skill_valid(path):
    errs = []
    assert load_skill(WORKFLOWS, path.parent.name, errs, "test") and not errs, errs


@pytest.mark.parametrize("name", ["config.yaml", "config.example.yaml"])
def test_workflow_configs_valid(tmp_path, name):
    if not (WORKFLOWS / name).is_file():
        pytest.skip(f"{name} neexistuje")
    shutil.copy(WORKFLOWS / name, tmp_path / "config.yaml")
    errs = []
    assert load_config(tmp_path, errs) and not errs, errs


def test_workflow_mcp_and_commands_examples():
    mcp = read_yaml(WORKFLOWS / "mcp.example.yaml")
    assert version_error(mcp, "mcp") is None and schema_errors("mcp", mcp, "mcp") == []
    # commands.yaml zatím bez JSON Schema (krok run není ve v1) — jen YAML 1.2 a verze
    assert version_error(read_yaml(WORKFLOWS / "commands.example.yaml"), "commands") is None


# --- ukázky ze specifikace --------------------------------------------------------------------

def _blocks(lang):
    for md in sorted(SPEC.glob("*.md")):
        for i, block in enumerate(re.findall(rf"```{lang}\n(.*?)```", md.read_text(), re.S), 1):
            yield pytest.param(md.name, block, id=f"{md.stem}-{lang}{i}")


def _check_expressions(steps):
    """Fragment kroků: každý výraz a šablona musí jít přečíst (syntaxe, zakázané konstrukce)."""
    for st in steps:
        for key in ("when",):
            if key in st:
                parse(st[key])
        if "switch" in st:
            parse(st["switch"]["value"])
        for v in (st.get("set") or {}).values():
            if isinstance(v, str):
                parse(v)
        for field in ("ask", "task", "image"):
            if field in st:
                for *_, expr in template_parts(st[field]["prompt"]):
                    parse_path(expr)
        for _, lst in nested_lists(st):
            _check_expressions(lst)


@pytest.mark.parametrize("md,block", list(_blocks("yaml")))
def test_spec_yaml_examples(tmp_path, md, block):
    data = load_yaml(block, md)
    if md == "scenario.md" and isinstance(data, dict) and "version" in data:
        # celý scénář: validate + běh s falešným poskytovatelem v kopii workflows/
        wf = tmp_path / "workflows"
        for d in ("agents", "skills", "scenarios"):
            shutil.copytree(WORKFLOWS / d, wf / d)
        (wf / "config.yaml").write_text(CONFIG)
        (wf / "scenarios" / f"{data['name']}.yaml").write_text(block)
        r, _ = run(wf / "scenarios" / f"{data['name']}.yaml", _sample_inputs(data))
        assert r.status == "succeeded", r.error
    elif md == "scenario.md":
        head = {"version": 1, "name": "x", "description": "x"}
        if isinstance(data, dict) and "id" not in data:  # úryvek hlavičky (inputs, outputs)
            assert scenario_schema_errors({**head, **data, "steps": [{"id": "a", "fail": "x"}]}, md) == []
            return
        steps = data if isinstance(data, list) else [data]
        assert scenario_schema_errors({**head, "steps": steps}, md) == []
        _check_expressions(steps)
    elif isinstance(data, dict) and "openrouter" in data:
        assert schema_errors("config", data, md) == []
    elif isinstance(data, dict) and "servers" in data:
        assert schema_errors("mcp", data, md) == []


@pytest.mark.parametrize("md,block", [p for p in _blocks("markdown") if p.values[0] in ("agent.md", "skill.md")])
def test_spec_markdown_examples(tmp_path, md, block):
    f = tmp_path / "x.md"
    f.write_text(block)
    fm, body = read_frontmatter(f, md)
    assert body.strip()
    assert schema_errors(md.removesuffix(".md"), fm, md) == []
