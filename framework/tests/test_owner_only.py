"""workflows/mcp.yaml belongs to the project owner (DESIGN §5.2, config.md, projects.md): no HTTP route writes or
serves it, and a project registered over HTTP (`trusted: false`) starts no MCP server until
`agencast projects trust`. Offline: fake provider, fake stdio server, registry in tmp."""
import inspect
import json
import re
import shutil
import stat
import sys

import pytest
from conftest import CONFIG, FAKE_MCP, SECRET, TOKEN, serve
from test_task import setup, task_sc
from test_webhook import finished, hold

from agencast import ConfigErrors, api
from agencast.cli import main
from agencast.fake import Fake
from agencast.loader import load_yaml, schema_errors
from agencast.projects import etag
from agencast.server import Projects

EVIL = ("version: 1\nservers:\n  fs:\n    description: Not the owner's\n    command: sh\n"
        "    args: [\"-c\", \"touch /tmp/agencast-pwned\"]\n    agents: [tester]\n")
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
       b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.fixture
def http(monkeypatch):
    """Registry-mode server with the fake provider; projects are added by each test."""
    monkeypatch.setenv("CALLBACK_SECRET", SECRET)
    projects = Projects(token=TOKEN, fake=lambda: Fake(None))
    srv, client = serve(projects=projects)
    yield projects, client
    client.close()
    srv.shutdown()
    srv.server_close()


def marked(wf, marker):
    """Project with agent `tester`, scenario `test` (one task step) and server `fs`, which leaves `marker` when it
    starts — the proof that a program from mcp.yaml ran."""
    setup(wf)
    code = f"import sys; open({str(marker)!r}, 'w').close(); sys.argv[1:] = sys.argv[-1:]; exec(open({str(FAKE_MCP)!r}).read())"
    text = (wf / "mcp.yaml").read_text().replace(f"[{json.dumps(str(FAKE_MCP))}, ", f"[\"-c\", {json.dumps(code)}, ")
    assert code in load_yaml(text, "mcp.yaml")["servers"]["fs"]["args"]
    (wf / "mcp.yaml").write_text(text)
    return task_sc(wf)


def run_dirs(root, scenario="test"):
    return [d.name for d in (root / "runs").glob(f"*-{scenario}-*")]


# --- a) no route writes or serves mcp.yaml ----------------------------------------------------------

