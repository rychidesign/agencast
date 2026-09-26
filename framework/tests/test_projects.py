"""agencast new: kostra projektu, agent a scénář ze šablon (projects.md)."""
import pytest

from agencast import ConfigErrors, api
from agencast.cli import main
from agencast.fake import Fake


def test_new_project_validates_and_runs_fake(tmp_path, capsys):
    root = tmp_path / "muj-projekt"
    assert main(["new", "project", str(root)]) == 0
    out = capsys.readouterr().out
    assert "vytvořeno: " + str(root / "workflows" / "config.yaml") in out and ".env.example" in out
    assert (root / ".env.example").read_text().startswith("# Zkopíruj")
    fake = Fake(None)
    p = api.load("ukazka", project_root=root, fake=fake)
    assert api.run(p, {}, fake=fake).status == "succeeded"
    assert main(["new", "project", str(root)]) == 2  # existující workflows/
    assert "už existuje" in capsys.readouterr().err


def test_new_agent_and_scenario(tmp_path):
    root = tmp_path / "p"
    api.new_project(root)
    with pytest.raises(ConfigErrors, match="už existuje"):
        api.new_agent(root, "pisatel")
    with pytest.raises(ConfigErrors, match="malá písmena"):
        api.new_scenario(root, "Novy_scenar")
    (agent,) = api.new_agent(root, "recenzent")
    assert "model: chytry    # alias z config.yaml: chytry, rychly, gemini-image" in agent.read_text()
    (sc,) = api.new_scenario(root, "druhy")
    assert sc == root / "workflows" / "scenarios" / "druhy.yaml"
    p = api.load("druhy", project_root=root, offline=True)
    assert p.scenario["steps"][0]["ask"]["agent"] == "pisatel"


def test_registry_add_list_rm(tmp_path, registry, capsys):
    root = tmp_path / "Muj Projekt"
    assert main(["new", "project", str(root)]) == 0
    assert "projekt muj-projekt přidán do registru" in capsys.readouterr().out
    assert api.projects() == [{"name": "muj-projekt", "root": str(root), "available": True}]
    assert "projects:" in registry.read_text() and "KEY" not in registry.read_text()
    other = tmp_path / "jinde" / "muj-projekt"
    api.new_project(other, "druhy")
    with pytest.raises(ConfigErrors, match="už je v registru jako 'druhy'"):
        api.add_project(other)
    assert main(["projects", "rm", "druhy"]) == 0
    assert main(["projects", "add", str(other)]) == 2  # jméno složky koliduje
    assert "--name <jméno>" in capsys.readouterr().err
    assert main(["projects", "add", str(other / "workflows"), "--name", "druhy"]) == 0
    (root / "workflows" / "config.yaml").unlink()
    assert main(["projects", "list"]) == 0
    out = capsys.readouterr().out
    assert "muj-projekt" in out and "nedostupný" in out and "druhy" in out
    assert main(["projects", "rm", "nic"]) == 2


def test_validate_adds_project_once(tmp_path, registry, capsys):
    root = tmp_path / "p"
    api.new_project(root)
    registry.unlink()
    assert main(["--project", str(root), "validate", "ukazka", "--offline"]) == 0
    assert f"projekt p přidán do registru ({registry})" in capsys.readouterr().err
    assert main(["--project", str(root), "run", "ukazka", "--fake"]) == 0
    assert "registru" not in capsys.readouterr().err
    registry.write_text(f"projects:\n  - {{name: p, root: {tmp_path / 'jiny'}}}\n")
    assert main(["--project", str(root), "validate", "ukazka", "--offline"]) == 0  # kolize validate nezastaví
    assert "config: projekt 'p' už v registru je" in capsys.readouterr().err
