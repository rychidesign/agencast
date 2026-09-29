"""agencast new: project skeleton, agent and scenario from templates (projects.md)."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from agencast import ConfigErrors, api
from agencast.cli import main
from agencast.fake import Fake


def test_new_project_validates_and_runs_fake(tmp_path, capsys):
    root = tmp_path / "my-project"
    assert main(["new", "project", str(root)]) == 0
    out = capsys.readouterr().out
    assert "created: " + str(root / "workflows" / "config.yaml") in out and ".env.example" in out
    assert (root / ".env.example").read_text().startswith("# Copy")
    fake = Fake(None)
    p = api.load("demo", project_root=root, fake=fake)
    assert api.run(p, {}, fake=fake).status == "succeeded"
    assert main(["new", "project", str(root)]) == 2  # existing workflows/
    assert "already exists" in capsys.readouterr().err


def test_new_agent_and_scenario(tmp_path):
    root = tmp_path / "p"
    api.new_project(root)
    with pytest.raises(ConfigErrors, match="already exists"):
        api.new_agent(root, "writer")
    with pytest.raises(ConfigErrors, match="lowercase letters"):
        api.new_scenario(root, "New_scenario")
    (agent,) = api.new_agent(root, "reviewer")
    assert "model: smart    # alias from config.yaml: smart, fast, gemini-image" in agent.read_text()
    (sc,) = api.new_scenario(root, "second")
    assert sc == root / "workflows" / "scenarios" / "second.yaml"
    p = api.load("second", project_root=root, offline=True)
    assert p.scenario["steps"][0]["ask"]["agent"] == "reviewer"


def test_registry_add_list_rm(tmp_path, registry, capsys):
    root = tmp_path / "My Project"
    assert main(["new", "project", str(root)]) == 0
    assert "project my-project added to the registry" in capsys.readouterr().out
    assert api.projects() == [{"name": "my-project", "root": str(root), "available": True}]
    assert "projects:" in registry.read_text() and "KEY" not in registry.read_text()
    other = tmp_path / "elsewhere" / "my-project"
    api.new_project(other, "second")
    with pytest.raises(ConfigErrors, match="already in the registry as 'second'"):
        api.add_project(other)
    assert main(["projects", "rm", "second"]) == 0
    assert main(["projects", "add", str(other)]) == 2  # folder name conflicts
    assert "--name <name>" in capsys.readouterr().err
    assert main(["projects", "add", str(other / "workflows"), "--name", "second"]) == 0
    (root / "workflows" / "config.yaml").unlink()
    assert main(["projects", "list"]) == 0
    out = capsys.readouterr().out
    assert "my-project" in out and "unavailable" in out and "second" in out
    assert main(["projects", "rm", "missing"]) == 2


def test_concurrent_registry_adds_keep_both(tmp_path):
    roots = [tmp_path / name for name in ("alpha", "beta")]
    for root in roots:
        (root / "workflows").mkdir(parents=True)
    gate = Barrier(len(roots))

    def add(root):
        gate.wait()
        return api.add_project(root)

    with ThreadPoolExecutor(max_workers=len(roots)) as pool:
        assert set(pool.map(add, roots)) == {"alpha", "beta"}
    assert {x["name"] for x in api.projects()} == {"alpha", "beta"}


def test_run_adds_project_once_validate_never(tmp_path, registry, capsys):
    root = tmp_path / "p"
    api.new_project(root)
    registry.unlink()
    assert main(["--project", str(root), "validate", "demo", "--offline"]) == 0  # 0.15.1: validate without side effects
    assert not registry.exists() and "registry" not in capsys.readouterr().err
    assert main(["--project", str(root), "run", "demo", "--fake"]) == 0
    assert f"project p added to the registry ({registry})" in capsys.readouterr().err
    assert main(["--project", str(root), "run", "demo", "--fake"]) == 0
    assert "registry" not in capsys.readouterr().err
    registry.write_text(f"projects:\n  - {{name: p, root: {tmp_path / 'other'}}}\n")
    assert main(["--project", str(root), "run", "demo", "--fake"]) == 0  # a conflict does not stop the run
    assert "config: project 'p' is already in the registry" in capsys.readouterr().err
