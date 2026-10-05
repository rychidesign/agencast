"""`agencast mcp --http`, step S5 (mcp-server.md “HTTP transport”). Black-box: every server is a subprocess on
127.0.0.1 and a free port with a dummy token made here, in a process group of its own; the SDK client speaks to it
over streamable HTTP, raw requests use httpx2 (both ship with the SDK). Every process a test starts is gone at its
end (`cleanup`)."""
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

import anyio
import httpx2
import pytest
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from agencast import api
from agencast.cli import main
from conftest import FAKE_MCP
from test_mcp_workers import (cleanup, copies, env_for, free_port, pictures, root, server, slow_script,  # noqa: F401
                              until, worker_pids)
from test_task import setup

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}
JSON = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
RUN_TOOLS = {"dry_run", "fake_run", "run_scenario"}
RUN_CARD = "ui://agencast/run-card.html"


class Http:
    """`agencast mcp --http` in a process group of its own, its stderr collected; `code` = a Python entry that
    patches the server before it calls `agencast.cli.main`."""

    def __init__(self, root, registry, cleanup, *args, port=None, token=None, code=None, **env):
        self.port, self.token = port or free_port(), token or secrets.token_hex(32)
        self.url = f"http://127.0.0.1:{self.port}/mcp"
        entry = ["-c", code] if code else ["-m", "agencast.cli"]
        self.p = subprocess.Popen([sys.executable, *entry, "--project", str(root), "mcp", "--http",
                                   "--port", str(self.port), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, cwd=root.parent, start_new_session=True,
                                  env=env_for(root, registry, AGENCAST_MCP_TOKEN=self.token, **env))
        self.stderr, self.stdout = [], []
        self.readers = [threading.Thread(target=lambda s=s, out=out: out.extend(s), daemon=True)
                        for s, out in ((self.p.stderr, self.stderr), (self.p.stdout, self.stdout))]
        for t in self.readers:
            t.start()
        cleanup.clients.append(self)
        until(lambda: "agencast mcp: http://" in "".join(self.stderr) or self.p.poll() is not None, 10)
        assert self.p.poll() is None, "".join(self.stderr)

    def stop(self, sig=signal.SIGTERM, timeout=7):
        os.kill(self.p.pid, sig)
        code = self.p.wait(timeout=timeout)
        for t in self.readers:
            t.join(timeout=1)
        return code

    def kill_group(self):
        if self.p.poll() is None:
            os.killpg(os.getpgid(self.p.pid), signal.SIGKILL)
            self.p.wait(timeout=3)

    def raw(self, token=None):
        return httpx2.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=10,
                             headers={"Authorization": f"Bearer {token or self.token}"})

    def client(self, mode="legacy", token=None):
        headers = {"Authorization": f"Bearer {token or self.token}"} if token != "" else {}
        return Client(streamable_http_client(self.url, http_client=httpx2.AsyncClient(headers=headers, timeout=60)),
                      mode=mode)

    def call(self, tool, arguments=None, mode="legacy"):
        async def go():
            async with self.client(mode) as c:
                r = await c.call_tool(tool, arguments or {})
                assert not r.is_error, r.content[0].text
                return r.structured_content
        return anyio.run(go)


def tools(client_):
    async def go():
        async with client_ as c:
            return sorted((t.model_dump() for t in (await c.list_tools()).tools), key=lambda t: t["name"])
    return anyio.run(go)


def sse(response) -> dict:
    return json.loads(next(line[5:] for line in response.text.splitlines() if line.startswith("data:")))


def listening(port) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return True
    except OSError:
        return False


