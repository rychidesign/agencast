"""`agencast mcp`, step S2: runs started through MCP live in worker processes of their own (mcp-server.md “Runs”).
Black-box over stdio: servers are subprocesses in their own process groups, workers are found by
`pgrep -f -- "--mcp-job <run_id>"` only, and every process a test started is gone at its end (`cleanup`)."""
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest
import yaml

from conftest import FAKE_MCP
from test_task import setup

from agencast.cli import main
from agencast.fake import png
from agencast.providers import DEFAULT_BASE_URL


SLOW = "write: [{sleep: 6, text: slow answer}]\n"
RUN_ID = re.compile(r"^\d{8}-\d{6}-demo-[0-9a-f]{4}$")


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A separately declared, registered project; conftest's registry stays temporary."""
    for name in ("OPENROUTER_API_KEY", "A_HOOK_TOKEN", "HTTPS_PROXY"):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "lumen"
    assert main(["new", "project", str(root)]) == 0
    return root


def until(check, timeout=8, interval=.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = check()
        if value:
            return value
        time.sleep(interval)
    assert check(), f"condition did not become true within {timeout}s"


def slots(root):
    return root / "runs" / "_mcp-slots"


def worker_pids(run_id):
    p = subprocess.run(["pgrep", "-f", "--", f"--mcp-job {run_id}"], text=True, capture_output=True)
    return [int(x) for x in p.stdout.split()] if p.returncode == 0 else []


def locked(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except BlockingIOError:
        return True


class Client:
    """Small ordered, newline-delimited JSON-RPC stdio client with a process-group watchdog."""
    def __init__(self, args, env, cwd, cleanup):
        self.p = subprocess.Popen([sys.executable, "-m", "agencast.cli", *args], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, cwd=cwd,
                                  env=env, start_new_session=True)
        self.stderr = []
        self._reader = threading.Thread(target=lambda: self.stderr.extend(self.p.stderr), daemon=True)
        self._reader.start()
        self.watchdog = threading.Timer(50, self.kill_group)
        self.watchdog.start()
        cleanup.clients.append(self)
        self._id = 0
        self.request("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                    "clientInfo": {"name": "test", "version": "1"}})
        self.notify("notifications/initialized")

    def request(self, method, params=None):
        self._id += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method,
                                       **({"params": params} if params is not None else {})}) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        assert line, "MCP server exited before replying: " + "".join(self.stderr)
        reply = json.loads(line)
        assert reply["id"] == self._id
        return reply["result"]

    def notify(self, method):
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.p.stdin.flush()

    def call(self, tool, arguments):
        result = self.request("tools/call", {"name": tool, "arguments": arguments})
        return result["content"][0]["text"] if result.get("isError") else result["structuredContent"]

    def close(self):
        if self.p.poll() is None:
            self.p.stdin.close()
            self.p.wait(timeout=2)
        self.watchdog.cancel()
        self._reader.join(timeout=1)
        return self.p.returncode

    def kill_group(self):
        if self.p.poll() is None:
            os.killpg(os.getpgid(self.p.pid), signal.SIGKILL)
            self.p.wait(timeout=3)
        self.watchdog.cancel()


class Cleanup:
    def __init__(self):
        self.clients, self.run_ids = [], []

    def finish(self):
        for run_id in self.run_ids:
            for pid in worker_pids(run_id):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        for client in self.clients:
            client.kill_group()


@pytest.fixture
def cleanup():
    value = Cleanup()
    yield value
    value.finish()


def env_for(root, registry, **extra):
    return {"PATH": os.environ["PATH"], "HOME": str(root.parent), "AGENCAST_CONFIG_DIR": str(registry.parent), **extra}


def server(root, registry, cleanup, *extra, registry_mode=False, **env):
    args = ["mcp", "--allow", "run", *extra] if registry_mode else ["--project", str(root), "mcp", "--allow", "run", *extra]
    return Client(args, env_for(root, registry, **env), root.parent, cleanup)


def run(client, cleanup, project="lumen", inputs=None, tool="fake_run"):
    value = client.call(tool, {"project": project, "scenario": "demo", "inputs": inputs or {"topic": "topic"}})
    assert isinstance(value, dict), value
    cleanup.run_ids.append(value["run_id"])
    return value


def status(client, run_id, project="lumen"):
    return client.call("run_status", {"project": project, "run_id": run_id})


def wait_state(client, run_id, state, project="lumen", timeout=8):
    def checked():
        value = status(client, run_id, project)
        return value if value["state"] == state else None
    return until(checked, timeout)


def wait_done(client, run_id, project="lumen", timeout=12):
    def checked():
        value = client.call("wait_run", {"project": project, "run_id": run_id, "timeout_s": 1})
        return value if value["done"] else None
    return until(checked, timeout)


def slow_script(root):
    script = root / "slow.yaml"
    script.write_text(SLOW)
    return script


def seed_models(root):
    cfg = yaml.safe_load((root / "workflows" / "config.yaml").read_text())
    data = [{"id": m["id"], "output_modalities": ["text"],
             "supported_parameters": ["response_format", "structured_outputs"]}
            for m in cfg["models"].values() if m.get("api", "chat") == "chat"]
    runs = root / "runs"
    runs.mkdir(exist_ok=True)
    (runs / "_models.json").write_text(json.dumps({"base_url": cfg["openrouter"].get("base_url", DEFAULT_BASE_URL),
                                                      "fetched_at": time.time(), "data": data}))


def set_parallel_one(root):
    config = root / "workflows" / "config.yaml"
    data = yaml.safe_load(config.read_text())
    data.setdefault("limits", {})["max_parallel_runs"] = 1
    config.write_text(yaml.safe_dump(data, sort_keys=False))


def queue_lock(root):
    path = root / "runs" / "_slots" / "1.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def test_worker_shape_disconnect_and_kill(root, registry, cleanup):
    """Checks 1–3: sealed worker command/environment, EOF and SIGKILL server survival."""
    secret, script = "sk-test-0123456789abcdef", slow_script(root)
    (root / ".env").write_text(f"OPENROUTER_API_KEY={secret}\n")
    c = server(root, registry, cleanup, "--fake", str(script), AGENCAST_MCP_TOKEN="t" * 40)
    started = time.monotonic()
    queued = run(c, cleanup, inputs={"topic": "marker-7f3a"})
    assert time.monotonic() - started < 2 and RUN_ID.fullmatch(queued["run_id"])
    assert queued["state"] == "queued" and queued["run_dir"] is None
    pid = until(lambda: next(iter(worker_pids(queued["run_id"])), None))
    cmd = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    assert {b"--mcp-job", queued["run_id"].encode(), b"run", b"demo", str(script.resolve()).encode()} <= set(cmd)
    assert b"marker-7f3a" not in cmd and secret.encode() not in cmd
    assert b"AGENCAST_MCP_TOKEN" not in Path(f"/proc/{pid}/environ").read_bytes()
    assert os.getsid(pid) != os.getsid(c.p.pid) and os.getpgid(pid) != os.getpgid(c.p.pid)
    assert [p.read_text() for p in slots(root).glob("*.lock") if p.read_text()] == [queued["run_id"]]
    until(lambda: status(c, queued["run_id"])["state"] == "running")
    assert c.close() == 0
    assert worker_pids(queued["run_id"])
    other = server(root, registry, cleanup, "--fake", str(script))
    assert status(other, queued["run_id"])["state"] == "running"
    done = wait_done(other, queued["run_id"])
    assert done["state"] == "succeeded" and done["outputs"] == {"text": "slow answer"}
    assert queued["run_id"] in {x["run_id"] for x in other.call("list_runs", {"project": "lumen"})["runs"]}
    second = run(other, cleanup)
    until(lambda: status(other, second["run_id"])["state"] == "running")
    os.killpg(os.getpgid(other.p.pid), signal.SIGKILL)
    assert other.p.wait(timeout=2) == -signal.SIGKILL
    fresh = server(root, registry, cleanup, "--fake", str(script))
    assert wait_done(fresh, second["run_id"])["state"] == "succeeded"


def test_server_signals_worker_interrupt_and_reaping(root, registry, cleanup):
    """Checks 4–6: server signals leave runs alone; worker SIGTERM records interruption; no zombies/slots."""
    script = slow_script(root)
    c = server(root, registry, cleanup, "--fake", str(script))
    r = run(c, cleanup)
    until(lambda: status(c, r["run_id"])["state"] == "running")
    os.killpg(os.getpgid(c.p.pid), signal.SIGTERM)
    assert c.p.wait(timeout=2) == -signal.SIGTERM
    assert "".join(c.stderr).endswith("agencast mcp: stopped — runs continue in their own processes\n")
    new = server(root, registry, cleanup, "--fake", str(script))
    assert wait_done(new, r["run_id"])["state"] == "succeeded"
    idle = server(root, registry, cleanup)
    os.killpg(os.getpgid(idle.p.pid), signal.SIGINT)
    assert idle.p.wait(timeout=2) == -signal.SIGINT
    r = run(new, cleanup)
    pid = until(lambda: next(iter(worker_pids(r["run_id"])), None))
    until(lambda: status(new, r["run_id"])["state"] == "running")
    os.kill(pid, signal.SIGTERM)
    until(lambda: not worker_pids(r["run_id"]), 3)
    interrupted = wait_state(new, r["run_id"], "interrupted", timeout=3)
    assert interrupted["state"] == "interrupted" and interrupted["done"]
    events = (root / "runs" / r["run_id"] / "events.jsonl").read_text()
    assert "run_finished" not in events and not (root / "runs" / r["run_id"] / "callback.json").exists()
    quick = run(new, cleanup)
    assert wait_done(new, quick["run_id"], timeout=8)["state"] == "succeeded"
    time.sleep(1)
    ps = subprocess.run(["ps", "--ppid", str(new.p.pid), "-o", "stat="], text=True, capture_output=True).stdout
    assert "Z" not in ps
    def free():
        for path in slots(root).glob("*.lock"):
            fd = os.open(path, os.O_RDWR | os.O_CREAT)
            try:
                if locked(fd):
                    return False
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
        return True
    assert until(free, 2)


def test_registry_environment_isolation(root, registry, cleanup, tmp_path):
    """Checks 7–8: a registry server never lends A's .env to B's worker or live run."""
    a, b = root, tmp_path / "beta"
    assert main(["new", "project", str(b)]) == 0
    (a / ".env").write_text("OPENROUTER_API_KEY=sk-test-A-0123456789abcdef\nA_HOOK_TOKEN=hook-A-0123456789abcdef\n")
    config = a / "workflows" / "config.yaml"
    data = yaml.safe_load(config.read_text())
    data["webhook"] = {"token_env": "A_HOOK_TOKEN"}
    config.write_text(yaml.safe_dump(data, sort_keys=False))
    seed_models(a)
    seed_models(b)
    script = slow_script(root)
    c = server(root, registry, cleanup, "--fake", str(script), registry_mode=True)
    c.call("describe_project", {"project": "lumen"})
    r = run(c, cleanup, "beta")
    pid = until(lambda: next(iter(worker_pids(r["run_id"])), None))
    environment = Path(f"/proc/{pid}/environ").read_bytes()
    assert b"sk-test-A-0123456789abcdef" not in environment and b"hook-A-0123456789abcdef" not in environment
    assert b"A_HOOK_TOKEN=" not in environment
    c.kill_group()
    c = server(root, registry, cleanup, registry_mode=True)
    c.call("describe_project", {"project": "lumen"})
    live = run(c, cleanup, "beta", tool="run_scenario")
    failed = wait_done(c, live["run_id"], "beta")
    message = failed["error"]["message"]
    assert failed["state"] == "failed" and failed["error"]["class"] == "internal"
    assert message.startswith("run did not start: worker exited with code 2") and "missing environment variable OPENROUTER_API_KEY" in message
    assert failed["run_dir"] is None and "sk-test-A-0123456789abcdef" not in json.dumps(failed)


def test_mcp_cap_and_queued_restart(root, registry, cleanup):
    """Checks 9, 10 and 12: four cross-server slots, queued visibility, and restart while waiting."""
    script = slow_script(root)
    c = server(root, registry, cleanup, "--fake", str(script))
    runs = [run(c, cleanup) for _ in range(4)]
    busy = c.call("fake_run", {"project": "lumen", "scenario": "demo", "inputs": {"topic": "x"}})
    assert "busy" in busy and "4 runs started through MCP" in busy and "list_runs" in busy
    assert "busy" in c.call("dry_run", {"project": "lumen", "scenario": "demo", "inputs": {"topic": "x"}})
    other = server(root, registry, cleanup, "--fake", str(script))
    assert "busy" in other.call("fake_run", {"project": "lumen", "scenario": "demo", "inputs": {"topic": "x"}})
    c.kill_group()
    fresh = server(root, registry, cleanup, "--fake", str(script))
    assert "busy" in fresh.call("fake_run", {"project": "lumen", "scenario": "demo", "inputs": {"topic": "x"}})
    for item in runs:
        assert wait_done(fresh, item["run_id"])["state"] == "succeeded"
    def retry_run():
        value = fresh.call("fake_run", {"project": "lumen", "scenario": "demo", "inputs": {"topic": "x"}})
        return value if isinstance(value, dict) else None
    last = until(retry_run, 2)
    cleanup.run_ids.append(last["run_id"])
    assert wait_done(fresh, last["run_id"])["state"] == "succeeded"
    set_parallel_one(root)
    fd = queue_lock(root)
    try:
        queued = run(fresh, cleanup)
        assert queued["state"] == "queued" and queued["run_dir"] is None
        assert not (root / "runs" / queued["run_id"]).exists()
        end = time.monotonic() + 2  # the worker waits for the `max_parallel_runs` slot: no directory, `queued`
        while time.monotonic() < end:
            assert not (root / "runs" / queued["run_id"]).exists() and status(fresh, queued["run_id"])["state"] == "queued"
            time.sleep(0.2)
        restarted = server(root, registry, cleanup, "--fake", str(script))
        assert status(restarted, queued["run_id"])["state"] == "queued"
        for scenario in (None, "demo"):
            assert queued["run_id"] in {x["run_id"] for x in restarted.call("list_runs", {"project": "lumen", **({"scenario": scenario} if scenario else {})})["runs"]}
        fresh.kill_group()
        after = server(root, registry, cleanup, "--fake", str(script))
        assert status(after, queued["run_id"])["state"] == "queued"
    finally:
        os.close(fd)  # releases the flock
    assert until(lambda: status(after, queued["run_id"])["state"] in ("running", "succeeded"), 5)
    assert wait_done(after, queued["run_id"])["state"] == "succeeded"


def test_queued_worker_stopped_and_coexistence(root, registry, cleanup):
    """Checks 11 and 13: a stopped queued worker is local failure; existing serve files are read-only."""
    script = slow_script(root)
    set_parallel_one(root)
    fd = queue_lock(root)
    c = server(root, registry, cleanup, "--fake", str(script))
    try:
        queued = run(c, cleanup)
        pid = until(lambda: next(iter(worker_pids(queued["run_id"])), None))
        os.kill(pid, signal.SIGTERM)
        failed = wait_state(c, queued["run_id"], "failed", timeout=3)
        assert failed["state"] == "failed" and failed["done"] and failed["run_dir"] is None
        assert failed["error"]["class"] == "internal" and "SIGTERM" in failed["error"]["message"]
        # `code 143 (SIGTERM)` once its handler is installed, `signal SIGTERM` while Python still starts
        assert failed["error"]["message"].startswith("run did not start: worker exited with ")
        new = server(root, registry, cleanup, "--fake", str(script))
        assert "not_found" in status_error(new, queued["run_id"])
        assert queued["run_id"] not in {x["run_id"] for x in new.call("list_runs", {"project": "lumen"})["runs"]}
        # SIGINT while it waits for the slot: exit 130 as for SIGTERM, no traceback
        stopped = run(new, cleanup)
        pid = until(lambda: next(iter(worker_pids(stopped["run_id"])), None))
        until(lambda: b"waiting for a free slot" in Path(f"/proc/{pid}/fd/2").read_bytes())  # its stderr file
        os.kill(pid, signal.SIGINT)
        message = wait_state(new, stopped["run_id"], "failed", timeout=3)["error"]["message"]
        assert message.startswith("run did not start: worker exited with code 130 (SIGINT)") and "Traceback" not in message
        # another process takes the id while the worker waits: that run stays the other's, this one did not start
        clash = run(new, cleanup)
        theirs = root / "runs" / clash["run_id"]
        theirs.mkdir()
        (theirs / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in (
            {"ts": "2026-01-01T00:00:00.000Z", "type": "run_started", "run_id": clash["run_id"], "scenario": "demo",
             "scenario_version": 1, "fake": True},
            {"ts": "2026-01-01T00:00:01.000Z", "type": "run_finished", "status": "succeeded", "duration_s": 1,
             "usage": {"cost_usd": 0}})))
        (theirs / "callback.json").write_text(json.dumps({"status": "succeeded", "outputs": {"text": "theirs"},
                                                          "warnings": ["theirs"], "report_url": "file://theirs"}))
        record = {p.name: p.read_bytes() for p in theirs.iterdir()}
    finally:
        os.close(fd)  # releases the flock
    until(lambda: not worker_pids(clash["run_id"]), 5)
    failed = wait_state(new, clash["run_id"], "failed", timeout=3)
    assert failed["error"]["class"] == "internal" and failed["run_dir"] is None and failed["outputs"] is None
    assert failed["error"]["message"].startswith("run did not start: worker exited with code 2")
    assert (failed["warnings"], failed["report_url"]) == ([], None)
    assert {p.name: p.read_bytes() for p in theirs.iterdir()} == record
    assert status(server(root, registry, cleanup), clash["run_id"])["state"] == "succeeded"  # any other server
    runs, qid, eid = root / "runs", "20260101-000000-other-aaaa", "20260101-000001-other-bbbb"
    (runs / "_queue").mkdir(parents=True, exist_ok=True)
    queue = {"run_id": qid, "scenario": "other", "inputs": {}, "callback_url": "https://example.invalid", "request_key": None, "queued_ns": 1}
    qfile, efile = runs / "_queue" / f"{qid}.json", runs / eid / "events.jsonl"
    qfile.write_text(json.dumps(queue))
    efile.parent.mkdir()
    efile.write_text(json.dumps({"ts": "2026-01-01T00:00:01.000Z", "type": "run_started", "run_id": eid,
                                 "scenario": "other", "scenario_version": 1, "fake": True}) + "\n")
    before = qfile.read_bytes(), efile.read_bytes()
    assert status(new, qid)["state"] == "queued"
    assert qid in {x["run_id"] for x in new.call("list_runs", {"project": "lumen"})["runs"]}
    regular = run(new, cleanup)
    assert wait_done(new, regular["run_id"])["state"] == "succeeded"
    assert new.close() == 0 and (qfile.read_bytes(), efile.read_bytes()) == before
    # Registry-mode serve is the callback-free GUI route; project-mode serve's POST /runs requires callback_url.
    port, token = free_port(), "test-registry-token"
    proc = subprocess.Popen([sys.executable, "-m", "agencast.cli", "serve", "--fake", "--port", str(port)],
                            cwd=root.parent, env=env_for(root, registry, AGENCAST_TOKEN=token),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        accepted = until(lambda: _try_http_run(port, token), 4)
        assert until(lambda: _callback(root, accepted["run_id"]), 8)["status"] == "succeeded"
        mcp = server(root, registry, cleanup, "--fake", str(script))
        slow = run(mcp, cleanup)
        until(lambda: status(mcp, slow["run_id"])["state"] == "running")
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=4)
        assert wait_done(mcp, slow["run_id"])["state"] == "succeeded"
    finally:
        if proc.poll() is None:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout=3)


