"""MCP servers: mcp.yaml diagnostics and the Pool's failure paths — offline: fake provider, fake stdio server
(tests/fake_mcp_server.py, wrapped where a test needs it to misbehave) and a stdlib stand-in for a remote server."""
import asyncio
import gc
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx2
import pytest
from conftest import FAKE_MCP, events, run, scenario
from test_task import HEAD, calls, children, errors, setup, task_sc

from agencast import AgencastError, ConfigErrors, api, mcp_client
from agencast.engine import dry_run
from agencast.mcp_client import Pool, describe
from agencast.record import Record
from agencast.validate import validate

# The fake server imported as module `f`: a test appends what the server should do (f.main() = serve normally).
WRAP = f"import sys; sys.path.insert(0, {str(FAKE_MCP.parent)!r}); import fake_mcp_server as f; "


def server(wf, settings: str, **kw):
    """Agent `tester` (test_task.setup) with server `fs` replaced by `settings` (YAML lines of the entry)."""
    setup(wf, **kw)
    lines = "".join(f"    {line}\n" for line in settings.splitlines())
    (wf / "mcp.yaml").write_text(f"version: 1\nservers:\n  fs:\n    description: Test server\n    agents: [tester]\n{lines}")


def python(code: str, root="{run_dir}/work") -> str:
    return f"command: {json.dumps(sys.executable)}\nargs: {json.dumps(['-c', code, root])}"


# --- mcp.yaml: errors name the field and the line, valid servers stay known ---------------------

@pytest.mark.parametrize("entry, msg", [
    ("command: x\n    url: https://mcp.example.com", "line 9: servers.bad: server must have either command or url (exactly one)"),
    ("", "line 9: servers.bad: server must have either command or url (exactly one)"),
    ("command: x\n    agnets: [a]", "line 13: servers.bad.agnets: unknown field 'agnets' (typo?)"),
    ("command: x\n    transport: sse", "line 13: servers.bad.transport: field 'transport' is only allowed with url"),
    ("url: https://mcp.example.com\n    env: { A: B }", "line 13: servers.bad.env: field 'env' is only allowed with command"),
    ("url: https://mcp.example.com\n    timeouts: { handshake: 10 }", "servers.bad.timeouts.handshake: expected string, got number"),
    ("command: x\n    env: { PATH: MY_VAR }", "servers.bad.env: variable 'PATH' must not be set for a server (not allowed: PATH, HOME,"),
    ("command: x\n    env: { lower: MY_VAR }", "servers.bad.env: variable name does not match pattern ^[A-Z][A-Z0-9_]*$ "
                                               "(expected NAME_FOR_SERVER: NAME_ON_HOST)"),
    # a line pasted from .env, or the key itself where the name belongs: named by its place, never quoted
    ("command: x\n    env: { GITHUB_TOKEN=sk-or-v1-SECRETdeadbeef0123456789 }", "servers.bad.env: variable name does not match"),
    ("command: x\n    env:\n      sk-or-v1-SECRETdeadbeef0123456789: MY_VAR", "servers.bad.env: variable name does not match"),
    ("command: x\n    env: { TOKEN: sk-or-pasted-key-123 }", "servers.bad.env.TOKEN: value does not match pattern ^[A-Z][A-Z0-9_]*$ — "
                                                           "expected the NAME of an environment variable, not its value"),
    ("url: http://mcp.example.com/x", "line 12: servers.bad.url: value does not match pattern"),
    # plain http only to loopback: userinfo must not smuggle another host in (httpx: host = example.com)
    ('url: "http://127.0.0.1:1@example.com/mcp"', "servers.bad.url: value does not match pattern"),
    ('url: "http://localhost:x@example.com/mcp"', "servers.bad.url: value does not match pattern"),
    ('url: "http://127.0.0.1@example.com/"', "servers.bad.url: value does not match pattern"),
    ("url: http://localhost.example.com/", "servers.bad.url: value does not match pattern"),
])
def test_mcp_yaml_error_names_field_and_line(wf, entry, msg):
    setup(wf)
    with open(wf / "mcp.yaml", "a") as f:
        f.write(f"  bad:\n    description: Broken entry\n    agents: [tester]\n    {entry}\n")
    got = errors(task_sc(wf))
    assert msg in got, got
    assert "any allowed form" not in got and "sk-or" not in got, got
    assert "is not in workflows/mcp.yaml" not in got, got  # `fs` is valid: one broken entry does not hide it
    assert "sk-or" not in json.dumps(api.describe_project(wf.parent))  # what GET /projects/<p> returns


@pytest.mark.parametrize("url", ["http://127.0.0.1:8080/mcp", "http://localhost/mcp", "http://localhost:9",
                                 "https://user@mcp.example.com/mcp"])
def test_mcp_yaml_url_accepted(wf, url):
    server(wf, f"url: {json.dumps(url)}")
    assert validate(task_sc(wf), check_models=False)


def test_broken_mcp_yaml_blocks_the_run_without_false_errors(wf):
    setup(wf)
    good = (wf / "mcp.yaml").read_text()
    (wf / "mcp.yaml").write_text(good.replace("agents: [tester]", "agnets: [tester]"))  # the agent's own server
    got = errors(task_sc(wf))  # still a config error (errors() expects ConfigErrors) …
    assert "servers.fs.agnets: unknown field 'agnets'" in got and "servers.fs: missing required field 'agents'" in got
    assert "is not in workflows/mcp.yaml" not in got, got  # … but the server is there
    (wf / "mcp.yaml").write_text(good + "  x: [unclosed\n")  # unreadable file: no server is known to be missing
    got = errors(task_sc(wf))
    assert "mcp.yaml, line" in got and "is not in workflows/mcp.yaml" not in got, got
    (wf / "mcp.yaml").write_bytes(b"\xff\xfe\x00bin")  # not text at all: a config error, not a traceback
    assert "mcp.yaml: cannot read the file (not UTF-8 text)" in errors(task_sc(wf))
    (wf / "mcp.yaml").write_text(good)
    (wf / "config.yaml").write_bytes(b"\xff\xfe\x00bin")
    assert errors(task_sc(wf)) == "config.yaml: cannot read the file (not UTF-8 text)"


