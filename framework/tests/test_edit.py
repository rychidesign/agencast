"""Editing operations (edit.py, api.md “Editing”): round-trip YAML, step address, hash, validation before writing."""
import difflib
import json
import re
from pathlib import Path

import pytest
from conftest import example_files

from agencast import ConfigErrors, api, edit
from agencast.edit import FRONTMATTER, _new, merge, yaml_edit
from agencast.loader import load_yaml

SCENARIOS = example_files("scenarios/*.yaml")
AGENTS = example_files("agents/*.md")


def changed_lines(a: str, b: str) -> list[str]:
    """Original lines replaced or deleted by a change (inserted lines do not count)."""
    sm = difflib.SequenceMatcher(None, a.splitlines(), b.splitlines(), autojunk=False)
    return [ln for op, i1, i2, _, _ in sm.get_opcodes() if op in ("replace", "delete") for ln in a.splitlines()[i1:i2]]


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.name)
def test_scenario_roundtrip(path):
    name = path.name
    text = path.read_text(encoding="utf-8")
    assert yaml_edit(text, lambda d: None, name) == text  # no-op = byte-identical file

    new_step = {"id": "rt_new", "fail": "Multiple lines\n{{ inputs.x }}"}

    def change(d):
        merge(d, {"description": "New description: {{ not a template }}"})
        d["steps"].insert(1, _new(new_step))
    new = yaml_edit(text, change, name)
    want = load_yaml(text, name)
    want["description"] = "New description: {{ not a template }}"
    want["steps"].insert(1, new_step)
    assert load_yaml(new, name) == want  # loader (PyYAML 1.2 core) reads the expected content
    assert 'description: "New description: {{ not a template }}"' in new
    # only the description is rewritten (all its lines if multiline); comments, quotes and the rest remain verbatim
    lines = text.splitlines()
    i = next(n for n, ln in enumerate(lines) if ln.startswith("description:"))
    j = next(n for n in range(i + 1, len(lines)) if not lines[n].startswith(" "))
    assert set(changed_lines(text, new)) <= set(lines[i:j])


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.name)
def test_agent_roundtrip(path):
    name = path.name
    src = path.read_text(encoding="utf-8")
    m = FRONTMATTER.match(src)
    assert m
    assert m[1] + yaml_edit(m[2], lambda d: merge(d, {}), name) + m[3] + m[4] == src  # no-op
    fm = yaml_edit(m[2], lambda d: merge(d, {"description": "Another description", "limits": {"budget_usd": 0.5}}), name)
    new = m[1] + fm + m[3] + m[4]
    want = load_yaml(m[2], name)
    want["description"] = "Another description"
    want.setdefault("limits", {})["budget_usd"] = 0.5
    m2 = FRONTMATTER.match(new)
    assert m2 and load_yaml(m2[2], name) == want and m2[4] == m[4]  # body unchanged
    assert [ln for ln in m[2].splitlines() if ln.lstrip().startswith("#")] == \
           [ln for ln in fm.splitlines() if ln.lstrip().startswith("#")]  # comments preserved


def test_noop_operation_on_golden_project(wf):
    root = wf.parent
    p = wf / "scenarios" / "ig-post.yaml"
    before = p.read_bytes()
    d = api.describe_scenario(root, "ig-post")
    assert d and d["steps"][0]["address"] == ["steps", 0]
    r = api.set_header(root, "ig-post", d["etag"], {})
    assert p.read_bytes() == before and r["etag"] == d["etag"]


BRANCHES = """\
version: 1
name: branches
description: Arbitrarily nested branches
inputs:
  topic: { type: string, default: café }   # alignment and spacing preserved
outputs:
  text: { type: string }
steps:
  # branch by topic
  - id: decide
    switch:
      value: inputs.topic
      cases:
        café:
          - id: par
            parallel:
              a:
                - id: a1
                  ask: { agent: writer, prompt: "A {{ inputs.topic }}" }
              b:
                - id: b1
                  ask: { agent: writer, prompt: "B {{ inputs.topic }}" }
                - id: b2
                  ask: { agent: writer, prompt: "B2 {{ inputs.topic }}" }
              c:
                - id: c1
                  ask: { agent: writer, prompt: "C {{ inputs.topic }}" }
      default:
        - id: d1
          ask: { agent: writer, prompt: "D {{ inputs.topic }}" }

  - id: result
    output:
      text: "{{ inputs.topic }}"
"""


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "p"
    api.new_project(root)
    r = api.write_file(root, "scenarios/branches.yaml", None, BRANCHES)
    assert r["errors"] == []
    return root


def ids(tree):
    out = []
    for s in tree:
        out.append((s["id"], s["address"]))
        for sub in [*s.get("branches", {}).values(), *s.get("cases", {}).values(), s.get("default") or []]:
            out += ids(sub)
    return out