def status_error(client, run_id):
    return client.call("run_status", {"project": "lumen", "run_id": run_id})


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _try_http_run(port, token):
    body = json.dumps({"scenario": "demo", "inputs": {"topic": "http"}}).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}/projects/lumen/runs", data=body,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=1) as response:
            return json.loads(response.read())
    except OSError:
        return None


def _callback(root, run_id):
    path = root / "runs" / run_id / "callback.json"
    return json.loads(path.read_text()) if path.is_file() else None


def test_registry_is_unchanged_by_project_mode(root, registry, cleanup, tmp_path):
    """Check 14: --project runs never register a project or modify the registry."""
    other = tmp_path / "unregistered"
    shutil.copytree(root, other)
    before = hashlib.sha256(registry.read_bytes()).hexdigest()
    c = server(other, registry, cleanup)
    for _ in range(2):
        item = run(c, cleanup, "unregistered")
        assert wait_done(c, item["run_id"], "unregistered")["state"] == "succeeded"
    assert hashlib.sha256(registry.read_bytes()).hexdigest() == before


# --- file inputs (step S3): the copy is the server's until the job is handed over, then the worker's -------------

def photo_demo(root):
    """`demo` with a file input `photo`."""
    path = root / "workflows" / "scenarios" / "demo.yaml"
    path.write_text(path.read_text().replace("inputs:\n", "inputs:\n  photo: { type: file, required: true }\n"))


