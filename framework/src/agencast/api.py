"""Public API for wrappers (DESIGN “Wrappers”): CLI, `serve`, later Modal and MCP.

Thin functions over validate, engine and record — logic belongs in the core
with a hermetic test. Secrets come only from the environment (and `.env`).
"""
import json
import re
from pathlib import Path
from typing import Any

from . import ConfigErrors, projects as _projects
# Project registry re-exported from projects.py (projects.md): new_project, projects = [{name, root, available}],
# projects_root (default ~/workspace), normalize_project_root (expands ~, rejects .., relative paths under base).
from .projects import (ProjectConflict, list_projects as projects, new_project, normalize_root as normalize_project_root,
                       projects_root, registry_writable, remove as remove_project)
from .edit import (Conflict, NotFound, OpError, add_step, batch, delete_agent, delete_scenario, delete_skill, delete_step,
                   file_etag, move_step, read_file, rename_agent, rename_scenario, render, replace_step, set_agent,
                   set_config, set_header, set_skill, render_text as _render_text, update_step, validate_text, write_file)
from .engine import RUN_ID, Run, dry_run as _dry_run, run_scenario
from .fake import Fake
from .loader import LoadError, load_dotenv, read_yaml
from .record import Record, run_detail as _run_detail, run_status, step_detail as _step_detail
from .task import local_ledger
from .validate import Project, require_config, resolve_inputs, validate

__all__ = ["find_root", "load", "run", "dry_run", "runs_list", "run_status", "new_project", "new_agent",
           "new_scenario", "projects", "projects_root", "normalize_project_root", "registry_writable",
           "ProjectConflict", "add_project", "remove_project", "ensure_project", "describe_project", "describe_scenario", "run_detail", "run_file",
           "last_run", "step_detail",
           "spend", "Project", "Run", "Fake",
           # GUI editing operations (edit.py, api.md “Editing”): files are the source of truth, fingerprints, validation before writes
           "Conflict", "NotFound", "set_header", "add_step", "update_step", "move_step", "delete_step",
           "delete_scenario", "rename_scenario", "set_agent", "delete_agent", "rename_agent", "set_skill",
           "delete_skill", "set_config", "read_file",
           "write_file", "validate_text",
           # 0.8.0: batch and preview without writes, whole step, lightweight file fingerprint
           "OpError", "batch", "render", "render_text", "replace_step", "file_etag"]


def find_root(project_root=None) -> Path:
    """Project root: `project_root`, otherwise the first directory containing workflows/ searching upward from cwd."""
    if project_root:
        root = Path(project_root).resolve()
        root = root.parent if root.name == "workflows" else root
        if not (root / "workflows").is_dir():
            raise ConfigErrors([f"{root}: missing workflows/ directory — --project must point to the project root"])
        return root
    for d in (Path.cwd(), *Path.cwd().parents):
        if (d / "workflows").is_dir():
            return d
    raise ConfigErrors(["no workflows/ directory in the current directory or its parents — use --project <path>"])


def load(scenario_path, *, project_root=None, fake: Fake | None = None, offline: bool = False) -> Project:
    """Validated scenario. `scenario_path` = name (ig-post → workflows/scenarios/ig-post.yaml at the
    project root) or path to .yaml. Load `.env` from the project root and current directory. With `fake`,
    validate models against its fake catalogs (if empty, populate them from config.yaml aliases)."""
    s = str(scenario_path)
    if not s.endswith((".yaml", ".yml")) and "/" not in s:
        s = str(find_root(project_root) / "workflows" / "scenarios" / f"{s}.yaml")
    wf = Path(s).resolve().parent.parent
    load_dotenv(wf.parent / ".env")
    load_dotenv(Path.cwd() / ".env")
    if fake is not None and not fake.models and not fake.image_models:
        models = require_config(wf)["models"]
        fake.models = [m["id"] for m in models.values() if m.get("api", "chat") == "chat"]
        fake.image_models = [m["id"] for m in models.values() if m.get("api", "chat") == "images"]
    return validate(s, transport=fake.transport() if fake else None, check_models=not offline)


def run(project: Project, inputs: dict, *, fake: Fake | None = None, callback_url=None, request_key=None,
        **kw) -> Run:
    """Start a run and wait for completion. Validate `inputs` (defaults, types). Wrapper `kw`:
    `run_id` (assigned on acceptance), `callback_transport`, `error` (a run that cannot start —
    inputs are not validated, only passed to the callback)."""
    if kw.get("error") is None:
        inputs = resolve_inputs(project.scenario, inputs)
    return run_scenario(project, inputs, fake=fake, callback_url=callback_url, request_key=request_key, **kw)


def dry_run(project: Project, inputs: dict) -> Record:
    """Run directory containing only plan.md and inputs.json."""
    return _dry_run(project, resolve_inputs(project.scenario, inputs))


def _runs_dir(project_root) -> Path:
    """`runs_dir` from config.yaml; reading runs does not require a valid config (API findings 4) — just this field.
    Fall back to `./runs` if it cannot be read."""
    wf = find_root(project_root) / "workflows"
    try:
        cfg = read_yaml(wf / "config.yaml", "config.yaml")
    except (OSError, LoadError):
        cfg = None
    d = cfg.get("runs_dir") if isinstance(cfg, dict) else None
    return wf.parent / (d if isinstance(d, str) else "./runs")


