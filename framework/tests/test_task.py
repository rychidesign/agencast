"""Krok task, MCP servery, skilly a dedupe_key (Fáze 3a) — bez sítě: falešný poskytovatel
a falešný MCP server (tests/fake_mcp_server.py)."""
import json
import os
import subprocess
import sys

import pytest
from conftest import FAKE_MCP, events, run, scenario

from maw import ConfigErrors
from maw.mcp_client import api_name, arg_errors, provider_schema
from maw.task import system_prompt_task
from maw.engine import system_prompt_ask
from maw.validate import validate

ALL = "[read_text_file, write_file, broken, red_pixel, get_env, slow, complex]"
HEAD = "version: 1\nname: NAME\ndescription: Test kroku task\n"


def setup(wf, *, server="", agent_tools=ALL, agent_extra="", limits="max_turns: 5, budget_usd: 0.5",
          env=""):
    """Falešný MCP server `fs` (kořen {run_dir}/work) a agent `tester`, který ho smí použít."""
    (wf / "mcp.yaml").write_text(f"""version: 1
servers:
  fs:
    description: Falešný server pro testy
    command: {json.dumps(sys.executable)}
    args: [{json.dumps(str(FAKE_MCP))}, "{{run_dir}}/work"]
    agents: [tester]
    timeouts: {{ call: 1s }}
{server}{env}""")
    (wf / "agents" / "tester.md").write_text(f"""---
version: 1
name: tester
description: Testovací agent
model: chytry
mcp: [fs]
tools: {{ fs: {agent_tools} }}
limits: {{ {limits} }}
{agent_extra}---
Jsi testovací agent.
""")


def task_sc(wf, task="", step="", name="test"):
    return scenario(wf, HEAD + f"""
steps:
  - id: t
    {step}
    task: {{ agent: tester, prompt: "Udělej úkol" {task} }}
""", name)


def calls(*tools):
    return {"tool_calls": [{"name": n, "arguments": a} for n, a in tools]}


def children() -> list[str]:
    """Potomci tohoto procesu (kromě ps) — po běhu nesmí zbýt žádný MCP server."""
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


# --- oprávnění: vlastník → agent → krok (validate) ---------------------------------------

@pytest.mark.parametrize("kw, task, msg", [
    ({"server": "    tools: [read_text_file]\n"}, "", "nástroje write_file, broken"),        # agent > vlastník
    ({"agent_tools": "[read_text_file]", "server": "    scenarios: [jiny]\n"}, "", "nesmí spustit agenta se serverem 'fs'"),
    ({}, ", mcp: [jiny]", "server 'jiny' agent 'tester' nepovoluje"),                         # krok rozšiřuje server
    ({"agent_tools": "[read_text_file]"}, ", tools: { fs: [write_file] }", "chce nástroj fs.write_file"),
    ({}, ", max_turns: 9", "víc než limits.max_turns"),
])
def test_permissions_only_narrow(wf, kw, task, msg):
    setup(wf, **kw)
    got = errors(task_sc(wf, task))
    assert msg in got, got


def test_agent_without_tools_list_and_without_max_turns(wf):
    setup(wf, limits="budget_usd: 0.5")  # agent s mcp bez max_turns: schéma agenta
    assert "max_turns" in errors(task_sc(wf))
    (wf / "agents" / "tester.md").write_text((wf / "agents" / "tester.md").read_text()
                                             .replace("tools: { fs: " + ALL + " }\n", ""))
    assert "tools" in errors(task_sc(wf))  # server v agentovi bez seznamu tools = config


def test_owner_decides_which_agents(wf):
    setup(wf)
    (wf / "mcp.yaml").write_text((wf / "mcp.yaml").read_text().replace("agents: [tester]", "agents: [publisher]"))
    assert "server 'fs' agentovi 'tester' vlastník nepovolil" in errors(task_sc(wf))
    (wf / "mcp.yaml").unlink()
    assert "MCP server 'fs' není v workflows/mcp.yaml" in errors(task_sc(wf))