# --- start failures -----------------------------------------------------------------------------

def test_start_failure_quotes_stderr_and_prints_no_traceback(wf, capfd):
    server(wf, python("import sys; print('fatal: cannot open database', file=sys.stderr); sys.exit(3)"))
    r, _ = run(task_sc(wf))
    assert r.error["class"] == "config", r.error
    assert r.error["message"].endswith("MCPError: Connection closed; stderr: fatal: cannot open database"), r.error
    assert events(r, "mcp_server")[0]["error"] == r.error["message"]
    assert "Traceback" not in capfd.readouterr().err  # one config line for the user, no Python traceback


def test_non_json_stdout_is_named_instead_of_a_timeout(wf):
    server(wf, python("import sys; print('Welcome to my server v1', flush=True); sys.stdin.read()")
           + "\ntimeouts: { handshake: 1s }")
    r, _ = run(task_sc(wf))
    assert r.error["class"] == "config" and "wrote a line that is not a JSON-RPC message" in r.error["message"], r.error
    assert r.error["message"].endswith(": Welcome to my server v1") and "did not respond" not in r.error["message"]


TRICKY = 'pass"word\\with-quote-123'  # a `"` and a `\`: Python's repr and JSON escape it differently


def record_text(r) -> str:
    return "".join(f.read_text() for f in r.rec.dir.rglob("*") if f.is_file() and f.suffix != ".png")


def test_json_stdout_line_is_quoted_as_json_so_that_its_secret_is_masked(wf, monkeypatch):
    """A stdout line that is JSON, just not JSON-RPC, reaches the client parsed; quoted with str() it was Python's
    repr of a dict — a form of the secret that masking does not know."""
    monkeypatch.setenv("AGENCAST_TEST_MCP_SECRET", TRICKY)
    server(wf, python("import json, os, sys; print(json.dumps(dict(token=os.environ['SERVER_SECRET'])), flush=True); "
                      "sys.stdin.read()") + "\ntimeouts: { handshake: 1s }\nenv: { SERVER_SECRET: AGENCAST_TEST_MCP_SECRET }")
    r, _ = run(task_sc(wf))
    assert r.error["class"] == "config", r.error
    assert r.error["message"].endswith(': {"token": "<secret: AGENCAST_TEST_MCP_SECRET>"}'), r.error
    assert "with-quote-123" not in record_text(r)


def test_pydantic_errors_are_quoted_without_the_server_input(wf, monkeypatch):
    """pydantic quotes the invalid value cut to its start and end: part of a secret, which masking (whole values)
    cannot find. Both in a handshake answer and in a tool result."""
    monkeypatch.setenv("AGENCAST_TEST_MCP_SECRET", "sk-or-v1-0123456789abcdefghij")
    leak = "f.os.environ['SERVER_SECRET'] + '-' * 60"
    server(wf, python(WRAP + f"\nreply = f.reply\ndef bad(id_, result=None, error=None):\n"
                             f"    if result and 'capabilities' in result: result['capabilities'] = {leak}\n"
                             f"    reply(id_, result, error)\nf.reply = bad\nf.main()")
           + "\nenv: { SERVER_SECRET: AGENCAST_TEST_MCP_SECRET }")
    r, _ = run(task_sc(wf))
    assert r.error["class"] == "config" and "failed to start" in r.error["message"], r.error
    assert "ValidationError: capabilities: Input should be" in r.error["message"], r.error
    assert "sk-or-v1" not in record_text(r) and "input_value" not in record_text(r)
    server(wf, python(WRAP + f"f.call = lambda *a: {leak}; f.main()") + "\nenv: { SERVER_SECRET: AGENCAST_TEST_MCP_SECRET }")
    r, _ = run(task_sc(wf, name="result"), script={"t": [calls(("fs__red_pixel", {}))]})
    assert r.error == {"class": "config", "step": "t", "message": "tool fs.red_pixel failed: ValidationError: content: "
                                                                  "Input should be a valid list"}, r.error
    assert "sk-or-v1" not in record_text(r) and "Traceback" not in record_text(r)
    # … and in a message the SDK built from pydantic's own text (a remote answer that is not JSON-RPC)
    sdk = "Failed to parse JSON response: 1 validation error for X\nid\n  Field required [type=missing, input_value={'token': 'sk-or-v1-01...'}, input_type=dict]"
    assert describe(ValueError(sdk)) == "ValueError: Failed to parse JSON response: 1 validation error for X\nid\n  Field required [type=missing]"


def test_failed_start_is_not_cached(tmp_path):
    """Pool.get contract for the handshake retry: the next get() starts the server again."""
    script = tmp_path / "server.py"  # does not exist yet: python exits with 'can't open file'
    spec = {"fs": {"command": sys.executable, "args": [str(script), str(tmp_path)]}}

    async def main():
        rec = Record(tmp_path / "run", {})
        pool = Pool(spec, rec.dir, rec)
        try:
            with pytest.raises(AgencastError, match="failed to start"):
                await pool.get("fs")
            shutil.copy(FAKE_MCP, script)
            assert "read_text_file" in (await pool.get("fs")).tools
        finally:
            await pool.close()
        return rec

    assert [e["action"] for e in asyncio.run(main()).events] == ["failed", "started", "stopped"]
    assert children() == []


