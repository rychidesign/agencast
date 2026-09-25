"""CLI. Jméno příkazu (`maw`) je jen v pyproject.toml → [project.scripts].

    maw validate <scénář> [--offline]
    maw run <scénář> -i klíč=hodnota [--dry-run] [--fake [SKRIPT]] [--callback-url URL]
    maw runs list | show <run_id>
    maw serve [--host H] [--port P] [--fake [SKRIPT]]
    maw migrate <soubor>

<scénář> je jméno (ig-post) nebo cesta k .yaml. Kořen projektu = první složka
s workflows/ od aktuální složky nahoru, nebo --project <cesta> (u každého příkazu).
"""
import argparse
import sys
from pathlib import Path

from . import ConfigErrors, __version__
from .loader import LoadError, load_dotenv, read_frontmatter, read_yaml, version_error
from .engine import dry_run, run_scenario
from .fake import Fake
from .record import cz, run_status
from .validate import load_config, resolve_inputs, validate


def _fail_config(errors: list[str]) -> int:
    for e in errors:
        print(e if e.startswith(("config:", "transient:")) else f"config: {e}", file=sys.stderr)
    return 2


def _fake(arg: str | None, config_models: dict):
    script = read_yaml(Path(arg), arg) if arg else None
    return Fake(script, [m["id"] for m in config_models.values()])


def _root(a) -> Path:
    """Kořen projektu: --project, jinak první složka s workflows/ od cwd nahoru."""
    if a.project:
        root = Path(a.project).resolve()
        root = root.parent if root.name == "workflows" else root
        if not (root / "workflows").is_dir():
            raise ConfigErrors([f"{root}: chybí složka workflows/ — --project má ukazovat na kořen projektu"])
        return root
    for d in (Path.cwd(), *Path.cwd().parents):
        if (d / "workflows").is_dir():
            return d
    raise ConfigErrors(["složka workflows/ není v aktuální ani nadřazené složce — použij --project <cesta>"])


def _scenario_path(a) -> str:
    """Jméno scénáře → workflows/scenarios/<jméno>.yaml v kořeni projektu; cesta zůstává cestou."""
    s = a.scenario
    if s.endswith((".yaml", ".yml")) or "/" in s:
        return s
    return str(_root(a) / "workflows" / "scenarios" / f"{s}.yaml")


def _project(path: str, *, fake_arg=None, offline=False):
    """Ověří scénář; s --fake se modely ověřují proti falešnému /models."""
    wf = Path(path).resolve().parent.parent
    load_dotenv(wf.parent / ".env")
    load_dotenv(Path.cwd() / ".env")
    fake = None
    if fake_arg is not None:
        errs = []
        cfg = load_config(wf, errs)
        if errs:
            raise ConfigErrors(errs)
        fake = _fake(fake_arg, cfg["models"])
    p = validate(path, transport=fake.transport() if fake else None, check_models=not offline)
    return p, fake


def cmd_validate(a) -> int:
    try:
        p, _ = _project(_scenario_path(a), offline=a.offline)
    except ConfigErrors as e:
        return _fail_config(e.errors)
    print(f"v pořádku: {p.scenario['name']} (kroků: {len(p.order)}"
          f"{', bez kontroly modelů' if a.offline else ''})")
    return 0


def cmd_run(a) -> int:
    raw = {}
    for item in a.input:
        key, sep, value = item.partition("=")
        if not sep:
            return _fail_config([f"vstup '{item}' má mít tvar klíč=hodnota"])
        raw[key] = value
    try:
        p, fake = _project(_scenario_path(a), fake_arg=a.fake)
        inputs = resolve_inputs(p.scenario, raw, from_text=True)
        if a.dry_run:
            rec = dry_run(p, inputs)
            print((rec.dir / "plan.md").read_text(encoding="utf-8"))
            print(f"\nplán: {rec.dir / 'plan.md'}")
            return 0
        run = run_scenario(p, inputs, fake=fake, callback_url=a.callback_url, request_key=a.request_key)
    except (ConfigErrors, LoadError) as e:
        return _fail_config(e.errors if isinstance(e, ConfigErrors) else [str(e)])
    ok = run.status == "succeeded"
    print(f"běh {run.run_id}: {'úspěch' if ok else 'chyba'} · {cz(run.duration, 1)} s · {cz(run.cost, 4)} USD")
    if run.error:
        print(run.rec.mask(f"{run.error['class']} v kroku {run.error['step']}: {run.error['message']}"), file=sys.stderr)
    if run.callback_failed:
        print("callback nedoručen", file=sys.stderr)
    print(f"záznam: {run.rec.dir / 'summary.md'}")
    if run.report_url:
        print(f"report: {run.report_url}")
    return 0 if ok else 1


def _config(a) -> tuple[Path, dict]:
    wf = _root(a) / "workflows"
    load_dotenv(wf.parent / ".env")
    load_dotenv(Path.cwd() / ".env")
    errs = []
    cfg = load_config(wf, errs)
    if errs:
        raise ConfigErrors(errs)
    return wf, cfg


