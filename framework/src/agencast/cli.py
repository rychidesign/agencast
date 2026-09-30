"""CLI. The command name (`agencast`) is defined only in pyproject.toml → [project.scripts].

    agencast validate <scenario> [--offline]
    agencast run <scenario> -i key=value [--dry-run] [--fake [SCRIPT]] [--callback-url URL]
    agencast runs list | show <run_id>
    agencast serve [--host H] [--port P] [--workers N] [--fake [SCRIPT]] [--cors ORIGIN]   (outside a project: registry mode)
    agencast migrate <file>
    agencast skills list | path | install [--to all] [--prefix DIR] [--copy] [--force]
    agencast docs [show <path>]
    agencast new project <path> [--example showcase|tutorial] [--name N] | agent <name> | scenario <name>
    agencast rename scenario <old> <new> | agent <old> <new>
    agencast projects list | add <path> [--name N] | rm <name>

<scenario> is a name (ig-post) or a path to .yaml. Project root = the first directory
containing workflows/ searching upward from cwd, or --project <path> (for each command).
`serve` reads its default address and port from AGENCAST_HOST and AGENCAST_PORT in the process environment;
.env is loaded after argument parsing.
"""
import argparse
import difflib
import shutil
import os
import sys
from pathlib import Path

from . import ConfigErrors, __version__, api, projects as _projects
from .loader import LoadError, load_dotenv, read_frontmatter, read_yaml, version_error
from .fake import Fake
from .record import count, format_number, format_usd
from .resources import resource_dir
from .validate import require_config, resolve_inputs


def _fail_config(errors: list[str]) -> int:
    for e in errors:
        print(e if e.startswith(("config:", "transient:")) else f"config: {e}", file=sys.stderr)
    return 2


def _fake(arg: str | None, config_models: dict, root: Path | None = None):
    if arg and root and not Path(arg).is_absolute() and not Path(arg).exists():
        arg = str(root / arg)
    script = read_yaml(Path(arg), arg) if arg else None
    return Fake(script, [m["id"] for m in config_models.values() if m.get("api", "chat") == "chat"],
                [m["id"] for m in config_models.values() if m.get("api", "chat") == "images"])


def _root(a) -> Path:
    return api.find_root(a.project)


def _project(a, *, offline=False, register=False):
    """Validate a scenario; with --fake, check models against fake catalogs. `register` = successful `run`
    adds the project to the registry (not validate since 0.15.1: it has no side effects and is also called
    by tools and tests from other project copies); registry errors do not stop the command."""
    arg = getattr(a, "fake", None)
    fake = _fake(arg, {}, _root(a)) if arg is not None else None  # api.load populates models from config.yaml
    p = api.load(a.scenario, project_root=a.project, fake=fake, offline=offline)
    if not register:
        return p, fake
    try:
        msg = api.ensure_project(p.base)
    except ConfigErrors as e:
        msg = "\n".join(f"config: {x}" for x in e.errors)
    if msg:
        print(msg, file=sys.stderr)
    return p, fake


def cmd_validate(a) -> int:
    try:
        p, _ = _project(a, offline=a.offline)
    except ConfigErrors as e:
        return _fail_config(e.errors)
    print(f"valid: {p.scenario['name']} ({count(len(p.order), 'step', 'steps')}"
          f"{', model checks skipped' if a.offline else ''})")
    return 0


def cmd_run(a) -> int:
    raw = {}
    for item in a.input:
        key, sep, value = item.partition("=")
        if not sep:
            return _fail_config([f"input '{item}' must use key=value format"])
        raw[key] = value
    try:
        p, fake = _project(a, register=True)
        inputs = resolve_inputs(p.scenario, raw, from_text=True)
        if a.dry_run:
            rec = api.dry_run(p, inputs)
            print((rec.dir / "plan.md").read_text(encoding="utf-8"))
            print(f"\nplan: {rec.dir / 'plan.md'}")
            return 0
        run = api.run(p, inputs, fake=fake, callback_url=a.callback_url, request_key=a.request_key)
    except (ConfigErrors, LoadError) as e:
        return _fail_config(e.errors if isinstance(e, ConfigErrors) else [str(e)])
    ok = run.status == "succeeded"
    print(f"run {run.run_id}: {'succeeded' if ok else 'failed'} · {format_number(run.duration, 1)} s · {format_usd(run.cost)} USD")
    if run.error:
        where = f" in step {run.error['step']}" if run.error["step"] else ""  # a run that did not start has no step
        print(run.rec.mask(f"{run.error['class']}{where}: {run.error['message']}"), file=sys.stderr)
    if run.callback_failed:
        print("callback not delivered", file=sys.stderr)
    print(f"run record: {run.rec.dir / 'summary.md'}")
    if run.report_url:
        print(f"report: {run.report_url}")
    return 0 if ok else 1