def test_stderr_log_keeps_the_start_that_failed(wf, tmp_path):
    """A later step starts the server again: the log of the failed start, which its error points to, must stay."""
    once = tmp_path / "failed-once"
    server(wf, python(WRAP + f"\nif f.os.path.exists({str(once)!r}):\n    f.main()\n    sys.exit(0)\n"
                             f"open({str(once)!r}, 'w').close()\n"
                             "print('fatal: cannot open database', file=sys.stderr); sys.exit(3)"))
    scenario(wf, HEAD + """
steps:
  - id: one
    on_error: continue
    task: { agent: tester, prompt: "Complete the task" }
  - id: two
    task: { agent: tester, prompt: "Complete the task" }
""")
    r, _ = run(wf / "scenarios" / "test.yaml", script={"two": [{"text": "ok"}]})
    assert r.status == "succeeded" and [e["action"] for e in events(r, "mcp_server")] == ["failed", "started", "stopped"]
    assert "(stderr: mcp/fs.stderr.log)" in events(r, "error")[0]["message"]
    log = (r.rec.dir / "mcp/fs.stderr.log").read_text()
    assert "fatal: cannot open database" in log and "fake-mcp: root" in log, log


# --- a start that is abandoned: interrupt, step or run deadline ---------------------------------

HANGS = python("import time; time.sleep(60)") + "\ntimeouts: { handshake: 30s }"  # never answers `initialize`


def test_close_ends_a_start_in_flight(tmp_path):
    """close() while a server is still in its handshake (Ctrl-C, `serve` stopping, the run's end after a step
    deadline) used to wait for timeouts.handshake — longer than the 15 s `serve` waits, which left the server
    running — and asyncio printed 'Future exception was never retrieved' for the start nobody waited for."""
    spec = {"fs": {"command": sys.executable, "args": ["-c", "import time; time.sleep(60)"], "timeouts": {"handshake": "30s"}}}
    noise = []

    async def main():
        asyncio.get_running_loop().set_exception_handler(lambda loop, ctx: noise.append(ctx["message"]))
        rec = Record(tmp_path / "run", {})
        pool = Pool(spec, rec.dir, rec)
        waiter = asyncio.create_task(pool.get("fs"))
        await asyncio.sleep(0.5)  # the process runs, the handshake is in flight
        assert len(children()) == 1
        waiter.cancel()
        await pool.close()
        return rec

    t0 = time.monotonic()
    rec = asyncio.run(main())
    gc.collect()
    assert time.monotonic() - t0 < 10 and children() == [] and noise == []
    assert [(e["action"], e.get("error")) for e in rec.events] == [("stopped", None)]


def test_close_during_the_teardown_of_a_failed_start_stops_the_server(tmp_path):
    """After a failed handshake the SDK closes the server's stdin and waits before it kills. A close() in that wait
    (Ctrl-C, `serve` stopping, a step deadline) used to cancel the owner task natively, inside the SDK's shielded
    teardown: the kill never came and close() waited for the server to exit by itself — forever for one that hangs."""
    eof = tmp_path / "stdin-closed"  # the server sees EOF = the teardown has begun; it ignores it for 20 s
    code = f"import sys, time; sys.stdin.read(); open({str(eof)!r}, 'w').close(); time.sleep(20)"
    spec = {"fs": {"command": sys.executable, "args": ["-c", code], "timeouts": {"handshake": "1s"}}}

    async def main():
        rec = Record(tmp_path / "run", {})
        pool = Pool(spec, rec.dir, rec)
        waiter = asyncio.create_task(pool.get("fs"))
        while not eof.exists():
            await asyncio.sleep(0.05)
        await pool.close()
        await asyncio.gather(waiter, return_exceptions=True)
        return rec

    t0 = time.monotonic()
    rec = asyncio.run(main())
    assert time.monotonic() - t0 < 10 and children() == []
    assert len(rec.events) == 1 and (rec.dir / "mcp/fs.stderr.log").is_file(), rec.events  # the start is on record


@pytest.mark.parametrize("kind", ["stdio", "remote"])
def test_step_deadline_during_a_handshake_ends_the_run(wf, kind, capfd):
    with socket.create_server(("127.0.0.1", 0)) as listener:  # accepts (backlog) and never answers
        server(wf, HANGS if kind == "stdio" else
               f"url: http://127.0.0.1:{listener.getsockname()[1]}/mcp\ntimeouts: {{ handshake: 30s }}")
        t0 = time.monotonic()
        r, _ = run(task_sc(wf, step="timeout: 1s"))
    assert r.error["class"] == "timeout" and time.monotonic() - t0 < 10, r.error
    assert [e["action"] for e in events(r, "mcp_server")] == ["stopped"] and children() == []
    gc.collect()
    assert "never retrieved" not in capfd.readouterr().err


def test_dry_run_names_missing_server_variable(wf, monkeypatch):
    monkeypatch.delenv("AGENCAST_TEST_NOPE", raising=False)
    setup(wf, env="    env: { X: AGENCAST_TEST_NOPE }\n")
    rec = dry_run(validate(task_sc(wf), check_models=False), {})  # a dry run has no preflight
    plan = (rec.dir / "plan.md").read_text()
    assert "missing environment variable AGENCAST_TEST_NOPE (MCP server fs in mcp.yaml)" in plan and "KeyError" not in plan


# --- stderr log ---------------------------------------------------------------------------------

