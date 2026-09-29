"""Project registry, new projects/agents/scenarios from templates and project descriptions for the GUI
(`agencast projects`, `new`, `GET /projects/...`; projects.md, api.md).

Registry = `<AGENCAST_CONFIG_DIR, default ~/.config/agencast>/projects.yaml`,
`projects: [{name, root}]`, without secrets; projects are not scanned.
Templates are strings here, not copies from workflows/ — those are golden tests
and change with them. Never overwrite: existing file = `config` error.
"""
import ast
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

import yaml

from . import ConfigErrors
from .expressions import ExprError, parse, template_parts
from .loader import LoadError, load_yaml, nested_lists, read_frontmatter, read_yaml, step_kind
from .mcp_client import load_mcp, secret_names
from .validate import _strings, env_fields, load_agent, load_skill, require_config, validate

NAME = re.compile(r"[a-z][a-z0-9-]*")  # matches agent and scenario names in the schemas

CONFIG = """\
# Only the project owner may edit this. No secret values: *_env fields contain the NAME
# of an environment variable; its value is in .env (copy .env.example).
version: 1

openrouter:
  api_key_env: OPENROUTER_API_KEY

# Model aliases. Agents and scenarios only use the left-hand names.
models:
  smart:       { id: anthropic/claude-haiku-4.5 }
  fast:       { id: google/gemini-3.5-flash-lite, structured_output: tool_wrapper }
  gemini-image: { id: google/gemini-3.1-flash-image }

runs_dir: ./runs

storage:
  type: local
  local: { path: ./outputs }

# Limits for a single run.
limits:
  run_budget_usd: 1.00
  run_image_budget_usd: 0.30
  run_timeout: 1h
  max_call_depth: 3

# Only for agencast serve.
webhook:
  token_env: WEBHOOK_TOKEN

callback:
  secret_env: CALLBACK_SECRET
"""

ENV_EXAMPLE = """\
# Copy to .env and fill in the values. Do not commit .env to git.
OPENROUTER_API_KEY=
# only for agencast serve
WEBHOOK_TOKEN=
CALLBACK_SECRET=
"""

GITIGNORE = ".env\nruns/\noutputs/\n"

AGENT = """\
---
version: 1
name: {name}
description: {description}
model: {model}{aliases}
limits:
  budget_usd: 0.02
---
{body}
"""

SCENARIO = """\
version: 1
name: {name}
description: {description}
inputs:
  topic: {{ type: string, default: coffee, description: What to write about }}
outputs:
  text: {{ type: string }}
steps:
  - id: write
    ask:
      agent: {agent}
      prompt: "Write two sentences about: {{{{ inputs.topic }}}}"
  - id: result
    output:
      text: "{{{{ steps.write.text }}}}"
"""


def etag(text: str | None) -> str | None:
    """File version hash for editing operations (edit.py): sha256 of content, None = no file."""
    return None if text is None else hashlib.sha256(text.encode()).hexdigest()