def test_address_in_get_and_nested_ops(proj):
    d = api.describe_scenario(proj, "branches")
    assert d
    assert ids(d["steps"]) == [
        ("decide", ["steps", 0]), ("par", ["steps", 0, "switch", "cases", "café", 0]),
        ("a1", ["steps", 0, "switch", "cases", "café", 0, "parallel", "a", 0]),
        ("b1", ["steps", 0, "switch", "cases", "café", 0, "parallel", "b", 0]),
        ("b2", ["steps", 0, "switch", "cases", "café", 0, "parallel", "b", 1]),
        ("c1", ["steps", 0, "switch", "cases", "café", 0, "parallel", "c", 0]),
        ("d1", ["steps", 0, "switch", "default", 0]), ("result", ["steps", 1])]
    a = ["steps", 0, "switch", "cases", "café", 0, "parallel", "a"]
    # add at branch start (list address) and after a step (step address); URL addresses are strings
    r = api.add_step(proj, "branches", d["etag"], a, {"id": "a0", "ask": {"agent": "writer", "prompt": "Zero {{ inputs.topic }}"}})
    r = api.add_step(proj, "branches", r["etag"], [*a[:-1], "a", "1"],
                     {"id": "a2", "ask": {"agent": "writer", "prompt": "Two\n{{ steps.a1.text }}"}})
    text = (proj / "workflows" / "scenarios" / "branches.yaml").read_text()
    assert 'prompt: "Zero {{ inputs.topic }}"' in text and "prompt: |-\n" in text
    assert "  topic: { type: string, default: café }   # alignment and spacing preserved\n" in text
    assert "  # branch by topic\n" in text
    tree = api.describe_scenario(proj, "branches")
    assert tree and [i for i, _ in ids(tree["steps"])] == ["decide", "par", "a0", "a1", "a2", "b1", "b2", "c1", "d1", "result"]
    # update: merge patch, null deletes fields
    r = api.update_step(proj, "branches", r["etag"], ["steps", 0, "switch", "default", 0],
                        {"ask": {"prompt": "Another {{ inputs.topic }}"}, "timeout": "1m"})
    r = api.update_step(proj, "branches", r["etag"], ["steps", 0, "switch", "default", 0], {"timeout": None})
    data = load_yaml((proj / "workflows" / "scenarios" / "branches.yaml").read_text(), "")
    assert data["steps"][0]["switch"]["default"][0] == {"id": "d1", "ask": {"agent": "writer", "prompt": "Another {{ inputs.topic }}"}}
    # move: from nested branch b to the start of default; then delete
    r = api.move_step(proj, "branches", r["etag"], [*a[:-1], "b", 0], ["steps", 0, "switch", "default"])
    tree = api.describe_scenario(proj, "branches")
    assert tree and [i for i, _ in ids(tree["steps"])] == ["decide", "par", "a0", "a1", "a2", "b2", "c1", "b1", "d1", "result"]
    assert ("b1", ["steps", 0, "switch", "default", 0]) in ids(tree["steps"])
    r = api.delete_step(proj, "branches", r["etag"], ["steps", 0, "switch", "default", 0])
    r = api.delete_step(proj, "branches", r["etag"], [*a[:-1], "c", 0])  # last step in a branch → remove the branch
    tree = api.describe_scenario(proj, "branches")
    assert tree and tree["etag"] == r["etag"]
    assert [i for i, _ in ids(tree["steps"])] == ["decide", "par", "a0", "a1", "a2", "b2", "d1", "result"]
    assert list(tree["steps"][0]["cases"]["café"][0]["branches"]) == ["a", "b"]
    with pytest.raises(api.NotFound):
        api.delete_step(proj, "branches", r["etag"], ["steps", 0, "parallel", "x", 0])
    with pytest.raises(ConfigErrors, match="its own branch"):
        api.move_step(proj, "branches", r["etag"], ["steps", 0], ["steps", 0, "switch", "default"])


def test_etag_conflict_and_validation_write_nothing(proj):
    p = proj / "workflows" / "scenarios" / "branches.yaml"
    before = p.read_bytes()
    cur = api.describe_scenario(proj, "branches")["etag"]  # type: ignore[index]
    with pytest.raises(api.Conflict) as e:
        api.set_header(proj, "branches", "stale", {"description": "x"})
    assert e.value.etag == cur and p.read_bytes() == before
    # output must remain last → config error, nothing is written
    with pytest.raises(ConfigErrors) as e2:
        api.add_step(proj, "branches", cur, ["steps", 1], {"id": "after", "fail": "done"})
    assert any("output" in x for x in e2.value.errors) and p.read_bytes() == before
    with pytest.raises(ConfigErrors):  # reference to a nonexistent step
        api.update_step(proj, "branches", cur, ["steps", 1], {"output": {"text": "{{ steps.missing.text }}"}})
    with pytest.raises(ConfigErrors, match="steps"):
        api.set_header(proj, "branches", cur, {"steps": []})
    assert p.read_bytes() == before


def test_file_changed_during_validation_conflicts(proj, monkeypatch):
    rel = "scenarios/branches.yaml"
    p = proj / "workflows" / rel
    doc = api.read_file(proj, rel)
    manual = p.read_text() + "# manual change during validation\n"

    def check(root, path, text):
        p.write_text(manual)
        return []

    monkeypatch.setattr(edit, "_check", check)
    with pytest.raises(api.Conflict) as exc:
        api.write_file(proj, rel, doc["etag"], "change from the GUI\n")

    assert exc.value.etag == api.read_file(proj, rel)["etag"]
    assert p.read_text() == manual
    assert not p.with_name(f".{p.name}.tmp").exists()