@pytest.mark.parametrize("args,env,message", [
    (["--http", "--port", "PORT"], {}, "AGENCAST_MCP_TOKEN"),
    (["--http", "--port", "PORT"], {"AGENCAST_MCP_TOKEN": "t" * 10}, "at least 32 characters"),
    (["--host", "127.0.0.1"], {}, "--host only with --http"),
    (["--allow-host", "box", "--port", "PORT"], {}, "--port, --allow-host only with --http"),
    (["--http", "--port", "70000"], {"AGENCAST_MCP_TOKEN": "t" * 32}, "--port must be an integer in the range 1–65535"),
    (["--http"], {"AGENCAST_MCP_TOKEN": "t" * 32, "AGENCAST_MCP_PORT": "abc"}, "AGENCAST_MCP_PORT must be an integer"),
    (["--http", "--port", "HELD"], {"AGENCAST_MCP_TOKEN": "t" * 32}, "cannot start server at 127.0.0.1:"),
])
def test_start_errors(args, env, message, registry, monkeypatch, capsys):
    """Each start error: exit 2, `config:` on stderr, nothing on stdout, nothing listening, no token in a message."""
    for name in ("AGENCAST_MCP_TOKEN", "AGENCAST_MCP_HOST", "AGENCAST_MCP_PORT"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    port = free_port()
    with socket.create_server(("127.0.0.1", 0)) as held:
        args = [{"PORT": str(port), "HELD": str(held.getsockname()[1])}.get(x, x) for x in args]
        assert main(["mcp", *args]) == 2
    out, err = capsys.readouterr()
    assert out == "" and err.startswith("config: ") and message in err and "t" * 10 not in err
    assert not listening(port) and "AGENCAST_MCP_TOKEN" not in os.environ


def test_port_spellings(registry, monkeypatch, capsys):
    """A port is ASCII digits only: the spellings int() also takes are start errors. Each spells a port the test
    holds, so a regression fails on the bind instead of serving."""
    with socket.create_server(("127.0.0.1", 0)) as held:
        port = str(held.getsockname()[1])
        arabic = port.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
        for args, env in [*((["--port", spelled], port) for spelled in (f"+{port}", f"{port[0]}_{port[1:]}", arabic, "")),
                          ([], f" {port} ")]:
            monkeypatch.setenv("AGENCAST_MCP_TOKEN", "t" * 32)
            monkeypatch.setenv("AGENCAST_MCP_PORT", env)  # `--port ''` does not fall back to it
            assert main(["mcp", "--http", *args]) == 2
            assert f"{'--port' if args else 'AGENCAST_MCP_PORT'} must be an integer" in capsys.readouterr().err


def test_stdio_ignores_http_environment(root, registry, cleanup):
    """AGENCAST_MCP_HOST / _PORT are read only with --http: broken values never stop a stdio server."""
    c = server(root, registry, cleanup, AGENCAST_MCP_PORT="abc", AGENCAST_MCP_HOST="nowhere.invalid")
    assert [p["name"] for p in c.call("list_projects", {})["projects"]] == ["lumen"]
    assert c.close() == 0


def test_http_transport(root, registry, cleanup, tmp_path):
    """One --fake server: start line, both SDK modes against the stdio tool list, the bearer token, POST only,
    Host/Origin, stateless initialize, request bounds and idle connections."""
    s = Http(root, registry, cleanup, "--fake")
    wrong = secrets.token_hex(32)
    err = "".join(s.stderr)
    assert f"agencast mcp: http://127.0.0.1:{s.port}/mcp — project {root} · allow run · input dirs: none · fake " \
           "provider · token from AGENCAST_MCP_TOKEN · hosts: 127.0.0.1, localhost, [::1]\n" == err
    stdio = Client(StdioServerParameters(command=sys.executable, args=["-m", "agencast.cli", "--project", str(root),
                                                                        "mcp", "--fake"],
                                         env=env_for(root, registry), cwd=root.parent))
    expected = tools(stdio)
    assert {t["name"] for t in expected} >= {"fake_run", "dry_run"} and "run_scenario" not in {t["name"] for t in expected}

    async def read_card():
        async with s.client() as client:
            return (await client.read_resource(RUN_CARD)).contents[0].text

    assert (html := anyio.run(read_card)).lower().startswith(("<!doctype html>", "<html")) and "ui/initialize" in html
    for mode in ("legacy", "auto"):
        assert tools(s.client(mode)) == expected
        assert [p["name"] for p in s.call("list_projects", mode=mode)["projects"]] == ["lumen"]
        run_id = s.call("fake_run", {"project": "lumen", "scenario": "demo", "inputs": {"topic": "t"}}, mode)["run_id"]
        cleanup.run_ids.append(run_id)
        done = s.call("wait_run", {"project": "lumen", "run_id": run_id, "timeout_s": 20}, mode)
        assert (done["state"], done["outputs"]) == ("succeeded", {"text": "Fake response."})

    # the token: missing or wrong → 401 before the MCP layer; the SDK client cannot connect
    for headers in ({}, {"Authorization": f"Bearer {wrong}"}):
        r = httpx2.post(s.url, json=INIT, headers=JSON | headers)
        assert (r.status_code, r.headers["www-authenticate"], r.text) == (401, "Bearer", "missing or wrong bearer token")
        r = httpx2.post(s.url, json={"jsonrpc": "2.0", "id": 2, "method": "resources/read",
                                     "params": {"uri": RUN_CARD}}, headers=JSON | headers)
        assert (r.status_code, r.headers["www-authenticate"], r.text) == (401, "Bearer", "missing or wrong bearer token")
    for token in ("", wrong):
        for mode in ("legacy", "auto"):
            with pytest.raises(Exception):
                tools(s.client(mode, token=token))
    with s.raw() as raw:
        r = raw.post("/mcp", json=INIT, headers=JSON)
        assert r.status_code == 200 and "mcp-session-id" not in r.headers  # stateless
        assert sse(r)["result"]["serverInfo"]["name"] == "agencast"
        for method in ("GET", "DELETE"):  # POST only
            r = raw.request(method, "/mcp")
            assert (r.status_code, r.headers["allow"]) == (405, "POST")
        assert httpx2.get(s.url).status_code == 401
        # Host and Origin
        assert raw.post("/mcp", json=INIT, headers=JSON | {"Host": "evil.example"}).status_code == 421
        assert raw.post("/mcp", json=INIT, headers=JSON | {"Origin": "https://evil.example"}).status_code == 403
        assert raw.post("/mcp", json=INIT, headers=JSON | {"Host": f"localhost:{s.port}"}).status_code == 200
        assert raw.post("/mcp", json=INIT, headers=JSON | {"Origin": f"http://localhost:{s.port}"}).status_code == 200
        # bounds: 4 MiB per request, which a text of 1,000,000 ASCII characters fits
        assert raw.post("/mcp", content=b" " * (5 * 2**20), headers=JSON).status_code == 413
    big = s.call("validate", {"project": "lumen", "kind": "agent", "name": "big", "text": "x" * 1_000_000})
    assert big["valid"] is False and big["path"] == "agents/big.md"
    idle = [socket.create_connection(("127.0.0.1", s.port)) for _ in range(40)]  # no bound on connections: no 503
    try:
        assert [p["name"] for p in s.call("list_projects", mode="auto")["projects"]] == ["lumen"]
    finally:
        for sock in idle:
            sock.close()
    assert s.stop() == -signal.SIGTERM
    err = "".join(s.stderr)
    assert s.token not in err and wrong not in err and "".join(s.stdout) == ""
    assert err.endswith("agencast mcp: stopped — runs continue in their own processes\n")


def test_http_allow_host_and_levels(root, registry, cleanup):
    """--allow-host adds a name to the Host check (an IPv6 address in brackets either way); --http --allow read lists
    no run tools."""
    s = Http(root, registry, cleanup, "--allow", "read", "--allow-host", "100.64.0.7", "--allow-host", "fd7a:115c::1",
             "--allow-host", "[fd7a:115c::2]")
    assert "hosts: 127.0.0.1, localhost, [::1], 100.64.0.7, [fd7a:115c::1], [fd7a:115c::2]\n" in "".join(s.stderr)
    with s.raw() as raw:
        assert raw.post("/mcp", json=INIT, headers=JSON | {"Host": f"100.64.0.7:{s.port}"}).status_code == 200
        for host in (f"[fd7a:115c::1]:{s.port}", "[fd7a:115c::1]", f"[fd7a:115c::2]:{s.port}"):
            assert raw.post("/mcp", json=INIT, headers=JSON | {"Host": host}).status_code == 200
        assert raw.post("/mcp", json=INIT, headers=JSON | {"Origin": "https://100.64.0.7"}).status_code == 200
        assert raw.post("/mcp", json=INIT, headers=JSON | {"Host": "100.64.0.8"}).status_code == 421
    names = {t["name"] for t in tools(s.client())}
    assert "list_projects" in names and not names & RUN_TOOLS
    assert s.stop() == -signal.SIGTERM


def test_http_restarts_and_runs(root, registry, cleanup):
    """A slow fake run: the token reaches no worker, waits do not block each other, one SDK session (both modes)
    outlives restarts of the server on the same port, the run outlives them too, and the listener is free at once
    after every stop, also with a kept-alive connection open."""
    script = slow_script(root)
    s = Http(root, registry, cleanup, "--fake", str(script))
    port, token = s.port, s.token

    async def go():
        async with s.client("legacy") as legacy, s.client("auto") as auto:
            started = (await legacy.call_tool("fake_run", {"project": "lumen", "scenario": "demo",
                                                           "inputs": {"topic": "t"}})).structured_content
            run_id = started["run_id"]
            cleanup.run_ids.append(run_id)
            pid = until(lambda: next(iter(worker_pids(run_id)), None))
            with open(f"/proc/{pid}/environ", "rb") as f:
                assert b"AGENCAST_MCP_TOKEN" not in f.read()
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                assert token.encode() not in f.read()

            async def timed(c, tool, args, out):
                begin = time.monotonic()
                r = await c.call_tool(tool, args)
                out.append((tool, time.monotonic() - begin, r.structured_content))
            waits, quick = [], []
            wait = {"project": "lumen", "run_id": run_id, "timeout_s": 3}
            async with anyio.create_task_group() as tg:
                tg.start_soon(timed, legacy, "wait_run", wait, waits)
                tg.start_soon(timed, auto, "wait_run", wait, waits)
                await anyio.sleep(0.5)
                await timed(legacy, "list_projects", {}, quick)
            assert [w[2]["done"] for w in waits] == [False, False] and all(w[1] < 4 for w in waits)
            assert quick[0][1] < 1

            # the server stops with a call in flight, which still gets its answer (up to 5 s); the worker goes on; a
            # new server on the same port serves the same sessions
            answer, call = [], {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                                "params": {"name": "wait_run", "arguments": wait | {"timeout_s": 1}}}

            def post():
                with s.raw() as raw:
                    answer.append(raw.post("/mcp", json=call, headers=JSON))
            async with anyio.create_task_group() as tg:
                tg.start_soon(anyio.to_thread.run_sync, post)
                await anyio.sleep(0.5)  # the wait_run(1) is in the server
                assert await anyio.to_thread.run_sync(s.stop) == -signal.SIGTERM
            assert sse(answer[0])["result"]["structuredContent"]["done"] is False
            assert "ERROR" not in "".join(s.stderr)
            assert worker_pids(run_id)
            new = Http(root, registry, cleanup, "--fake", str(script), port=port, token=token)
            for c in (legacy, auto):
                assert [p["name"] for p in (await c.call_tool("list_projects", {})).structured_content["projects"]] \
                       == ["lumen"]
            done = (await auto.call_tool("wait_run", {"project": "lumen", "run_id": run_id, "timeout_s": 20})
                    ).structured_content
            assert (done["state"], done["outputs"]) == ("succeeded", {"text": "slow answer"})
            return new
    s = anyio.run(go)
    for _ in range(3):  # restartable listener: a kept-alive connection open while the server stops
        with s.raw() as raw:
            assert raw.post("/mcp", json=INIT, headers=JSON).status_code == 200
            assert s.stop() == -signal.SIGTERM
            stopped = time.monotonic()
            s = Http(root, registry, cleanup, "--fake", str(script), port=port, token=token)
            assert time.monotonic() - stopped < 5 and "cannot start server" not in "".join(s.stderr)
        assert [p["name"] for p in s.call("list_projects")["projects"]] == ["lumen"]
    assert s.stop() == -signal.SIGTERM


def test_http_stop_cancels_a_dry_run(root, registry, cleanup, tmp_path):
    """SIGTERM while a dry run with a file input waits for an MCP server that takes 30 s to start: the stop gives the
    call its 5 s, not more — the dry run is cancelled (no plan), the copy removed, the server ends killed by the
    signal."""
    pics, tmp = pictures(tmp_path)
    marker, wf = tmp_path / "mcp-started", root / "workflows"
    setup(wf)  # MCP server `fs` and agent `tester`
    code = (f"import sys, time; open({str(marker)!r}, 'w').close(); time.sleep(30); sys.argv[1:] = sys.argv[-1:]; "
            f"exec(open({str(FAKE_MCP)!r}).read())")
    (wf / "mcp.yaml").write_text((wf / "mcp.yaml").read_text().replace(f"[{json.dumps(str(FAKE_MCP))}, ",
                                                                       f"[\"-c\", {json.dumps(code)}, "))
    (wf / "scenarios" / "probe.yaml").write_text("version: 1\nname: probe\ndescription: Probe\n"
                                                 "inputs: { photo: { type: file, required: true } }\n"
                                                 "steps:\n  - id: t\n    task: { agent: tester, prompt: Look }\n")
    s = Http(root, registry, cleanup, "--input-dir", str(pics), TMPDIR=str(tmp))
    call = {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "dry_run", "arguments": {
        "project": "lumen", "scenario": "probe", "inputs": {"photo": str(pics / "photo.png")}}}}

    def post():
        try:
            with s.raw() as raw:
                raw.post("/mcp", json=call, headers=JSON, timeout=40)
        except httpx2.HTTPError:  # a call still in flight after 5 s gets no answer
            pass
    threading.Thread(target=post, daemon=True).start()
    until(marker.exists)
    assert len(copies(tmp)) == 1
    stopped = time.monotonic()
    assert s.stop(timeout=25) == -signal.SIGTERM and time.monotonic() - stopped < 20
    assert copies(tmp) == [] and not list((root / "runs").glob("*-probe-*"))