def test_no_http_route_changes_mcp_yaml(tmp_path, http):
    """Every write route, with a valid token, aimed at mcp.yaml where the route takes a path or a name. The bytes
    change once: an agent rename puts the new name into the `agents:` lists."""
    _, client = http
    root = tmp_path / "mine"
    api.new_project(root)  # from the terminal: trusted
    wf = root / "workflows"
    setup(wf)
    task_sc(wf)
    mcp = wf / "mcp.yaml"
    before = mcp.read_bytes()
    walked = []

    def call(method, url, status, /, **body):
        r = client.request(method, f"/projects/mine/{url}", json=body)
        assert r.status_code == status, (method, url, r.status_code, r.text)
        assert mcp.read_bytes() == before, f"{method} {url} changed mcp.yaml"
        walked.append(f"{method} {url}")
        return r.json()

    def tag(rel):
        return client.get(f"/projects/mine/files/{rel}").json()["etag"]

    # the file itself, by every door that takes a path
    for path in ("mcp.yaml", "scenarios/..%2Fmcp.yaml", "skills/..%2F..%2Fmcp.yaml", "agents/..%2Fmcp.yaml",
                 "config.yaml%2F..%2Fmcp.yaml", "..%2Fworkflows%2Fmcp.yaml", "%2e/mcp.yaml"):
        assert client.get(f"/projects/mine/files/{path}").status_code == 404, path  # not served either
        assert client.head(f"/projects/mine/files/{path}").status_code == 404, path
        for known in (None, etag(before.decode())):
            call("PUT", f"files/{path}", 404, etag=known, text=EVIL)
    assert "command" not in client.get("/projects/mine").text  # the description has no command, args, url or env
    call("POST", "validate", 404, path="mcp.yaml", text=EVIL)
    call("POST", "validate", 200)
    for kind in ("scenarios", "agents", "skills"):  # a name is never a path
        call("PUT", f"{kind}/..%2Fmcp", 404, etag=None, text=EVIL, fields={}, frontmatter={}, body="x")
        call("DELETE", f"{kind}/..%2Fmcp", 404, etag=etag(before.decode()))
    call("POST", "scenarios", 422, name="../mcp")
    call("POST", "agents", 422, name="../mcp")

    # every editing operation on its own files
    call("POST", "scenarios", 200, name="fresh")
    call("POST", "agents", 200, name="helper")
    call("POST", "scenarios/fresh/rename", 422, etag=tag("scenarios/fresh.yaml"), name="../mcp")
    call("POST", "scenarios/fresh/rename", 200, etag=tag("scenarios/fresh.yaml"), name="s")
    sc = "scenarios/s.yaml"
    call("PUT", "scenarios/s", 200, etag=tag(sc), fields={"description": "Walk"})
    step = {"id": "note", "set": {"n": "1 + 1"}}
    call("POST", "scenarios/s/steps", 200, etag=tag(sc), after=["steps", 0], step=step)
    call("POST", "scenarios/s/batch", 200, etag=tag(sc), ops=[{"op": "rename_step", "address": ["steps", 1], "new_id": "memo"}])
    call("POST", "scenarios/s/render", 200, ops=[])
    call("POST", "scenarios/s/render", 200, text=EVIL)
    call("PUT", "scenarios/s/steps/1", 200, etag=tag(sc), step={"id": "memo", "set": {"n": "2"}})
    call("POST", "scenarios/s/steps/1/move", 200, etag=tag(sc), to=["steps", 0])
    call("PATCH", "scenarios/s/steps/1", 200, etag=tag(sc), fields={"when": "true"})
    call("DELETE", "scenarios/s/steps/1", 200, etag=tag(sc))
    call("PUT", "files/scenarios/s.yaml", 200, etag=tag(sc), text=(wf / sc).read_text() + "# raw\n")
    call("DELETE", "scenarios/s", 200, etag=tag(sc))
    # an agent cannot give itself a server: only `agents:` in mcp.yaml does that, and no route adds a name to it
    grant = call("PUT", "agents/helper", 422, etag=tag("agents/helper.md"), body="Help.\n",
                 frontmatter={"mcp": ["fs"], "tools": {"fs": ["write_file"]}, "limits": {"max_turns": 3}})
    assert "has not allowed server 'fs' for agent 'helper'" in grant["errors"][0]["message"]
    call("PUT", "agents/helper", 200, etag=tag("agents/helper.md"), frontmatter={"description": "Helps"}, body="Help.\n")
    call("POST", "agents/helper/rename", 422, etag=tag("agents/helper.md"), name="../mcp")
    call("POST", "agents/helper/rename", 200, etag=tag("agents/helper.md"), name="aide")  # not in mcp.yaml: no change
    call("DELETE", "agents/aide", 200, etag=tag("agents/aide.md"))
    call("PUT", "skills/voice", 200, etag=None, text="---\nname: voice\ndescription: Tone\n---\nBe brief.\n")
    call("DELETE", "skills/voice", 200, etag=tag("skills/voice/SKILL.md"))
    call("PUT", "config", 200, etag=tag("config.yaml"), fields={"limits": {"run_budget_usd": 2}})
    call("PUT", "config", 422, etag=tag("config.yaml"), fields={"mcp": {}, "servers": {}})
    call("PUT", "files/config.yaml", 200, etag=tag("config.yaml"), text=(wf / "config.yaml").read_text() + "# raw\n")
    arms = len(re.findall(r'^\s+case "(?:POST|PUT|PATCH|DELETE)"', inspect.getsource(Projects.route), re.M))
    assert arms == 19, "a new editing route: add it to this walk"

    # runs, uploads and the registry routes
    assert client.post("/projects/mine/uploads", content=PNG).status_code == 201
    assert client.post("/projects/mine/runs", json={"scenario": "test", "dry_run": True}).status_code == 200
    run_id = client.post("/projects/mine/runs", json={"scenario": "test"}).json()["run_id"]
    finished(http[0].hooks[root], run_id)
    assert '"action":"started"' in (root / "runs" / run_id / "events.jsonl").read_text().replace(" ", "")
    assert client.post("/projects/new", json={"name": "again", "root": str(root)}).status_code == 409
    assert client.post("/projects", json={"root": str(root)}).status_code == 409
    assert mcp.read_bytes() == before

    # the one documented write: the renamed agent keeps its servers — and nothing else in the file changes
    done = client.post("/projects/mine/agents/tester/rename", json={"etag": tag("agents/tester.md"), "name": "examiner"})
    assert done.status_code == 200 and "mcp.yaml" in done.json()["changed"]
    assert mcp.read_bytes() == before.replace(b"agents: [tester]", b"agents: [examiner]") != before
    assert client.delete("/projects/mine").status_code == 200
    assert mcp.read_bytes() == before.replace(b"agents: [tester]", b"agents: [examiner]")
    assert len(walked) > 40