def test_existing_errors_do_not_block(proj):
    wf = proj / "workflows"
    (wf / "scenarios" / "broken.yaml").write_text("version: 1\nname: broken\ndescription: x\nsteps: []\n")
    r = api.set_header(proj, "demo", api.describe_scenario(proj, "demo")["etag"], {"description": "New"})  # type: ignore[index]
    assert any("broken" in e for e in r["errors"])  # still reported, but does not block the change


def test_rename_scenario_updates_calls_and_keeps_comments(wf):
    proj = wf.parent
    api.new_scenario(proj, "demo")
    callee = api.read_file(proj, "scenarios/demo.yaml")
    api.set_header(proj, "demo", callee["etag"], {"callable": True})
    api.new_scenario(proj, "caller")
    caller = api.read_file(proj, "scenarios/caller.yaml")
    api.add_step(proj, "caller", caller["etag"], ["steps", 0],
                 {"id": "invoke", "call": {"scenario": "demo"}})
    callee_path = wf / "scenarios" / "demo.yaml"
    callee_path.write_text(callee_path.read_text().replace("name: demo\n", "# preserved comment\nname: demo\n"))
    caller_path = wf / "scenarios" / "caller.yaml"
    caller_path.write_text(caller_path.read_text().replace("scenario: demo", "scenario: demo # call"))

    r = api.rename_scenario(proj, "demo", api.read_file(proj, "scenarios/demo.yaml")["etag"], "intro")

    assert r["name"] == "intro" and r["etag"] == api.read_file(proj, "scenarios/intro.yaml")["etag"]
    assert r["changed"] == ["scenarios/caller.yaml", "scenarios/intro.yaml"]
    assert "# preserved comment" in (wf / "scenarios" / "intro.yaml").read_text()
    assert re.search(r"scenario: intro\s+# call", caller_path.read_text())
    assert ["caller", "intro"] in api.describe_project(proj)["links"]["scenario_scenario"]
    with pytest.raises(api.NotFound):
        api.read_file(proj, "scenarios/demo.yaml")


def test_rename_agent_updates_task_and_mcp(wf):
    proj = wf.parent
    agent_path = wf / "agents" / "librarian.md"
    before = api.read_file(proj, "agents/librarian.md")
    agent_path.write_text(before["text"].replace("name: librarian\n", "# preserved frontmatter\nname: librarian\n"))
    mcp_path = wf / "mcp.yaml"
    mcp_path.write_text(yaml_edit(mcp_path.read_text(),
                                  lambda d: d["servers"]["filesystem"]["agents"].yaml_add_eol_comment("preserved permission", 0),
                                  "mcp.yaml"))

    r = api.rename_agent(proj, "librarian", api.read_file(proj, "agents/librarian.md")["etag"], "archivist")

    assert r["name"] == "archivist"
    assert r["changed"] == ["agents/archivist.md", "mcp.yaml", "scenarios/demo-task.yaml"]
    new_agent = api.read_file(proj, "agents/archivist.md")
    assert new_agent["frontmatter"]["name"] == "archivist"
    assert "# preserved frontmatter" in new_agent["text"]
    assert new_agent["body"] == before["body"]
    task = api.read_file(proj, "scenarios/demo-task.yaml")["data"]["steps"][0]["task"]
    assert task["agent"] == "archivist"
    assert "archivist" in load_yaml(mcp_path.read_text(), "mcp.yaml")["servers"]["filesystem"]["agents"]
    assert "# preserved permission" in mcp_path.read_text()
    links = api.describe_project(proj)["links"]
    assert ["demo-task", "catalog", "archivist"] in links["scenario_step_agent"]
    assert ["archivist", "filesystem"] in links["agent_server"]


def test_rename_rejects_conflicts_collisions_names_and_new_errors(wf):
    proj = wf.parent
    rel = "scenarios/demo-task.yaml"
    source = wf / rel
    original = source.read_bytes()
    tag = api.read_file(proj, rel)["etag"]
    with pytest.raises(api.Conflict):
        api.rename_scenario(proj, "demo-task", "stale", "new")
    with pytest.raises(ConfigErrors):
        api.rename_scenario(proj, "demo-task", tag, "Writer")
    with pytest.raises(ConfigErrors):
        api.rename_scenario(proj, "demo-task", tag, "tone-check")
    assert source.read_bytes() == original

    # New error: after renaming, a scenario using an MCP server is absent from its allowlist.
    mcp = wf / "mcp.yaml"
    mcp.write_text(yaml_edit(mcp.read_text(),
                             lambda d: d["servers"]["filesystem"].update({"scenarios": ["demo-task"]}), "mcp.yaml"))
    mcp_before = mcp.read_bytes()
    source_before = source.read_bytes()
    with pytest.raises(ConfigErrors, match="cannot run an agent"):
        api.rename_scenario(proj, "demo-task", api.read_file(proj, rel)["etag"], "demo-new")
    assert source.read_bytes() == source_before and mcp.read_bytes() == mcp_before
    assert not (wf / "scenarios" / "demo-new.yaml").exists()


