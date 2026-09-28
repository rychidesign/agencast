"""CLI. Jméno příkazu (`agencast`) je jen v pyproject.toml → [project.scripts].

    agencast validate <scénář> [--offline]
    agencast run <scénář> -i klíč=hodnota [--dry-run] [--fake [SKRIPT]] [--callback-url URL]
    agencast runs list | show <run_id>
    agencast serve [--host H] [--port P] [--workers N] [--fake [SKRIPT]] [--cors ORIGIN]   (mimo projekt: režim registru)
    agencast migrate <soubor>
    agencast new project <cesta> [--name N] | agent <jméno> | scenario <jméno>
    agencast rename scenario <staré> <nové> | agent <staré> <nové>
    agencast projects list | add <cesta> [--name N] | rm <jméno>

<scénář> je jméno (ig-post) nebo cesta k .yaml. Kořen projektu = první složka
s workflows/ od aktuální složky nahoru, nebo --project <cesta> (u každého příkazu).
`serve` čte výchozí adresu a port z AGENCAST_HOST a AGENCAST_PORT v prostředí procesu;
.env se načítá až po parsování argumentů.
"""
import argparse
import os
import sys
from pathlib import Path

from . import ConfigErrors, __version__, api, projects as _projects
from .loader import LoadError, load_dotenv, read_frontmatter, read_yaml, version_error
from .fake import Fake
from .record import count, cz, cz_usd
from .validate import require_config, resolve_inputs


def _fail_config(errors: list[str]) -> int:
    for e in errors:
        print(e if e.startswith(("config:", "transient:")) else f"config: {e}", file=sys.stderr)
    return 2


def _fake(arg: str | None, config_models: dict):
    script = read_yaml(Path(arg), arg) if arg else None
    return Fake(script, [m["id"] for m in config_models.values() if m.get("api", "chat") == "chat"],
                [m["id"] for m in config_models.values() if m.get("api", "chat") == "images"])


def _root(a) -> Path:
    return api.find_root(a.project)