# --- systemd (where `systemctl --user` is available) ---------------------------------------------------------------

def systemctl(*args, check=False):
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, check=check, timeout=30)


def user_systemd() -> bool:
    return bool(shutil.which("systemd-run")) and systemctl("show", "--property=Version").returncode == 0


def unit_props(unit) -> dict[str, str]:
    out = systemctl("show", unit, "--property=ActiveState,Result,NRestarts").stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def state(root, run_id):
    info = api.run_detail(root, run_id)
    return info and info["state"]


@pytest.mark.skipif(not user_systemd(), reason="no systemd user manager (systemctl --user)")
def test_systemd_units(root, registry, cleanup):
    """Transient user units as the documented service: KillMode=process keeps runs over a restart, the default
    KillMode interrupts them; stop is a success and `kill` ends the unit and its runs without a restart."""
    script, token, units, run_ids = slow_script(root), secrets.token_hex(32), [], []

    def start(*props):
        unit, port = f"agencast-mcp-test-{secrets.token_hex(4)}", free_port()
        units.append(unit)
        subprocess.run(["systemd-run", "--user", "--quiet", f"--unit={unit}", *props, "-p", "Restart=on-failure",
                        f"--setenv=AGENCAST_MCP_TOKEN={token}", f"--setenv=AGENCAST_CONFIG_DIR={registry.parent}",
                        sys.executable, "-m", "agencast.cli", "--project", str(root), "mcp", "--http", "--fake",
                        str(script), "--port", str(port)], check=True, capture_output=True, timeout=30)
        url = f"http://127.0.0.1:{port}/mcp"
        until(lambda: listening(port), 15)
        return unit, url

    def slow_run(url):
        async def go():
            async with Client(streamable_http_client(url, http_client=httpx2.AsyncClient(
                    headers={"Authorization": f"Bearer {token}"}, timeout=30)), mode="legacy") as c:
                r = await c.call_tool("fake_run", {"project": "lumen", "scenario": "demo", "inputs": {"topic": "t"}})
                return r.structured_content["run_id"]
        run_id = anyio.run(go)
        run_ids.append(run_id)
        cleanup.run_ids.append(run_id)
        until(lambda: state(root, run_id) == "running", 10)
        return run_id

    try:
        unit, url = start("-p", "KillMode=process")  # (1) restart: the run goes on
        run_id = slow_run(url)
        systemctl("restart", unit, check=True)
        until(lambda: state(root, run_id) == "succeeded", 15)
        systemctl("stop", unit, check=True)  # (3) stop: a clean end, not `failed`
        props = unit_props(unit)
        assert (props["ActiveState"], props["Result"]) == ("inactive", "success"), props

        unit, url = start()  # (2) default KillMode: a restart ends the run
        run_id = slow_run(url)
        systemctl("restart", unit, check=True)
        until(lambda: state(root, run_id) == "interrupted", 15)
        systemctl("stop", unit, check=True)

        unit, url = start("-p", "KillMode=process")  # (4) kill: server and runs end, no restart
        run_id = slow_run(url)
        systemctl("kill", unit, check=True)
        until(lambda: state(root, run_id) == "interrupted", 15)
        time.sleep(1)  # RestartSec defaults to 100 ms: a restart would have happened by now
        props = unit_props(unit)
        assert props["ActiveState"] == "inactive" and props.get("NRestarts", "0") == "0", props
    finally:
        for unit in units:
            systemctl("kill", unit)
            systemctl("stop", unit)
            systemctl("reset-failed", unit)
        for run_id in run_ids:
            until(lambda: not worker_pids(run_id), 10)