def test_rename_allows_existing_error_with_name_as_substring(wf):
    proj = wf.parent
    api.new_scenario(proj, "demo")
    unrelated = wf / "scenarios" / "demoextra.yaml"
    unrelated.write_text("version: [\n")

    result = api.rename_scenario(proj, "demo", api.read_file(proj, "scenarios/demo.yaml")["etag"], "intro")

    assert result["name"] == "intro"
    assert unrelated.read_text() == "version: [\n"
    assert any("demoextra.yaml" in error for error in result["errors"])


def test_delete_refused_when_used(proj):
    wf = proj / "workflows"
    d = api.describe_project(proj)
    tag = {a["name"]: a["etag"] for a in d["agents"]}["writer"]
    with pytest.raises(ConfigErrors, match="writer.*demo"):
        api.delete_agent(proj, "writer", tag)
    assert (wf / "agents" / "writer.md").is_file()
    # skill: new, used by an agent → cannot be deleted
    r = api.set_skill(proj, "voice", None, "---\nname: voice\ndescription: Tone of texts\n---\nUse an informal tone.\n")
    ra = api.set_agent(proj, "writer", tag, {"skills": ["voice"]})
    with pytest.raises(ConfigErrors, match="voice.*writer"):
        api.delete_skill(proj, "voice", r["etag"])
    api.set_agent(proj, "writer", ra["etag"], {"skills": None})
    assert api.delete_skill(proj, "voice", r["etag"])["etag"] is None and not (wf / "skills" / "voice").exists()
    # a scenario referenced by call cannot be deleted
    callee = api.read_file(proj, "scenarios/demo.yaml")
    api.set_header(proj, "demo", callee["etag"], {"callable": True})
    callee = api.read_file(proj, "scenarios/demo.yaml")
    branches = api.read_file(proj, "scenarios/branches.yaml")
    api.add_step(proj, "branches", branches["etag"], ["steps"], {"id": "invoke", "call": {"scenario": "demo"}})
    with pytest.raises(ConfigErrors, match="demo.*branches"):
        api.delete_scenario(proj, "demo", callee["etag"])
    assert api.delete_scenario(proj, "branches", api.read_file(proj, "scenarios/branches.yaml")["etag"])["etag"] is None


def test_set_agent_keeps_comments_and_creates(proj):
    wf = proj / "workflows"
    f = api.read_file(proj, "agents/writer.md")
    assert f["frontmatter"]["model"] == "smart" and f["body"].startswith("Write")
    api.set_agent(proj, "writer", f["etag"], {"description": "Different"}, "New body.\n")
    text = (wf / "agents" / "writer.md").read_text()
    assert "description: Different\n" in text and text.endswith("---\nNew body.\n")
    with pytest.raises(ConfigErrors, match="frontmatter and body"):
        api.set_agent(proj, "new", None, {"description": "x"})
    r = api.set_agent(proj, "new", None, {"description": "New agent", "model": "fast", "limits": {"budget_usd": 0.01}},
                      "Instructions.\n")
    assert r["etag"] and api.read_file(proj, "agents/new.md")["frontmatter"]["name"] == "new"
    api.new_agent(proj, "commented")
    k = api.read_file(proj, "agents/commented.md")
    api.set_agent(proj, "commented", k["etag"], {"model": "fast"})
    assert "model: fast     # alias from config.yaml" in (wf / "agents" / "commented.md").read_text()


def test_set_config_no_secrets(proj):
    c = api.read_file(proj, "config.yaml")
    r = api.set_config(proj, c["etag"], {"models": {"cheap": {"id": "google/gemini-3.5-flash-lite"}},
                                         "limits": {"run_budget_usd": 2}})
    text = (proj / "workflows" / "config.yaml").read_text()
    assert "  cheap:" in text and "run_budget_usd: 2\n" in text and "# Limits for a single run." in text
    for bad in ({"version": 2}, {"openrouter": {"base_url": "http://127.0.0.1/x"}}):
        with pytest.raises(ConfigErrors, match="cannot"):
            api.set_config(proj, r["etag"], bad)
    with pytest.raises(ConfigErrors) as e:  # value instead of a variable name
        api.set_config(proj, r["etag"], {"openrouter": {"api_key_env": "sk-or-v1-secret"}})
    assert "secret" not in " ".join(e.value.errors)


@pytest.mark.parametrize("rel", ["../.env", ".env", "agents/../../.env", "agents/x.txt", "scenarios/a/b.yaml",
                                 "runs/x.yaml", "/etc/passwd", "skills/x/other.md", "commands.yaml"])
def test_files_only_inside_workflows(proj, rel):
    with pytest.raises(api.NotFound):
        api.read_file(proj, rel)
    with pytest.raises(api.NotFound):
        api.write_file(proj, rel, None, "x")


