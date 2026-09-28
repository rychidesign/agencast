"""CLI z libovolné složky: kořen projektu podle workflows/ nahoru nebo --project; migrate."""
from pathlib import Path

from agencast import api
import agencast.cli as cli
from agencast.cli import main
from agencast.fake import Fake
from agencast.record import count
from conftest import add_image_model, scenario

GOLDEN = str(Path(__file__).resolve().parents[2] / "examples" / "showcase" / "fake" / "ukazka-call.yaml")


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
        assert "config: AGENCAST_PORT musí být celé číslo v rozsahu 1–65535" in err
    assert not called


def test_commands_from_other_cwd_with_project(wf, tmp_path, monkeypatch, capsys):
    elsewhere = tmp_path / "jinde"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    root = str(wf.parent)
    assert main(["--project", root, "validate", "ig-post", "--offline"]) == 0
    assert main(["validate", "kontrola-tonu", "--offline", "--project", str(wf)]) == 0  # i cesta k workflows/
    assert main(["run", "ukazka-call", "-i", "tema=káva", "--fake", GOLDEN, "--project", root]) == 0
    out = capsys.readouterr().out
    assert "v pořádku: ig-post (8 kroků" in out and "report: file://" in out
    run_id = out.split("běh ", 1)[1].split(":", 1)[0]
    assert (wf.parent / "runs" / run_id / "steps/02-ton/steps/01-kontrola").is_dir()
    assert main(["runs", "list", "--project", root]) == 0
    assert run_id in capsys.readouterr().out
    assert main(["--project", root, "runs", "show", run_id]) == 0
    assert "# ukazka-call — úspěch" in capsys.readouterr().out


def test_project_found_upwards(wf, monkeypatch, capsys):
    monkeypatch.chdir(wf / "scenarios")
    assert main(["validate", "ig-post", "--offline"]) == 0
    assert main(["runs", "list"]) == 0
    assert "žádné běhy" in capsys.readouterr().out


def test_rename_cli(wf, monkeypatch, capsys):
    root = str(wf.parent)
    api.new_agent(root, "pisatel")
    api.new_scenario(root, "ukazka")
    assert main(["rename", "scenario", "ukazka", "uvod", "--project", root]) == 0
    assert "scenarios/uvod.yaml" in capsys.readouterr().out
    assert (wf / "scenarios" / "uvod.yaml").is_file()
    assert not (wf / "scenarios" / "ukazka.yaml").exists()

    monkeypatch.chdir(root)
    assert main(["rename", "agent", "pisatel", "redaktor"]) == 0
    out = capsys.readouterr().out
    assert "agents/redaktor.md" in out and "scenarios/ukazka-task.yaml" not in out
    assert main(["rename", "agent", "redaktor", "invalid name"]) == 2
    assert "začíná písmenem" in capsys.readouterr().err


def test_no_project(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["validate", "ig-post", "--offline"]) == 2
    assert "použij --project" in capsys.readouterr().err
    assert main(["--project", str(tmp_path), "runs", "list"]) == 2
    assert "chybí složka workflows/" in capsys.readouterr().err


def test_migrate(tmp_path, capsys):
    f = tmp_path / "x.yaml"
    f.write_text("version: 1\nname: x\n")
    assert main(["migrate", str(f)]) == 0
    assert "nic k převodu" in capsys.readouterr().out
    f.write_text("version: 2\nname: x\n")
    assert main(["migrate", str(f)]) == 2
    assert "neznámá verze formátu 2" in capsys.readouterr().err
    assert main(["migrate", str(tmp_path / "nic.yaml")]) == 2


def test_step_count_czech_plural(wf, capsys):
    """BUGS.md #5: 1 krok, 2–4 kroky, 0 a 5+ kroků (ne „2 kroků“)."""
    assert [count(n, "krok", "kroky", "kroků") for n in (0, 1, 2, 4, 5, 9)] == \
        ["0 kroků", "1 krok", "2 kroky", "4 kroky", "5 kroků", "9 kroků"]
    assert main(["--project", str(wf.parent), "validate", "tutorial-01-nazvy", "--offline"]) == 0
    assert "v pořádku: tutorial-01-nazvy (2 kroky, bez kontroly modelů)" in capsys.readouterr().out


def test_api_for_wrappers(wf):
    """agencast.api: jméno scénáře + kořen projektu → běh → výpis běhů (obálky nad jádrem)."""
    fake = Fake(None)  # modely doplní api.load z config.yaml
    p = api.load("kontrola-tonu", project_root=wf.parent, fake=fake)
    plan = api.dry_run(p, {"text": "Ahoj"})
    r = api.run(p, {"text": "Ahoj"}, fake=fake)
    assert r.status == "succeeded" and fake.models
    listed = {s["run_id"]: s for s in api.runs_list(wf.parent)}
    assert listed[r.run_id] == api.run_status(r.rec.dir) and listed[r.run_id]["status"] == "succeeded"
    assert listed[plan.dir.name]["status"] == "dry-run"


def test_fake_cli_runs_images_api(wf, capsys):
    add_image_model(wf)
    p = scenario(wf, 'version: 1\nname: NAME\ndescription: Fake Images API\n'
                      'steps: [{ id: foto, image: { model: gpt-image, prompt: "Káva", aspect_ratio: "1:1" } }]')
    assert main(["--project", str(wf.parent), "run", p.stem, "--fake"]) == 0
    out = capsys.readouterr().out
    assert "úspěch" in out and "0,0400 USD" in out
    run_id = out.split("běh ", 1)[1].split(":", 1)[0]
    assert (wf.parent / "runs" / run_id / "steps/01-foto/image.png").is_file()