def _queue(runs: Path) -> dict[str, dict[str, Any]]:
    """`serve` queue entries (oldest first) with `queue_position` as in `GET /runs/<id>`
    (queued + running ahead of this run, including itself). Entries are removed only after the callback."""
    entries = []
    for f in (runs / "_queue").glob("*.json"):
        try:
            entries.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass  # the run just finished (or its entry is being written)
    return {e["run_id"]: {"run_id": e["run_id"], "status": "queued", "state": "queued", "scenario": e.get("scenario"),
                          "queue_position": sum(x["queued_ns"] <= e["queued_ns"] for x in entries)}
            for e in sorted(entries, key=lambda e: e["queued_ns"])}


def _in_queue(info: dict[str, Any], queue: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """0.8.0: an unfinished run directory in the `serve` queue with no lock held (yet) is `queued`
    (just picked up by a worker, or waiting for a server restart) — never `interrupted` or `dry_run`."""
    if info["run_id"] in queue and info["finished_at"] is None and info["state"] in ("interrupted", "dry_run"):
        info.update(status="queued", state="queued", queue_position=queue[info["run_id"]]["queue_position"])
    return info


def runs_list(project_root=None, scenario: str | None = None, limit: int | None = None,
              before: str | None = None) -> list[dict]:
    """Project runs by directory name, descending; `scenario` filters run_id and `before` paginates."""
    runs = _runs_dir(project_root)
    mine = re.compile(rf"\d{{8}}-\d{{6}}-{re.escape(scenario)}-[0-9a-f]{{4}}") if scenario else RUN_ID
    queue = _queue(runs)
    queued = {q["run_id"]: q for q in queue.values()
              if mine.fullmatch(q["run_id"]) and not (runs / q["run_id"]).is_dir()}
    dirs = {d.name for d in runs.glob("*") if d.is_dir() and mine.fullmatch(d.name)}
    ids = sorted(queued.keys() | dirs, reverse=True)
    if before is not None:
        ids = [run_id for run_id in ids if run_id < before]
    if limit is not None:
        ids = ids[:limit]
    return [queued[run_id] if run_id in queued else _in_queue(run_status(runs / run_id), queue) for run_id in ids]


def last_run(project_root, scenario: str | None = None) -> dict[str, Any] | None:
    """Latest run (of a project or scenario) for the GUI."""
    r = runs_list(project_root, scenario, limit=1)
    return {k: r[0].get(k) for k in ("run_id", "state", "started_at", "finished_at", "cost_usd")} if r else None


def new_agent(project_root, name: str, description: str | None = None, model: str | None = None) -> list[Path]:
    """Create workflows/agents/<name>.md with a model alias from project config.yaml (`model`, otherwise the first); no overwrites."""
    return _projects.new_agent(find_root(project_root), name, description, model)


def new_scenario(project_root, name: str, description: str | None = None) -> list[Path]:
    """Create workflows/scenarios/<name>.yaml with the first project agent; no overwrites."""
    return _projects.new_scenario(find_root(project_root), name, description)


def add_project(path, name: str | None = None) -> str:
    """Add a project (root containing workflows/) to the registry; return its name."""
    return _projects.add(find_root(path), name)


def ensure_project(root) -> str | None:
    """After a successful run (also validate until 0.15.0): register unlisted projects; return a stderr message (or None)."""
    return _projects.ensure(Path(root).resolve())


def describe_project(project_root) -> dict[str, Any]:
    """Project for the GUI: scenarios (with latest run), agents, skills, MCP servers, aliases, limits, links (api.md)."""
    root = find_root(project_root)
    body = _projects.describe_project(root)
    for sc in body["scenarios"]:
        sc["last_run"] = last_run(root, sc["name"])
    return body


def render_text(project_root, name: str, text: Any) -> dict[str, Any]:
    """Scenario tree and errors from draft YAML text, without writing."""
    return _render_text(find_root(project_root), name, text)


def describe_scenario(project_root, name: str) -> dict[str, Any] | None:
    """Scenario step tree for cards (api.md); None = scenario does not exist."""
    return _projects.describe_scenario(find_root(project_root), name)


def run_detail(project_root, run_id: str) -> dict[str, Any] | None:
    """Run status, steps and step tree (from the `scenario/` snapshot, or the current file for older
    runs); runs waiting in the `serve` queue have only `status: queued`; None = does not exist."""
    runs = _runs_dir(project_root)
    if not RUN_ID.fullmatch(run_id):
        return None
    queue = _queue(runs)
    if (runs / run_id).is_dir():
        body = _in_queue(_run_detail(runs / run_id), queue)
        return body | _projects.run_tree(find_root(project_root), runs / run_id, body["scenario"])
    return queue.get(run_id)


def step_detail(project_root, run_id: str, path: str) -> dict[str, Any] | None:
    """Run step by path (`copy`, or `propose/copy` for `call`): events, output, files; None = does not exist."""
    d = _runs_dir(project_root) / run_id
    return _step_detail(d, path) if RUN_ID.fullmatch(run_id) and d.is_dir() else None


def run_file(project_root, run_id: str, rel: str) -> Path | None:
    """File inside the run directory; outside it (path traversal, external symlink) or missing → None."""
    d = (_runs_dir(project_root) / run_id).resolve()
    p = (d / rel).resolve()
    return p if RUN_ID.fullmatch(run_id) and p.is_relative_to(d) and p.is_file() else None


def spend(project_root, day: str) -> dict[str, Any]:
    """Daily spend ledger (live runs, UTC day): `{day, total_usd, runs: [{run_id, cost_usd, finished_at}]}`."""
    rows = local_ledger(_runs_dir(project_root), False).rows(day)
    return {"day": day, "total_usd": round(sum(r["cost_usd"] for r in rows), 10), "runs": rows}
