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
