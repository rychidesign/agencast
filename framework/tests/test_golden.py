"""Conformance suite (DESIGN §5.6, §5.9 item 3): every scenario, agent and skill in
examples/ and every example in docs/spec/ must pass validate, and scenarios must complete
with a fake provider. Adding a scenario to examples/*/workflows/ = adding a test.

Scripted responses for a golden scenario: examples/<project>/fake/<name>.yaml (optional;
without them the run must succeed or end with an intentional `fail`).
"""
import re
import shutil
from pathlib import Path

import pytest
import yaml
from conftest import REPO, WORKFLOWS, TUTORIAL, example_files, golden_config, run

from agencast.expressions import parse, parse_path, template_parts
from agencast.loader import (load_yaml, nested_lists, read_frontmatter, read_yaml, scenario_schema_errors, schema_errors,
                        version_error)
from agencast.mcp_client import load_mcp
from agencast.validate import load_agent, load_config, load_skill

SPEC = REPO / "docs" / "spec"


@pytest.mark.parametrize("path", example_files("scenarios/*.yaml"), ids=lambda p: p.stem)
def test_workflow_scenario_runs_with_fake(wf, path):
    fixture = path.parents[2] / "fake" / path.name
    script = read_yaml(fixture) if fixture.is_file() else None
    r, _ = run(wf / "scenarios" / path.name, _sample_inputs(read_yaml(path)), script)
    if script:
        assert r.status == "succeeded", r.error
    else:
        assert r.status == "succeeded" or r.error["class"] == "fail", r.error


def _sample_inputs(sc):
    samples = {"string": "test", "number": 1, "integer": 1, "boolean": True, "list": [], "object": {}}
    return {k: samples[v["type"]] for k, v in (sc.get("inputs") or {}).items() if v.get("required")}


@pytest.mark.parametrize("path", example_files("agents/*.md"), ids=lambda p: p.stem)
def test_workflow_agent_valid(wf, path):
    errs = []
    cfg = load_config(wf, errs)
    assert load_agent(wf, path.stem, cfg, errs) and not errs, errs


def test_owner_alias_reaches_golden_tests(wf, tmp_path):
    """BUGS.md #6: golden tests also recognize aliases the owner adds to config.yaml (temporary alias only in this test)."""
    owner = yaml.safe_load((WORKFLOWS / "config.yaml").read_text())
    owner["models"]["cheap"] = {"id": "test/cheap-1"}
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(owner))
    (wf / "config.yaml").write_text(golden_config(tmp_path / "config.yaml"))
    agent = wf / "agents" / "tutorial-namer.md"
    agent.write_text(agent.read_text().replace("model: smart", "model: cheap"))
    test_workflow_agent_valid(wf, agent)
    test_workflow_scenario_runs_with_fake(wf, TUTORIAL / "scenarios" / "tutorial-01-names.yaml")


def test_archive_subfolders_ignored(wf):
    """ISSUES 37: subdirectories (archive/) in agents/ and scenarios/ are ignored — validation and execution pass."""
    for source in (WORKFLOWS, TUTORIAL):
        for d in ("agents", "scenarios"):
            shutil.copytree(source / d, wf / d / "archive", dirs_exist_ok=True)
    for path in example_files("scenarios/*.yaml"):
        test_workflow_scenario_runs_with_fake(wf, path)


@pytest.mark.parametrize("path", example_files("skills/*/SKILL.md"), ids=lambda p: p.parent.name)
def test_workflow_skill_valid(path):
    errs = []
    assert load_skill(path.parents[2], path.parent.name, errs, "test") and not errs, errs


@pytest.mark.parametrize("name", ["config.yaml", "config.example.yaml"])
def test_workflow_configs_valid(tmp_path, name):
    if not (WORKFLOWS / name).is_file():
        pytest.skip(f"{name} does not exist")
    shutil.copy(WORKFLOWS / name, tmp_path / "config.yaml")
    errs = []
    assert load_config(tmp_path, errs) and not errs, errs


def test_workflow_mcp_and_commands_examples():
    assert read_yaml(TUTORIAL / "config.yaml")["models"] == read_yaml(WORKFLOWS / "config.yaml")["models"]
    assert (TUTORIAL / "scenarios/tone-check.yaml").read_bytes() == (WORKFLOWS / "scenarios/tone-check.yaml").read_bytes()
    mcp = read_yaml(WORKFLOWS / "mcp.example.yaml")
    assert version_error(mcp, "mcp") is None and schema_errors("mcp", mcp, "mcp") == []
    if (WORKFLOWS / "mcp.yaml").is_file():  # owner's file
        errs = []
        assert load_mcp(WORKFLOWS, errs) and not errs, errs
    # commands.yaml has no JSON Schema yet (run step is not in v1) — only YAML 1.2 and version
    assert version_error(read_yaml(WORKFLOWS / "commands.example.yaml"), "commands") is None


# --- examples from the specification --------------------------------------------------------------------

def _blocks(lang):
    for md in sorted(SPEC.glob("*.md")):
        for i, block in enumerate(re.findall(rf"```{lang}\n(.*?)```", md.read_text(), re.S), 1):
            yield pytest.param(md.name, block, id=f"{md.stem}-{lang}{i}")


def _check_expressions(steps):
    """Step fragment: every expression and template must parse (syntax, forbidden constructs)."""
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
def test_spec_yaml_examples(wf, md, block):
    data = load_yaml(block, md)
    if md == "scenario.md" and isinstance(data, dict) and "version" in data:
        # whole scenario: validate + run with a fake provider in a copy of workflows/
        (wf / "scenarios" / f"{data['name']}.yaml").write_text(block)
        r, _ = run(wf / "scenarios" / f"{data['name']}.yaml", _sample_inputs(data))
        assert r.status == "succeeded", r.error
    elif md == "scenario.md":
        head = {"version": 1, "name": "x", "description": "x"}
        if isinstance(data, dict) and "id" not in data:  # header fragment (inputs, outputs)
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
