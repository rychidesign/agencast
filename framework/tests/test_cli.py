"""CLI z libovolné složky: kořen projektu podle workflows/ nahoru nebo --project; migrate."""
from pathlib import Path

from maw.cli import main
from maw.record import count

GOLDEN = str(Path(__file__).parent / "golden" / "ukazka-call.yaml")


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
