"""The tool step (0.20.0): a direct MCP tool call without a model — offline: fake provider and fake MCP server
(tests/fake_mcp_server.py)."""
import json

import pytest
from conftest import events, run, scenario
from test_task import HEAD, errors, setup

from agencast import api
from agencast.engine import dry_run
from agencast.validate import mcp_servers_used, validate

DIRECT = "    direct: [structured, complex, read_text_file, write_file, broken, red_pixel, slow]\n"


def tool_sc(wf, tool, step="", head="", name="test", after=""):
    return scenario(wf, HEAD + head + f"""
steps:
  - id: s
    {step}
    tool: {tool}
{after}""", name)


def call_file(r, n=1):
    return json.loads((r.rec.dir / f"steps/01-s/calls/{n:02d}.tool.json").read_text())


# --- validate: the owner's `direct` list ------------------------------------------------------

@pytest.mark.parametrize("server, tool, msg", [
    (DIRECT, "{ server: nope, name: x }", "tool.server: MCP server 'nope' is not in workflows/mcp.yaml"),
    ("", "{ server: fs, name: structured }", "tool.name: the project owner has not allowed tool 'structured' of server "
                                             "'fs' for tool steps (mcp.yaml → servers.fs.direct: —)"),
    (DIRECT + "    scenarios: [other]\n", "{ server: fs, name: structured }",
     "scenario 'test' cannot call server 'fs' (mcp.yaml → servers.fs.scenarios: other)"),
    (DIRECT, "{ server: fs, name: structured, args: { domain: '{{ steps.nope.x }}' } }",
     "tool.args.domain: step 'nope' does not exist"),
    (DIRECT, "{ server: fs, name: structured, args: { '{{ inputs.k }}': 1 } }", "template {{ }} is not allowed here"),
])
def test_validate_permissions_and_templates(wf, server, tool, msg):
    setup(wf, server=server)
    got = errors(tool_sc(wf, tool))
    assert msg in got, got


def test_budget_usd_is_not_allowed(wf):
    setup(wf, server=DIRECT)
    assert "budget_usd" in errors(tool_sc(wf, "{ server: fs, name: structured }", step="budget_usd: 0.1"))


def test_server_only_for_tool_steps_needs_no_agents(wf):
    setup(wf, server=DIRECT)
    text = (wf / "mcp.yaml").read_text()
    (wf / "agents" / "tester.md").unlink()
    (wf / "mcp.yaml").write_text(text.replace("    agents: [tester]\n", ""))
    p = validate(tool_sc(wf, "{ server: fs, name: structured, args: { domain: x } }"), check_models=False)
    assert mcp_servers_used(p) == {"fs"}
    fs = api.describe_project(wf.parent)["mcp_servers"][0]
    assert fs["agents"] is None and fs["direct"] == ["structured", "complex", "read_text_file", "write_file", "broken",
                                                     "red_pixel", "slow"]
    (wf / "mcp.yaml").write_text(text.replace("    agents: [tester]\n", "").replace(DIRECT, ""))
    assert "missing required field 'agents'" in errors(tool_sc(wf, "{ server: fs, name: structured }"))


# --- run -----------------------------------------------------------------------------------

def test_structured_content_is_the_output_and_args_keep_their_types(wf):
    setup(wf, server=DIRECT)
    path = scenario(wf, HEAD + """
inputs: { d: { type: string, required: true } }
steps:
  - id: prep
    set: { tags: "['x', 'y']" }
  - id: s
    tool: { server: fs, name: structured, args: { domain: "{{ inputs.d }}", pages: 5, tags: "{{ steps.prep.tags }}" } }
""")
    r, fake = run(path, {"d": "a.cz"})
    assert r.status == "succeeded", r.error
    args = {"domain": "a.cz", "pages": 5, "tags": ["x", "y"]}
    assert r.values["steps"]["s"] == {"echo": args}
    assert fake.calls == []  # no model
    c = json.loads((r.rec.dir / "steps/02-s/calls/01.tool.json").read_text())
    assert c["arguments"] == args and c["structured"] == {"echo": args} and c["is_error"] is False
    assert c["files"] == ["steps/02-s/tool-01-1.mp3", "steps/02-s/tool-01-2.md"]
    assert (r.rec.dir / "steps/02-s/tool-01-2.md").read_text() == "# Report"
    assert c["skipped"] == ["[content of type resource_link is not forwarded by the framework]"]
    e = events(r, "tool_call")[0]
    assert "turn" not in e and e["server"] == "fs" and e["tool"] == "structured"
    assert events(r, "step_finished")[-1]["cost_usd"] == 0


def test_json_text(wf):
    setup(wf, server=DIRECT)
    r, _ = run(tool_sc(wf, "{ server: fs, name: complex, json: true, args: { tag: { label: a }, kind: post, level: 2 } }"))
    assert r.values["steps"]["s"] == {"tag": {"label": "a"}, "kind": "post", "level": 2}