def test_write_file_raw(proj):
    f = api.read_file(proj, "scenarios/demo.yaml")
    assert f["data"]["name"] == "demo" and f["errors"] == []
    with pytest.raises(ConfigErrors):  # broken YAML is not written
        api.write_file(proj, "scenarios/demo.yaml", f["etag"], "version: 1\nname: [\n")
    new = f["text"].replace("description: ", "# comment\ndescription: ")
    r = api.write_file(proj, "scenarios/demo.yaml", f["etag"], new)
    assert (proj / "workflows" / "scenarios" / "demo.yaml").read_text() == new and r["etag"] != f["etag"]
    assert not list((proj / "workflows").rglob("*.tmp"))
    assert re.fullmatch(r"[0-9a-f]{64}", r["etag"])


def test_describe_has_etags(proj):
    d = api.describe_project(proj)
    for x in d["scenarios"] + d["agents"]:
        kind = "scenarios" if x in d["scenarios"] else "agents"
        suffix = ".yaml" if kind == "scenarios" else ".md"
        assert x["etag"] == api.read_file(proj, f"{kind}/{x['name']}{suffix}")["etag"]
    assert Path(d["root"]) == proj.resolve()


def test_merge_new_map_matches_sibling_style():
    """A new alias in `models` (GUI Config) uses flow style next to `{ … }` mappings, block style next to blocks (0.10.3)."""
    flow = "models:\n  smart:       { id: a/b }\n  fast: { id: c/d, structured_output: tool_wrapper }\nlimits:\n  run_budget_usd: 1\n"
    out = yaml_edit(flow, lambda d: merge(d, {"models": {"gpt-image": {"id": "openai/gpt-image-2"}}}), "config.yaml")
    assert "  smart:       { id: a/b }\n" in out and "  gpt-image: {id: openai/gpt-image-2}\n" in out
    assert load_yaml(out, "")["models"]["gpt-image"] == {"id": "openai/gpt-image-2"}
    block = "models:\n  smart:\n    id: a/b\n"
    out = yaml_edit(block, lambda d: merge(d, {"models": {"new": {"id": "x/y"}}}), "config.yaml")
    assert "  new:\n    id: x/y\n" in out
    out = yaml_edit("limits:\n  run_budget_usd: 1\n", lambda d: merge(d, {"storage": {"type": "local"}}), "config.yaml")
    assert "storage:\n  type: local\n" in out  # keep block style without sibling mappings
    # rename a block alias next to flow mappings: delete first, then use flow style (even with null last)
    mixed = flow.replace("limits:", "  model-1:\n    id: openai/gpt-image-2\nlimits:")
    out = yaml_edit(mixed, lambda d: merge(d, {"models": {"gpt-image": {"id": "openai/gpt-image-2"}, "model-1": None}}), "config.yaml")
    assert "model-1" not in out and "  gpt-image: {id: openai/gpt-image-2}\n" in out


def test_merge_keeps_what_separates_steps():
    """A key added to (or removed from) the end of a step leaves the blank line and comment before the next step
    where they were — ruamel hangs them on the step's last value (api.md “Editing”: blank lines are preserved)."""
    src = ("steps:\n  - id: probe\n    task:\n      agent: tester\n      schema:\n        summary: string  # one line\n"
           "\n  # publish\n  - id: out\n    fail: no\n")
    out = yaml_edit(src, lambda d: merge(d["steps"][0], {"task": {"tools": {"testkit": ["red_pixel"]}}, "retry": 2}), "t")
    assert out == src.replace("# one line\n", "# one line\n      tools:\n        testkit:\n          - red_pixel\n    retry: 2\n")
    out = yaml_edit(src, lambda d: merge(d["steps"][0], {"task": {"schema": None, "prompt": "a\nb\n"}}), "t")
    assert out == src.replace("      schema:\n        summary: string  # one line\n", "      prompt: |\n        a\n        b\n")


def test_replace_step_keeps_what_separates_steps():
    """The blank line and the comment before the next step are not part of the replaced step (they used to be dropped)."""
    src = ("steps:\n  - id: a\n    task:\n      agent: x\n      prompt: p  # inside: goes with the step\n"
           "\n  # about b\n  - id: b\n    fail: no\n\n  - id: c\n    fail: no\n")
    out = yaml_edit(src, lambda d: edit._replace_step(d, ["steps", 0], {"id": "a", "fail": "x"}), "t")
    assert out == src.replace("    task:\n      agent: x\n      prompt: p  # inside: goes with the step\n", "    fail: x\n")
    out = yaml_edit(src, lambda d: edit._replace_step(d, ["steps", 2], {"id": "c", "fail": "yes"}), "t")  # the last step
    assert out == src.replace("  - id: c\n    fail: no\n", "  - id: c\n    fail: yes\n")