def _config(a) -> tuple[Path, dict]:
    wf = _root(a) / "workflows"
    load_dotenv(wf.parent / ".env")
    load_dotenv(Path.cwd() / ".env")
    return wf, require_config(wf)


def cmd_runs(a) -> int:
    try:
        wf, cfg = _config(a)
    except ConfigErrors as e:
        return _fail_config(e.errors)
    runs = wf.parent / cfg["runs_dir"]
    if a.runs_cmd == "list":
        items = api.runs_list(wf.parent)
        for s in items:
            if s["status"] == "queued":
                print(f"{s['run_id']:45} queued (agencast serve)")
                continue
            cost = "" if s["cost_usd"] is None else f"{format_usd(s['cost_usd'])} USD"
            dur = "" if s["duration_s"] is None else f"{format_number(s['duration_s'], 1)} s"
            print(f"{s['run_id']:45} {s['status']:30} {dur:>8} {cost:>12} {s['callback']}")
        if not items:
            print(f"no runs in {runs}")
        return 0
    d = runs / a.run_id
    for name in ("summary.md", "plan.md"):
        if (d / name).is_file():
            print((d / name).read_text(encoding="utf-8"))
            print(f"\n{d / name}")
            if (d / "report.html").is_file():
                print(d / "report.html")
            return 0
    print(f"run {a.run_id} does not exist in {runs}", file=sys.stderr)
    return 2