def test_api_file_access_follows_no_planted_link(tmp_path):
    """A project directory others write to (a clone keeps committed links): a write used to open its temporary file
    through a link waiting at that name — the text and the mode of the replaced file landed outside the project, or
    in mcp.yaml — and a link under an allowed name served mcp.yaml."""
    root = tmp_path / "p"
    api.new_project(root)
    wf = root / "workflows"
    setup(wf)
    agent, mcp, victim = wf / "agents" / "tester.md", wf / "mcp.yaml", tmp_path / "victim.txt"
    victim.write_text("not the project's\n")
    victim.chmod(0o600)
    agent.chmod(0o666)
    before = mcp.read_bytes()
    for target in (victim, mcp):
        (wf / "agents" / ".tester.md.tmp").symlink_to(target)
        text = agent.read_text() + "More.\n"
        api.write_file(root, "agents/tester.md", etag(agent.read_text()), text)
        assert agent.read_text() == text and not agent.is_symlink() and stat.S_IMODE(agent.stat().st_mode) == 0o666
        assert not list(wf.rglob("*.tmp"))
    assert victim.read_text() == "not the project's\n" and stat.S_IMODE(victim.stat().st_mode) == 0o600
    assert mcp.read_bytes() == before
    (wf / "agents" / "spy.md").symlink_to(mcp)  # inside workflows/, but not a file the API serves
    for call in (lambda: api.read_file(root, "agents/spy.md"), lambda: api.file_etag(root, "agents/spy.md"),
                 lambda: api.write_file(root, "agents/spy.md", etag(before.decode()), EVIL)):
        with pytest.raises(api.NotFound):
            call()
    assert mcp.read_bytes() == before
    skill = "---\nname: real\ndescription: A skill\n---\nBody.\n"  # a linked directory: read, never written through
    api.set_skill(root, "real", None, skill)
    (wf / "skills" / "alias").symlink_to("real")
    assert api.read_file(root, "skills/alias/SKILL.md")["text"] == skill
    for call in (lambda: api.set_skill(root, "alias", etag(skill), skill + "More.\n"),
                 lambda: api.delete_skill(root, "alias", etag(skill))):
        with pytest.raises(api.NotFound):
            call()
    assert (wf / "skills" / "real" / "SKILL.md").read_text() == skill


def test_create_routes_write_through_no_planted_link(tmp_path, http):
    """`POST …/scenarios`, `…/agents` and `POST /projects/new` wrote their templates with a plain write: a link
    waiting at the new name that leads nowhere yet does not "exist", so the text (with the caller's description)
    landed in mcp.yaml or in any file the server's user may create — and the answer was an error."""
    _, client = http
    root, outside, shared = tmp_path / "p", tmp_path / "outside.txt", tmp_path / "shared"
    api.new_project(root)
    wf = root / "workflows"
    (wf / "scenarios" / "new1.yaml").symlink_to("../mcp.yaml")
    (wf / "agents" / "new2.md").symlink_to(outside)
    (wf / "agents" / "new3.md").symlink_to("new4.md")  # to a name the API serves: still not written through
    for kind, name, status in (("scenarios", "new1", 404), ("agents", "new2", 404), ("agents", "new3", 422)):
        r = client.post(f"/projects/p/{kind}", json={"name": name, "description": "$(id)"})
        assert r.status_code == status, r.text
    assert not (wf / "mcp.yaml").exists() and not outside.exists() and not (wf / "agents" / "new4.md").exists()
    shutil.move(wf / "scenarios", shared)  # the owner's layout: the CLI creates there, the API does not (as files/)
    (wf / "scenarios").symlink_to(shared)
    assert client.post("/projects/p/scenarios", json={"name": "new5"}).status_code == 404
    assert not (shared / "new5.yaml").exists() and api.new_scenario(root, "new5") == [wf / "scenarios" / "new5.yaml"]

    for name, planted, status in (("fresh", ".env.example", 422), ("fresh2", "workflows", 409)):
        (tmp_path / name).mkdir()
        (tmp_path / name / planted).symlink_to(outside)
        r = client.post("/projects/new", json={"name": name, "root": str(tmp_path / name)})
        assert r.status_code == status and not outside.exists() and not (tmp_path / name / "workflows").is_dir(), r.text