# A blank line and a comment directly above a step are its header (the examples number and describe their steps there).
# ruamel keeps them in different places: after a scalar (a, c, d), after a flow value (b) and at the end of a block (p).
HEADERS = """steps:
  # 1. first
  - id: a
    fail: no

  # 2. second
  - id: b
    set: { x: "1" }

  # 3. parallel
  - id: p
    parallel:
      left:
        # 3a. inner
        - id: l
          set: { y: "1" }

  # 4. text
  - id: c
    ask:
      agent: w
      prompt: |
        Hello

  # 5. last
  - id: d
    fail: no

# after the steps
outputs:
  x: { type: string }
"""
A, B, P, C, D = ("  # 1. first\n  - id: a\n    fail: no\n", "  # 2. second\n  - id: b\n    set: { x: \"1\" }\n",
                 "  # 3. parallel\n  - id: p\n    parallel:\n      left:\n        # 3a. inner\n        - id: l\n"
                 "          set: { y: \"1\" }\n",
                 "  # 4. text\n  - id: c\n    ask:\n      agent: w\n      prompt: |\n        Hello\n",
                 "  # 5. last\n  - id: d\n    fail: no\n")
END = "\n# after the steps\noutputs:\n  x: { type: string }\n"
NEW = "  - id: n\n    fail: x\n"


def test_headers_fixture_is_what_the_tests_take_it_for():
    assert HEADERS == "steps:\n" + "\n".join([A, B, P, C, D]) + END


@pytest.mark.parametrize("i, left", [(0, [B, P, C, D]), (1, [A, P, C, D]), (2, [A, B, C, D]), (3, [A, B, P, D]),
                                     (4, [A, B, P, C])])
def test_delete_step_removes_its_header_and_keeps_the_next_one(i, left):
    out = yaml_edit(HEADERS, lambda d: edit._delete_step(d, ["steps", i]), "t")
    # the first step's header has no blank line above it; the one that takes its place keeps its own
    assert out == "steps:\n" + ("\n" if i == 0 else "") + "\n".join(left) + END


def test_delete_last_step_of_a_branch_keeps_what_follows_the_branch():
    out = yaml_edit(HEADERS, lambda d: edit._delete_step(d, ["steps", 2, "parallel", "left", 0]), "t")
    assert out == "steps:\n" + "\n".join([A, B, "  # 3. parallel\n  - id: p\n    parallel: {}\n", C, D]) + END
    two = ("steps:\n  - id: p\n    parallel:\n      left:\n        - id: l\n          fail: no\n\n      # the other\n"
           "      right:\n        - id: r\n          set: { y: \"1\" }\n\n  # next\n  - id: c\n    fail: no\n")
    out = yaml_edit(two, lambda d: edit._delete_step(d, ["steps", 0, "parallel", "left", 0]), "t")
    assert out == two.replace("      left:\n        - id: l\n          fail: no\n", "")
    out = yaml_edit(two, lambda d: edit._delete_step(d, ["steps", 0, "parallel", "right", 0]), "t")
    assert out == two.replace("      right:\n        - id: r\n          set: { y: \"1\" }\n", "")  # "# next" stays


@pytest.mark.parametrize("after, want", [
    (None, "steps:\n" + NEW + "\n".join([A, B, P, C, D]) + END),            # the old first step keeps its header
    (["steps", 0], "steps:\n" + "\n".join([A + NEW, B, P, C, D]) + END),
    (["steps", 1], "steps:\n" + "\n".join([A, B + NEW, P, C, D]) + END),    # after a flow value
    (["steps", 2], "steps:\n" + "\n".join([A, B, P + NEW, C, D]) + END),    # after a block that ends in one
    (["steps", 3], "steps:\n" + "\n".join([A, B, P, C + NEW, D]) + END),    # after a `|` text
    (["steps", 4], "steps:\n" + "\n".join([A, B, P, C, D + NEW]) + END),    # what follows the steps stays below
])
def test_add_step_goes_below_the_step_before_and_above_the_next_header(after, want):
    assert yaml_edit(HEADERS, lambda d: edit._add_step(d, {"id": "n", "fail": "x"}, after), "t") == want


def test_move_step_carries_its_header():
    def moved(address, to):
        return yaml_edit(HEADERS, lambda d: edit._move_step(d, address, to), "t")
    flow = B.replace('{ x: "1" }', '{x: "1"}')  # moved lines are ruamel's
    assert moved(["steps", 0], ["steps", 3]) == "steps:\n\n" + "\n".join([B, P, C + A, D]) + END
    assert moved(["steps", 4], ["steps", 0]) == "steps:\n" + "\n".join([A, D, B, P, C]) + END
    assert moved(["steps", 1], ["steps", 2]) == "steps:\n" + "\n".join([A, P, flow, C, D]) + END
    assert moved(["steps", 3], ["steps"]) == "steps:\n\n" + C + "\n".join([A, B, P, D]) + END
    # into a branch and out of it: the header is indented like its new list — left deeper, below `prompt: |`, it
    # would become a part of that text
    assert moved(["steps", 4], ["steps", 2, "parallel", "left", 0]) == "steps:\n" + "\n".join(
        [A, B, P + "\n        # 5. last\n        - id: d\n          fail: no\n", C]) + END
    out = moved(["steps", 2, "parallel", "left", 0], ["steps", 3])
    assert out == "steps:\n" + "\n".join([A, B, "  # 3. parallel\n  - id: p\n    parallel: {}\n",
                                           C + "  # 3a. inner\n  - id: l\n    set: {y: \"1\"}\n", D]) + END
    assert load_yaml(out, "t")["steps"][3]["ask"]["prompt"] == "Hello\n"


