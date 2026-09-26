"""Veřejné API pro obálky (DESIGN „Obálky“): CLI, `serve`, později Modal a MCP.

Jen tenké funkce nad validate, engine a record — logika sem nepatří, patří
do jádra a má hermetický test. Tajné klíče jen z prostředí (a `.env`).
"""
from pathlib import Path

from . import ConfigErrors, projects
from .engine import Run, dry_run as _dry_run, run_scenario
from .fake import Fake
from .loader import load_dotenv
from .record import Record, run_status
from .validate import Project, load_config, resolve_inputs, validate

__all__ = ["find_root", "load", "run", "dry_run", "runs_list", "run_status", "new_project", "new_agent",
           "new_scenario", "Project", "Run", "Fake"]


def find_root(project_root=None) -> Path:
    """Kořen projektu: `project_root`, jinak první složka s workflows/ od aktuální složky nahoru."""
    if project_root:
        root = Path(project_root).resolve()
        root = root.parent if root.name == "workflows" else root
        if not (root / "workflows").is_dir():
            raise ConfigErrors([f"{root}: chybí složka workflows/ — --project má ukazovat na kořen projektu"])
        return root
    for d in (Path.cwd(), *Path.cwd().parents):
        if (d / "workflows").is_dir():
            return d
    raise ConfigErrors(["složka workflows/ není v aktuální ani nadřazené složce — použij --project <cesta>"])


def load(scenario_path, *, project_root=None, fake: Fake | None = None, offline: bool = False) -> Project:
    """Ověřený scénář. `scenario_path` = jméno (ig-post → workflows/scenarios/ig-post.yaml v kořeni
    projektu) nebo cesta k .yaml. Načte `.env` z kořene projektu a z aktuální složky. S `fake` se
    modely ověřují proti jeho falešnému /models (bez modelů dostane aliasy z config.yaml)."""
    s = str(scenario_path)
    if not s.endswith((".yaml", ".yml")) and "/" not in s:
        s = str(find_root(project_root) / "workflows" / "scenarios" / f"{s}.yaml")
    wf = Path(s).resolve().parent.parent
    load_dotenv(wf.parent / ".env")
    load_dotenv(Path.cwd() / ".env")
    if fake is not None and not fake.models:
        errs = []
        cfg = load_config(wf, errs)
        if errs:
            raise ConfigErrors(errs)
        fake.models = [m["id"] for m in cfg["models"].values()]
    return validate(s, transport=fake.transport() if fake else None, check_models=not offline)


def run(project: Project, inputs: dict, *, fake: Fake | None = None, callback_url=None, request_key=None,
        **kw) -> Run:
    """Spustí běh a počká na konec. `inputs` projdou kontrolou (default, typy). `kw` pro obálky:
    `run_id` (přidělený při přijetí), `callback_transport`, `error` (běh, který nezačne — vstupy
    se nekontrolují, jdou jen do callbacku)."""
    if kw.get("error") is None:
        inputs = resolve_inputs(project.scenario, inputs)
    return run_scenario(project, inputs, fake=fake, callback_url=callback_url, request_key=request_key, **kw)


def dry_run(project: Project, inputs: dict) -> Record:
    """Složka běhu jen s plan.md a inputs.json."""
    return _dry_run(project, resolve_inputs(project.scenario, inputs))


def runs_list(project_root=None) -> list[dict]:
    """Běhy projektu, nejnovější první: nejdřív čekající ve frontě `serve` (`status: queued`),
    pak záznamy běhů (`run_status`)."""
    wf = find_root(project_root) / "workflows"
    errs = []
    cfg = load_config(wf, errs)
    if errs:
        raise ConfigErrors(errs)
    runs = wf.parent / cfg["runs_dir"]
    queued = sorted(f.stem for f in (runs / "_queue").glob("*.json") if not (runs / f.stem).is_dir())
    dirs = sorted((d for d in runs.glob("*") if d.is_dir() and not d.name.startswith("_")), reverse=True)
    return [{"run_id": r, "status": "queued"} for r in queued] + [run_status(d) for d in dirs]


def new_project(root) -> list[Path]:
    """Kostra projektu v `root` (odmítne existující workflows/); vrací vytvořené soubory."""
    return projects.new_project(root)


def new_agent(project_root, name: str) -> list[Path]:
    """workflows/agents/<name>.md s aliasem modelu z config.yaml projektu; nepřepisuje."""
    return projects.new_agent(find_root(project_root), name)


def new_scenario(project_root, name: str) -> list[Path]:
    """workflows/scenarios/<name>.yaml s prvním agentem projektu; nepřepisuje."""
    return projects.new_scenario(find_root(project_root), name)