def pictures(tmp_path):
    """(an allowed --input-dir with photo.png, the servers' TMPDIR: where their copies go)."""
    pics, tmp = tmp_path / "pictures", tmp_path / "tmp"
    pics.mkdir()
    tmp.mkdir()
    (pics / "photo.png").write_bytes(png(4, 3))
    return pics, tmp


def copies(tmp):
    return sorted(p.name for p in tmp.glob("agencast-mcp-*"))


def test_file_input_staging_and_a_copy_that_outlives_the_server(root, registry, cleanup, tmp_path):
    """No false `interrupted` while a 9 MB image is staged; a queued run keeps the bytes read at the call after the
    source changed and the server was killed; neither path is on the worker's command line; the worker removes
    its copy."""
    pics, tmp = pictures(tmp_path)
    photo_demo(root)
    (pics / "big.png").write_bytes(png(4, 3) + b"\0" * 9_000_000)
    c = server(root, registry, cleanup, "--input-dir", str(pics), TMPDIR=str(tmp))
    big = run(c, cleanup, inputs={"photo": str(pics / "big.png")})
    states = []
    while not states or states[-1] not in ("succeeded", "failed", "interrupted", "dry_run"):
        states.append(status(c, big["run_id"])["state"])
        time.sleep(0.01)
    assert states[-1] == "succeeded" and set(states) <= {"queued", "running", "succeeded"}, states
    assert (root / "runs" / big["run_id"] / "inputs" / "photo.png").stat().st_size == (pics / "big.png").stat().st_size
    until(lambda: not worker_pids(big["run_id"]), 3)
    assert copies(tmp) == []
    original = (pics / "photo.png").read_bytes()
    set_parallel_one(root)
    fd = queue_lock(root)
    try:
        queued = run(c, cleanup, inputs={"photo": str(pics / "photo.png")})
        assert queued["state"] == "queued"
        pid = until(lambda: next(iter(worker_pids(queued["run_id"])), None))
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes()
        assert str(pics / "photo.png").encode() not in cmd and b"agencast-mcp-" not in cmd
        assert len(copies(tmp)) == 1
        (pics / "photo.png").write_bytes(png(8, 8))
        os.killpg(os.getpgid(c.p.pid), signal.SIGKILL)
        assert c.p.wait(timeout=2) == -signal.SIGKILL
    finally:
        os.close(fd)  # releases the flock
    fresh = server(root, registry, cleanup, "--input-dir", str(pics), TMPDIR=str(tmp))
    assert wait_done(fresh, queued["run_id"])["state"] == "succeeded"
    assert (root / "runs" / queued["run_id"] / "inputs" / "photo.png").read_bytes() == original
    until(lambda: not worker_pids(queued["run_id"]), 3)
    assert copies(tmp) == []


