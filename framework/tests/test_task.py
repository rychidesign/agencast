"""The task step, MCP servers, skills and dedupe_key (Phase 3a) — offline: fake provider
and fake MCP server (tests/fake_mcp_server.py)."""
import json
import os
import subprocess
import sys

import pytest
import yaml
from conftest import FAKE_MCP, events, model_ids, run, scenario

from agencast import ConfigErrors
from agencast.mcp_client import api_name, arg_errors, provider_schema
from agencast.task import system_prompt_task
from agencast.engine import system_prompt_ask
from agencast.validate import validate

ALL = "[read_text_file, write_file, broken, red_pixel, get_env, slow, complex]"
HEAD = "version: 1\nname: NAME\ndescription: Task step test\n"


def setup(wf, *, server="", agent_tools=ALL, agent_extra="", limits="max_turns: 5, budget_usd: 0.5",
          env=""):
    """Fake MCP server `fs` (root {run_dir}/work) and agent `tester`, which may use it."""
    (wf / "mcp.yaml").write_text(f"""version: 1
servers:
  fs:
    description: Fake server for tests
    command: {json.dumps(sys.executable)}
    args: [{json.dumps(str(FAKE_MCP))}, "{{run_dir}}/work"]
    agents: [tester]
    timeouts: {{ call: 1s }}
{server}{env}""")
    (wf / "agents" / "tester.md").write_text(f"""---
version: 1
name: tester
description: Test agent
model: smart
mcp: [fs]
tools: {{ fs: {agent_tools} }}
limits: {{ {limits} }}
{agent_extra}---
You are a test agent.
""")


def task_sc(wf, task="", step="", name="test"):
    return scenario(wf, HEAD + f"""
steps:
  - id: t
    {step}
    task: {{ agent: tester, prompt: "Complete the task" {task} }}
""", name)


def calls(*tools):
    return {"tool_calls": [{"name": n, "arguments": a} for n, a in tools]}


def children() -> list[str]:
    """Descendants of this process (except ps) — no MCP server may remain after the run."""
    out = subprocess.run(["ps", "-e", "-o", "pid=,ppid=,args="], capture_output=True, text=True).stdout
    rows = [line.split(None, 2) for line in out.splitlines() if line.strip()]
    kids, frontier = [], {str(os.getpid())}
    while frontier:
        new = [r for r in rows if r[1] in frontier]
        kids += [r[2] for r in new if not r[2].startswith("ps ")]
        frontier = {r[0] for r in new}
    return kids


def errors(path) -> str:
    with pytest.raises(ConfigErrors) as e:
        validate(path, check_models=False)
    return "\n".join(e.value.errors)


# --- permissions: owner → agent → step (validate) ---------------------------------------

@pytest.mark.parametrize("kw, task, msg", [
    ({"server": "    tools: [read_text_file]\n"}, "", "tools write_file, broken"),        # agent > owner
    ({"agent_tools": "[read_text_file]", "server": "    scenarios: [other]\n"}, "", "cannot run an agent with server 'fs'"),
    ({}, ", mcp: [other]", "server 'other' is not allowed by agent 'tester'"),                         # step expands server access
    ({"agent_tools": "[read_text_file]"}, ", tools: { fs: [write_file] }", "requests tool fs.write_file"),
    ({}, ", max_turns: 9", "exceeds limits.max_turns"),
])
def test_permissions_only_narrow(wf, kw, task, msg):
    setup(wf, **kw)
    got = errors(task_sc(wf, task))
    assert msg in got, got


def test_agent_without_tools_list_and_without_max_turns(wf):
    setup(wf, limits="budget_usd: 0.5")  # agent with mcp without max_turns: agent schema
    assert "max_turns" in errors(task_sc(wf))
    (wf / "agents" / "tester.md").write_text((wf / "agents" / "tester.md").read_text()
                                             .replace("tools: { fs: " + ALL + " }\n", ""))
    got = errors(task_sc(wf))  # server in agent without tools list = config; message names the server (BUGS 9)
    assert "tools: { fs: [tool, …] }" in got and "--dry-run" in got, got