@pytest.mark.parametrize("i, old, new", [(0, "    fail: no\n\n  # 2.", "    fail: x\n\n  # 2."),
                                         (1, '    set: { x: "1" }\n', "    fail: x\n"),
                                         (2, P.split("# 3. parallel\n")[1], "  - id: p\n    fail: x\n"),
                                         (3, C.split("# 4. text\n")[1], "  - id: c\n    fail: x\n"),
                                         (4, "    fail: no\n\n# after", "    fail: x\n\n# after")])
def test_replace_step_keeps_its_header_and_the_next_one(i, old, new):
    ids = "abpcd"
    out = yaml_edit(HEADERS, lambda d: edit._replace_step(d, ["steps", i], {"id": ids[i], "fail": "x"}), "t")
    assert old in HEADERS and out == HEADERS.replace(old, new)


@pytest.mark.parametrize("path", example_files("scenarios/*.yaml"), ids=lambda p: p.stem)
def test_step_operations_on_the_examples_keep_the_data_and_every_comment(path):
    """Headers travel as text: wherever one lands, it must stay a comment (not a line of a `|` text above it)."""
    src = path.read_text()
    steps = load_yaml(src, "t")["steps"]

    def comments(text):
        return sorted(ln.strip() for ln in text.splitlines() if ln.strip().startswith("#"))
    for i in range(len(steps)):
        rest = steps[:i] + steps[i + 1:]
        out = yaml_edit(src, lambda d: edit._delete_step(d, ["steps", i]), "t")
        assert load_yaml(out, "t")["steps"] == rest
        for j in range(len(steps)):
            if j != i:
                out = yaml_edit(src, lambda d: edit._move_step(d, ["steps", i], ["steps", j]), "t")
                at = rest.index(steps[j]) + 1
                assert load_yaml(out, "t")["steps"] == rest[:at] + [steps[i]] + rest[at:], (i, j)
                assert comments(out) == comments(src), (i, j)
        out = yaml_edit(src, lambda d: edit._add_step(d, {"id": "added_here", "fail": "x"}, ["steps", i]), "t")
        assert load_yaml(out, "t")["steps"] == steps[:i + 1] + [{"id": "added_here", "fail": "x"}] + steps[i + 1:]
        assert comments(out) == comments(src)


def test_update_step_keeps_the_next_header_after_a_block_that_ends_in_a_flow_value():
    out = yaml_edit(HEADERS, lambda d: edit._update_step(d, ["steps", 2], {"retry": 2}), "t")
    assert out == HEADERS.replace(P, P + "    retry: 2\n")


def test_step_operations_keep_a_header_directly_below_a_block_text():
    """ruamel keeps the indentation of a comment right below a `|` or `>` text apart from the comment's text: the
    header of the next step used to be written back at column 0."""
    src = ("steps:\n  - id: a\n    ask:\n      agent: w\n      prompt: |\n        Hello\n  # about b\n  - id: b\n"
           "    parallel:\n      left:\n        - id: l\n          ask:\n            agent: w\n            prompt: >\n"
           "              Hi\n        # about m\n        - id: m\n          fail: no\n")
    out = yaml_edit(src, lambda d: edit._add_step(d, {"id": "n", "fail": "x"}), "t")
    assert out == src.replace("steps:\n", "steps:\n" + NEW)
    out = yaml_edit(src, lambda d: edit._update_step(d, ["steps", 0], {"retry": 2}), "t")
    assert out == src.replace("  # about b\n", "    retry: 2\n  # about b\n")
    out = yaml_edit(src, lambda d: edit._delete_step(d, ["steps", 1, "parallel", "left", 0]), "t")
    assert out == src.replace(src[src.index("        - id: l"):src.index("        # about m")], "")
    out = yaml_edit(src, lambda d: edit._add_step(d, {"id": "n", "fail": "x"}, ["steps", 1, "parallel", "left"]), "t")
    assert out == src.replace("      left:\n", "      left:\n        - id: n\n          fail: x\n")


def test_step_operations_keep_what_follows_a_list_whose_last_step_cannot_carry_it():
    for one in ("steps:\n  - id: a\n    fail: no\n" + END, "steps:\n  # the only\n  - id: a\n    fail: no\n" + END):
        assert yaml_edit(one, lambda d: edit._move_step(d, ["steps", 0], ["steps"]), "t") == one  # the list is empty meanwhile
    flow = "steps:\n  - { id: a, fail: no }\n  - id: b\n    fail: no\n" + END
    out = yaml_edit(flow, lambda d: edit._delete_step(d, ["steps", 1]), "t")  # a flow step is the last one now
    assert out == flow.replace("  - id: b\n    fail: no\n", "")