def test_file_input_copy_of_a_stopped_worker(root, registry, cleanup, tmp_path):
    """A worker stopped while it waits for a slot exits 143 and removes its copy; one killed while it starts
    leaves none either — the server's reaper removes it — and did not start."""
    pics, tmp = pictures(tmp_path)
    photo_demo(root)
    set_parallel_one(root)
    fd = queue_lock(root)
    c = server(root, registry, cleanup, "--input-dir", str(pics), TMPDIR=str(tmp))
    try:
        queued = run(c, cleanup, inputs={"photo": str(pics / "photo.png")})
        pid = until(lambda: next(iter(worker_pids(queued["run_id"])), None))
        until(lambda: b"waiting for a free slot" in Path(f"/proc/{pid}/fd/2").read_bytes())  # its stderr file
        assert len(copies(tmp)) == 1
        os.kill(pid, signal.SIGTERM)
        message = wait_state(c, queued["run_id"], "failed", timeout=3)["error"]["message"]
        assert message.startswith("run did not start: worker exited with code 143 (SIGTERM)"), message
        assert copies(tmp) == []
    finally:
        os.close(fd)
    early = run(c, cleanup, inputs={"photo": str(pics / "photo.png")})
    returned = time.monotonic()
    pid = until(lambda: next(iter(worker_pids(early["run_id"])), None), 0.2, interval=0.005)
    os.kill(pid, signal.SIGTERM)
    assert time.monotonic() - returned < 0.2
    message = wait_state(c, early["run_id"], "failed", timeout=3)["error"]["message"]
    assert message.startswith("run did not start: worker exited with") and "SIGTERM" in message, message
    assert until(lambda: copies(tmp) == [], 3)