def test_stderr_is_never_raw_in_the_run_directory(wf, monkeypatch):
    monkeypatch.setenv("AGENCAST_TEST_MCP_SECRET", "very-secret-value-42")
    server(wf, python(WRAP + "print('token', f.os.environ['SERVER_SECRET'], file=sys.stderr, flush=True); f.main()",
                      root="{run_dir}") + "\nenv: { SERVER_SECRET: AGENCAST_TEST_MCP_SECRET }")
    r, _ = run(task_sc(wf), script={"t": [calls(("fs__read_text_file", {"path": "mcp/fs.stderr.log"})), {"text": "ok"}]})
    assert r.status == "succeeded", r.error
    assert events(r, "tool_call")[0]["is_error"]  # while the server runs, its stderr is not in the run directory
    log = (r.rec.dir / "mcp/fs.stderr.log").read_text()  # written (masked) when the server stopped
    assert "token <secret: AGENCAST_TEST_MCP_SECRET>" in log and "very-secret-value-42" not in log


# --- a server that dies during a call ------------------------------------------------------------

def test_crashed_server_is_recorded_as_failed(wf):
    server(wf, python(WRAP + "f.call = lambda *a: f.os._exit(3); f.main()"))
    r, _ = run(task_sc(wf), script={"t": [calls(("fs__broken", {}))]})
    assert r.error["class"] == "config", r.error
    assert r.error["message"] == "MCP server 'fs' closed the connection while calling broken (see mcp/fs.stderr.log)"
    last = events(r, "mcp_server")[-1]
    assert (last["action"], last["error"]) == ("failed", r.error["message"])


def test_image_that_is_not_base64_is_an_invalid_answer(wf):
    """It used to fail the step as `internal`, with a traceback of the framework in the record and the callback."""
    server(wf, python(WRAP + "f.call = lambda *a: [dict(type='image', mimeType='image/png', data='abc')]; f.main()"))
    r, _ = run(task_sc(wf), script={"t": [calls(("fs__red_pixel", {}))]})
    assert r.error == {"class": "config", "step": "t", "message": "tool fs.red_pixel returned an image that is not base64"}
    assert events(r, "tool_call")[0]["error"] == r.error["message"]


def test_close_cancelled_still_stops_the_server(tmp_path):
    """A server that ignores stdin EOF is killed by the SDK after its grace period — also when close() is cancelled."""
    spec = {"fs": {"command": sys.executable,
                   "args": ["-c", WRAP + "\ntry: f.main()\nfinally: __import__('time').sleep(30)", str(tmp_path)]}}

    async def main():
        rec = Record(tmp_path / "run", {})
        pool = Pool(spec, rec.dir, rec)
        await pool.get("fs")
        closing = asyncio.create_task(pool.close())
        await asyncio.sleep(0.3)
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing

    t0 = time.monotonic()
    asyncio.run(main())
    assert time.monotonic() - t0 < 15 and children() == []  # not the 30 s the server would take on its own


# --- remote servers ------------------------------------------------------------------------------