def test_owner_decides_which_agents(wf):
    setup(wf)
    (wf / "mcp.yaml").write_text((wf / "mcp.yaml").read_text().replace("agents: [tester]", "agents: [publisher]"))
    assert "the project owner has not allowed server 'fs' for agent 'tester'" in errors(task_sc(wf))
    (wf / "mcp.yaml").unlink()
    assert "MCP server 'fs' is not in workflows/mcp.yaml" in errors(task_sc(wf))


def test_mcp_yaml_checks(wf):
    setup(wf, env="    env: { KEY: OPENROUTER_API_KEY }\n")
    assert "OPENROUTER_API_KEY is already used in config.yaml" in errors(task_sc(wf))  # the OpenRouter key would be sent to the server
    setup(wf)
    (wf / "mcp.yaml").write_text((wf / "mcp.yaml").read_text().replace("{run_dir}/work", "{home}/work"))
    assert "{home} — the only allowed substitution is {run_dir}" in errors(task_sc(wf))


def test_tool_name_collision_after_normalization(wf):
    setup(wf, agent_tools='["a.b", "a_b"]')
    assert "have the same normalized name fs__a_b" in errors(task_sc(wf))


def test_model_without_tools_is_config(wf):
    from agencast.validate import check_models_list
    cfg = {"models": {"smart": {"id": "x/y"}}}
    got = check_models_list(cfg, {"smart": {"tools"}}, [{"id": "x/y", "output_modalities": ["text"],
                                                         "supported_parameters": ["response_format"]}])
    assert "does not support tools" in got[0]


# --- schema normalization (fixtures from spike (d): $ref, const, numeric enum) -----------------

def test_provider_schema_normalization():
    s = {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object",
         "$defs": {"Tag": {"type": "object", "properties": {"label": {"type": "string"}}, "required": ["label"]}},
         "properties": {"tag": {"$ref": "#/$defs/Tag"}, "kind": {"const": "post"},
                        "level": {"type": "integer", "enum": [1, 2, 3], "default": 2},
                        "value": {"oneOf": [{"type": "string", "maxLength": 20}, {"type": "integer"}]},
                        "meta": {"allOf": [{"type": "object", "properties": {"a": {"type": "string"}}}]}},
         "required": ["tag", "kind", "level"]}
    n = provider_schema(s)
    assert "$schema" not in n and "$defs" not in n
    assert n["properties"]["tag"] == {"type": "object", "properties": {"label": {"type": "string"}}, "required": ["label"]}
    assert n["properties"]["kind"] == {"enum": ["post"]}
    assert "enum" not in n["properties"]["level"] and "Allowed values: 1, 2, 3." in n["properties"]["level"]["description"]
    assert "anyOf" in n["properties"]["value"] and "oneOf" not in n["properties"]["value"]
    assert n["properties"]["meta"] == {"type": "object", "properties": {"a": {"type": "string"}}}
    assert provider_schema({"type": "object"}) == {"type": "object", "properties": {}}
    with pytest.raises(ValueError, match="recursive"):
        provider_schema({"$defs": {"N": {"properties": {"n": {"$ref": "#/$defs/N"}}}}, "properties": {"x": {"$ref": "#/$defs/N"}}})
    with pytest.raises(ValueError, match="unsupported"):
        provider_schema({"properties": {"x": {"$ref": "https://example.com/s.json"}}})
    # arguments are validated against the ORIGINAL schema (Gemini ignores parts of the simplified one)
    assert arg_errors(s, {"tag": {"label": "x"}, "kind": "post", "level": 2}) == []
    assert any("level" in e for e in arg_errors(s, {"tag": {"label": "x"}, "kind": "post", "level": 5}))
    assert any("kind" in e for e in arg_errors(s, {"tag": {"label": "x"}, "kind": "other", "level": 1}))


def test_api_name():
    assert api_name("fs", "list.directory") == "fs__list_directory"
    assert len(api_name("fs", "x" * 70)) == 64