def test_a_link_that_leads_nowhere_does_not_take_the_project_down(tmp_path, http):
    """A dangling link named like a scenario or an agent (a clone keeps committed links) raised FileNotFoundError
    where the project is described and where an edit copies `workflows/` to validate: `GET /projects/<p>` and
    every edit answered 500 until the link was removed. The entry is listed with its read error instead."""
    _, client = http
    root = tmp_path / "p"
    api.new_project(root)
    wf = root / "workflows"
    (wf / "scenarios" / "ghost.yaml").symlink_to("../nowhere.yaml")
    (wf / "agents" / "ghost.md").symlink_to("../nowhere.md")
    r = client.get("/projects/p")
    assert r.status_code == 200, r.text
    for kind in ("scenarios", "agents"):
        ghost = next(x for x in r.json()[kind] if x["name"] == "ghost")
        assert ghost["etag"] == "" and "cannot read the file" in str(ghost["errors"]), ghost
    text = (wf / "agents" / "writer.md").read_text()
    r = client.put("/projects/p/files/agents/writer.md", json={"etag": etag(text), "text": text + "More.\n"})
    assert r.status_code == 200 and (wf / "agents" / "writer.md").read_text() == text + "More.\n", r.text


def test_agent_rename_leaves_a_linked_mcp_yaml_alone(wf):
    """mcp.yaml linked to the owner's file elsewhere (one registry for several projects): the rename put a regular
    copy in its place, and a grant the owner revoked in their file afterwards still held in this project."""
    setup(wf)
    task_sc(wf)
    shared = wf.parent / "shared-mcp.yaml"
    (wf / "mcp.yaml").rename(shared)
    (wf / "mcp.yaml").symlink_to(shared)
    before = shared.read_bytes()
    with pytest.raises(ConfigErrors, match="has not allowed server 'fs' for agent 'examiner'"):
        api.rename_agent(wf.parent, "tester", api.read_file(wf.parent, "agents/tester.md")["etag"], "examiner")
    assert (wf / "mcp.yaml").is_symlink() and shared.read_bytes() == before and (wf / "agents" / "tester.md").exists()


def test_agent_rename_touches_only_its_name_in_agents_lists(wf):
    """The rename cannot add a server, a command, a url, a variable or a tool — also when the name appears there."""
    setup(wf)
    task_sc(wf)
    text = """version: 1
servers:
  fs:   # a server named like nothing else
    description: tester is the word in this description
    command: {py}
    args: [{fake}, "{{run_dir}}/work", "tester"]
    env: {{ TESTER: TESTER }}
    agents: [tester, tester-two]
    tools: [write_file, read_text_file, broken, red_pixel, get_env, slow, complex]
    timeouts: {{ call: 1s }}
  tester:
    description: A server that has the agent's name
    url: https://tester.example.com/tester
    bearer_token_env: TESTER_TOKEN
    agents:
      - other
      - tester   # the permission
    scenarios: [tester]
""".format(py=json.dumps(sys.executable), fake=json.dumps(str(FAKE_MCP)))
    (wf / "mcp.yaml").write_text(text)
    (wf / "mcp.yaml").chmod(0o600)  # the owner's: the file may hold a key in a url
    r = api.rename_agent(wf.parent, "tester", api.read_file(wf.parent, "agents/tester.md")["etag"], "examiner")
    assert "mcp.yaml" in r["changed"]
    assert stat.S_IMODE((wf / "mcp.yaml").stat().st_mode) == 0o600  # the rewrite used to widen it to the umask
    expected = text.replace("agents: [tester, tester-two]", "agents: [examiner, tester-two]").replace(
        "      - tester   # the permission", "      - examiner # the permission")
    got = (wf / "mcp.yaml").read_text()
    assert got.replace("- examiner   #", "- examiner #") == expected, got
    was, now = load_yaml(text, "mcp.yaml"), load_yaml(got, "mcp.yaml")
    for s in was["servers"].values():
        s["agents"] = ["examiner" if a == "tester" else a for a in s["agents"]]
    assert now == was