def test_mcp_yaml_checks(wf):
    setup(wf, env="    env: { KLIC: OPENROUTER_API_KEY }\n")
    assert "OPENROUTER_API_KEY je už v config.yaml" in errors(task_sc(wf))  # klíč OpenRouteru by odešel serveru
    setup(wf)
    (wf / "mcp.yaml").write_text((wf / "mcp.yaml").read_text().replace("{run_dir}/work", "{home}/work"))
    assert "{home} — jediná povolená náhrada je {run_dir}" in errors(task_sc(wf))


def test_tool_name_collision_after_normalization(wf):
    setup(wf, agent_tools='["a.b", "a_b"]')
    assert "mají po normalizaci stejné jméno fs__a_b" in errors(task_sc(wf))


def test_model_without_tools_is_config(wf):
    from maw.validate import check_models_list
    cfg = {"models": {"chytry": {"id": "x/y"}}}
    got = check_models_list(cfg, {"chytry": {"tools"}}, [{"id": "x/y", "output_modalities": ["text"],
                                                         "supported_parameters": ["response_format"]}])
    assert "neumí tools" in got[0]


# --- normalizace schémat (fixtury ze spiku (d): $ref, const, číselný enum) -----------------

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
    assert "enum" not in n["properties"]["level"] and "Povolené hodnoty: 1, 2, 3." in n["properties"]["level"]["description"]
    assert "anyOf" in n["properties"]["value"] and "oneOf" not in n["properties"]["value"]
    assert n["properties"]["meta"] == {"type": "object", "properties": {"a": {"type": "string"}}}
    assert provider_schema({"type": "object"}) == {"type": "object", "properties": {}}
    with pytest.raises(ValueError, match="rekurzivní"):
        provider_schema({"$defs": {"N": {"properties": {"n": {"$ref": "#/$defs/N"}}}}, "properties": {"x": {"$ref": "#/$defs/N"}}})
    with pytest.raises(ValueError, match="nepodporovaný"):
        provider_schema({"properties": {"x": {"$ref": "https://example.com/s.json"}}})
    # argumenty se validují proti PŮVODNÍMU schématu (Gemini části zjednodušeného ignoruje)
    assert arg_errors(s, {"tag": {"label": "x"}, "kind": "post", "level": 2}) == []
    assert any("level" in e for e in arg_errors(s, {"tag": {"label": "x"}, "kind": "post", "level": 5}))
    assert any("kind" in e for e in arg_errors(s, {"tag": {"label": "x"}, "kind": "jiné", "level": 1}))


def test_api_name():
    assert api_name("fs", "list.directory") == "fs__list_directory"
    assert len(api_name("fs", "x" * 70)) == 64


# --- smyčka model ↔ nástroje ----------------------------------------------------------------