# --- model ↔ tools loop ----------------------------------------------------------------

def test_task_loop_record_and_messages(wf):
    setup(wf)
    script = {"t": [calls(("fs__write_file", {"path": "a.txt", "content": "hello"}),
                          ("fs__broken", {}),
                          ("fs__red_pixel", {})),
                    calls(("fs__delete_everything", {}),                       # disallowed tool
                          ("fs__write_file", {"path": "b.txt"}),               # missing content → invalid_args
                          ("fs__complex", {"tag": {"label": "x"}, "kind": "post", "level": 7})),
                    {"text": "Done."}]}
    r, fake = run(task_sc(wf), script=script)
    assert r.status == "succeeded", r.error
    assert r.values["steps"]["t"] == {"text": "Done."}
    d = r.rec.dir
    assert (d / "work" / "a.txt").read_text() == "hello" and not (d / "work" / "b.txt").exists()
    tc = events(r, "tool_call")
    assert [(e["tool"], e["allowed"], e["invalid_args"], e["is_error"]) for e in tc] == [
        ("write_file", True, False, False), ("broken", True, False, True), ("red_pixel", True, False, False),
        ("delete_everything", False, False, False), ("write_file", True, True, False), ("complex", True, True, False)]
    assert [e["turn"] for e in events(r, "model_call")] == [1, 2, 3]
    # requests sent to the model
    bodies = [b for s, _, b in fake.calls if s == "t"]
    assert [t["function"]["name"] for t in bodies[0]["tools"]] == [
        "fs__read_text_file", "fs__write_file", "fs__broken", "fs__red_pixel", "fs__get_env", "fs__slow", "fs__complex"]
    second = bodies[1]["messages"]
    assistant = next(m for m in second if m["role"] == "assistant")
    assert assistant["reasoning_details"] and len(assistant["tool_calls"]) == 3   # reasoning_details returned unchanged
    tools_msgs = [m for m in second if m["role"] == "tool"]
    assert tools_msgs[1]["content"].startswith("Tool error:")                  # isError → model
    assert "image in the next message: tool-04-1.png" in tools_msgs[2]["content"]
    assert second[-1]["role"] == "user" and second[-1]["content"][1]["image_url"]["url"].startswith("data:image/png")
    third = [m for m in bodies[2]["messages"] if m["role"] == "tool"]
    assert "is not allowed" in third[-3]["content"] and "did not match the tool schema" in third[-2]["content"]
    # record: image as a file, no base64 in request.json
    assert (d / "steps/01-t/tool-04-1.png").read_bytes()[:4] == b"\x89PNG"
    assert events(r, "image_saved")[0]["path"] == "steps/01-t/tool-04-1.png"
    req = (d / "steps/01-t/calls/05.request.json").read_text()
    assert "<file: steps/01-t/tool-04-1.png" in req and "base64," not in req
    tool = json.loads((d / "steps/01-t/calls/02.tool.json").read_text())
    assert tool["arguments"] == {"path": "a.txt", "content": "hello"} and tool["result"].startswith("Successfully")
    assert "stderr" not in (d / "mcp/fs.stderr.log").read_text() and "fake-mcp" in (d / "mcp/fs.stderr.log").read_text()
    assert [e["action"] for e in events(r, "mcp_server")] == ["started", "stopped"]
    assert children() == []


def test_max_turns_is_budget_and_retry_not_counted(wf):
    setup(wf)
    loop = calls(("fs__read_text_file", {"path": "x"}))
    r, _ = run(task_sc(wf, ", max_turns: 2"), script={"t": [loop, {"status": 503}, loop, loop]})
    assert r.error["class"] == "budget" and "max_turns 2" in r.error["message"]
    assert [e["turn"] for e in events(r, "model_call")] == [1, 2, 2]              # retry after 503 = same turn
    assert len(events(r, "tool_call")) == 1                                        # last turn does not execute tools