def _etag(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_name(name: str, what: str):
    if not NAME.fullmatch(name):
        raise ConfigErrors([f"{what} '{name}': name must use lowercase letters, digits and hyphens, starting with a letter"])


def _write(files: dict[Path, str]) -> list[Path]:
    if taken := [p for p in files if p.exists()]:
        raise ConfigErrors([f"{p}: already exists — refusing to overwrite" for p in taken])
    for p, text in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return list(files)


# --- registry ---------------------------------------------------------------------

def registry_path() -> Path:
    return Path(os.environ.get("AGENCAST_CONFIG_DIR") or Path.home() / ".config" / "agencast") / "projects.yaml"


class ProjectConflict(ConfigErrors):
    """Project conflict returned as HTTP 409 by the API; the CLI treats it as a config error."""


def _read_registry() -> dict[str, Any]:
    p = registry_path()
    if not p.is_file():
        return {}
    try:
        data = read_yaml(p, str(p)) or {}
    except LoadError as e:
        raise ConfigErrors([str(e)]) from None
    if not isinstance(data, dict):
        raise ConfigErrors([f"{p}: expected format projects: [{{name, root}}]"])
    items = data.get("projects") or []
    if not isinstance(items, list) or not all(
            isinstance(x, dict) and isinstance(x.get("name"), str) and isinstance(x.get("root"), str) for x in items):
        raise ConfigErrors([f"{p}: expected format projects: [{{name, root}}]"])
    if "projects_root" in data and not isinstance(data["projects_root"], str):
        raise ConfigErrors([f"{p}: projects_root must be a path string"])
    return data


def _read() -> list[dict[str, str]]:
    return _read_registry().get("projects", [])


def projects_root() -> Path:
    """Root for projects created in the GUI; default `~/workspace`."""
    try:
        return Path(_read_registry().get("projects_root", "~/workspace")).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as e:
        raise ConfigErrors([f"projects_root: invalid path ({e})"]) from None


def normalize_root(value: str | Path, base: Path | None = None) -> Path:
    """Expand `~`, absolute paths or paths under `base`; reject `..` and relative paths escaping the base."""
    try:
        path = Path(value).expanduser()
        if ".." in path.parts:
            raise ConfigErrors(["root: path must not contain '..'"])
        if path.is_absolute():
            return path.resolve()
        if base is None:
            return path.resolve()
        base = base.resolve()
        root = (base / path).resolve()
    except (OSError, RuntimeError, TypeError, ValueError) as e:
        raise ConfigErrors([f"root: invalid path ({e})"]) from None
    if not root.is_relative_to(base):
        raise ConfigErrors([f"root: relative path must stay under {base}"])
    return root


def registry_writable() -> bool:
    """Whether the process can write the registry atomically (file and directory for replacement)."""
    path = registry_path()
    if path.exists():
        if not os.access(path, os.W_OK):
            return False
        directory = path.parent
    else:
        directory = path.parent
        while not directory.exists() and directory != directory.parent:
            directory = directory.parent
    return os.access(directory, os.W_OK | os.X_OK)


def _save(change: Callable[[list[dict[str, str]]], Any]):
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.with_suffix(p.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = _read_registry()
        items = data.get("projects") or []
        result = change(items)
        data["projects"] = items
        tmp = p.with_suffix(".tmp")
        tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        tmp.replace(p)  # serve reads the registry on every request → never expose a partial file
    return result


def list_projects() -> list[dict[str, str | bool]]:
    """Registry projects; `available: false` = missing workflows/config.yaml (keep the entry, with `reason`)."""
    out: list[dict[str, str | bool]] = []
    for x in _read():
        cfg = Path(x["root"]) / "workflows" / "config.yaml"
        out.append({"name": x["name"], "root": x["root"], "available": cfg.is_file()}
                   | ({} if cfg.is_file() else {"reason": f"missing {cfg}"}))
    return out


def default_name(root: Path) -> str:
    return re.sub(r"[^a-z0-9]+", "-", root.name.lower()).strip("-")


def _checked_name(root: Path, name: str | None, items: list[dict[str, str]]) -> str:
    name = name or default_name(root)
    other = next((x for x in items if x["name"] == name), None)
    if other:
        raise ProjectConflict([f"project '{name}' is already in the registry ({other['root']}) — choose a name: agencast projects add {root} --name <name>"])
    if not NAME.fullmatch(name):
        raise ConfigErrors([f"project '{name}' must use lowercase letters, digits and hyphens, starting with a letter — "
                            f"choose a name: agencast projects add {root} --name <name>"])
    return name


def add(root: Path, name: str | None = None) -> str:
    """Add a project to the registry; default name = folder (kebab-case). Return the name."""
    def append(items):
        if hit := next((x for x in items if Path(x["root"]) == root), None):
            raise ProjectConflict([f"{root}: already in the registry as '{hit['name']}'"])
        checked_name = _checked_name(root, name, items)
        items.append({"name": checked_name, "root": str(root)})
        return checked_name
    return _save(append)


def remove(name: str):
    def discard(items):
        if not any(x["name"] == name for x in items):
            raise ConfigErrors([f"project '{name}' is not in the registry ({registry_path()})"])
        items[:] = [x for x in items if x["name"] != name]
    _save(discard)


def ensure(root: Path) -> str | None:
    """After a successful run, register the project if absent. Return a message for stderr."""
    if any(Path(x["root"]) == root for x in _read()):
        return None
    return f"project {add(root)} added to the registry ({registry_path()})"


# --- templates ------------------------------------------------------------------------

def new_project(root, name: str | None = None, *, example: str | None = None) -> list[Path]:
    """Project skeleton with one agent and scenario that pass both `validate --offline` and `--fake`;
    register it immediately (check the name before creating files)."""
    root = Path(root).resolve()
    wf = root / "workflows"
    if wf.exists():
        raise ProjectConflict([f"{wf}: already exists — add an existing project with agencast projects add"])
    items = _read()
    if hit := next((x for x in items if Path(x["root"]) == root), None):
        raise ProjectConflict([f"{root}: already in the registry as '{hit['name']}'"])
    name = _checked_name(root, name, items)
    files = {
        wf / "config.yaml": CONFIG,
        root / ".env.example": ENV_EXAMPLE,
        wf / "agents" / "writer.md": AGENT.format(
            name="writer", description="Write short texts on a given topic", model="smart", aliases="",
            body="Write short, factual texts in English. Text only, no emoji or headings."),
        wf / "scenarios" / "demo.yaml": SCENARIO.format(
            name="demo", description="Write a short text on a given topic", agent="writer"),
    }
    if example is not None:
        from .resources import resource_dir
        if example not in {"showcase", "tutorial"}:
            raise ConfigErrors([f"unknown example: {example}"])
        source = resource_dir("examples") / example
        files = {}
        for part in ("workflows", "fake", ".env.example", "README.md"):
            item = source / part
            for path in sorted(item.rglob("*")) if item.is_dir() else [item]:
                if path.is_file():
                    files[root / path.relative_to(source)] = path.read_text(encoding="utf-8")
    if not (root / ".gitignore").exists():
        files[root / ".gitignore"] = GITIGNORE
    made = _write(files)
    add(root, name)
    return made


def _workflows(root: Path):
    wf = root / "workflows"
    return wf, require_config(wf)


def _description(description) -> str | None:
    """API description as a quoted YAML string (JSON strings are valid YAML); None = template TODO."""
    if description is not None and not isinstance(description, str):
        raise ConfigErrors(["description: must be a string"])
    return None if description is None else json.dumps(description, ensure_ascii=False)


def new_agent(root: Path, name: str, description: str | None = None, model: str | None = None) -> list[Path]:
    """Minimal agent; model = `model` (config.yaml alias) or the first alias; list other aliases in a comment."""
    _check_name(name, "agent")
    wf, cfg = _workflows(root)
    aliases = list(cfg["models"])
    if model is not None and (not isinstance(model, str) or model not in aliases):
        raise ConfigErrors([f"model: {model!r} is not an alias from config.yaml (available: {', '.join(aliases)})"])
    return _write({wf / "agents" / f"{name}.md": AGENT.format(
        name=name, description=_description(description) or "TODO — what the agent does (for people, not sent to the model)",
        model=model or aliases[0], aliases=f"    # alias from config.yaml: {', '.join(aliases)}",
        body="TODO: agent instructions (system prompt).")})


def new_scenario(root: Path, name: str, description: str | None = None) -> list[Path]:
    """Minimal scenario (input → ask → output) with the project's first agent alphabetically."""
    _check_name(name, "scenario")
    wf, _ = _workflows(root)
    desc = _description(description)
    agents = sorted(p.stem for p in (wf / "agents").glob("*.md"))
    if not agents:
        raise ConfigErrors([f"{wf / 'agents'}: project has no agent — first run agencast new agent <name>"])
    return _write({wf / "scenarios" / f"{name}.yaml": SCENARIO.format(
        name=name, description=desc or "TODO — what the scenario does", agent=agents[0])})


# --- project description for the GUI (api.md) ------------------------------------------------
# Load YAML with loader, errors from validate (check_models=False) — even broken files can be displayed.

def _refs(own: dict[str, Any]) -> list[str]:
    """`steps.<id>.<field>` references in step expressions and templates (excluding nested steps)."""
    out = set()
    for path, text in _strings(own):
        if "{{" in text:
            try:
                srcs = [e for _, _, e in template_parts(text)]
            except ExprError:
                continue
        elif path in (("when",), ("switch", "value")) or (len(path) == 2 and path[0] == "set"):
            srcs = [text]
        else:
            continue
        for src in srcs:
            try:
                tree = parse(src)
            except ExprError:
                continue
            out |= {f"steps.{n.value.attr}.{n.attr}" for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                    and isinstance(n.value, ast.Attribute) and isinstance(n.value.value, ast.Name)
                    and n.value.value.id == "steps"}
    return sorted(out)


def _steps(steps, flat: list[dict[str, Any]], at: tuple[Any, ...] = ("steps",)) -> list[dict[str, Any]]:
    """Step tree for cards; `nn` = depth-first file order (as in run folders). `flat` = all steps.
    `address` = step path in the document (`at` + index), used by editing operations (edit.py)."""
    out = []
    for i, st in enumerate(steps if isinstance(steps, list) else []):
        if not isinstance(st, dict):
            continue
        k = step_kind(st)
        own = {key: v for key, v in st.items() if key not in ("id", "when", "parallel")}
        if k == "switch" and isinstance(st["switch"], dict):
            own["switch"] = {key: v for key, v in st["switch"].items() if key not in ("cases", "default")}
        item: dict[str, Any] = {"nn": len(flat) + 1, "address": [*at, i], "id": st.get("id"), "type": k, "when": st.get("when"), "fields": own,
                "refs": _refs({**own, **({"when": st["when"]} if "when" in st else {})})}
        if k in ("ask", "task", "call") and isinstance(st[k], dict):
            item["call" if k == "call" else "agent"] = st[k].get("scenario" if k == "call" else "agent")
        flat.append(item)
        for p, lst in nested_lists(st):
            sub = _steps(lst, flat, (*at, i, *p))
            if p[0] == "parallel":
                item.setdefault("branches", {})[p[1]] = sub
            elif p[1] == "cases":
                item.setdefault("cases", {})[p[2]] = sub
            else:
                item["default"] = sub
        if k == "switch":
            item.setdefault("cases", {})
            item.setdefault("default", [])
        out.append(item)
    return out


# Validation/loader message prefix: `<file>[, line N][: step "id"][, field|: field]: …` (_Checker.err,
# schema_errors, load_yaml). Scenarios use the file name (ig-post.yaml), others the path within workflows/.
ERROR_HEAD = re.compile(r"(?P<file>agents/[^/:,\s]+\.md|skills/[^/:,\s]+/SKILL\.md|(?:scenarios/)?[^/:,\s]+\.yaml)"
                        r"(?:, line (?P<line>\d+))?(?:: step [\"'](?P<step>[^\"']+)[\"'])?"
                        r"(?:(?:, |: )(?P<field>[\w.\[\]-]+(?: \(key\))?)(?=: ))?: ")


def error_fields(message: str, root: Path) -> dict[str, Any]:
    """Message as an object for the GUI (api.md): `{message, file?, step?, field?, line?}`; `message` unchanged.
    ponytail: parse fields from the message prefix — other formats only have `message`."""
    out: dict[str, Any] = {"message": message}
    m = ERROR_HEAD.match(message.removeprefix(f"{root / 'workflows'}/"))
    if not m:
        return out
    f = m["file"]
    # ponytail: scenarios named config or mcp are confused with config.yaml/mcp.yaml here
    out["file"] = f if "/" in f or f in ("config.yaml", "mcp.yaml") else f"scenarios/{f}"
    out |= {k: m[k] for k in ("step", "field") if m[k]}
    if m["line"]:
        out["line"] = int(m["line"])
    return out


def _scenario(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(scenario description with step tree and validation errors, all steps)."""
    info: dict[str, Any] = {"name": path.stem, "etag": _etag(path), "description": None, "inputs": {}, "outputs": {}, "callable": False}
    try:
        sc = read_yaml(path, path.name)
    except LoadError as e:
        return {**info, "steps_count": 0, "errors": [str(e)], "steps": [], "types": []}, []
    sc = sc if isinstance(sc, dict) else {}
    flat: list[dict[str, Any]] = []
    tree = _steps(sc.get("steps"), flat)
    try:
        validate(path, check_models=False)
        errors = []
    except ConfigErrors as e:
        errors = e.errors
    info.update({k: sc.get(k) or info[k] for k in ("description", "inputs", "outputs")},
                callable=sc.get("callable") is True, steps_count=len(flat), errors=errors, steps=tree,
                types=[x["type"] for x in tree])
    return info, flat


def describe_scenario(root: Path, name: str) -> dict[str, Any] | None:
    """Scenario for step cards; None = does not exist."""
    path = root / "workflows" / "scenarios" / f"{name}.yaml"
    return _scenario(path)[0] if NAME.fullmatch(name) and path.is_file() else None


def describe_project(root: Path) -> dict[str, Any]:
    """Scenarios, agents, skills, MCP servers (without secrets), aliases, limits and their links."""
    wf, cfg = _workflows(root)
    errs = []
    mcp = load_mcp(wf, errs)
    links = {"scenario_agent": set(), "scenario_step_agent": set(), "scenario_scenario": set(), "agent_skill": set(),
             "agent_server": set(), "scenario_model": set()}
    scenarios = []
    for path in sorted((wf / "scenarios").glob("*.yaml")):
        info, flat = _scenario(path)
        del info["steps"]
        scenarios.append(info)
        links["scenario_agent"] |= {(info["name"], s["agent"]) for s in flat if isinstance(s.get("agent"), str)}
        links["scenario_step_agent"] |= {(info["name"], s["id"], s["agent"]) for s in flat
                                         if isinstance(s.get("agent"), str) and isinstance(s["id"], str)}
        links["scenario_scenario"] |= {(info["name"], s["call"]) for s in flat if isinstance(s.get("call"), str)}
        links["scenario_model"] |= {(info["name"], m) for s in flat if s["type"] == "image"
                                    and isinstance(s["fields"]["image"], dict)
                                    and isinstance(m := s["fields"]["image"].get("model"), str)}
    agents = []
    for path in sorted((wf / "agents").glob("*.md")):
        a_errs = []
        try:
            fm = read_frontmatter(path, f"agents/{path.name}")[0]
        except LoadError as e:
            fm, a_errs = {}, [str(e)]
        fm = fm if isinstance(fm, dict) else {}
        if not a_errs:
            load_agent(wf, path.stem, cfg, a_errs, mcp=mcp)
        model = fm.get("model")
        agents.append({"name": path.stem, "etag": _etag(path), "description": fm.get("description"), "model": model,
                       "model_id": cfg["models"].get(model, {}).get("id") if isinstance(model, str) else None,
                       "skills": fm.get("skills") or [], "mcp": fm.get("mcp") or [], "tools": fm.get("tools") or {},
                       "errors": a_errs})
        links["agent_skill"] |= {(path.stem, x) for x in agents[-1]["skills"] if isinstance(x, str)}
        links["agent_server"] |= {(path.stem, x) for x in agents[-1]["mcp"] if isinstance(x, str)}
    skills = []
    for path in sorted((wf / "skills").glob("*/SKILL.md")):
        s_errs = []
        s = load_skill(wf, path.parent.name, s_errs, "skills")
        skills.append({"name": path.parent.name, "etag": _etag(path), "description": s[1] if s else None, "errors": s_errs})
    servers = [{"name": n, "type": "stdio" if "command" in s else "http", "agents": s["agents"],
                "tools": s.get("tools"), "scenarios": s.get("scenarios")} for n, s in mcp.items()]
    # variables from config.yaml (*_env) and mcp.yaml (env, bearer_token_env): presence only, never values
    env = {n: bool(os.environ.get(n)) for n in sorted({n for _, n in env_fields(cfg)} | set(secret_names(mcp)))}
    # 0.8.0: alias → files using it (agent via model, scenario via image.model); [] = unused
    used: dict[str, list[str]] = {a: [] for a in cfg["models"]}
    for a in agents:
        if isinstance(a["model"], str):
            used.setdefault(a["model"], []).append(f"agents/{a['name']}.md")
    for sc, m in sorted(links["scenario_model"]):
        used.setdefault(m, []).append(f"scenarios/{sc}.yaml")
    return {"root": str(root), "models": {a: m["id"] for a, m in cfg["models"].items()}, "limits": cfg["limits"], "env": env,
            "scenarios": scenarios, "agents": agents, "skills": skills, "mcp_servers": servers,
            "links": {k: sorted(map(list, v)) for k, v in links.items()}, "models_used": used, "errors": errs}


def text_tree(text: str, where: str) -> list[dict[str, Any]]:
    """Step tree from scenario YAML text; unreadable YAML = empty tree (validate reports errors)."""
    try:
        sc = load_yaml(text, where)
    except LoadError:
        return []
    return _steps(sc.get("steps") if isinstance(sc, dict) else None, [])


def _tree(path: Path) -> list[dict[str, Any]]:
    return text_tree(path.read_text(encoding="utf-8"), path.name)


def run_tree(root: Path, run_dir: Path, scenario: str | None) -> dict[str, Any]:
    """Step tree for run details (`steps` shape from GET …/scenarios/<s>): from snapshot `<run>/scenario/`
    (0.7.0, including called scenarios in `callees`); older runs use the current file (`tree_source: current`)."""
    snap = run_dir / "scenario"
    if snap.is_dir():
        trees = {p.stem: _tree(p) for p in sorted(snap.glob("*.yaml"))}
        return {"tree": trees.pop(scenario, []) if scenario else [], "callees": trees, "tree_source": "snapshot"}
    path = root / "workflows" / "scenarios" / f"{scenario}.yaml"
    ok = scenario is not None and NAME.fullmatch(scenario) and path.is_file()
    return {"tree": _tree(path) if ok else [], "callees": {}, "tree_source": "current"}
