"""Veřejné API pro obálky (DESIGN „Obálky“): CLI, `serve`, později Modal a MCP.

Jen tenké funkce nad validate, engine a record — logika sem nepatří, patří
do jádra a má hermetický test. Tajné klíče jen z prostředí (a `.env`).
"""
import json
import re
from pathlib import Path
from typing import Any

from . import ConfigErrors, projects as _projects
from .edit import (Conflict, NotFound, OpError, add_step, batch, delete_agent, delete_scenario, delete_skill, delete_step,
                   file_etag, move_step, read_file, render, replace_step, set_agent, set_config, set_header, set_skill,
                   update_step, validate_text, write_file)
from .engine import RUN_ID, Run, dry_run as _dry_run, run_scenario
from .fake import Fake
from .loader import LoadError, load_dotenv, read_yaml
from .record import Record, run_detail as _run_detail, run_status, step_detail as _step_detail
from .task import local_ledger
from .validate import Project, load_config, resolve_inputs, validate

__all__ = ["find_root", "load", "run", "dry_run", "runs_list", "run_status", "new_project", "new_agent",
           "new_scenario", "projects", "add_project", "remove_project", "ensure_project", "describe_project", "describe_scenario", "run_detail", "run_file",
           "last_run", "step_detail",
           "spend", "Project", "Run", "Fake",
           # editační operace pro GUI (edit.py, api.md „Editace“): soubor je pravda, otisk, validace před zápisem
           "Conflict", "NotFound", "set_header", "add_step", "update_step", "move_step", "delete_step",
           "delete_scenario", "set_agent", "delete_agent", "set_skill", "delete_skill", "set_config", "read_file",
           "write_file", "validate_text",
           # 0.8.0: dávka a náhled bez zápisu, celý krok, lehký otisk souboru
           "OpError", "batch", "render", "replace_step", "file_etag"]


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


def _runs_dir(project_root) -> Path:
    """`runs_dir` z config.yaml; čtení běhů nepotřebuje platný config (nalezy-api 4) — stačí to pole,
    a když ani to nejde přečíst, výchozí `./runs`."""
    wf = find_root(project_root) / "workflows"
    try:
        cfg = read_yaml(wf / "config.yaml", "config.yaml")
    except (OSError, LoadError):
        cfg = None
    d = cfg.get("runs_dir") if isinstance(cfg, dict) else None
    return wf.parent / (d if isinstance(d, str) else "./runs")


def _queue(runs: Path) -> dict[str, dict[str, Any]]:
    """Záznamy fronty `serve` (nejstarší první) s `queue_position` jako v `GET /runs/<id>`
    (čekající + běžící přede mnou, včetně mě). Záznam zmizí až po callbacku."""
    entries = []
    for f in (runs / "_queue").glob("*.json"):
        try:
            entries.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass  # běh právě skončil (nebo se záznam zapisuje)
    return {e["run_id"]: {"run_id": e["run_id"], "status": "queued", "state": "queued", "scenario": e.get("scenario"),
                          "queue_position": sum(x["queued_ns"] <= e["queued_ns"] for x in entries)}
            for e in sorted(entries, key=lambda e: e["queued_ns"])}