def test_file_input_copy_of_a_dry_run_stopped_with_the_server(root, registry, cleanup, tmp_path):
    """SIGTERM to the server while a dry run with a file input waits for an MCP server: the dry run is cancelled,
    the server ends killed by the signal and its copy is removed."""
    pics, tmp = pictures(tmp_path)
    marker, wf = tmp_path / "mcp-started", root / "workflows"
    setup(wf)  # MCP server `fs` and agent `tester`; the project is the owner's: trusted
    code = (f"import sys, time; open({str(marker)!r}, 'w').close(); time.sleep(5); sys.argv[1:] = sys.argv[-1:]; "
            f"exec(open({str(FAKE_MCP)!r}).read())")
    (wf / "mcp.yaml").write_text((wf / "mcp.yaml").read_text().replace(f"[{json.dumps(str(FAKE_MCP))}, ",
                                                                       f"[\"-c\", {json.dumps(code)}, "))
    (wf / "scenarios" / "probe.yaml").write_text("version: 1\nname: probe\ndescription: Probe\n"
                                                 "inputs: { photo: { type: file, required: true } }\n"
                                                 "steps:\n  - id: t\n    task: { agent: tester, prompt: Look }\n")
    c = server(root, registry, cleanup, "--input-dir", str(pics), TMPDIR=str(tmp))
    c.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 99, "method": "tools/call", "params": {"name": "dry_run",
                    "arguments": {"project": "lumen", "scenario": "probe",
                                  "inputs": {"photo": str(pics / "photo.png")}}}}) + "\n")
    c.p.stdin.flush()
    until(marker.exists)
    assert len(copies(tmp)) == 1
    stopped = time.monotonic()
    os.kill(c.p.pid, signal.SIGTERM)
    assert c.p.wait(timeout=20) == -signal.SIGTERM and time.monotonic() - stopped < 20
    assert copies(tmp) == [] and not list((root / "runs").glob("*-probe-*"))
    # the backstop for a copy the server still owns when the signal comes (a run start in flight; a dry run that
    # has not reached its MCP servers): the stop handler removes it before the process ends
    code = ("import sys, tempfile; from agencast import cli, mcp_server; "
            "mcp_server.OWNED.add(tempfile.mkdtemp(prefix='agencast-mcp-')); sys.exit(cli.main(sys.argv[1:]))")
    p = subprocess.Popen([sys.executable, "-c", code, "--project", str(root), "mcp"], stdin=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=env_for(root, registry, TMPDIR=str(tmp)), start_new_session=True)
    try:
        assert p.stderr.readline().startswith(b"agencast mcp: stdio") and len(copies(tmp)) == 1
        p.send_signal(signal.SIGTERM)
        assert p.wait(timeout=5) == -signal.SIGTERM and copies(tmp) == []
    finally:
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait(timeout=3)