def test_task_loop_record_and_messages(wf):
    setup(wf)
    script = {"t": [calls(("fs__write_file", {"path": "a.txt", "content": "ahoj"}),
                          ("fs__broken", {}),
                          ("fs__red_pixel", {})),
                    calls(("fs__delete_everything", {}),                       # nepovolený nástroj
                          ("fs__write_file", {"path": "b.txt"}),               # chybí content → invalid_args
                          ("fs__complex", {"tag": {"label": "x"}, "kind": "post", "level": 7})),
                    {"text": "Hotovo."}]}
    r, fake = run(task_sc(wf), script=script)
    assert r.status == "succeeded", r.error
    assert r.values["steps"]["t"] == {"text": "Hotovo."}
    d = r.rec.dir
    assert (d / "work" / "a.txt").read_text() == "ahoj" and not (d / "work" / "b.txt").exists()
    tc = events(r, "tool_call")
    assert [(e["tool"], e["allowed"], e["invalid_args"], e["is_error"]) for e in tc] == [
        ("write_file", True, False, False), ("broken", True, False, True), ("red_pixel", True, False, False),
        ("delete_everything", False, False, False), ("write_file", True, True, False), ("complex", True, True, False)]
    assert [e["turn"] for e in events(r, "model_call")] == [1, 2, 3]
    # požadavky poslané modelu
    bodies = [b for s, _, b in fake.calls if s == "t"]
    assert [t["function"]["name"] for t in bodies[0]["tools"]] == [
        "fs__read_text_file", "fs__write_file", "fs__broken", "fs__red_pixel", "fs__get_env", "fs__slow", "fs__complex"]
    second = bodies[1]["messages"]
    assistant = next(m for m in second if m["role"] == "assistant")
    assert assistant["reasoning_details"] and len(assistant["tool_calls"]) == 3   # reasoning_details zpět beze změny
    tools_msgs = [m for m in second if m["role"] == "tool"]
    assert tools_msgs[1]["content"].startswith("Chyba nástroje:")                  # isError → modelu
    assert "obrázek v další zprávě: tool-04-1.png" in tools_msgs[2]["content"]
    assert second[-1]["role"] == "user" and second[-1]["content"][1]["image_url"]["url"].startswith("data:image/png")
    third = [m for m in bodies[2]["messages"] if m["role"] == "tool"]
    assert "není povolen" in third[-3]["content"] and "neprošly schématem" in third[-2]["content"]
    # záznam: obrázek jako soubor, v request.json bez base64
    assert (d / "steps/01-t/tool-04-1.png").read_bytes()[:4] == b"\x89PNG"
    assert events(r, "image_saved")[0]["path"] == "steps/01-t/tool-04-1.png"
    req = (d / "steps/01-t/calls/05.request.json").read_text()
    assert "<soubor: steps/01-t/tool-04-1.png" in req and "base64," not in req
    tool = json.loads((d / "steps/01-t/calls/02.tool.json").read_text())
    assert tool["arguments"] == {"path": "a.txt", "content": "ahoj"} and tool["result"].startswith("Successfully")
    assert "stderr" not in (d / "mcp/fs.stderr.log").read_text() and "fake-mcp" in (d / "mcp/fs.stderr.log").read_text()
    assert [e["action"] for e in events(r, "mcp_server")] == ["started", "stopped"]
    assert children() == []


def test_max_turns_is_budget_and_retry_not_counted(wf):
    setup(wf)
    loop = calls(("fs__read_text_file", {"path": "x"}))
    r, _ = run(task_sc(wf, ", max_turns: 2"), script={"t": [loop, {"status": 503}, loop, loop]})
    assert r.error["class"] == "budget" and "max_turns 2" in r.error["message"]
    assert [e["turn"] for e in events(r, "model_call")] == [1, 2, 2]              # opakování po 503 = stejný tah
    assert len(events(r, "tool_call")) == 1                                        # poslední tah nástroje nespustí


def test_schema_native_and_cascade_to_tool_wrapper(wf):
    setup(wf)
    r, fake = run(task_sc(wf, ", schema: { pocet: integer }"),
                  script={"t": [calls(("fs__read_text_file", {"path": "x"})), {"text": "nejde o JSON"}, {}]})
    assert r.status == "succeeded", r.error
    mc = events(r, "model_call")
    assert [(e["turn"], e["structured_output"]) for e in mc] == [(1, "native_schema"), (2, "native_schema"),
                                                                  (2, "tool_wrapper")]
    last = fake.calls[-1][2]
    assert "_submit_output" in [t["function"]["name"] for t in last["tools"]] and "tool_choice" not in last
    assert r.values["steps"]["t"] == {"pocet": 1}
    assert all(e["tool"] != "_submit_output" for e in events(r, "tool_call"))  # nikdy do dispatch


def test_tool_timeout_is_timeout_class(wf):
    setup(wf)
    r, _ = run(task_sc(wf), script={"t": [calls(("fs__slow", {"seconds": 3}))]})
    assert r.error["class"] == "timeout" and "mohl proběhnout" in r.error["message"]
    assert children() == []


def test_secret_from_tool_is_masked(wf, monkeypatch):
    monkeypatch.setenv("MAW_TEST_MCP_SECRET", "velmi-tajna-hodnota-42")
    setup(wf, env="    env: { PRO_SERVER: MAW_TEST_MCP_SECRET }\n")
    r, fake = run(task_sc(wf), script={"t": [calls(("fs__get_env", {"name": "PRO_SERVER"})), {"text": "ok"}]})
    assert r.status == "succeeded", r.error
    assert "velmi-tajna-hodnota-42" in json.dumps(fake.calls[-1][2])  # model hodnotu dostal (server ji vrátil)
    for f in r.rec.dir.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".jsonl", ".md", ".log"):
            assert "velmi-tajna-hodnota-42" not in f.read_text(), f
    assert "<tajné: MAW_TEST_MCP_SECRET>" in (r.rec.dir / "steps/01-t/calls/02.tool.json").read_text()