@pytest.fixture
def remote():
    """Stand-in for a remote MCP server (streamable HTTP). `mode`: an HTTP status answered to every request,
    "drop" = the handshake works and offers `echo`, tools/call closes the connection without an answer,
    "flaky" = like "drop", but the first POST is answered with 503, "busy" = … with 429 and `Retry-After: 1`,
    "hangup" = … closed without an answer, "deaf" = like "drop", with a session whose DELETE is not answered,
    "trickle" = … is answered at once, its body a byte at a time, "nolist" = like "trickle", tools/list is refused."""
    started, closing = [], threading.Event()

    def start(mode) -> str:
        failed = []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def answer(self, status, body=b""):
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                if getattr(self, "retry_after", False):
                    self.send_header("retry-after", "1")
                if mode in ("deaf", "trickle", "nolist"):
                    self.send_header("mcp-session-id", "s1")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self.retry_after = mode == 429  # SSE: the refused request is this GET of the event stream
                self.answer(405 if isinstance(mode, str) else mode)

            def do_DELETE(self):
                if mode == "deaf":
                    closing.wait(10)
                if mode in ("trickle", "nolist"):
                    self.send_response(200)
                    self.send_header("content-length", "1000")
                    self.end_headers()
                    try:
                        for _ in range(100):  # 10 s, no read waits longer than 0.1 s
                            if closing.wait(0.1):
                                break
                            self.wfile.write(b"x")
                            self.wfile.flush()
                    except OSError:  # the client gave up
                        pass
                    self.close_connection = True
                    return
                self.answer(200)

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers["content-length"])))
                if mode in ("flaky", "busy", "hangup") and not failed:
                    failed.append(req)
                    if mode == "hangup":
                        self.close_connection = True
                        return self.connection.shutdown(socket.SHUT_RDWR)
                    self.retry_after = mode == "busy"
                    return self.answer(503 if mode == "flaky" else 429, b'{"error": "status test"}')
                if not isinstance(mode, str):
                    return self.answer(mode, b'{"error": "status test"}')
                if "id" not in req:  # notification
                    return self.answer(202)
                if req["method"] == "tools/call":
                    self.close_connection = True
                    return self.connection.shutdown(socket.SHUT_RDWR)
                if mode == "nolist" and req["method"] == "tools/list":
                    return self.answer(200, json.dumps({"jsonrpc": "2.0", "id": req["id"],
                                                        "error": {"code": -32601, "message": "no tools"}}).encode())
                result = {"initialize": {"protocolVersion": req["params"].get("protocolVersion"),
                                         "capabilities": {"tools": {}}, "serverInfo": {"name": "t", "version": "1"}},
                          "tools/list": {"tools": [{"name": "echo", "inputSchema": {"type": "object"}}]}}[req["method"]]
                self.answer(200, json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}).encode())

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        started.append(srv)
        return f"http://127.0.0.1:{srv.server_port}/mcp"

    yield start
    closing.set()
    for srv in started:
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def sse():
    """Stand-in for a remote MCP server with the SSE transport: GET opens the event stream and names the message
    endpoint, every message POST is answered with `status`."""
    started, closing = [], threading.Event()

    def start(status) -> str:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b"event: endpoint\ndata: /messages?session_id=1\n\n")
                self.wfile.flush()
                closing.wait(30)

            def do_POST(self):
                self.rfile.read(int(self.headers["content-length"]))
                self.send_response(status)
                self.send_header("content-length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        started.append(srv)
        return f"http://127.0.0.1:{srv.server_port}/sse"

    yield start
    closing.set()
    for srv in started:
        srv.shutdown()
        srv.server_close()


@pytest.mark.parametrize("status, cls, text", [
    (503, "transient", "failed to start: HTTP 503: "),
    (429, "transient", "failed to start: HTTP 429: "),
    (401, "config", "failed to start: HTTP 401 (check bearer_token_env in mcp.yaml: not set): "),
])
def test_http_status_of_a_failed_handshake(wf, remote, status, cls, text):
    """The SDK reports any non-2xx of streamable HTTP as 'Server returned an error response' — the status decides the class."""
    server(wf, f"url: {remote(status)}")
    r, _ = run(task_sc(wf))
    assert r.error["class"] == cls and text in r.error["message"], r.error
    assert events(r, "error")[-1]["http_status"] == status


@pytest.mark.parametrize("status, cls, text", [
    (401, "config", "failed to start: HTTP 401 (check bearer_token_env in mcp.yaml: not set): "),
    (503, "transient", "failed to start: HTTP 503: "),
])
def test_sse_status_of_a_refused_message_is_not_a_handshake_timeout(wf, sse, status, cls, text):
    """The SDK only logs a refused message POST and the handshake runs into its limit: it used to be reported as
    'did not respond' — transient and retried, without the status or the hint for 401."""
    server(wf, f"url: {sse(status)}\ntransport: sse\ntimeouts: {{ handshake: 1s }}")
    r, _ = run(task_sc(wf, step="retry: 0"))
    assert r.error["class"] == cls and text in r.error["message"], r.error
    assert events(r, "error")[-1]["http_status"] == status


def test_start_error_quotes_the_url_without_its_query(wf, remote):
    """httpx quotes the request URL in its error: a key in the query (or userinfo) is literal text in mcp.yaml, which
    masking does not know — and the record, the callback and the plan are served by the API."""
    url = remote(401)  # SSE: the GET of the event stream is refused
    server(wf, f"url: {url}?key=not-for-the-record\ntransport: sse")
    r, _ = run(task_sc(wf))
    assert r.error["class"] == "config" and f"for url '{url}'" in r.error["message"], r.error
    assert "not-for-the-record" not in record_text(r)
    plan = (dry_run(validate(task_sc(wf), check_models=False), {}).dir / "plan.md").read_text()
    assert f"for url '{url}'" in plan and "not-for-the-record" not in plan
    assert describe(ExceptionGroup("g", [httpx2.ConnectError("no route to https://u:p4ss@h.example/x?k=v")])) == \
        "ConnectError: no route to https://h.example/x"
    # httpx leaves an apostrophe in userinfo and query as it is: the URL does not end there, only at the closing quote
    assert describe(ValueError("for url 'https://u:pa'ss@h.example/x?k=v1'TAIL''MORE'\nsee https://h.example/doc")) == \
        "ValueError: for url 'https://h.example/x'\nsee https://h.example/doc"


def test_remote_drop_names_the_url_not_a_stderr_log(wf, remote):
    url = remote("drop")
    server(wf, f"url: {url}?key=not-for-the-record", agent_tools="[echo]")
    r, _ = run(task_sc(wf), script={"t": [calls(("fs__echo", {}))]})
    assert r.error["class"] == "config", r.error
    assert r.error["message"] == f"MCP server 'fs' closed the connection while calling echo ({url})"  # no stderr.log, no query
    assert events(r, "mcp_server")[-1]["action"] == "failed" and not (r.rec.dir / "mcp").exists()


@pytest.mark.parametrize("mode, actions", [("deaf", ["started", "stopped"]), ("trickle", ["started", "stopped"]),
                                           ("nolist", ["failed"])])
def test_session_delete_gets_its_limit_as_a_whole(tmp_path, remote, monkeypatch, mode, actions):
    """The SDK ends a remote session with a DELETE that it reads to its end, under timeouts that are per read (its
    own: 300 s): the end of every run with a server that does not answer it — or trickles its answer — waited for
    it, and so did Ctrl-C and SIGTERM, which are ignored while the servers are being stopped. A start that failed
    with a session (no tools/list) held its step the same way."""
    monkeypatch.setattr(mcp_client, "GUARD_S", 0.5)

    async def main():
        rec = Record(tmp_path / "run", {})
        pool = Pool({"fs": {"url": remote(mode)}}, rec.dir, rec)
        t0 = time.monotonic()
        try:
            await pool.get("fs")
        except AgencastError as e:
            assert mode == "nolist" and "no tools" in e.message, e.message
        await pool.close()
        return time.monotonic() - t0, rec

    took, rec = asyncio.run(main())
    assert took < 5 and [e["action"] for e in rec.events] == actions, (took, rec.events)


def test_remote_start_failure_reaches_the_step_before_the_session_is_ended(tmp_path, remote, monkeypatch):
    """A start that failed with a session open was handed to the step only after the session DELETE, up to its
    limit later: a retryable failure answered in a millisecond became a step timeout when the deadline fell in that
    window, and the server that never started was recorded as `stopped`."""
    monkeypatch.setattr(mcp_client, "GUARD_S", 0.5)

    async def main():
        rec = Record(tmp_path / "run", {})
        pool = Pool({"fs": {"url": remote("nolist")}}, rec.dir, rec)
        with pytest.raises(AgencastError, match="no tools"):
            await pool.get("fs")
        seen = [t.done() for t in pool._owners], [e["action"] for e in rec.events]
        await pool.close()
        return seen, [e["action"] for e in rec.events]

    assert asyncio.run(main()) == (([False], ["failed"]), ["failed"])  # the owner is still ending the session


def test_describe_takes_linear_time_on_a_long_server_message():
    """A remote server's JSON-RPC error message goes through `describe` uncut, on the run's event loop: both
    patterns used to be quadratic there — tens of seconds in which no step deadline and no Ctrl-C worked."""
    t0 = time.monotonic()
    assert describe(ValueError("a" * 30_000)) == "ValueError: " + "a" * 30_000
    assert describe(ValueError(", input_value=" * 6_000)) == "ValueError: " + ", input_value=" * 6_000
    assert time.monotonic() - t0 < 2
    # the bound on a scheme's length leaves no URL as it is
    assert describe(ValueError("x" * 40 + "://u:p4ss@h.example/x?k=v")) == "ValueError: " + "x" * 40 + "://h.example/x"


def test_sse_handshake_timeout_is_the_configured_one(wf):
    """SSE connects inside the transport, outside the SDK's handshake timeout: the limit used to be handshake + 5 s."""
    with socket.create_server(("127.0.0.1", 0)) as listener:  # accepts (backlog) and never answers
        server(wf, f"url: http://127.0.0.1:{listener.getsockname()[1]}/sse\ntransport: sse\ntimeouts: {{ handshake: 1s }}")
        t0 = time.monotonic()
        r, _ = run(task_sc(wf))
    assert time.monotonic() - t0 < 4
    assert r.error["class"] == "transient" and "did not respond to the handshake within 1 s" in r.error["message"], r.error


# --- a transient start is retried like a model call ----------------------------------------------

def test_transient_handshake_is_retried_per_step_retry(wf, remote):
    server(wf, f"url: {remote('flaky')}", agent_tools="[echo]")
    r, _ = run(task_sc(wf, step="retry: 1"), script={"t": [{"text": "ok"}]})
    assert r.status == "succeeded", r.error
    assert [(e["class"], e["attempt"], e["will_retry"], e["http_status"]) for e in events(r, "error")] == [
        ("transient", 1, True, 503)]
    assert [e["action"] for e in events(r, "mcp_server")] == ["failed", "started", "stopped"]
    server(wf, f"url: {remote('flaky')}", agent_tools="[echo]")
    r, _ = run(task_sc(wf, step="retry: 0", name="no-retry"))
    assert r.error["class"] == "transient" and "HTTP 503" in r.error["message"], r.error
    assert [(e["attempt"], e["will_retry"]) for e in events(r, "error")] == [(1, False)]


def test_connection_closed_without_an_answer_is_a_network_error(wf, remote):
    """A reset or a server that hangs up during the handshake is httpx's ReadError/RemoteProtocolError — neither an
    OSError nor a 'Connect…' error, so it used to be `config` and never retried."""
    server(wf, f"url: {remote('hangup')}", agent_tools="[echo]")
    r, _ = run(task_sc(wf, step="retry: 1"), script={"t": [{"text": "ok"}]})
    assert r.status == "succeeded", r.error
    assert [(e["class"], e["will_retry"], e["http_status"]) for e in events(r, "error")] == [("transient", True, None)]


def test_handshake_retry_waits_for_retry_after(wf, remote):
    """Like a model call (scenario.md `retry`): the delay a remote server asks for, not the framework's own."""
    server(wf, f"url: {remote('busy')}", agent_tools="[echo]")
    t0 = time.monotonic()
    r, _ = run(task_sc(wf, step="retry: 1"), script={"t": [{"text": "ok"}]})  # the tests' own delay is 0 s
    assert r.status == "succeeded" and time.monotonic() - t0 >= 1, r.error
    assert [(e["class"], e["will_retry"], e["http_status"]) for e in events(r, "error")] == [("transient", True, 429)]


def test_sse_refused_stream_carries_retry_after(tmp_path, remote):
    """SSE: the refused request is the GET of the event stream, not a POST — its Retry-After used to be dropped and
    the retry came after the framework's own 2 s."""
    async def main():
        rec = Record(tmp_path / "run", {})
        pool = Pool({"fs": {"url": remote(429), "transport": "sse"}}, rec.dir, rec)
        try:
            with pytest.raises(AgencastError) as e:
                await pool.get("fs")
        finally:
            await pool.close()
        return e.value

    err = asyncio.run(main())
    assert (err.cls, err.http_status, err.retry_after) == ("transient", 429, 1), err.message


# --- a tool call that did not return is still in the record ---------------------------------------

@pytest.mark.parametrize("call, step, cls, error", [
    ("1s", "", "timeout", "tool fs.slow did not respond within 1 s (may have run)"),
    ("20s", "timeout: 1s", "timeout", "cancelled before the tool answered (may have run)"),  # the step deadline
])
def test_failed_tool_call_is_recorded(wf, call, step, cls, error):
    setup(wf)
    (wf / "mcp.yaml").write_text((wf / "mcp.yaml").read_text().replace("call: 1s", f"call: {call}"))
    r, _ = run(task_sc(wf, step=step), script={"t": [calls(("fs__slow", {"seconds": 5}))]})
    assert r.error["class"] == cls, r.error
    (ev,) = events(r, "tool_call")
    assert (ev["tool"], ev["allowed"], ev["is_error"], ev["error"]) == ("slow", True, True, error)
    tool = json.loads((r.rec.dir / ev["call_file"]).read_text())
    assert tool["arguments"] == {"seconds": 5} and tool["result"] is None and tool["error"] == error
    assert children() == []


# --- a retry after a schema error only allows the answer ------------------------------------------

def test_schema_retry_never_runs_a_tool_again(wf):
    setup(wf)
    write = calls(("fs__write_file", {"path": "a.txt", "content": "once"}))
    again = calls(("fs__write_file", {"path": "a.txt", "content": "twice"}))  # a model that ignores tool_choice
    r, fake = run(task_sc(wf, ", schema: { count: integer }"), script={"t": [write, {"text": "Done."}, again, {}]})
    assert r.status == "succeeded" and r.values["steps"]["t"] == {"count": 1}, r.error
    assert len(events(r, "tool_call")) == 1 and (r.rec.dir / "work/a.txt").read_text() == "once"
    assert [e["message"] for e in events(r, "error")] == ["model did not call tool _submit_output",
                                                         "model called tools instead of answering"]
    first, second, retry, last = (b for _, _, b in fake.calls)
    assert "tool_choice" not in first and "tool_choice" not in second
    for body in (retry, last):  # level `prompt`: the answer is text, the definitions stay for the tool history
        assert body["tool_choice"] == "none"
        assert [t["function"]["name"] for t in body["tools"]] == [t["function"]["name"] for t in first["tools"]][:-1]
    feedback = retry["messages"][-1]["content"]
    assert "_submit_output" not in feedback and "already ran" in feedback and "Do not call tools." in feedback, feedback
    # before the first tool call there is nothing to repeat: the retry keeps the tools
    r, fake = run(task_sc(wf, ", schema: { count: integer }", name="preamble"),
                  script={"t": [{"text": "I will write the file."}, write, {}]})
    assert r.status == "succeeded" and len(events(r, "tool_call")) == 1, r.error
    assert "tool_choice" not in fake.calls[1][2] and "_submit_output" not in fake.calls[1][2]["messages"][-1]["content"]


# --- dry run: the plan says what is wrong with a server -------------------------------------------

def test_dry_run_plan_quotes_stderr_and_marks_tools_not_offered(wf):
    server(wf, python("import sys; print('fatal: cannot open database', file=sys.stderr); sys.exit(3)"))
    plan = (dry_run(validate(task_sc(wf), check_models=False), {}).dir / "plan.md").read_text()
    assert "failed to start: " in plan and "stderr: fatal: cannot open database" in plan, plan
    assert "stderr.log" not in plan  # the log was in the temporary directory of the dry run
    setup(wf, agent_tools="[read_text_file, ghost_tool]")
    plan = (dry_run(validate(task_sc(wf, name="ghost"), check_models=False), {}).dir / "plan.md").read_text()
    assert "tools: fs: read_text_file, ghost_tool (NOT OFFERED by the server);" in plan, plan
    assert plan.rstrip().endswith("write_file; allowed but NOT OFFERED: ghost_tool")


# --- SIGINT / SIGTERM to the CLI --------------------------------------------------------------------

def test_signal_stops_the_servers_once_and_exits_143(wf, tmp_path):
    """The first signal cancels the run, close() kills a server that ignores stdin EOF (SDK escalation), a second
    signal while closing is ignored. Without the handler SIGTERM killed the CLI and left the server running."""
    server(wf, python(WRAP + "\ntry: f.main()\nfinally: __import__('time').sleep(60)") + "\ntimeouts: { call: 60s }")
    task_sc(wf)
    (tmp_path / "script.yaml").write_text(json.dumps({"t": [calls(("fs__slow", {"seconds": 60}))]}))
    cli = subprocess.Popen([sys.executable, "-m", "agencast.cli", "--project", str(tmp_path), "run", "test",
                            "--fake", str(tmp_path / "script.yaml")], stderr=subprocess.PIPE, text=True)

    def servers():  # by command line: an orphaned server is no longer a descendant of the CLI
        out = subprocess.run(["ps", "-e", "-o", "pid=,args="], capture_output=True, text=True).stdout
        return [int(line.split()[0]) for line in out.splitlines() if str(tmp_path) in line and "fake_mcp_server" in line]
    try:
        t0 = time.monotonic()
        while not list(tmp_path.glob("runs/*/steps/01-t/calls/01.response.json")) and time.monotonic() - t0 < 20:
            time.sleep(0.05)
        time.sleep(0.5)  # the tool call is in flight
        cli.send_signal(signal.SIGTERM)
        time.sleep(0.3)
        cli.send_signal(signal.SIGINT)
        err = cli.communicate(timeout=20)[1]
        assert cli.returncode == 143 and "interrupted by SIGTERM" in err and "Traceback" not in err, err
        assert [line.split(" ", 2)[:2] for line in err.splitlines()[-2:]] == [  # one at the signal, one at the end
            ["SIGTERM:", "stopping"], ["interrupted", "by"]], err
        assert servers() == []
        (run_dir,) = tmp_path.glob("runs/2*")
        evs = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
        assert "run_finished" not in [e["type"] for e in evs]  # an interrupted run, as before
        assert [e["error"] for e in evs if e["type"] == "tool_call"] == ["cancelled before the tool answered (may have run)"]
        assert [e["action"] for e in evs if e["type"] == "mcp_server"] == ["started", "stopped"]
    finally:
        cli.kill()
        for pid in servers():
            os.kill(pid, signal.SIGKILL)


# --- `agencast serve` stopped with a run in flight ---------------------------------------------------

def test_serve_stop_ends_the_run_and_the_restart_reports_it(wf, monkeypatch):
    """Runs execute in worker threads, where no signal arrives: `stop_runs` (cmd_serve on SIGTERM/Ctrl-C) interrupts
    them, the server that ignores stdin EOF is killed, the queue entry stays and the next start sends the callback."""
    from test_webhook import Receiver, finished, start

    from agencast import engine
    monkeypatch.setenv("WEBHOOK_TOKEN", "token-webhook-123")
    monkeypatch.setenv("CALLBACK_SECRET", "callback-signature-456")
    monkeypatch.setattr(engine, "_STOPPING", None)  # restored after the test: stop_runs sets it for good
    server(wf, python(WRAP + "\ntry: f.main()\nfinally: __import__('time').sleep(60)") + "\ntimeouts: { call: 60s }")
    scenario(wf, HEAD + """
steps:
  - id: t
    task: { agent: tester, prompt: "Complete the task" }
  - id: after
    set: { done: "true" }
""")
    rcv, runs = Receiver(), wf.parent / "runs"
    hook, srv, client = start(wf, {"t": [calls(("fs__slow", {"seconds": 60}))]})
    try:
        r = client.post("/runs", json={"scenario": "test", "callback_url": rcv.url})
        run_id = r.json()["run_id"]
        t0 = time.monotonic()
        while not (runs / run_id / "steps/01-t/calls/01.response.json").exists() and time.monotonic() - t0 < 20:
            time.sleep(0.05)
        time.sleep(0.5)  # the tool call is in flight
        assert len(children()) == 1
        t0 = time.monotonic()
        assert engine.stop_runs() is True and time.monotonic() - t0 < 12
        assert children() == [] and not engine._LIVE
        evs = [json.loads(line) for line in (runs / run_id / "events.jsonl").read_text().splitlines()]
        assert "run_finished" not in [e["type"] for e in evs] and not rcv.got
        assert [e["action"] for e in evs if e["type"] == "mcp_server"] == ["started", "stopped"]
        (skipped,) = [e for e in evs if e["type"] == "step_skipped"]
        assert (skipped["step"], skipped["reason"]) == ("after", "cancelled — the run was interrupted (SIGTERM)")
        assert (hook.qdir / f"{run_id}.json").exists()  # kept for the restart
        with pytest.raises(engine.Interrupted):  # nothing starts while the server stops
            run(wf / "scenarios" / "tone-check.yaml", {"text": "Hi"})
    finally:
        srv.shutdown()
        srv.server_close()
        client.close()
    monkeypatch.setattr(engine, "_STOPPING", None)  # the next `agencast serve`
    hook, srv, client = start(wf)
    try:
        finished(hook, run_id)
        (cb,) = rcv.wait(1)
        assert cb["run_id"] == run_id and cb["error"] == {"class": "internal", "step": "t",
                                                          "message": "run interrupted by server restart"}
    finally:
        srv.shutdown()
        srv.server_close()
        client.close()


# --- the SDK's log must not quote a server's raw output ---------------------------------------------

def test_sdk_log_does_not_quote_a_non_json_stdout_line(wf, monkeypatch, caplog):
    """The SDK logs every non-JSON stdout line with a traceback that quotes it — unmasked, on the stderr of the CLI
    and in the journal of the service. The log line stays, the quote goes."""
    monkeypatch.setenv("AGENCAST_TEST_MCP_SECRET", "very-secret-value-42")
    server(wf, python(WRAP + "print('token', f.os.environ['SERVER_SECRET'], flush=True); f.main()")
           + "\nenv: { SERVER_SECRET: AGENCAST_TEST_MCP_SECRET }")
    r, _ = run(task_sc(wf), script={"t": [{"text": "ok"}]})
    assert r.status == "succeeded", r.error
    assert "Failed to parse JSONRPC message from server" in caplog.text
    assert "very-secret-value-42" not in caplog.text and "Traceback" not in caplog.text


def test_sdk_log_does_not_quote_an_invalid_notification(wf, monkeypatch, caplog):
    """The session logs a notification it cannot validate with the pydantic error, which quotes the server's input —
    through the logger "client", not "mcp.client.session"."""
    monkeypatch.setenv("AGENCAST_TEST_MCP_SECRET", "very-secret-value-42")
    note = "dict(jsonrpc='2.0', method='notifications/message', params=dict(level=f.os.environ['SERVER_SECRET'], data='x'))"
    server(wf, python(WRAP + f"print(f.json.dumps({note}), flush=True); f.main()")
           + "\nenv: { SERVER_SECRET: AGENCAST_TEST_MCP_SECRET }")
    r, _ = run(task_sc(wf), script={"t": [{"text": "ok"}]})
    assert r.status == "succeeded", r.error
    assert "Failed to validate notification" in caplog.text
    assert "very-secret-value-42" not in caplog.text and "Traceback" not in caplog.text


# --- `serve` is stopping: nothing starts any more ----------------------------------------------------

def test_no_server_starts_once_serve_is_stopping(wf, tmp_path, monkeypatch):
    """A dry run (or a run) that reaches its start after `stop_runs` looked at the runs in flight for the last time
    would start servers nobody stops."""
    from agencast import engine
    marker = tmp_path / "server-started"
    server(wf, python(WRAP + f"open({str(marker)!r}, 'w').close(); f.main()"))
    p = validate(task_sc(wf), check_models=False)
    monkeypatch.setattr(engine, "_STOPPING", signal.SIGTERM)
    with pytest.raises(engine.Interrupted):
        dry_run(p, {})
    assert not marker.exists() and children() == []
