"""CLI from any directory: project root found by searching upward for workflows/ or via --project; migrate."""
import os
import subprocess
import sys
from pathlib import Path

from agencast import api
import agencast.cli as cli
from agencast.cli import main
from agencast.fake import Fake
from agencast.record import count
from conftest import add_image_model, scenario

GOLDEN = str(Path(__file__).resolve().parents[2] / "examples" / "showcase" / "fake" / "demo-call.yaml")


def test_serve_bind_defaults_and_environment(monkeypatch):
    got = []
    monkeypatch.setattr(cli, "cmd_serve", lambda a: got.append((a.host, a.port)) or 0)
    monkeypatch.delenv("AGENCAST_HOST", raising=False)
    monkeypatch.delenv("AGENCAST_PORT", raising=False)
    assert main(["serve"]) == 0
    monkeypatch.setenv("AGENCAST_HOST", "192.0.2.4")
    monkeypatch.setenv("AGENCAST_PORT", "9090")
    assert main(["serve"]) == 0
    monkeypatch.setenv("AGENCAST_PORT", "bad-but-overridden")
    assert main(["serve", "--host", "localhost", "--port", "8081"]) == 0
    assert got == [("127.0.0.1", 8080), ("192.0.2.4", 9090), ("localhost", 8081)]


def test_serve_invalid_environment_port_is_config_before_server(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(cli, "cmd_serve", lambda a: called.append(a) or 0)
    for value in ("abc", "0", "65536"):
        monkeypatch.setenv("AGENCAST_PORT", value)
        assert main(["serve"]) == 2
        err = capsys.readouterr().err
        assert "config: AGENCAST_PORT must be an integer in the range 1–65535" in err
    assert not called


def test_commands_from_other_cwd_with_project(wf, tmp_path, monkeypatch, capsys):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    root = str(wf.parent)
    assert main(["--project", root, "validate", "ig-post", "--offline"]) == 0
    assert main(["validate", "tone-check", "--offline", "--project", str(wf)]) == 0  # also a path to workflows/
    assert main(["run", "demo-call", "-i", "topic=coffee", "--fake", GOLDEN, "--project", root]) == 0
    out = capsys.readouterr().out
    assert "valid: ig-post (8 steps" in out and "report: file://" in out
    run_id = out.split("run ", 1)[1].split(":", 1)[0]
    assert (wf.parent / "runs" / run_id / "steps/02-tone/steps/01-check").is_dir()
    assert main(["runs", "list", "--project", root]) == 0
    assert run_id in capsys.readouterr().out
    assert main(["--project", root, "runs", "show", run_id]) == 0
    assert "# demo-call — success" in capsys.readouterr().out


def test_project_found_upwards(wf, monkeypatch, capsys):
    monkeypatch.chdir(wf / "scenarios")
    assert main(["validate", "ig-post", "--offline"]) == 0
    assert main(["runs", "list"]) == 0
    assert "no runs" in capsys.readouterr().out


def test_rename_cli(wf, monkeypatch, capsys):
    root = str(wf.parent)
    api.new_agent(root, "writer")
    api.new_scenario(root, "demo")
    assert main(["rename", "scenario", "demo", "intro", "--project", root]) == 0
    assert "scenarios/intro.yaml" in capsys.readouterr().out
    assert (wf / "scenarios" / "intro.yaml").is_file()
    assert not (wf / "scenarios" / "demo.yaml").exists()

    monkeypatch.chdir(root)
    assert main(["rename", "agent", "writer", "editor"]) == 0
    out = capsys.readouterr().out
    assert "agents/editor.md" in out and "scenarios/demo-task.yaml" not in out
    assert main(["rename", "agent", "editor", "invalid name"]) == 2
    assert "starting with a letter" in capsys.readouterr().err


def test_no_project(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["validate", "ig-post", "--offline"]) == 2
    assert "use --project" in capsys.readouterr().err
    assert main(["--project", str(tmp_path), "runs", "list"]) == 2
    assert "missing workflows/ directory" in capsys.readouterr().err


def test_migrate(tmp_path, capsys):
    f = tmp_path / "x.yaml"
    f.write_text("version: 1\nname: x\n")
    assert main(["migrate", str(f)]) == 0
    assert "nothing to convert" in capsys.readouterr().out
    f.write_text("version: 2\nname: x\n")
    assert main(["migrate", str(f)]) == 2
    assert "unknown format version 2" in capsys.readouterr().err
    assert main(["migrate", str(tmp_path / "missing.yaml")]) == 2


def test_step_count_english_plural(wf, capsys):
    """BUGS.md #5: singular for 1 step, plural for 0 and 2+ steps."""
    assert [count(n, "step", "steps") for n in (0, 1, 2, 4, 5, 9)] == \
        ["0 steps", "1 step", "2 steps", "4 steps", "5 steps", "9 steps"]
    assert main(["--project", str(wf.parent), "validate", "tutorial-01-names", "--offline"]) == 0
    assert "valid: tutorial-01-names (2 steps, model checks skipped)" in capsys.readouterr().out


def test_api_for_wrappers(wf):
    """agencast.api: scenario name + project root → run → list runs (wrappers over the core)."""
    fake = Fake(None)  # api.load populates models from config.yaml
    p = api.load("tone-check", project_root=wf.parent, fake=fake)
    plan = api.dry_run(p, {"text": "Hello"})
    r = api.run(p, {"text": "Hello"}, fake=fake)
    assert r.status == "succeeded" and fake.models
    listed = {s["run_id"]: s for s in api.runs_list(wf.parent)}
    assert listed[r.run_id] == api.run_status(r.rec.dir) and listed[r.run_id]["status"] == "succeeded"
    assert listed[plan.dir.name]["status"] == "dry-run"


def test_fake_cli_runs_images_api(wf, capsys):
    add_image_model(wf)
    p = scenario(wf, 'version: 1\nname: NAME\ndescription: Fake Images API\n'
                      'steps: [{ id: photo, image: { model: gpt-image, prompt: "Coffee", aspect_ratio: "1:1" } }]')
    assert main(["--project", str(wf.parent), "run", p.stem, "--fake"]) == 0
    out = capsys.readouterr().out
    assert "succeeded" in out and "0.0400 USD" in out
    run_id = out.split("run ", 1)[1].split(":", 1)[0]
    assert (wf.parent / "runs" / run_id / "steps/01-photo/image.png").is_file()


def test_fake_script_missing_is_a_config_error(wf, capsys):
    """`--fake <missing file>` used to end in a Python traceback (FileNotFoundError)."""
    root = str(wf.parent)
    assert main(["--project", root, "run", "tone-check", "-i", "text=Hi", "--fake", "no-such-script.yaml"]) == 2
    assert main(["--project", root, "serve", "--port", "0", "--fake", "no-such-script.yaml"]) == 2
    err = capsys.readouterr().err
    assert err.count("no-such-script.yaml: file does not exist") == 2 and "cannot start server" not in err, err
    script = wf.parent / "script.yaml"
    script.write_bytes(b"\xff\xfe\x00bin")  # exists, cannot be read: also a config error, not a traceback
    assert main(["--project", root, "run", "tone-check", "-i", "text=Hi", "--fake", str(script)]) == 2
    assert f"config: {script}: cannot read the file (not UTF-8 text)" in capsys.readouterr().err


def test_serve_signal_during_startup_takes_the_shutdown_path(tmp_path):
    """Workers run the restored queue as soon as they start: a SIGTERM while `serve` is still starting used to kill
    the process (default disposition) and leave their MCP servers running — it must end in `stop_runs`."""
    code = ("import os, signal, sys\nfrom agencast import cli, server\n"
            "server.Projects.start = lambda self: os.kill(os.getpid(), signal.SIGTERM)\n"
            "sys.exit(cli.main(['serve', '--port', '0']))")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, cwd=tmp_path,
                       env={**os.environ, "AGENCAST_TOKEN": "token-123", "AGENCAST_CONFIG_DIR": str(tmp_path / "cfg")})
    assert r.returncode == 0 and "stopped (unfinished requests remain" in r.stdout and "Traceback" not in r.stderr, r