def cmd_serve(a) -> int:
    """Single project inside a project or with --project (as in 0.3.x); registry mode outside a project (api.md)."""
    from .server import Projects, Server, Webhook
    try:
        if a.workers < 1:
            raise ConfigErrors([f"--workers must be at least 1, got {a.workers}"])
        try:
            _root(a)
            registry = False
        except ConfigErrors:
            if a.project:
                raise
            registry = True
        if registry:
            load_dotenv(Path.cwd() / ".env")
            if not (token := os.environ.get("AGENCAST_TOKEN")):
                raise ConfigErrors(["missing environment variable AGENCAST_TOKEN — outside a project, serve uses "
                                    "registry mode and requires this server token (.env in the current directory or environment); "
                                    "single project: --project <path>"])
            hook, projects = None, Projects(token=token, workers=a.workers,
                                            fake=(lambda: _fake(a.fake, {})) if a.fake is not None else None)
        else:
            wf, cfg = _config(a)
            hook = Webhook(wf, fake=_fake(a.fake, cfg["models"], wf.parent) if a.fake is not None else None, workers=a.workers)
            projects = Projects(hook)
        srv = Server(hook, a.host, a.port, projects, cors=a.cors)
        if not hook:
            projects.start()
    except (ConfigErrors, LoadError) as e:
        return _fail_config(e.errors if isinstance(e, ConfigErrors) else [str(e)])
    except OSError as e:
        return _fail_config([f"cannot start server at {a.host}:{a.port}: {e.strerror}"])
    url = f"agencast serve: http://{a.host}:{srv.server_address[1]}"
    fake = " · fake provider" if a.fake is not None else ""
    if hook:
        hook.start()
        print(f"{url} — POST /runs, GET /runs/<run_id>, GET /projects/… · workers {hook.workers} · "
              f"queued {count(hook.q.qsize(), 'run', 'runs')} · run records {hook.runs}{fake}", flush=True)
    else:
        print(f"{url} — registry mode ({_projects.registry_path()}): GET /projects/…, "
              f"POST /projects/<project>/runs · workers per project {a.workers}{fake}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("stopped (unfinished requests remain in _queue/ and will be processed on startup)")
    return 0


def cmd_new(a) -> int:
    try:
        if a.what == "project":
            made = api.new_project(a.name, a.as_name, example=a.example)
        else:
            made = (api.new_agent if a.what == "agent" else api.new_scenario)(a.project, a.name)
    except ConfigErrors as e:
        return _fail_config(e.errors)
    for p in made:
        print(f"created: {p}")
    if a.what == "project":
        root = Path(a.name).resolve()
        print(f"project {a.as_name or next(x['name'] for x in api.projects() if x['root'] == str(root))} "
              "added to the registry")
        if a.example == "showcase":
            print(f'next: agencast --project {root} run ig-post -i topic="new coffee" --fake fake/ig-post.yaml')
            return 0
        if a.example == "tutorial":
            print("next: agencast docs show tutorials/01-first-agent-and-scenario.md")
            return 0
        print(f"next: cp {root / '.env.example'} {root / '.env'}, set OPENROUTER_API_KEY and try\n"
              f"  agencast --project {root} run demo --fake")
    return 0


SKILL_TARGETS = {
    "claude": (".claude", "skills"),
    "codex": (".codex", "skills"),
    "opencode": (".config/opencode", "skills"),
    "omp": (".omp", "agent/managed-skills"),
}


def cmd_skills(a) -> int:
    try:
        source = resource_dir("skills")
        if a.skills_cmd == "path":
            print(source)
            return 0
        skills = sorted(p.parent for p in source.glob("*/SKILL.md"))
        if a.skills_cmd == "list":
            for skill in skills:
                fm, _ = read_frontmatter(skill / "SKILL.md", str(skill))
                print(f"{skill.name}: {fm['description']}\n  {skill}")
            return 0
        prefix = a.prefix.expanduser().resolve()
        targets = list(SKILL_TARGETS) if a.to == "all" else (
            a.to.split(",") if a.to else [k for k, (base, _) in SKILL_TARGETS.items() if (prefix / base).is_dir()])
        if unknown := set(targets) - SKILL_TARGETS.keys():
            return _fail_config([f"unknown tools: {', '.join(sorted(unknown))}; use claude,codex,opencode,omp or all"])
        if not targets:
            print("no tools found; use --to all")
        for target in dict.fromkeys(targets):
            base, subdir = SKILL_TARGETS[target]
            dest = prefix / base / subdir
            dest.mkdir(parents=True, exist_ok=True)
            for skill in skills:
                path = dest / skill.name
                if path.is_symlink():
                    if not a.copy and path.resolve() == skill.resolve():
                        print(f"unchanged: {path}")
                        continue
                    path.unlink()
                elif path.exists():
                    if not a.force:
                        print(f"kept: {path} (overwrite: --force)")
                        continue
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                if a.copy:
                    shutil.copytree(skill, path)
                else:
                    path.symlink_to(skill.resolve(), target_is_directory=True)
                print(f"created: {path}")
        return 0
    except ConfigErrors as e:
        return _fail_config(e.errors)
    except (OSError, LoadError) as e:
        return _fail_config([str(e)])


def cmd_docs(a) -> int:
    try:
        root = resource_dir("docs").resolve()
        if a.docs_cmd == "show":
            path = (root / a.path).resolve()
            if Path(a.path).is_absolute() or not path.is_relative_to(root):
                return _fail_config(["path must be relative and inside docs/"])
            if not path.is_file():
                names = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
                nearest = difflib.get_close_matches(a.path, names, n=5, cutoff=0)
                return _fail_config([f"document {a.path} does not exist; closest matches: {', '.join(nearest)}"])
            print(path.read_text(encoding="utf-8"), end="")
        else:
            print(f"documentation: {root}\n  getting-started.md")
            for section in ("tutorials", "spec"):
                for path in sorted((root / section).glob("*.md")):
                    print(f"  {path.relative_to(root)}")
            print("read: agencast docs show <path>\nhttps://github.com/rychidesign/agencast")
        return 0
    except ConfigErrors as e:
        return _fail_config(e.errors)
    except OSError as e:
        return _fail_config([str(e)])


def cmd_rename(a) -> int:
    try:
        root = _root(a)
        rel = f"{'scenarios' if a.what == 'scenario' else 'agents'}/{a.old}.{'yaml' if a.what == 'scenario' else 'md'}"
        tag = api.read_file(root, rel)["etag"]
        rename = api.rename_scenario if a.what == "scenario" else api.rename_agent
        result = rename(root, a.old, tag, a.new)
    except api.Conflict as e:
        return _fail_config([f"{rel}: file changed during rename (current fingerprint: {e.etag}); retry the command"])
    except (ConfigErrors, api.NotFound) as e:
        return _fail_config(e.errors if isinstance(e, ConfigErrors) else [str(e)])
    for rel in result["changed"]:
        print(f"renamed: {root / 'workflows' / rel}")
    return 0


def cmd_projects(a) -> int:
    try:
        if a.projects_cmd == "add":
            print(f"project {api.add_project(a.path, a.as_name)} added to the registry")
        elif a.projects_cmd == "rm":
            api.remove_project(a.name)
            print(f"project {a.name} removed from the registry (files are kept)")
        else:
            items = api.projects()
            for x in items:
                print(f"{x['name']:30} {x['root']}{'' if x['available'] else '  (unavailable: missing workflows/config.yaml)'}")
            if not items:
                print("registry is empty — agencast projects add <path> or agencast new project <path>")
    except ConfigErrors as e:
        return _fail_config(e.errors)
    return 0


def cmd_migrate(a) -> int:
    """Convert a file to the current format version (§5.9 item 2). Nothing to convert in v1."""
    path = Path(a.file)
    if not path.is_file():
        return _fail_config([f"{a.file}: file does not exist"])
    try:
        data = read_frontmatter(path, a.file)[0] if path.suffix == ".md" else read_yaml(path, a.file)
    except LoadError as e:
        return _fail_config([str(e)])
    if err := version_error(data, a.file):
        return _fail_config([err])
    print(f"{a.file}: version {data['version']} is current — nothing to convert")
    return 0


def main(argv=None) -> int:
    top, common = argparse.ArgumentParser(add_help=False), argparse.ArgumentParser(add_help=False)
    for p, default in ((top, None), (common, argparse.SUPPRESS)):  # SUPPRESS: a subcommand does not overwrite --project specified before it
        p.add_argument("--project", metavar="PATH", default=default,
                       help="project root (directory containing workflows/); default: search upward from the current directory")
    ap = argparse.ArgumentParser(prog=Path(sys.argv[0]).name or "agencast", parents=[top],
                                 description=f"AgenCast {__version__} — scenarios with LLM agents")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", parents=[common], help="validate a scenario, agents, skills and config")
    v.add_argument("scenario", help="scenario name or path to workflows/scenarios/<name>.yaml")
    v.add_argument("--offline", action="store_true", help="skip alias checks via GET /models")
    r = sub.add_parser("run", parents=[common], help="run a scenario")
    r.add_argument("scenario", help="scenario name or path to .yaml")
    r.add_argument("-i", "--input", action="append", default=[], metavar="KEY=VALUE",
                   help="scenario input; numbers, true/false, lists and objects as JSON; "
                        "file/files = a path (or a JSON list of paths)")
    r.add_argument("--dry-run", action="store_true", help="generate a plan without making calls")
    r.add_argument("--fake", nargs="?", const="", metavar="SCRIPT",
                   help="fake provider without network access; optional YAML with scripted responses")
    r.add_argument("--callback-url", help="send the result after the run (https only, HMAC signature)")
    r.add_argument("--request-key", help="idempotency key (recorded only in the run record and callback)")
    rs = sub.add_parser("runs", parents=[common], help="run records")
    rss = rs.add_subparsers(dest="runs_cmd", required=True)
    rss.add_parser("list", parents=[common], help="list runs")
    rss.add_parser("show", parents=[common], help="show the run summary.md").add_argument("run_id")
    s = sub.add_parser("serve", parents=[common], help="webhook server and read API: POST /runs, GET /runs/<run_id>, "
                                                       "/projects/…; AGENCAST_HOST/AGENCAST_PORT; outside a project "
                                                       "registry mode (AGENCAST_TOKEN)")
    s.add_argument("--host", default=os.environ.get("AGENCAST_HOST", "127.0.0.1"),
                   help="bind address (AGENCAST_HOST; default 127.0.0.1)")
    s.add_argument("--port", type=int, default=None,
                   help="port (AGENCAST_PORT; default 8080; range 1–65535)")
    s.add_argument("--workers", type=int, default=1, metavar="N",
                   help="concurrent runs (default 1 = sequential; more = completion order is not guaranteed)")
    s.add_argument("--fake", nargs="?", const="", metavar="SCRIPT", help="fake provider without network access")
    s.add_argument("--cors", metavar="ORIGIN", help="CORS for GUI development, e.g. http://localhost:5173 (vite dev)")
    m = sub.add_parser("migrate", parents=[common], help="convert a file to the current format version")
    m.add_argument("file", help="scenario, config or agent (.md)")
    n = sub.add_parser("new", help="create a project, agent or scenario from a template (no overwrites)")
    ns = n.add_subparsers(dest="what", required=True)
    np = ns.add_parser("project", help="create and register a project skeleton with an example agent and scenario")
    np.add_argument("name", metavar="path", help="project directory (must not already contain workflows/)")
    np.add_argument("--example", choices=["showcase", "tutorial"], help="copy a bundled example including fake fixtures")
    np.add_argument("--name", dest="as_name", metavar="NAME", help="registry name (default: directory name)")
    pr = sub.add_parser("projects", help="project registry (~/.config/agencast/projects.yaml)")
    prs = pr.add_subparsers(dest="projects_cmd", required=True)
    prs.add_parser("list", help="list registered projects")
    pa = prs.add_parser("add", help="add a project to the registry")
    pa.add_argument("path", metavar="path", help="project root (directory containing workflows/)")
    pa.add_argument("--name", dest="as_name", metavar="NAME", help="registry name (default: directory name)")
    prs.add_parser("rm", help="remove a project from the registry (keep files)").add_argument("name", metavar="name")
    for what, help_ in (("agent", "workflows/agents/<name>.md"), ("scenario", "workflows/scenarios/<name>.yaml")):
        ns.add_parser(what, parents=[common], help=help_).add_argument("name", metavar="name")
    rn = sub.add_parser("rename", help="rename a scenario or agent and update references")
    rns = rn.add_subparsers(dest="what", required=True)
    for what in ("scenario", "agent"):
        p = rns.add_parser(what, parents=[common])
        p.add_argument("old", metavar="old")
        p.add_argument("new", metavar="new")
    sk = sub.add_parser("skills", help="skills for coding agents")
    sks = sk.add_subparsers(dest="skills_cmd", required=True)
    sks.add_parser("list", help="list skill names, descriptions and paths")
    sks.add_parser("path", help="show the bundled skills directory")
    si = sks.add_parser("install", help="install skills for selected tools")
    si.add_argument("--to", help="claude,codex,opencode,omp or all; default: detected tools")
    si.add_argument("--prefix", type=Path, default=Path.home(), metavar="DIR", help="home directory for installation")
    si.add_argument("--copy", action="store_true", help="copy instead of creating symlinks")
    si.add_argument("--force", action="store_true", help="overwrite existing files and directories")
    doc = sub.add_parser("docs", help="index of bundled documentation")
    ds = doc.add_subparsers(dest="docs_cmd")
    ds.add_parser("show", help="print a document").add_argument("path", help="relative path inside docs/")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        from_env = a.port is None
        if from_env:
            try:
                a.port = int(os.environ.get("AGENCAST_PORT", "8080"))
            except ValueError:
                return _fail_config(["AGENCAST_PORT must be an integer in the range 1–65535"])
            if not 1 <= a.port <= 65535:
                return _fail_config(["AGENCAST_PORT must be an integer in the range 1–65535"])
    return {"validate": cmd_validate, "run": cmd_run, "runs": cmd_runs, "serve": cmd_serve,
            "migrate": cmd_migrate, "new": cmd_new,
            "rename": cmd_rename, "projects": cmd_projects, "skills": cmd_skills, "docs": cmd_docs}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