def _in_queue(info: dict[str, Any], queue: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """0.8.0: složka běhu ze fronty `serve`, jejíž zámek (ještě) nikdo nedrží a která neskončila, je `queued`
    (pracovní vlákno ji právě převzalo, nebo čeká na restart serveru) — nikdy `interrupted` ani `dry_run`."""
    if info["run_id"] in queue and info["state"] in ("interrupted", "dry_run"):
        info.update(status="queued", state="queued", queue_position=queue[info["run_id"]]["queue_position"])
    return info


def runs_list(project_root=None, scenario: str | None = None, limit: int | None = None) -> list[dict]:
    """Běhy projektu, nejnovější první: nejdřív čekající ve frontě `serve` (`status: queued`),
    pak záznamy běhů (`run_status`). `scenario` filtruje podle jména v run_id, `limit` ořízne
    seznam dřív, než se čtou záznamy (0.7.0)."""
    runs = _runs_dir(project_root)
    mine = re.compile(rf"\d{{8}}-\d{{6}}-{re.escape(scenario)}-[0-9a-f]{{4}}") if scenario else RUN_ID
    queue = _queue(runs)
    queued = [q for q in queue.values() if mine.fullmatch(q["run_id"]) and not (runs / q["run_id"]).is_dir()]
    dirs = sorted((d for d in runs.glob("*") if d.is_dir() and mine.fullmatch(d.name)), reverse=True)
    if limit is not None:
        queued, dirs = queued[:limit], dirs[:max(limit - len(queued), 0)]
    return queued + [_in_queue(run_status(d), queue) for d in dirs]


def last_run(project_root, scenario: str | None = None) -> dict[str, Any] | None:
    """Nejnovější běh (projektu nebo scénáře) pro stavový čip GUI: `{run_id, state, finished_at, cost_usd}`."""
    r = runs_list(project_root, scenario, limit=1)
    return {k: r[0].get(k) for k in ("run_id", "state", "finished_at", "cost_usd")} if r else None


def new_project(root, name: str | None = None) -> list[Path]:
    """Kostra projektu v `root` (odmítne existující workflows/), zapsaná do registru pod `name`
    (výchozí jméno složky); vrací vytvořené soubory."""
    return _projects.new_project(root, name)


def new_agent(project_root, name: str, description: str | None = None, model: str | None = None) -> list[Path]:
    """workflows/agents/<name>.md s aliasem modelu z config.yaml projektu (`model`, jinak první); nepřepisuje."""
    return _projects.new_agent(find_root(project_root), name, description, model)


def new_scenario(project_root, name: str, description: str | None = None) -> list[Path]:
    """workflows/scenarios/<name>.yaml s prvním agentem projektu; nepřepisuje."""
    return _projects.new_scenario(find_root(project_root), name, description)


def projects() -> list[dict[str, str | bool]]:
    """Registr projektů: `[{name, root, available}]` (projects.md)."""
    return _projects.list_projects()


def add_project(path, name: str | None = None) -> str:
    """Zapíše projekt (kořen s workflows/) do registru; vrací jeho jméno."""
    return _projects.add(find_root(path), name)


def remove_project(name: str):
    _projects.remove(name)


def ensure_project(root) -> str | None:
    """Po úspěšném validate/run: projekt mimo registr do něj přidá; vrací hlášku pro stderr (nebo None)."""
    return _projects.ensure(Path(root).resolve())


def describe_project(project_root) -> dict[str, Any]:
    """Projekt pro GUI: scénáře (s posledním během), agenti, skilly, MCP servery, aliasy, limity, vazby (api.md)."""
    root = find_root(project_root)
    body = _projects.describe_project(root)
    for sc in body["scenarios"]:
        sc["last_run"] = last_run(root, sc["name"])
    return body


def describe_scenario(project_root, name: str) -> dict[str, Any] | None:
    """Strom kroků scénáře pro karty (api.md); None = scénář neexistuje."""
    return _projects.describe_scenario(find_root(project_root), name)


def run_detail(project_root, run_id: str) -> dict[str, Any] | None:
    """Stav běhu, jeho kroky a strom kroků (ze snímku `scenario/`, u starších běhů ze současného
    souboru); čekající ve frontě `serve` jen `status: queued`; None = neexistuje."""
    runs = _runs_dir(project_root)
    if not RUN_ID.fullmatch(run_id):
        return None
    queue = _queue(runs)
    if (runs / run_id).is_dir():
        body = _in_queue(_run_detail(runs / run_id), queue)
        return body | _projects.run_tree(find_root(project_root), runs / run_id, body["scenario"])
    return queue.get(run_id)


def step_detail(project_root, run_id: str, path: str) -> dict[str, Any] | None:
    """Krok běhu podle cesty (`copy`, u `call` `navrh/copy`): události, výstup, soubory; None = není."""
    d = _runs_dir(project_root) / run_id
    return _step_detail(d, path) if RUN_ID.fullmatch(run_id) and d.is_dir() else None


def run_file(project_root, run_id: str, rel: str) -> Path | None:
    """Soubor uvnitř složky běhu; mimo ni (path traversal, symlink ven) nebo neexistuje → None."""
    d = (_runs_dir(project_root) / run_id).resolve()
    p = (d / rel).resolve()
    return p if RUN_ID.fullmatch(run_id) and p.is_relative_to(d) and p.is_file() else None


def spend(project_root, day: str) -> dict[str, Any]:
    """Denní kniha útraty (ostré běhy, den UTC): `{day, total_usd, runs: [{run_id, cost_usd, finished_at}]}`."""
    rows = local_ledger(_runs_dir(project_root), False).rows(day)
    return {"day": day, "total_usd": round(sum(r["cost_usd"] for r in rows), 10), "runs": rows}