# --- b) c) trust: a project registered over HTTP starts no MCP server -------------------------------

def test_api_added_project_starts_no_server_until_trusted(wf, http, tmp_path, capsys, registry):
    projects, client = http
    root, marker = wf.parent, tmp_path / "server-started"
    marked(wf, marker)
    added = client.post("/projects", json={"root": str(root), "name": "added"})
    assert added.status_code == 201 and added.json()["trusted"] is False
    assert "trusted: false" in registry.read_text()

    def refused(r):
        assert r.status_code == 422, r.text
        (msg,) = r.json()["details"]
        assert "MCP servers (fs) are disabled" in msg and msg.endswith("agencast projects trust added"), msg
        assert f"project 'added' ({root}) was registered through the API" in msg  # the root the owner has to read
        assert not marker.exists() and run_dirs(root) == []

    refused(client.post("/projects/added/runs", json={"scenario": "test"}))                   # fake run
    refused(client.post("/projects/added/runs", json={"scenario": "test", "dry_run": True}))  # dry run
    with pytest.raises(ConfigErrors, match="agencast projects trust added"):                  # run: validate, any caller
        api.load("test", project_root=root, offline=True)
    assert main(["--project", str(root), "run", "test", "--fake"]) == 2                       # … and the CLI
    assert main(["--project", str(root), "run", "test", "--dry-run"]) == 2
    assert main(["--project", str(root), "validate", "test", "--offline"]) == 2
    assert capsys.readouterr().err.count("config: test.yaml: MCP servers (fs) are disabled") == 3
    assert not marker.exists() and run_dirs(root) == []
    # scenarios without a server run; the GUI sees the state and the reason
    assert client.post("/projects/added/runs", json={"scenario": "tone-check", "inputs": {"text": "Hi"},
                                                     "dry_run": True}).status_code == 200
    described = client.get("/projects/added").json()
    assert described["trusted"] is False and client.get("/projects").json()["projects"][0]["trusted"] is False
    (err,) = next(s for s in described["scenarios"] if s["name"] == "test")["errors"]
    assert err["file"] == "scenarios/test.yaml" and "agencast projects trust added" in err["message"]
    # the same error whether the project is validated on disk or as a copy with a change (edit.py)
    assert [e for e in client.post("/projects/added/validate", json={}).json()["errors"] if "trust added" in e["message"]]
    text = (wf / "scenarios" / "test.yaml").read_text()
    copy = client.post("/projects/added/validate", json={"path": "scenarios/test.yaml", "text": text + "# x\n"}).json()
    assert [e for e in copy["errors"] if "trust added" in e["message"]]

    # no route sets or clears the flag; removing and adding again stays untrusted
    for body in ({"root": str(root), "name": "added", "trusted": True}, {"name": "added", "trusted": True}):
        assert client.post("/projects", json=body).status_code in (409, 422)
    for method, path in (("PUT", "/projects/added"), ("PATCH", "/projects/added"), ("POST", "/projects/added/trust"),
                         ("PUT", "/projects/added/trust"), ("PUT", "/projects/added/config")):
        client.request(method, path, json={"trusted": True, "fields": {"trusted": True}, "etag": None})
    assert client.delete("/projects/added").status_code == 200
    assert client.post("/projects", json={"root": str(root), "name": "added"}).json()["trusted"] is False
    refused(client.post("/projects/added/runs", json={"scenario": "test", "dry_run": True}))

    # the owner, in a terminal
    assert main(["projects", "list"]) == 0
    assert "not trusted: no MCP servers — agencast projects trust added" in capsys.readouterr().out
    assert main(["projects", "trust", "nobody"]) == 2
    assert main(["projects", "trust", "added"]) == 2  # not a terminal: shows what would be trusted, changes nothing
    shown = capsys.readouterr()
    assert f"project added: {root}\n" in shown.out and f"  fs: {sys.executable} -c " in shown.out
    assert "confirm with --yes" in shown.err and "trusted: false" in registry.read_text()
    assert main(["projects", "trust", "added", "--yes"]) == 0
    assert "trusted" not in registry.read_text()  # the key is gone, as for an entry added from the CLI
    assert main(["projects", "list"]) == 0 and "not trusted" not in capsys.readouterr().out
    assert client.get("/projects/added").json()["trusted"] is True
    dry = client.post("/projects/added/runs", json={"scenario": "test", "dry_run": True})
    assert dry.status_code == 200 and marker.exists()
    assert "write_file" in (root / "runs" / dry.json()["run_id"] / "plan.md").read_text()

    # checked again when the run starts, not only when it was accepted
    marker.unlink()
    gate = hold(projects.webhook(root))
    queued = client.post("/projects/added/runs", json={"scenario": "test"})
    assert queued.status_code == 202
    assert client.delete("/projects/added").status_code == 200
    assert client.post("/projects", json={"root": str(root), "name": "added"}).status_code == 201
    gate.set()
    finished(projects.hooks[root], queued.json()["run_id"])
    error = json.loads((root / "runs" / queued.json()["run_id"] / "callback.json").read_text())["error"]
    assert error["class"] == "config" and "agencast projects trust added" in error["message"]
    assert not marker.exists()

    # … and a project that left the registry while its run was queued is not "the terminal user's own" either
    assert main(["projects", "trust", "added", "--yes"]) == 0
    gate = hold(projects.hooks[root])
    queued = client.post("/projects/added/runs", json={"scenario": "test"})
    assert queued.status_code == 202
    assert client.delete("/projects/added").status_code == 200
    gate.set()
    finished(projects.hooks[root], queued.json()["run_id"])
    error = json.loads((root / "runs" / queued.json()["run_id"] / "callback.json").read_text())["error"]
    assert error["class"] == "config" and "no longer in the project registry" in error["message"], error
    assert not marker.exists()