def _project(a, *, offline=False, register=False):
    """Ověří scénář; s --fake se modely ověřují proti falešným katalogům. `register` = úspěšný `run`
    zapíše projekt do registru (validate od 0.15.1 ne: je bez vedlejších účinků, volají ho i nástroje
    a testy z cizích kopií projektu); chyba registru příkaz nezastaví."""
    arg = getattr(a, "fake", None)
    fake = _fake(arg, {}) if arg is not None else None  # modely doplní api.load z config.yaml
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
    print(f"v pořádku: {p.scenario['name']} ({count(len(p.order), 'krok', 'kroky', 'kroků')}"
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
        p, fake = _project(a, register=True)
        inputs = resolve_inputs(p.scenario, raw, from_text=True)
        if a.dry_run:
            rec = api.dry_run(p, inputs)
            print((rec.dir / "plan.md").read_text(encoding="utf-8"))
            print(f"\nplán: {rec.dir / 'plan.md'}")
            return 0
        run = api.run(p, inputs, fake=fake, callback_url=a.callback_url, request_key=a.request_key)
    except (ConfigErrors, LoadError) as e:
        return _fail_config(e.errors if isinstance(e, ConfigErrors) else [str(e)])
    ok = run.status == "succeeded"
    print(f"běh {run.run_id}: {'úspěch' if ok else 'chyba'} · {cz(run.duration, 1)} s · {cz_usd(run.cost)} USD")
    if run.error:
        where = f" v kroku {run.error['step']}" if run.error["step"] else ""  # běh, který nezačal, krok nemá
        print(run.rec.mask(f"{run.error['class']}{where}: {run.error['message']}"), file=sys.stderr)
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
                print(f"{s['run_id']:45} ve frontě (agencast serve)")
                continue
            cost = "" if s["cost_usd"] is None else f"{cz_usd(s['cost_usd'])} USD"
            dur = "" if s["duration_s"] is None else f"{cz(s['duration_s'], 1)} s"
            print(f"{s['run_id']:45} {s['status']:30} {dur:>8} {cost:>12} {s['callback']}")
        if not items:
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
    """V projektu nebo s --project jeden projekt (jako do 0.3.x); mimo projekt režim registru (api.md)."""
    from .server import Projects, Server, Webhook
    try:
        if a.workers < 1:
            raise ConfigErrors([f"--workers má být aspoň 1, je {a.workers}"])
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
                raise ConfigErrors(["chybí proměnná prostředí AGENCAST_TOKEN — mimo projekt běží serve v režimu "
                                    "registru a tohle je token serveru (.env v aktuální složce nebo prostředí); "
                                    "jeden projekt: --project <cesta>"])
            hook, projects = None, Projects(token=token, workers=a.workers,
                                            fake=(lambda: _fake(a.fake, {})) if a.fake is not None else None)
        else:
            wf, cfg = _config(a)
            hook = Webhook(wf, fake=_fake(a.fake, cfg["models"]) if a.fake is not None else None, workers=a.workers)
            projects = Projects(hook)
        srv = Server(hook, a.host, a.port, projects, cors=a.cors)
        if not hook:
            projects.start()
    except (ConfigErrors, LoadError) as e:
        return _fail_config(e.errors if isinstance(e, ConfigErrors) else [str(e)])
    except OSError as e:
        return _fail_config([f"server nejde spustit na {a.host}:{a.port}: {e.strerror}"])
    url = f"agencast serve: http://{a.host}:{srv.server_address[1]}"
    fake = " · falešný poskytovatel" if a.fake is not None else ""
    if hook:
        hook.start()
        print(f"{url} — POST /runs, GET /runs/<run_id>, GET /projects/… · workerů {hook.workers} · "
              f"ve frontě {count(hook.q.qsize(), 'běh', 'běhy', 'běhů')} · záznamy {hook.runs}{fake}", flush=True)
    else:
        print(f"{url} — režim registru ({_projects.registry_path()}): GET /projects/…, "
              f"POST /projects/<projekt>/runs · workerů na projekt {a.workers}{fake}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("ukončeno (nedokončené požadavky zůstávají v _queue/ a po startu se zpracují)")
    return 0


def cmd_new(a) -> int:
    try:
        if a.what == "project":
            made = api.new_project(a.name, a.as_name)
        else:
            made = (api.new_agent if a.what == "agent" else api.new_scenario)(a.project, a.name)
    except ConfigErrors as e:
        return _fail_config(e.errors)
    for p in made:
        print(f"vytvořeno: {p}")
    if a.what == "project":
        root = made[0].parent.parent
        print(f"projekt {a.as_name or next(x['name'] for x in api.projects() if x['root'] == str(root))} "
              "přidán do registru")
        print(f"dál: cp {root / '.env.example'} {root / '.env'}, doplň OPENROUTER_API_KEY a zkus\n"
              f"  agencast --project {root} run ukazka --fake")
    return 0


def cmd_rename(a) -> int:
    try:
        root = _root(a)
        rel = f"{'scenarios' if a.what == 'scenario' else 'agents'}/{a.old}.{'yaml' if a.what == 'scenario' else 'md'}"
        tag = api.read_file(root, rel)["etag"]
        rename = api.rename_scenario if a.what == "scenario" else api.rename_agent
        result = rename(root, a.old, tag, a.new)
    except api.Conflict as e:
        return _fail_config([f"{rel}: soubor se během přejmenování změnil (aktuální otisk: {e.etag}); opakuj příkaz"])
    except (ConfigErrors, api.NotFound) as e:
        return _fail_config(e.errors if isinstance(e, ConfigErrors) else [str(e)])
    for rel in result["changed"]:
        print(f"přejmenováno: {root / 'workflows' / rel}")
    return 0


def cmd_projects(a) -> int:
    try:
        if a.projects_cmd == "add":
            print(f"projekt {api.add_project(a.path, a.as_name)} přidán do registru")
        elif a.projects_cmd == "rm":
            api.remove_project(a.name)
            print(f"projekt {a.name} odebrán z registru (soubory zůstávají)")
        else:
            items = api.projects()
            for x in items:
                print(f"{x['name']:30} {x['root']}{'' if x['available'] else '  (nedostupný: chybí workflows/config.yaml)'}")
            if not items:
                print("registr je prázdný — agencast projects add <cesta> nebo agencast new project <cesta>")
    except ConfigErrors as e:
        return _fail_config(e.errors)
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
    ap = argparse.ArgumentParser(prog=Path(sys.argv[0]).name or "agencast", parents=[top],
                                 description=f"AgenCast {__version__} — scénáře s LLM agenty")
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
    s = sub.add_parser("serve", parents=[common], help="webhook server a čtecí API: POST /runs, GET /runs/<run_id>, "
                                                       "/projects/…; AGENCAST_HOST/AGENCAST_PORT; mimo projekt "
                                                       "režim registru (AGENCAST_TOKEN)")
    s.add_argument("--host", default=os.environ.get("AGENCAST_HOST", "127.0.0.1"),
                   help="bind adresa (AGENCAST_HOST; výchozí 127.0.0.1)")
    s.add_argument("--port", type=int, default=None,
                   help="port (AGENCAST_PORT; výchozí 8080; rozsah 1–65535)")
    s.add_argument("--workers", type=int, default=1, metavar="N",
                   help="kolik běhů najednou (výchozí 1 = jeden po druhém; víc = pořadí dokončení není zaručené)")
    s.add_argument("--fake", nargs="?", const="", metavar="SKRIPT", help="falešný poskytovatel bez sítě")
    s.add_argument("--cors", metavar="ORIGIN", help="CORS pro vývoj GUI, např. http://localhost:5173 (vite dev)")
    m = sub.add_parser("migrate", parents=[common], help="převede soubor na aktuální verzi formátu")
    m.add_argument("file", help="scénář, config nebo agent (.md)")
    n = sub.add_parser("new", help="nový projekt, agent nebo scénář ze šablony (nic nepřepisuje)")
    ns = n.add_subparsers(dest="what", required=True)
    np = ns.add_parser("project", help="kostra projektu s ukázkovým agentem a scénářem, zapíše ji do registru")
    np.add_argument("name", metavar="cesta", help="složka projektu (workflows/ v ní ještě nesmí být)")
    np.add_argument("--name", dest="as_name", metavar="JMÉNO", help="jméno v registru (výchozí: jméno složky)")
    pr = sub.add_parser("projects", help="registr projektů (~/.config/agencast/projects.yaml)")
    prs = pr.add_subparsers(dest="projects_cmd", required=True)
    prs.add_parser("list", help="projekty v registru")
    pa = prs.add_parser("add", help="zapíše projekt do registru")
    pa.add_argument("path", metavar="cesta", help="kořen projektu (složka s workflows/)")
    pa.add_argument("--name", dest="as_name", metavar="JMÉNO", help="jméno v registru (výchozí: jméno složky)")
    prs.add_parser("rm", help="odebere projekt z registru (soubory nemaže)").add_argument("name", metavar="jméno")
    for what, help_ in (("agent", "workflows/agents/<jméno>.md"), ("scenario", "workflows/scenarios/<jméno>.yaml")):
        ns.add_parser(what, parents=[common], help=help_).add_argument("name", metavar="jméno")
    rn = sub.add_parser("rename", help="přejmenuje scénář nebo agenta včetně odkazů")
    rns = rn.add_subparsers(dest="what", required=True)
    for what in ("scenario", "agent"):
        p = rns.add_parser(what, parents=[common])
        p.add_argument("old", metavar="staré")
        p.add_argument("new", metavar="nové")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        from_env = a.port is None
        if from_env:
            try:
                a.port = int(os.environ.get("AGENCAST_PORT", "8080"))
            except ValueError:
                return _fail_config(["AGENCAST_PORT musí být celé číslo v rozsahu 1–65535"])
            if not 1 <= a.port <= 65535:
                return _fail_config(["AGENCAST_PORT musí být celé číslo v rozsahu 1–65535"])
    return {"validate": cmd_validate, "run": cmd_run, "runs": cmd_runs, "serve": cmd_serve,
            "migrate": cmd_migrate, "new": cmd_new,
            "rename": cmd_rename, "projects": cmd_projects}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
