"""CLI. Jméno příkazu (`maw`) je jen v pyproject.toml → [project.scripts].

    maw validate <scénář> [--offline]
    maw run <scénář> -i klíč=hodnota [--dry-run] [--fake [SKRIPT]] [--callback-url URL]
    maw runs list | show <run_id>
"""
import argparse
import sys
from pathlib import Path

from . import ConfigErrors, __version__
from .loader import LoadError, load_dotenv, read_yaml
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
        p, _ = _project(a.scenario, offline=a.offline)
    except ConfigErrors as e:
        return _fail_config(e.errors)
    print(f"v pořádku: {p.scenario['name']} ({len(p.order)} kroků"
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
        p, fake = _project(a.scenario, fake_arg=a.fake)
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
    return 0 if ok else 1


def _runs_dir(workflows: str) -> Path:
    wf = Path(workflows).resolve()
    errs = []
    cfg = load_config(wf, errs)
    if errs:
        raise ConfigErrors(errs)
    return wf.parent / cfg["runs_dir"]


def cmd_runs(a) -> int:
    try:
        runs = _runs_dir(a.workflows)
    except ConfigErrors as e:
        return _fail_config(e.errors)
    if a.runs_cmd == "list":
        dirs = sorted((d for d in runs.glob("*") if d.is_dir() and not d.name.startswith("_")), reverse=True)
        for d in dirs:
            s = run_status(d)
            cost = "" if s["cost_usd"] is None else f"{cz(s['cost_usd'], 4)} USD"
            dur = "" if s["duration_s"] is None else f"{cz(s['duration_s'], 1)} s"
            print(f"{s['run_id']:45} {s['status']:30} {dur:>8} {cost:>12} {s['callback']}")
        if not dirs:
            print(f"žádné běhy v {runs}")
        return 0
    d = runs / a.run_id
    for name in ("summary.md", "plan.md"):
        if (d / name).is_file():
            print((d / name).read_text(encoding="utf-8"))
            print(f"\n{d / name}")
            return 0
    print(f"běh {a.run_id} v {runs} není", file=sys.stderr)
    return 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog=Path(sys.argv[0]).name or "maw",
                                 description=f"multiagent-workflows {__version__} — scénáře s LLM agenty")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="zkontroluje scénář, agenty, skilly a config")
    v.add_argument("scenario", help="cesta k workflows/scenarios/<jméno>.yaml")
    v.add_argument("--offline", action="store_true", help="bez kontroly aliasů přes GET /models")
    r = sub.add_parser("run", help="spustí scénář")
    r.add_argument("scenario")
    r.add_argument("-i", "--input", action="append", default=[], metavar="KLÍČ=HODNOTA",
                   help="vstup scénáře; čísla, true/false, seznamy a objekty jako JSON")
    r.add_argument("--dry-run", action="store_true", help="jen plán, žádné volání")
    r.add_argument("--fake", nargs="?", const="", metavar="SKRIPT",
                   help="falešný poskytovatel bez sítě; volitelně YAML se skriptovanými odpověďmi")
    r.add_argument("--callback-url", help="po běhu pošle výsledek (jen https, podpis HMAC)")
    r.add_argument("--request-key", help="idempotenční klíč (jen do záznamu a callbacku)")
    rs = sub.add_parser("runs", help="záznamy běhů")
    rs.add_argument("--workflows", default="workflows", help="složka workflows (výchozí ./workflows)")
    rss = rs.add_subparsers(dest="runs_cmd", required=True)
    rss.add_parser("list", help="seznam běhů")
    rss.add_parser("show", help="summary.md běhu").add_argument("run_id")
    a = ap.parse_args(argv)
    return {"validate": cmd_validate, "run": cmd_run, "runs": cmd_runs}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