def test_schema_always_tool_wrapper_and_cascade_to_prompt(wf):
    """BUGS 7 / ISSUES 36: task with schema starts at tool_wrapper even for a native_schema alias (smart)."""
    setup(wf)
    assert "structured_output" not in yaml.safe_load((wf / "config.yaml").read_text())["models"]["smart"]
    r, fake = run(task_sc(wf, ", schema: { count: integer }"),
                  script={"t": [calls(("fs__read_text_file", {"path": "x"})), {"text": "not JSON"}, {}]})
    assert r.status == "succeeded", r.error
    mc = events(r, "model_call")
    assert [(e["turn"], e["structured_output"]) for e in mc] == [(1, "tool_wrapper"), (2, "tool_wrapper"),
                                                                  (2, "prompt")]
    first = fake.calls[0][2]
    assert "response_format" not in first and "tool_choice" not in first
    assert "_submit_output" in [t["function"]["name"] for t in first["tools"]]
    assert r.values["steps"]["t"] == {"count": 1}
    assert all(e["tool"] != "_submit_output" for e in events(r, "tool_call"))  # never sent to dispatch
    assert "(prompt)" in r.rows["t"]["note"]


def test_tool_timeout_is_timeout_class(wf):
    setup(wf)
    r, _ = run(task_sc(wf), script={"t": [calls(("fs__slow", {"seconds": 3}))]})
    assert r.error["class"] == "timeout" and "may have run" in r.error["message"]
    assert children() == []


def test_secret_from_tool_is_masked(wf, monkeypatch):
    monkeypatch.setenv("AGENCAST_TEST_MCP_SECRET", "very-secret-value-42")
    setup(wf, env="    env: { SERVER_SECRET: AGENCAST_TEST_MCP_SECRET }\n")
    r, fake = run(task_sc(wf), script={"t": [calls(("fs__get_env", {"name": "SERVER_SECRET"})), {"text": "ok"}]})
    assert r.status == "succeeded", r.error
    assert "very-secret-value-42" in json.dumps(fake.calls[-1][2])  # the model received the value (returned by the server)
    for f in r.rec.dir.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".jsonl", ".md", ".log"):
            assert "very-secret-value-42" not in f.read_text(), f
    assert "<secret: AGENCAST_TEST_MCP_SECRET>" in (r.rec.dir / "steps/01-t/calls/02.tool.json").read_text()


def test_missing_server_env_is_config_before_run(wf, monkeypatch):
    monkeypatch.delenv("AGENCAST_TEST_NOPE", raising=False)
    setup(wf, env="    env: { X: AGENCAST_TEST_NOPE }\n")
    with pytest.raises(ConfigErrors, match="missing environment variable AGENCAST_TEST_NOPE"):
        run(task_sc(wf))


def test_server_start_failure_is_config(wf):
    setup(wf)
    (wf / "mcp.yaml").write_text((wf / "mcp.yaml").read_text().replace(json.dumps(sys.executable), "nonexistent-agencast"))
    r, _ = run(task_sc(wf))
    assert r.error["class"] == "config" and "failed to start" in r.error["message"]
    assert events(r, "mcp_server")[0]["action"] == "failed"


def test_parallel_branches_share_one_server(wf):
    setup(wf)
    path = scenario(wf, HEAD + """
steps:
  - id: p
    parallel:
      a:
        - id: t1
          task: { agent: tester, prompt: "A" }
      b:
        - id: t2
          task: { agent: tester, prompt: "B" }
""")
    one = calls(("fs__read_text_file", {"path": "missing"}))
    r, _ = run(path, script={"t1": [one, {"text": "a"}], "t2": [one, {"text": "b"}]})
    assert r.status == "succeeded", r.error
    assert [e["action"] for e in events(r, "mcp_server")] == ["started", "stopped"]
    assert len(events(r, "tool_call")) == 2 and children() == []


# --- skills ---------------------------------------------------------------------------------