def test_text_output_and_image_file(wf):
    setup(wf, server=DIRECT)
    r, _ = run(tool_sc(wf, "{ server: fs, name: red_pixel }"))
    assert r.values["steps"]["s"] == {"text": "Red image:"}
    assert call_file(r)["files"] == ["steps/01-s/tool-01-1.png"]
    assert events(r, "image_saved")[0]["path"] == "steps/01-s/tool-01-1.png"


@pytest.mark.parametrize("tool, cls, msg", [
    ("{ server: fs, name: broken }", "tool", "tool fs.broken returned an error: Error: tool is broken"),
    ("{ server: fs, name: red_pixel, json: true }", "tool", "tool fs.red_pixel (json: true) did not answer with one JSON object"),
    ("{ server: fs, name: structured, args: { pages: x } }", "config",
     "tool.args do not match the inputSchema of fs.structured: "),
    ("{ server: fs, name: slow, args: { seconds: 5 } }", "timeout", "tool fs.slow did not respond within 1 s"),
])
def test_failures(wf, tool, cls, msg):
    setup(wf, server=DIRECT)
    r, _ = run(tool_sc(wf, tool, step="retry: 2"))
    assert r.error["class"] == cls and r.error["message"].startswith(msg), r.error
    assert len(events(r, "tool_call")) == 1  # never repeated


def test_invalid_args_do_not_reach_the_tool(wf):
    setup(wf, server=DIRECT)
    r, _ = run(tool_sc(wf, "{ server: fs, name: write_file, args: { path: a.txt } }"))
    assert r.error["class"] == "config" and "root: missing required field 'content'" in r.error["message"]
    assert call_file(r)["invalid_args"] is True and not (r.rec.dir / "work/a.txt").exists()


def test_on_error_continue_uses_any_default(wf):
    setup(wf, server=DIRECT)
    r, _ = run(tool_sc(wf, "{ server: fs, name: broken }", step="on_error: continue\n    default: { score: 0 }",
                       after="  - id: next\n    set: { score: steps.s.score }\n"))
    assert r.status == "succeeded" and r.values["steps"]["next"] == {"score": 0}


def test_missing_output_field_is_an_expression_error(wf):
    setup(wf, server=DIRECT)
    r, _ = run(tool_sc(wf, "{ server: fs, name: red_pixel }", after="  - id: next\n    set: { x: steps.s.nope }\n"))
    assert r.error["class"] == "expression" and r.error["step"] == "next"


# --- fake runs and dedupe_key ------------------------------------------------------------------

def test_scripted_response_does_not_start_the_server(wf):
    setup(wf, server=DIRECT)
    r, _ = run(tool_sc(wf, "{ server: fs, name: structured, args: { domain: x } }"),
               script={"s": [{"result": {"overall_sov": 0.4}}]})
    assert r.values["steps"]["s"] == {"overall_sov": 0.4} and events(r, "mcp_server") == []
    r, _ = run(tool_sc(wf, "{ server: fs, name: broken }", name="err"), script={"s": {"text": "no", "is_error": True}})
    assert r.error == {"class": "tool", "step": "s", "message": "tool fs.broken returned an error: no"}


def test_dedupe_key_needs_a_scripted_response_in_a_fake_run(wf):
    setup(wf, server=DIRECT)
    path = tool_sc(wf, "{ server: fs, name: write_file, args: { path: a.txt, content: x } }", step='dedupe_key: "once"')
    r, _ = run(path)
    assert r.error["class"] == "config" and "needs a scripted response" in r.error["message"]
    assert events(r, "mcp_server") == [] and not list((wf.parent / "runs").glob("_dedupe*/*.json"))
    r1, _ = run(path, script={"s": {"text": "written"}})
    r2, _ = run(path, script={"s": {"text": "again"}})
    assert r1.values["steps"]["s"] == r2.values["steps"]["s"] == {"text": "written"}
    assert events(r2, "step_skipped")[0]["reason_code"] == "dedupe"


# --- dry run ---------------------------------------------------------------------------------

def test_dry_run_marks_missing_tool_and_fixed_args(wf):
    setup(wf, server="    direct: [structured, gone]\n")
    path = scenario(wf, HEAD + """
inputs: { d: { type: string, required: true } }
steps:
  - id: a
    tool: { server: fs, name: structured, args: { domain: "{{ inputs.d }}", pages: many } }
  - id: b
    tool: { server: fs, name: gone }
""")
    plan = (dry_run(validate(path, check_models=False), {}).dir / "plan.md").read_text()
    assert "| fs.structured; args do not match the inputSchema: pages: expected integer, got string |  |" in plan
    assert "| fs.gone (NOT OFFERED by the server) |  |" in plan
    assert "allowed but NOT OFFERED: gone" in plan