def test_missing_server_env_is_config_before_run(wf, monkeypatch):
    monkeypatch.delenv("MAW_TEST_NOPE", raising=False)
    setup(wf, env="    env: { X: MAW_TEST_NOPE }\n")
    with pytest.raises(ConfigErrors, match="chybí proměnná prostředí MAW_TEST_NOPE"):
        run(task_sc(wf))


def test_server_start_failure_is_config(wf):
    setup(wf)
    (wf / "mcp.yaml").write_text((wf / "mcp.yaml").read_text().replace(json.dumps(sys.executable), "neexistuje-maw"))
    r, _ = run(task_sc(wf))
    assert r.error["class"] == "config" and "se nepodařilo spustit" in r.error["message"]
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
    one = calls(("fs__read_text_file", {"path": "nic"}))
    r, _ = run(path, script={"t1": [one, {"text": "a"}], "t2": [one, {"text": "b"}]})
    assert r.status == "succeeded", r.error
    assert [e["action"] for e in events(r, "mcp_server")] == ["started", "stopped"]
    assert len(events(r, "tool_call")) == 2 and children() == []


# --- skilly ---------------------------------------------------------------------------------

def test_skills_task_list_and_load_skill(wf):
    setup(wf, agent_extra="skills: [thtd-hlas]\n")
    r, fake = run(task_sc(wf), script={"t": [calls(("load_skill", {"name": "thtd-hlas"})),
                                             calls(("load_skill", {"name": "neni"})), {"text": "ok"}]})
    assert r.status == "succeeded", r.error
    first = fake.calls[0][2]
    system = first["messages"][0]["content"]
    assert "## Skilly\n\n- thtd-hlas: Tón a slovník značky THTD" in system and "Tykáme" not in system
    skill = next(t for t in first["tools"] if t["function"]["name"] == "load_skill")
    assert skill["function"]["parameters"]["properties"]["name"]["enum"] == ["thtd-hlas"]
    tc = events(r, "tool_call")
    assert [(e["server"], e["tool"], e["invalid_args"]) for e in tc] == [("_skills", "load_skill", False),
                                                                        ("_skills", "load_skill", True)]
    assert [e["turn"] for e in events(r, "model_call")] == [1, 2, 3]                # load_skill je tah
    msgs = fake.calls[2][2]["messages"]
    tool_msgs = [m["content"] for m in msgs if m["role"] == "tool"]
    assert "Tykáme" in tool_msgs[0] and '"thtd-hlas"' in tool_msgs[1]            # chyba se seznamem skillů


def test_skills_ask_inlines_whole_body(wf):
    from maw.validate import load_agent, load_config
    errs = []
    agent = load_agent(wf, "copywriter", load_config(wf, errs), errs)
    ask = system_prompt_ask(agent)
    assert "## Skill: thtd-hlas\n\n- Tykáme." in ask
    assert system_prompt_task(agent).endswith("## Skilly\n\n- thtd-hlas: Tón a slovník značky THTD pro texty na sociální sítě")


# --- dedupe_key -----------------------------------------------------------------------------

def test_dedupe_two_runs(wf):
    setup(wf)
    path = task_sc(wf, step='dedupe_key: "post-{{ inputs.id }}"')
    path.write_text(path.read_text().replace("steps:", "inputs: { id: { type: string, required: true } }\nsteps:"))
    script = {"t": [calls(("fs__write_file", {"path": "a.txt", "content": "x"})), {"text": "zveřejněno"}]}
    r1, _ = run(path, {"id": "42"}, script)
    assert r1.status == "succeeded", r1.error
    files = list((wf.parent / "runs" / "_dedupe").glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text()) == {"state": "succeeded", "run_id": r1.run_id,
                                                "output": {"text": "zveřejněno"}}
    r2, fake2 = run(path, {"id": "42"}, script)
    assert r2.status == "succeeded" and r2.values["steps"]["t"] == {"text": "zveřejněno"}
    skip = events(r2, "step_skipped")[0]
    assert skip["reason_code"] == "dedupe" and r1.run_id in skip["reason"]
    assert fake2.calls == [] and events(r2, "mcp_server") == []                   # nic se nevolalo
    r3, _ = run(path, {"id": "43"}, script)                                        # jiný klíč = nový soubor
    assert r3.status == "succeeded" and len(list(files[0].parent.glob("*.json"))) == 2