def test_comment_below_a_block_text_never_becomes_a_part_of_it():
    """A comment written at the column of a `|` text, or deeper, is read as its next line — of a prompt. What followed
    a list (here the comment that ends its last step, deeper than the steps) landed there after a step operation
    that left a `|` text as the last value of the list."""
    src = ("steps:\n  - id: p\n    parallel:\n      one:\n        - id: deep\n          ask:\n            agent: w\n"
           "            prompt: |\n              Deep\n        - id: k\n          fail: no\n"
           "  - id: a\n    ask:\n      agent: w\n      prompt: |\n        Hello\n"
           "  - id: b\n    ask:\n      agent: w\n      prompt: \"Check\"\n      schema:\n        answer: string\n"
           "        # details: string\n")
    text = {"id": "c", "ask": {"agent": "w", "prompt": "One\nTwo\n"}}
    for op in (lambda d: edit._delete_step(d, ["steps", 2]),
               lambda d: edit._move_step(d, ["steps", 2], ["steps"]),
               lambda d: edit._add_step(d, text, ["steps", 2]),
               lambda d: edit._replace_step(d, ["steps", 2], text),
               lambda d: edit._update_step(d, ["steps", 2], {"ask": {"schema": None, "prompt": "One\nTwo\n"}}),
               lambda d: edit._move_step(d, ["steps", 0, "parallel", "one", 0], ["steps", 2])):  # from a deeper list
        out = yaml_edit(src, op, "t")
        prompts = re.findall(r'"prompt": "(.*?)"', json.dumps(load_yaml(out, "t")))
        assert set(prompts) <= {"Deep\\n", "Hello\\n", "Check", "One\\nTwo\\n"}, out
        assert "      # details: string\n" in out, out  # kept, at the column of the key that holds the text
    # a file indented wider than the editor writes: the comment below the blank line kept the column of the wider text
    wide = ("steps:\n    - id: a\n      ask:\n          agent: w\n          prompt: |\n              Hello\n\n"
            "          # about b\n    - id: b\n      fail: no\n")
    out = yaml_edit(wide, lambda d: edit._update_step(d, ["steps", 1], {"retry": 2}), "t")
    assert load_yaml(out, "t")["steps"][0]["ask"]["prompt"] == "Hello\n" and "\n      # about b\n" in out, out


def test_step_header_below_a_block_text_never_becomes_a_part_of_it():
    """A step's header holds what followed the step above it — at that step's depth (the disabled last step of a
    parallel branch). Written as it was above another step, it became the last line of that step's `|` prompt:
    after deleting the step between them, adding or moving a step with a text there, or emptying a branch."""
    src = ("steps:\n  - id: a\n    ask:\n      agent: w\n      prompt: |\n        Hello\n"
           "  - id: p\n    parallel:\n      one:\n        - id: k\n          fail: |\n            Deep\n"
           "      two:\n        - id: m\n          set:\n            v: 1\n            # w: 2   (off)\n"
           "      three:\n        - id: n\n          fail: no\n          # - id: o   (off)\n"
           "  - id: z\n    fail: no\n")
    text = {"id": "c", "ask": {"agent": "w", "prompt": "One\nTwo"}}
    for op, kept in ((lambda d: edit._delete_step(d, ["steps", 1]), "      # - id: o   (off)\n"),
                     (lambda d: edit._add_step(d, text, ["steps", 1]), "      # - id: o   (off)\n"),
                     (lambda d: edit._move_step(d, ["steps", 0], ["steps", 1]), "      # - id: o   (off)\n"),
                     (lambda d: edit._delete_step(d, ["steps", 1, "parallel", "two", 0]), "          # w: 2   (off)\n"),
                     (lambda d: edit._move_step(d, ["steps", 1, "parallel", "two", 0], ["steps"]), "          # w: 2   (off)\n")):
        out = yaml_edit(src, op, "t")
        texts = re.findall(r'"(?:prompt|fail)": "(.*?)"', json.dumps(load_yaml(out, "t")))
        assert set(texts) <= {"Hello\\n", "Deep\\n", "One\\nTwo", "no"}, out
        assert "\n" + kept in out, out  # kept, at the column of the key that holds the text above it


def test_emptied_branch_leaves_its_tail_below_the_tail_of_a_flow_list():
    """The last step of a branch moves into a list of flow steps, which keeps its own tail at its end: the header of
    the step after the parallel used to be written above that tail — two untouched comments swapped."""
    src = ("steps:\n  - id: p\n    parallel:\n      one:\n        - {id: f, fail: no}\n      # between branches\n"
           "      two:\n        - {id: g, fail: no}\n  # about z\n  - id: z\n    fail: no\n")
    out = yaml_edit(src, lambda d: edit._move_step(d, ["steps", 0, "parallel", "two", 0], ["steps", 0, "parallel", "one", 0]), "t")
    assert out == src.replace("      # between branches\n      two:\n        - {id: g, fail: no}\n",
                              "        - {id: g, fail: no}\n      # between branches\n")


def test_set_config_new_alias_flow_style(proj):
    c = api.read_file(proj, "config.yaml")
    api.set_config(proj, c["etag"], {"models": {"gpt-image": {"id": "openai/gpt-image-2"}}})
    text = (proj / "workflows" / "config.yaml").read_text()
    line = next(ln for ln in text.splitlines() if ln.startswith("  gpt-image:"))
    assert line == "  gpt-image: {id: openai/gpt-image-2}"
    assert api.describe_project(proj)["models"]["gpt-image"] == "openai/gpt-image-2"