def cmd_runs(a) -> int:
    try:
        wf, cfg = _config(a)
    except ConfigErrors as e:
        return _fail_config(e.errors)
    runs = wf.parent / cfg["runs_dir"]
    if a.runs_cmd == "list":
        dirs = sorted((d for d in runs.glob("*") if d.is_dir() and not d.name.startswith("_")), reverse=True)
        queued = sorted(f.stem for f in (runs / "_queue").glob("*.json") if not (runs / f.stem).is_dir())
        for run_id in queued:
            print(f"{run_id:45} ve frontě (maw serve)")
        for d in dirs:
            s = run_status(d)
            cost = "" if s["cost_usd"] is None else f"{cz(s['cost_usd'], 4)} USD"
            dur = "" if s["duration_s"] is None else f"{cz(s['duration_s'], 1)} s"
            print(f"{s['run_id']:45} {s['status']:30} {dur:>8} {cost:>12} {s['callback']}")
        if not dirs and not queued:
            print(f"žádné běhy v {runs}")
        return 0
    d = runs / a.run_id
    for name in ("summary.md", "plan.md"):
        if (d / name).is_file():
            print((d / name).read_text(encoding="utf-8"))
            print(f"\n{d / name}")
            if (d / "report.html").is_file():
                print(d / "report.html")
            return 0
    print(f"běh {a.run_id} v {runs} není", file=sys.stderr)
    return 2


def cmd_serve(a) -> int:
    from .server import Server, Webhook
    try:
        wf, cfg = _config(a)
        hook = Webhook(wf, fake=_fake(a.fake, cfg["models"]) if a.fake is not None else None)
        srv = Server(hook, a.host, a.port)
    except (ConfigErrors, LoadError) as e:
        return _fail_config(e.errors if isinstance(e, ConfigErrors) else [str(e)])
    except OSError as e:
        return _fail_config([f"server nejde spustit na {a.host}:{a.port}: {e.strerror}"])
    hook.start()
    print(f"maw serve: http://{a.host}:{srv.server_address[1]} — POST /runs, GET /runs/<run_id> · "
          f"ve frontě {hook.q.qsize()} · záznamy {hook.runs}" + (" · falešný poskytovatel" if hook.fake else ""),
          flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("ukončeno (nedokončené požadavky zůstávají v _queue/ a po startu se zpracují)")
    return 0


def cmd_migrate(a) -> int:
    """Převod souboru na aktuální verzi formátu (§5.9 bod 2). Ve v1 není co převádět."""
    path = Path(a.file)
    if not path.is_file():
        return _fail_config([f"{a.file}: soubor neexistuje"])
    try:
        data = read_frontmatter(path, a.file)[0] if path.suffix == ".md" else read_yaml(path, a.file)
    except LoadError as e:
        return _fail_config([str(e)])
    if err := version_error(data, a.file):
        return _fail_config([err])
    print(f"{a.file}: version {data['version']} je aktuální — nic k převodu")
    return 0


def main(argv=None) -> int:
    top, common = argparse.ArgumentParser(add_help=False), argparse.ArgumentParser(add_help=False)
    for p, default in ((top, None), (common, argparse.SUPPRESS)):  # SUPPRESS: podpříkaz nepřepíše --project zadané před ním
        p.add_argument("--project", metavar="CESTA", default=default,
                       help="kořen projektu (složka s workflows/); výchozí: hledá se od aktuální složky nahoru")
    ap = argparse.ArgumentParser(prog=Path(sys.argv[0]).name or "maw", parents=[top],
                                 description=f"multiagent-workflows {__version__} — scénáře s LLM agenty")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", parents=[common], help="zkontroluje scénář, agenty, skilly a config")
    v.add_argument("scenario", help="jméno scénáře nebo cesta k workflows/scenarios/<jméno>.yaml")
    v.add_argument("--offline", action="store_true", help="bez kontroly aliasů přes GET /models")
    r = sub.add_parser("run", parents=[common], help="spustí scénář")
    r.add_argument("scenario", help="jméno scénáře nebo cesta k .yaml")
    r.add_argument("-i", "--input", action="append", default=[], metavar="KLÍČ=HODNOTA",
                   help="vstup scénáře; čísla, true/false, seznamy a objekty jako JSON")
    r.add_argument("--dry-run", action="store_true", help="jen plán, žádné volání")
    r.add_argument("--fake", nargs="?", const="", metavar="SKRIPT",
                   help="falešný poskytovatel bez sítě; volitelně YAML se skriptovanými odpověďmi")
    r.add_argument("--callback-url", help="po běhu pošle výsledek (jen https, podpis HMAC)")
    r.add_argument("--request-key", help="idempotenční klíč (jen do záznamu a callbacku)")
    rs = sub.add_parser("runs", parents=[common], help="záznamy běhů")
    rss = rs.add_subparsers(dest="runs_cmd", required=True)
    rss.add_parser("list", parents=[common], help="seznam běhů")
    rss.add_parser("show", parents=[common], help="summary.md běhu").add_argument("run_id")
    s = sub.add_parser("serve", parents=[common], help="webhook server: POST /runs, GET /runs/<run_id>")
    s.add_argument("--host", default="127.0.0.1", help="výchozí 127.0.0.1")
    s.add_argument("--port", type=int, default=8080, help="výchozí 8080")
    s.add_argument("--fake", nargs="?", const="", metavar="SKRIPT", help="falešný poskytovatel bez sítě")
    m = sub.add_parser("migrate", parents=[common], help="převede soubor na aktuální verzi formátu")
    m.add_argument("file", help="scénář, config nebo agent (.md)")
    a = ap.parse_args(argv)
    return {"validate": cmd_validate, "run": cmd_run, "runs": cmd_runs, "serve": cmd_serve,
            "migrate": cmd_migrate}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