def test_skills_task_list_and_load_skill(wf):
    setup(wf, agent_extra="skills: [lumen-voice]\n")
    r, fake = run(task_sc(wf), script={"t": [calls(("load_skill", {"name": "lumen-voice"})),
                                             calls(("load_skill", {"name": "missing"})), {"text": "ok"}]})
    assert r.status == "succeeded", r.error
    first = fake.calls[0][2]
    system = first["messages"][0]["content"]
    assert "## Skills\n\n- lumen-voice: Lumen brand tone and vocabulary" in system and "We talk to the reader directly" not in system
    skill = next(t for t in first["tools"] if t["function"]["name"] == "load_skill")
    assert skill["function"]["parameters"]["properties"]["name"]["enum"] == ["lumen-voice"]
    tc = events(r, "tool_call")
    assert [(e["server"], e["tool"], e["invalid_args"]) for e in tc] == [("_skills", "load_skill", False),
                                                                        ("_skills", "load_skill", True)]
    assert [e["turn"] for e in events(r, "model_call")] == [1, 2, 3]                # load_skill is a turn
    msgs = fake.calls[2][2]["messages"]
    tool_msgs = [m["content"] for m in msgs if m["role"] == "tool"]
    assert "We talk to the reader directly" in tool_msgs[0] and '"lumen-voice"' in tool_msgs[1]  # error with the skills list


def test_skills_ask_inlines_whole_body(wf):
    from agencast.validate import load_agent, load_config
    errs = []
    agent = load_agent(wf, "copywriter", load_config(wf, errs), errs)
    ask = system_prompt_ask(agent)
    assert "## Skill: lumen-voice\n\n- We talk to the reader directly" in ask
    assert system_prompt_task(agent).endswith("## Skills\n\n- lumen-voice: Lumen brand tone and vocabulary for social media copy")


# --- dedupe_key -----------------------------------------------------------------------------

def test_dedupe_two_runs(wf):
    setup(wf)
    path = task_sc(wf, step='dedupe_key: "post-{{ inputs.id }}"')
    path.write_text(path.read_text().replace("steps:", "inputs: { id: { type: string, required: true } }\nsteps:"))
    script = {"t": [calls(("fs__write_file", {"path": "a.txt", "content": "x"})), {"text": "published"}]}
    r1, _ = run(path, {"id": "42"}, script)
    assert r1.status == "succeeded", r1.error
    files = list((wf.parent / "runs" / "_dedupe-fake").glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text()) == {"state": "succeeded", "run_id": r1.run_id,
                                                "output": {"text": "published"}}
    r2, fake2 = run(path, {"id": "42"}, script)
    assert r2.status == "succeeded" and r2.values["steps"]["t"] == {"text": "published"}
    skip = events(r2, "step_skipped")[0]
    assert skip["reason_code"] == "dedupe" and r1.run_id in skip["reason"]
    assert fake2.calls == [] and events(r2, "mcp_server") == []                   # no calls made
    r3, _ = run(path, {"id": "43"}, script)                                        # different key = new file
    assert r3.status == "succeeded" and len(list(files[0].parent.glob("*.json"))) == 2


def test_dedupe_started_without_succeeded_is_config(wf):
    setup(wf)
    path = task_sc(wf, step='dedupe_key: "once"')
    r1, _ = run(path, script={"t": [calls(("fs__write_file", {"path": "a.txt", "content": "x"})), {"status": 400}]})
    assert r1.error["class"] == "config"
    f = next((wf.parent / "runs" / "_dedupe-fake").glob("*.json"))
    assert json.loads(f.read_text())["state"] == "started"
    r2, fake2 = run(path, script={"t": [{"text": "ok"}]})
    assert r2.error["class"] == "config" and "check manually and delete" in r2.error["message"] and str(f) in r2.error["message"]
    assert fake2.calls == []
    # the same key in another scenario means a different file
    other = task_sc(wf, step='dedupe_key: "once"', name="other")
    r3, _ = run(other, script={"t": [{"text": "ok"}]})
    assert r3.status == "succeeded", r3.error