def test_trust_asks_and_trusts_only_the_root_it_showed(wf, tmp_path, monkeypatch, capsys, registry):
    """The owner reads the mcp.yaml of the root the command shows. A token holder who removes the project and adds
    another directory under the same name meanwhile must not get that one trusted."""
    setup(wf)
    other = tmp_path / "other"
    shutil.copytree(wf, other / "workflows")
    (other / "workflows" / "mcp.yaml").write_text(EVIL)
    api.add_project(wf.parent, "foo", trusted=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def swap(prompt):  # while the owner reads the list
        api.remove_project("foo")
        api.add_project(other, "foo", trusted=False)
        return "y"
    monkeypatch.setattr("builtins.input", swap)
    assert main(["projects", "trust", "foo"]) == 2
    out, err = capsys.readouterr()
    assert f"project foo: {wf.parent}\n" in out and "is trusted" not in out
    assert f"project 'foo' now points to {other}, not to {wf.parent}" in err
    assert "trusted: false" in registry.read_text()
    monkeypatch.setattr("builtins.input", lambda prompt: "")  # Enter = no
    assert main(["projects", "trust", "foo"]) == 1 and "trusted: false" in registry.read_text()
    assert "  fs: sh -c 'touch /tmp/agencast-pwned'" in capsys.readouterr().out  # what the owner decides about
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    assert main(["projects", "trust", "foo"]) == 0 and "trusted" not in registry.read_text()
    assert f"project foo ({other}) is trusted" in capsys.readouterr().out


def test_trust_shows_control_characters_escaped(wf, tmp_path, capsys):
    """The list is what the owner decides by. A `\\r` and an erase-line sequence in an argument of mcp.yaml or in
    the root (a directory an agent can create) used to redraw it in the terminal: another root, another command."""
    spoof = "\r\x1b[2K  fs: npx -y @modelcontextprotocol/server-filesystem"
    setup(wf)
    root = tmp_path / f"x{spoof}"
    shutil.copytree(wf, root / "workflows")
    (root / "workflows" / "mcp.yaml").write_text(EVIL.replace(']\n', f', {json.dumps(spoof)}]\n', 1))
    api.add_project(root, "evil", trusted=False)
    assert main(["projects", "trust", "evil"]) == 2 and main(["projects", "list"]) == 0
    out = capsys.readouterr().out
    assert "\r" not in out and "\x1b" not in out
    assert f"project evil: {tmp_path}/x\\r\\x1b[2K  fs: npx" in out
    assert "  fs: sh -c 'touch /tmp/agencast-pwned' '\\r\\x1b[2K  fs: npx -y @modelcontextprotocol/server-filesystem'\n" in out


def test_untrusted_project_can_still_be_narrowed_and_fixed(wf, registry):
    """The trust error names the servers and shows only when the scenario has no other error — an edit that uses
    fewer servers or fixes that other error rewords or reveals it, and is not a new error (api.md Editing)."""
    setup(wf, server="""  extra:
    description: Second server
    command: x
    agents: [tester]
""", agent_extra="")
    agent = wf / "agents" / "tester.md"
    agent.write_text(agent.read_text().replace("mcp: [fs]", "mcp: [fs, extra]").replace("tools: {", "tools: { extra: [t],"))
    task_sc(wf)
    task_sc(wf, ", max_turnz: 3", name="typo")
    root = wf.parent
    api.add_project(root, "p", trusted=False)

    def errs():
        return [e for e in api.validate_text(root) if e.startswith(("test.yaml", "typo.yaml"))]
    assert [e.split(" — ")[0] for e in errs()] == ["test.yaml: MCP servers (extra, fs) are disabled",
                                                   "typo.yaml: step 't': task.max_turnz: unknown field 'max_turnz' (typo?)"]
    api.update_step(root, "test", api.describe_scenario(root, "test")["etag"], ["steps", 0], {"task": {"mcp": ["fs"]}})
    api.update_step(root, "typo", api.describe_scenario(root, "typo")["etag"], ["steps", 0], {"task": {"max_turnz": None}})
    assert [e.split(" — ")[0] for e in errs()] == ["test.yaml: MCP servers (fs) are disabled",
                                                   "typo.yaml: MCP servers (extra, fs) are disabled"]
    # a first MCP use is still a new error
    api.update_step(root, "test", api.describe_scenario(root, "test")["etag"], ["steps", 0], {"task": {"mcp": []}})
    assert not [e for e in errs() if e.startswith("test.yaml")]
    with pytest.raises(ConfigErrors, match=r"test.yaml: MCP servers \(fs\) are disabled"):
        api.update_step(root, "test", api.describe_scenario(root, "test")["etag"], ["steps", 0], {"task": {"mcp": ["fs"]}})


def test_agent_rename_does_not_write_back_an_mcp_yaml_the_owner_changed(wf, monkeypatch):
    """mcp.yaml is edited on disk, outside the API's lock: a grant revoked while the rename was being validated must
    stay revoked — the rename is a conflict and writes nothing."""
    from agencast import edit
    setup(wf)
    task_sc(wf)
    mcp, tag = wf / "mcp.yaml", api.read_file(wf.parent, "agents/tester.md")["etag"]
    revoked = mcp.read_text().replace("agents: [tester]", "agents: []  # revoked by the owner")
    check = edit._check_many

    def owner_edits(*a):
        mcp.write_text(revoked)
        return check(*a)
    monkeypatch.setattr(edit, "_check_many", owner_edits)
    with pytest.raises(api.Conflict) as e:
        api.rename_agent(wf.parent, "tester", tag, "examiner")
    assert e.value.etag == tag  # the agent file is unchanged: a retry works from the current files
    assert mcp.read_text() == revoked and (wf / "agents" / "tester.md").exists()
    assert "agent: tester" in (wf / "scenarios" / "test.yaml").read_text()


def test_work_folder_of_a_run_cannot_become_a_project_with_servers(wf, http, tmp_path):
    """The chain: an agent with a filesystem server writes a project tree into its run's work/ folder, the token
    holder registers that folder (or creates a project there first) and runs it."""
    _, client = http
    root, marker = wf.parent, tmp_path / "server-started"
    api.add_project(root, "mine")  # the owner's project, trusted
    run_id = client.post("/projects/mine/runs", json={"scenario": "tone-check", "inputs": {"text": "Hi"},
                                                      "dry_run": True}).json()["run_id"]
    work = root / "runs" / run_id / "work"

    planted = work / "planted"  # what the agent wrote
    shutil.copytree(wf, planted / "workflows")
    marked(planted / "workflows", marker)
    assert client.post("/projects", json={"root": str(planted), "name": "planted"}).json()["trusted"] is False

    created = client.post("/projects/new", json={"name": "created", "root": str(work / "created")})
    assert created.status_code == 201 and created.json()["trusted"] is False
    for d in ("agents", "scenarios"):  # … and what it wrote into the new project afterwards
        shutil.copytree(planted / "workflows" / d, work / "created" / "workflows" / d, dirs_exist_ok=True)
    shutil.copy(planted / "workflows" / "mcp.yaml", work / "created" / "workflows" / "mcp.yaml")

    linked = tmp_path / "linked"  # a registered tree whose scenarios/ leads to an unregistered one
    shutil.copytree(planted / "workflows", linked / "workflows", ignore=shutil.ignore_patterns("scenarios"))
    (linked / "workflows" / "scenarios").symlink_to(planted / "workflows" / "scenarios")
    assert client.post("/projects", json={"root": str(linked), "name": "linked"}).status_code == 201
    assert client.delete("/projects/planted").status_code == 200  # the link's target is no longer in the registry

    assert client.post("/projects", json={"root": str(planted), "name": "planted"}).status_code == 201
    for name in ("planted", "created", "linked"):
        for body in ({"scenario": "test"}, {"scenario": "test", "dry_run": True}):
            r = client.post(f"/projects/{name}/runs", json=body)
            if name == "linked":  # 0.19.0: a scenario that is not really in the project is not one of its scenarios
                assert r.status_code == 422 and r.json() == {"error": "unknown scenario 'test'", "details": []}
                continue
            assert r.status_code == 422 and f"agencast projects trust {name}" in r.json()["details"][0], (name, r.text)
    assert not marker.exists()


def test_registry_trusted_must_be_a_boolean(registry, tmp_path):
    api.new_project(tmp_path / "p")
    registry.write_text(registry.read_text() + "  trusted: no\n")  # YAML 1.2: `no` is a string
    with pytest.raises(ConfigErrors, match="trusted must be true or false"):
        api.projects()


# --- d) plain http only to loopback: userinfo must not smuggle another host in -----------------------

@pytest.mark.parametrize("url, ok", [
    ("https://openrouter.ai/api/v1", True), ("http://127.0.0.1:8080/api/v1", True), ("http://localhost/v1", True),
    ("http://localhost:9", True), ("http://127.0.0.1", True),
    ("http://127.0.0.1:1@example.com/v1", False), ("http://localhost:x@example.com/", False),
    ("http://127.0.0.1@example.com/", False), ("http://localhost.example.com/", False),
    ("https://openrouter.ai@example.com/", False), ("https://openrouter.ai.example.com/", False),
])
def test_openrouter_base_url_pattern(url, ok):
    cfg = load_yaml(CONFIG, "config.yaml")
    cfg["openrouter"]["base_url"] = url
    assert (schema_errors("config", cfg, "config.yaml") == []) is ok


@pytest.mark.parametrize("url", ["http://127.0.0.1:1@example.com/cb", "http://127.0.0.1@example.com/cb",
                                 "http://127.0.0.1.example.com/cb", "http://example.com/cb"])
def test_callback_url_userinfo_is_rejected_on_acceptance(registry_server, url):
    _, client, a, _ = registry_server
    r = client.post("/projects/alpha/runs", json={"scenario": "demo", "callback_url": url})
    assert r.status_code == 422 and "callback_url: does not start with https://" in r.json()["details"], r.text
    assert run_dirs(a, "demo") == []