def test_dedupe_started_without_succeeded_is_config(wf):
    setup(wf)
    path = task_sc(wf, step='dedupe_key: "jednou"')
    r1, _ = run(path, script={"t": [calls(("fs__write_file", {"path": "a.txt", "content": "x"})), {"status": 400}]})
    assert r1.error["class"] == "config"
    f = next((wf.parent / "runs" / "_dedupe").glob("*.json"))
    assert json.loads(f.read_text())["state"] == "started"
    r2, fake2 = run(path, script={"t": [{"text": "ok"}]})
    assert r2.error["class"] == "config" and "ověř ručně a smaž" in r2.error["message"] and str(f) in r2.error["message"]
    assert fake2.calls == []
    # stejný klíč v jiném scénáři je jiný soubor
    other = task_sc(wf, step='dedupe_key: "jednou"', name="jiny")
    r3, _ = run(other, script={"t": [{"text": "ok"}]})
    assert r3.status == "succeeded", r3.error


def test_dedupe_without_tool_call_writes_only_succeeded(wf):
    setup(wf)
    r, _ = run(task_sc(wf, step='dedupe_key: "k"'), script={"t": [{"text": "bez nástrojů"}]})
    assert r.status == "succeeded"
    f = next((wf.parent / "runs" / "_dedupe").glob("*.json"))
    assert json.loads(f.read_text())["state"] == "succeeded"


# --- po sloučení s 3b: --dry-run a task uvnitř call ------------------------------------------

def test_dry_run_lists_server_tools(wf):
    from maw.engine import dry_run
    setup(wf, agent_tools="[read_text_file, write_file]")
    p = validate(task_sc(wf, ", tools: { fs: [read_text_file] }", step='dedupe_key: "k"'), check_models=False)
    rec = dry_run(p, {})
    assert sorted(f.name for f in rec.dir.iterdir()) == ["inputs.json", "plan.md"]  # server běžel v dočasné složce
    plan = (rec.dir / "plan.md").read_text()
    assert "agent tester → chytry" in plan and "nástroje: fs: read_text_file;" in plan and "dedupe_key" in plan
    assert "- **fs** (Falešný server pro testy): nabízí broken, complex, get_env," in plan
    assert children() == []


def test_task_with_dedupe_inside_call(wf):
    setup(wf)
    scenario(wf, """
version: 1
name: dite
description: Volaný scénář s krokem task
callable: true
outputs: { text: { type: string } }
steps:
  - id: t
    dedupe_key: "jednou"
    task: { agent: tester, prompt: "Udělej úkol" }
  - id: out
    output: { text: "{{ steps.t.text }}" }
""", "dite")
    path = scenario(wf, HEAD + """
outputs: { vysledek: { type: string } }
steps:
  - id: navrh
    call: { scenario: dite }
  - id: out
    output: { vysledek: "{{ steps.navrh.text }}" }
""")
    script = {"navrh/t": [calls(("fs__write_file", {"path": "a.txt", "content": "x"})), {"text": "hotovo"}]}
    r1, _ = run(path, script=script)
    assert r1.status == "succeeded", r1.error
    assert r1.outputs == {"vysledek": "hotovo"}
    assert (r1.rec.dir / "work" / "a.txt").is_file() and events(r1, "tool_call")[0]["step"] == "navrh/t"
    r2, fake2 = run(path, script=script)
    assert r2.status == "succeeded" and r2.outputs == {"vysledek": "hotovo"}
    assert events(r2, "step_skipped")[0]["reason_code"] == "dedupe" and fake2.calls == []
    assert children() == []