def test_dedupe_fake_and_live_do_not_share_state(wf, monkeypatch):
    """BUGS 8: fake run output must not skip a real step (or vice versa) — separate _dedupe*/."""
    from agencast import engine
    from agencast.engine import run_scenario
    from agencast.fake import Fake
    from agencast.providers import Client
    setup(wf)
    path = task_sc(wf, step='dedupe_key: "once"')

    def live(text):  # real run (without fake), network replaced by a fake transport
        fake = Fake({"t": [{"text": text}]}, model_ids(wf))
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        monkeypatch.setattr(engine, "Client", lambda url, key, _t: Client(url, key, fake.transport()))
        return run_scenario(validate(path, transport=fake.transport()), {})

    r1, _ = run(path, script={"t": [{"text": "fake"}]})
    assert r1.fake and events(r1, "run_started")[0]["fake"] is True
    assert "**Fake run**" in (r1.rec.dir / "summary.md").read_text()
    r2 = live("real")
    assert r2.status == "succeeded" and r2.values["steps"]["t"] == {"text": "real"}, r2.error
    assert events(r2, "step_skipped") == [] and events(r2, "run_started")[0]["fake"] is False
    assert "Fake run" not in (r2.rec.dir / "summary.md").read_text()
    r3, _ = run(path, script={"t": [{"text": "fake 2"}]})                       # fake does not read the real _dedupe
    assert r3.values["steps"]["t"] == {"text": "fake"}                          # skipped using its own record, not the real one
    runs = wf.parent / "runs"
    assert len(list((runs / "_dedupe").glob("*.json"))) == len(list((runs / "_dedupe-fake").glob("*.json"))) == 1


def test_dedupe_without_tool_call_writes_only_succeeded(wf):
    setup(wf)
    r, _ = run(task_sc(wf, step='dedupe_key: "k"'), script={"t": [{"text": "without tools"}]})
    assert r.status == "succeeded"
    f = next((wf.parent / "runs" / "_dedupe-fake").glob("*.json"))
    assert json.loads(f.read_text())["state"] == "succeeded"


# --- after merging with 3b: --dry-run and task inside call ------------------------------------------

def test_dry_run_lists_server_tools(wf):
    from agencast.engine import dry_run
    setup(wf, agent_tools="[read_text_file, write_file]")
    p = validate(task_sc(wf, ", tools: { fs: [read_text_file] }", step='dedupe_key: "k"'), check_models=False)
    rec = dry_run(p, {})
    assert sorted(f.name for f in rec.dir.iterdir()) == ["inputs.json", "plan.md"]  # server ran in a temporary directory
    plan = (rec.dir / "plan.md").read_text()
    assert "agent tester → smart" in plan and "tools: fs: read_text_file;" in plan and "dedupe_key" in plan
    assert "- **fs** (Fake server for tests): offers broken, complex, get_env," in plan
    assert children() == []


def test_task_with_dedupe_inside_call(wf):
    setup(wf)
    scenario(wf, """
version: 1
name: child
description: Called scenario with a task step
callable: true
outputs: { text: { type: string } }
steps:
  - id: t
    dedupe_key: "once"
    task: { agent: tester, prompt: "Complete the task" }
  - id: out
    output: { text: "{{ steps.t.text }}" }
""", "child")
    path = scenario(wf, HEAD + """
outputs: { result: { type: string } }
steps:
  - id: draft
    call: { scenario: child }
  - id: out
    output: { result: "{{ steps.draft.text }}" }
""")
    script = {"draft/t": [calls(("fs__write_file", {"path": "a.txt", "content": "x"})), {"text": "done"}]}
    r1, _ = run(path, script=script)
    assert r1.status == "succeeded", r1.error
    assert r1.outputs == {"result": "done"}
    assert (r1.rec.dir / "work" / "a.txt").is_file() and events(r1, "tool_call")[0]["step"] == "draft/t"
    r2, fake2 = run(path, script=script)
    assert r2.status == "succeeded" and r2.outputs == {"result": "done"}
    assert events(r2, "step_skipped")[0]["reason_code"] == "dedupe" and fake2.calls == []
    assert children() == []
