"""Bundled resources, safe paths and installation without modifying the host."""
from pathlib import Path

import pytest

from agencast import ConfigErrors, resources
from agencast.cli import main


@pytest.mark.parametrize("kind", ["skills", "docs", "examples"])
def test_resource_dir_package_and_clone(tmp_path, monkeypatch, kind):
    package = tmp_path / "package"
    bundled = package / kind
    bundled.mkdir(parents=True)
    monkeypatch.setattr(resources, "files", lambda _: package)
    assert resources.resource_dir(kind) == bundled
    bundled.rmdir()
    assert resources.resource_dir(kind) == Path(__file__).resolve().parents[2] / kind
    monkeypatch.setattr(resources, "__file__", str(tmp_path / "framework/src/agencast/resources.py"))
    with pytest.raises(ConfigErrors, match="bundled .* missing"):
        resources.resource_dir(kind)


def test_skills_install(tmp_path, capsys):
    args = ["skills", "install", "--prefix", str(tmp_path)]
    assert main(args) == 0
    assert "--to all" in capsys.readouterr().out
    assert main(args + ["--to", "wrong"]) == 2
    assert main(args + ["--to", "all"]) == 0
    for rel in (".claude/skills", ".codex/skills", ".config/opencode/skills", ".omp/agent/managed-skills"):
        assert (tmp_path / rel / "agencast-run").is_symlink()
    assert main(args) == 0
    assert "unchanged" in capsys.readouterr().out
    assert main(args + ["--to", "codex", "--copy"]) == 0
    copied = tmp_path / ".codex/skills/agencast-run"
    assert copied.is_dir() and not copied.is_symlink()
    sentinel = copied / "keep.txt"
    sentinel.write_text("keep")
    assert main(args + ["--to", "codex"]) == 0
    assert sentinel.read_text() == "keep"
    assert main(args + ["--to", "codex", "--force"]) == 0
    assert copied.is_symlink() and not sentinel.exists()
    copied.unlink()
    copied.symlink_to(tmp_path / "missing")
    assert main(args + ["--to", "codex"]) == 0
    assert (copied / "SKILL.md").is_file()
    assert main(["skills", "list"]) == 0
    assert main(["skills", "path"]) == 0


def test_docs_paths(tmp_path, monkeypatch, capsys):
    assert main(["docs"]) == 0
    assert "https://github.com/rychidesign/agencast" in capsys.readouterr().out
    assert main(["docs", "show", "spec/agent.md"]) == 0
    assert "specification v1" in capsys.readouterr().out
    assert main(["docs", "show", "spec/agen.md"]) == 2
    assert "spec/agent.md" in capsys.readouterr().err
    for path in ("../README.md", "/etc/passwd"):
        assert main(["docs", "show", path]) == 2
    (tmp_path / "escape").symlink_to("/etc/passwd")
    monkeypatch.setattr("agencast.cli.resource_dir", lambda _: tmp_path)
    assert main(["docs", "show", "escape"]) == 2


@pytest.mark.parametrize("example,scenario", [("showcase", "ig-post"), ("tutorial", "tutorial-07-composition")])
def test_example_project(tmp_path, example, scenario, monkeypatch):
    root = tmp_path / example
    assert main(["new", "project", str(root), "--example", example]) == 0
    assert (root / "fake" / f"{scenario}.yaml").is_file()
    assert (root / ".env.example").is_file()
    assert main(["--project", str(root), "validate", scenario, "--offline"]) == 0
    inputs = "topic=coffee" if example == "showcase" else "product=coffee"
    monkeypatch.chdir(tmp_path)
    assert main(["--project", str(root), "run", scenario, "-i", inputs, "--fake", f"fake/{scenario}.yaml"]) == 0
    assert main(["new", "project", str(root), "--example", example]) == 2


def test_example_conflict_preserves_files(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / ".env.example").write_text("keep")
    assert main(["new", "project", str(root), "--example", "showcase"]) == 2
    assert not (root / "workflows").exists()
    assert (root / ".env.example").read_text() == "keep"


def test_distribution_license_matches_repository():
    framework = Path(__file__).resolve().parents[1]
    assert (framework / "LICENSE").read_bytes() == (framework.parent / "LICENSE").read_bytes()
