"""Webhook server (webhook.md, D2): `POST /runs` hned odpoví 202 + run_id, výsledek
přijde později na `callback_url`. `GET /runs/<run_id>` vrací stav. Rodina
`/projects/...` (api.md, od 0.4.0) čte projekty pro GUI — jeden projekt, nebo
registr (projects.md) s tokenem serveru `AGENCAST_TOKEN`; od 0.5.0 i editační
operace (PUT/PATCH/DELETE, api.md „Editace“) nad `api` → edit.py.

Stdlib `ThreadingHTTPServer`: požadavky obsluhují vlákna, běhy `workers`
pracovních vláken nad jednou frontou (výchozí 1 → jeden běh po druhém; víc →
pořadí dokončení není zaručené). Fronta a request_key jsou soubory, takže
přežijí restart serveru:

    <runs>/_queue/<run_id>.json        požadavek ve frontě (smaže se po callbacku)
    <runs>/_queue/keys/<sha256>.json   request_key → run_id (platí, dokud ho někdo nesmaže)
"""
import hashlib
import hmac
import json
import mimetypes
import os
import queue
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from . import ConfigErrors, AgencastError, api
from .engine import RUN_ID, RUN_ID_TRIES, new_run_id
from .projects import default_name, error_fields, registry_path
from .validate import Project, load_config, resolve_inputs

FIELDS = ("scenario", "inputs", "callback_url", "request_key")
CALLBACK_PREFIXES = ("https://", "http://127.0.0.1:", "http://127.0.0.1/")  # 127.0.0.1 jen pro testy (ISSUES)
MAX_BODY = 1_000_000
UNAUTHORIZED = {"error": "chybí nebo nesedí token (hlavička Authorization: Bearer …)"}
UI = Path(__file__).resolve().parent / "ui"  # sestavené GUI (ui/ → npm run build); v gitu není
NO_UI = {"error": "GUI není sestavené — ve složce ui/ repozitáře spusť npm install a npm run build "
                  f"(výstup patří do {UI})"}


class Webhook:
    """Přijetí požadavku, fronta a pracovní vlákno; HTTP je jen tenká vrstva `Handler`."""

    def __init__(self, workflows: Path, *, fake=None, callback_transport=None, workers: int = 1,
                 token: str | None = None):
        """`token` = token serveru v režimu registru; jinak se bere z `webhook.token_env` projektu."""
        errs = []
        c = load_config(workflows, errs)
        if errs or c is None:
            raise ConfigErrors(errs)
        self.config = c
        need = ([] if token else [c["webhook"]["token_env"]]) + [c["callback"]["secret_env"]] + (
            [] if fake else [c["openrouter"]["api_key_env"]])
        if missing := [n for n in need if not os.environ.get(n)]:
            raise ConfigErrors([f"chybí proměnná prostředí {n} (.env nebo prostředí)" for n in missing])
        self.token = token or os.environ[c["webhook"]["token_env"]]
        self.wf, self.fake, self.callback_transport, self.workers = workflows, fake, callback_transport, workers
        self.runs = workflows.parent / c["runs_dir"]
        self.qdir = self.runs / "_queue"
        (self.qdir / "keys").mkdir(parents=True, exist_ok=True)
        # ponytail: jeden zámek na přijetí požadavku i validate v pracovních vláknech (validate trvá ms)
        self.lock = threading.Lock()
        self.q: queue.Queue = queue.Queue()
        with self.lock:
            for e in sorted(self.entries(), key=lambda e: e["queued_ns"]):  # obnova fronty po restartu
                self.q.put(e)

    def start(self):
        for i in range(self.workers):
            threading.Thread(target=self.work, name=f"agencast-worker-{i + 1}", daemon=True).start()

    def entries(self) -> list[dict]:
        out = []
        for f in self.qdir.glob("*.json"):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except FileNotFoundError:
                pass  # běh právě skončil
        return out

    def key_file(self, key: str) -> Path:
        return self.qdir / "keys" / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def authorized(self, auth: str | None) -> bool:
        return hmac.compare_digest((auth or "").encode(), f"Bearer {self.token}".encode())

    # --- POST /runs -----------------------------------------------------------------------
    def accept(self, auth: str | None, raw: bytes, gui: bool = False) -> tuple[int, dict]:
        """(status, tělo): 401/422 bez run_id a bez callbacku, 202 nový běh, 200 opakovaný request_key.
        `gui` = POST /projects/<p>/runs (api.md): callback_url volitelná, `dry_run: true` → jen plán (200)."""
        if not self.authorized(auth):
            return 401, UNAUTHORIZED
        try:
            body = json.loads(raw)
        except ValueError:
            return 422, {"error": "tělo není platný JSON", "details": []}
        if not isinstance(body, dict):
            return 422, {"error": "tělo musí být JSON objekt", "details": []}
        fields = FIELDS + ("dry_run",) if gui else FIELDS
        name, inputs, url, key = (body.get(f) for f in FIELDS)
        dry = body.get("dry_run", False)
        inputs = {} if inputs is None else inputs
        errs = [f"neznámé pole '{k}' (povolená: {', '.join(fields)})" for k in body if k not in fields]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9-]+", name):
            errs.append("scenario: chybí nebo to není jméno scénáře (malá písmena, číslice, pomlčka)")
        if not isinstance(inputs, dict):
            errs.append("inputs: má být objekt")
        if not (gui and url is None) and (not isinstance(url, str) or not url.startswith(CALLBACK_PREFIXES)):
            errs.append("callback_url: nezačíná https://" if gui else "callback_url: chybí nebo nezačíná https://")
        if key is not None and not (isinstance(key, str) and key):
            errs.append("request_key: má být neprázdný text")
        if not isinstance(dry, bool):
            errs.append("dry_run: má být true/false")
        elif dry and (url is not None or key is not None):
            errs.append("dry_run: s callback_url ani request_key nejde — dry-run nic nespouští")
        with self.lock:
            if isinstance(key, str) and key and (kf := self.key_file(key)).is_file():
                return 200, {"run_id": json.loads(kf.read_text(encoding="utf-8"))["run_id"], "queue_position": None}
            path = self.wf / "scenarios" / f"{name}.yaml"
            known = not any(e.startswith("scenario:") for e in errs) and path.is_file()
            if errs:  # BUGS 9: i chyby scénáře a vstupů, ať n8n opraví všechno v jednom kole
                more = self.check(path, inputs) if known and isinstance(inputs, dict) else []
                return 422, {"error": "neplatný požadavek", "details": errs + more}
            if not known:
                return 422, {"error": f"neznámý scénář '{name}'", "details": []}
            if errs := self.check(path, inputs):
                return 422, {"error": f"scénář '{name}' nebo jeho vstupy neprošly kontrolou", "details": errs}
            if not dry:
                return self.enqueue(name, inputs, url, key)
            p = api.load(path, fake=self.fake)
        # mimo zámek: dry-run spouští MCP servery kvůli seznamu nástrojů (sekundy)
        return 200, {"run_id": api.dry_run(p, inputs).dir.name, "dry_run": True}

    def enqueue(self, name: str, inputs: dict[str, Any], url: str | None, key: str | None) -> tuple[int, dict[str, Any]]:
        """Nový běh do fronty; volá se pod `self.lock` (request_key se ověřil ve stejném zámku)."""
        for _ in range(RUN_ID_TRIES):  # ISSUES 35: kolize run_id nesmí přepsat cizí požadavek
            run_id = new_run_id(name)
            if not (self.qdir / f"{run_id}.json").exists() and not (self.runs / run_id).exists():
                break
        else:
            raise AgencastError("internal", f"{RUN_ID_TRIES}× kolize run_id ve frontě {self.qdir}")
        entry = {"run_id": run_id, "scenario": name, "inputs": inputs, "callback_url": url, "request_key": key,
                 "queued_ns": time.time_ns()}
        if key:
            self.key_file(key).write_text(json.dumps({"run_id": run_id, "request_key": key}, ensure_ascii=False))
        tmp = self.qdir / f"{run_id}.tmp"
        tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.qdir / f"{run_id}.json")  # GET čte frontu bez zámku → nikdy půlka souboru
        position = len(self.entries())  # čekající + běžící (až `workers` najednou), včetně tohoto
        self.q.put(entry)
        return 202, {"run_id": run_id, "queue_position": position}

    def check(self, path: Path, inputs: dict) -> list[str]:
        try:
            resolve_inputs(api.load(path, fake=self.fake).scenario, inputs)
        except ConfigErrors as e:
            return e.errors
        return []

    # --- GET /runs/<run_id> ---------------------------------------------------------------
    def status(self, auth: str | None, run_id: str) -> tuple[int, dict]:
        if not self.authorized(auth):
            return 401, UNAUTHORIZED
        d = self.runs / run_id
        if not RUN_ID.fullmatch(run_id):
            return 404, {"error": f"běh {run_id} neexistuje"}
        if (d / "callback.json").is_file():
            body = json.loads((d / "callback.json").read_text(encoding="utf-8"))
            events = (d / "events.jsonl").read_text(encoding="utf-8")
            return 200, {**body, "callback_failed": '"type":"callback_failed"' in events}
        if d.is_dir():
            return 200, {"run_id": run_id, "status": "running"}
        mine = next((e for e in self.entries() if e["run_id"] == run_id), None)
        if mine:
            pos = sum(e["queued_ns"] <= mine["queued_ns"] for e in self.entries())
            return 200, {"run_id": run_id, "status": "queued", "queue_position": pos}
        return 404, {"error": f"běh {run_id} neexistuje"}

    # --- pracovní vlákno --------------------------------------------------------------------
    def work(self):
        while True:
            entry = self.q.get()
            try:
                self.execute(entry)
            except Exception:  # chyba mimo běh (např. zmizela proměnná prostředí): nahlas do logu, fronta jede dál
                print(f"běh {entry['run_id']} se nespustil:\n{traceback.format_exc()}", file=sys.stderr)
            finally:
                (self.qdir / f"{entry['run_id']}.json").unlink(missing_ok=True)

    def execute(self, entry: dict):
        """Jeden běh z fronty. Od přidělení run_id odejde callback vždy (webhook.md)."""
        path = self.wf / "scenarios" / f"{entry['scenario']}.yaml"
        kw = dict(fake=self.fake, callback_url=entry["callback_url"], request_key=entry["request_key"],
                  run_id=entry["run_id"], callback_transport=self.callback_transport)
        if (self.runs / entry["run_id"]).exists():
            # ponytail: přerušený běh se neopakuje (vedlejší účinky), jen se nahlásí; mohl i doběhnout bez callbacku
            return api.run(self.stub(path, entry), entry["inputs"], error=AgencastError(
                "internal", "běh přerušen — server skončil uprostřed běhu; co stihl, je v záznamu (ověř ručně)"), **kw)
        try:
            with self.lock:
                p = api.load(path, fake=self.fake)
            inputs = resolve_inputs(p.scenario, entry["inputs"])
        except ConfigErrors as e:
            return api.run(self.stub(path, entry), entry["inputs"], error=AgencastError(
                "config", "scénář neprošel kontrolou po vyzvednutí z fronty:\n" + "\n".join(e.errors)), **kw)
        return api.run(p, inputs, **kw)

    def stub(self, path: Path, entry: dict) -> Project:
        """Projekt pro běh, který nezačne: jméno scénáře a config ze startu serveru."""
        sc = {"version": None, "name": entry["scenario"], "description": "Běh nezačal — viz Chyba.", "steps": []}
        return Project(path, self.wf, sc, self.config, {}, {})


def structured(root: Path, errors: list[str]) -> list[dict[str, Any]]:
    """Hlášky validate jako objekty `{message, file?, step?, field?, line?}` (api.md, od 0.6.0)."""
    return [error_fields(e, root) for e in errors]


def with_structured(root: Path, body: dict[str, Any]) -> dict[str, Any]:
    """`errors` odpovědi a jejích scénářů, agentů a skillů jako objekty (`structured`)."""
    for x in [body, *(i for k in ("scenarios", "agents", "skills") for i in body.get(k) or [])]:
        if isinstance(x.get("errors"), list):
            x["errors"] = structured(root, x["errors"])
    return body


class Projects:
    """Rodina `/projects/...` (api.md). Jeden projekt = `hook` a jeho token; registr = `token` serveru,
    registr se čte při každém požadavku a Webhook projektu vznikne při startu nebo prvním POST."""

    def __init__(self, hook: Webhook | None = None, *, token: str | None = None, fake=None, workers: int = 1,
                 callback_transport=None):
        """`fake` = v režimu registru funkce, která vrátí nový Fake pro každý projekt."""
        self.hook, self.token, self.fake, self.workers = hook, token, fake, workers
        self.callback_transport = callback_transport
        self.hooks: dict[Path, Webhook] = {hook.wf.parent.resolve(): hook} if hook else {}
        self.lock = threading.Lock()

    def start(self):
        """Režim registru: Webhooky dostupných projektů hned (obnova fronty po restartu); chyba jen do logu."""
        for p in api.projects():
            if p["available"]:
                try:
                    self.webhook(Path(str(p["root"])))
                except ConfigErrors as e:
                    print(f"projekt {p['name']}: POST /projects/{p['name']}/runs zatím nepůjde:\n  "
                          + "\n  ".join(e.errors), file=sys.stderr)

    def webhook(self, root: Path) -> Webhook:
        with self.lock:
            if root not in self.hooks:
                h = Webhook(root / "workflows", fake=self.fake() if self.fake else None, workers=self.workers,
                            token=self.token, callback_transport=self.callback_transport)
                h.start()
                self.hooks[root] = h
            return self.hooks[root]

    def authorized(self, auth: str | None) -> bool:
        if self.hook:
            return self.hook.authorized(auth)
        return hmac.compare_digest((auth or "").encode(), f"Bearer {self.token}".encode())

    def listing(self) -> list[dict[str, str | bool]]:
        if not self.hook:
            return api.projects()
        root = self.hook.wf.parent.resolve()
        try:
            name = next((x["name"] for x in api.projects() if Path(str(x["root"])) == root), default_name(root))
        except ConfigErrors:  # rozbitý registr jeden projekt nezastaví
            name = default_name(root)
        return [{"name": name, "root": str(root), "available": True}]

    def project(self, name: str) -> tuple[Path | None, dict[str, Any]]:
        """(kořen, None) nebo (None, tělo 404)."""
        p = next((x for x in self.listing() if x["name"] == name), None)
        if p is None:
            return None, {"error": f"projekt '{name}' neexistuje (GET /projects)"}
        if not p["available"]:
            return None, {"error": f"projekt '{name}' je nedostupný — chybí {p['root']}/workflows/config.yaml"}
        return Path(str(p["root"])), {}

    def get(self, auth: str | None, path: str, query: str) -> tuple[int, dict[str, Any] | Path]:
        if not self.authorized(auth):
            return 401, UNAUTHORIZED
        parts = [unquote(x) for x in path.strip("/").split("/")][1:]
        if not parts:  # 0.7.0: last_run u dostupných projektů, cesta k registru
            return 200, {"projects": [x | {"last_run": api.last_run(Path(str(x["root"]))) if x["available"] else None}
                                      for x in self.listing()], "registry": str(registry_path())}
        root, err = self.project(parts[0])
        if root is None:
            return 404, err
        try:
            match parts[1:]:
                case []:
                    return 200, with_structured(root, {"name": parts[0], **api.describe_project(root)})
                case ["scenarios", s]:
                    body = api.describe_scenario(root, s)
                    return (200, with_structured(root, body)) if body else (
                        404, {"error": f"scénář '{s}' v projektu '{parts[0]}' neexistuje"})
                case ["runs"]:
                    q = parse_qs(query)
                    limit = q.get("limit", [None])[0]
                    if limit is not None and not re.fullmatch(r"[1-9]\d*", limit):
                        return 422, {"error": f"limit má být kladné celé číslo, je '{limit}'", "details": []}
                    return 200, {"runs": api.runs_list(root, q.get("scenario", [None])[0],
                                                       int(limit) if limit else None)}
                case ["runs", r]:
                    body = api.run_detail(root, r)
                    return (200, body) if body else (404, {"error": f"běh {r} neexistuje"})
                case ["runs", r, "steps", *rel] if rel:
                    body = api.step_detail(root, r, "/".join(rel))
                    return (200, body) if body else (404, {"error": f"krok {'/'.join(rel)} v běhu {r} není"})
                case ["runs", r, "files", *rel] if rel:
                    f = api.run_file(root, r, "/".join(rel))
                    return (200, f) if f else (404, {"error": "soubor ve složce běhu neexistuje"})
                case ["files", *rel] if rel:
                    return 200, with_structured(root, api.read_file(root, "/".join(rel)))
                case ["spend"]:
                    day = parse_qs(query).get("day", [f"{datetime.now(timezone.utc):%Y-%m-%d}"])[0]
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                        return 422, {"error": f"day má tvar RRRR-MM-DD, je '{day}'", "details": []}
                    return 200, api.spend(root, day)
        except ConfigErrors as e:
            return 422, {"error": f"projekt '{parts[0]}' neprošel kontrolou", "details": e.errors,
                         "errors": structured(root, e.errors)}
        except api.NotFound as e:
            return 404, {"error": str(e)}
        return 404, {"error": f"neznámá adresa {path} (api.md)"}

    def edit(self, method: str, auth: str | None, path: str, raw: bytes) -> tuple[int, dict[str, Any]]:
        """Editační operace (api.md „Editace“): tělo JSON s `etag`; 409 otisk nesedí, 422 kontrola neprošla."""
        if not self.authorized(auth):
            return 401, UNAUTHORIZED
        parts = [unquote(x) for x in path.strip("/").split("/")][1:]
        root, err = self.project(parts[0]) if parts else (None, {"error": "chybí projekt v adrese"})
        if root is None:
            return 404, err
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            return 422, {"error": "tělo není platný JSON", "errors": []}
        if not isinstance(body, dict):
            return 422, {"error": "tělo musí být JSON objekt", "errors": []}
        try:
            status, out = self.route(method, parts[1:], root, body) or (
                404, {"error": f"neznámá adresa {method} {path} (api.md)"})
        except api.Conflict as e:
            return 409, {"error": "soubor se mezitím změnil — načti ho znovu (etag = aktuální otisk)", "etag": e.etag}
        except api.NotFound as e:
            return 404, {"error": str(e)}
        except ConfigErrors as e:
            return 422, {"error": "změna neprošla kontrolou, nic se nezapsalo", "errors": structured(root, e.errors)}
        return status, with_structured(root, out) if status == 200 else out

    def route(self, method: str, parts: list[str], root: Path, body: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
        tag, g = body.get("etag"), body.get
        match method, parts:
            case "POST", ["validate"]:  # bez zápisu; bez path = projekt, jak je na disku
                return 200, {"errors": api.validate_text(root, g("path"), g("text"))}
            case "POST", [("scenarios" | "agents") as kind]:
                name = g("name")
                if not isinstance(name, str):
                    return 422, {"error": "name: chybí jméno", "errors": []}
                (api.new_scenario if kind == "scenarios" else api.new_agent)(root, name)
                rel = f"{kind}/{name}.{'yaml' if kind == 'scenarios' else 'md'}"
                return 200, {"name": name, "etag": api.read_file(root, rel)["etag"]}
            case "PUT", ["scenarios", s]:
                return 200, api.set_header(root, s, tag, g("fields"))
            case "DELETE", ["scenarios", s]:
                return 200, api.delete_scenario(root, s, tag)
            case "POST", ["scenarios", s, "steps"]:
                return 200, api.add_step(root, s, tag, g("after", ["steps"]), g("step"))
            case "POST", ["scenarios", s, "steps", *a, "move"] if a:
                return 200, api.move_step(root, s, tag, ["steps", *a], g("to"))
            case "PATCH", ["scenarios", s, "steps", *a] if a:
                return 200, api.update_step(root, s, tag, ["steps", *a], g("fields"))
            case "DELETE", ["scenarios", s, "steps", *a] if a:
                return 200, api.delete_step(root, s, tag, ["steps", *a])
            case "PUT", ["agents", a]:
                return 200, api.set_agent(root, a, tag, g("frontmatter"), g("body"))
            case "DELETE", ["agents", a]:
                return 200, api.delete_agent(root, a, tag)
            case "PUT", ["skills", n]:
                return 200, api.set_skill(root, n, tag, g("text"))
            case "DELETE", ["skills", n]:
                return 200, api.delete_skill(root, n, tag)
            case "PUT", ["config"]:
                return 200, api.set_config(root, tag, g("fields"))
            case "PUT", ["files", *rel] if rel:
                return 200, api.write_file(root, "/".join(rel), tag, g("text"))
        return None

    def post_run(self, auth: str | None, name: str, raw: bytes) -> tuple[int, dict[str, Any]]:
        if not self.authorized(auth):
            return 401, UNAUTHORIZED
        root, err = self.project(name)
        if root is None:
            return 404, err
        try:
            hook = self.webhook(root)
        except ConfigErrors as e:
            return 422, {"error": f"projekt '{name}' nejde spustit", "details": e.errors}
        return hook.accept(auth, raw, gui=True)


class Handler(BaseHTTPRequestHandler):
    server: "Server"

    def body(self) -> bytes | None:
        """Tělo požadavku; příliš velké → odpoví 422 a vrátí None."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if not 0 <= n <= MAX_BODY:
            self.reply(422, {"error": f"tělo má {n} B, nejvýš {MAX_BODY} B", "details": []})
            return None
        return self.rfile.read(n)

    def do_POST(self):
        path = urlsplit(self.path).path
        m = re.fullmatch(r"/projects/([^/]+)/runs", path)
        if path.startswith("/projects/") and not m:
            return self.do_edit()
        if path != "/runs" and not m:
            return self.reply(404, {"error": "neznámá adresa — běh se spouští přes POST /runs "
                                             "nebo POST /projects/<projekt>/runs"})
        hook = self.server.hook
        if not m and not hook:
            return self.reply(404, {"error": "server běží v režimu registru — běh se spouští přes "
                                             "POST /projects/<projekt>/runs"})
        if (raw := self.body()) is None:
            return
        auth = self.headers.get("Authorization")
        if m:
            return self.safe(self.server.projects.post_run, auth, unquote(m.group(1)), raw)
        assert hook
        self.safe(hook.accept, auth, raw)

    def do_edit(self):
        path = urlsplit(self.path).path
        if not path.startswith("/projects/"):
            return self.reply(404, {"error": f"neznámá adresa {self.command} {path} (api.md)"})
        if (raw := self.body()) is not None:
            self.safe(self.server.projects.edit, self.command, self.headers.get("Authorization"), path, raw)

    do_PUT = do_PATCH = do_DELETE = do_edit

    def do_GET(self):
        u = urlsplit(self.path)
        if u.path == "/projects" or u.path.startswith("/projects/"):
            return self.safe(self.server.projects.get, self.headers.get("Authorization"), u.path, u.query)
        if u.path != "/runs" and not u.path.startswith("/runs/"):
            return self.static(unquote(u.path))
        m = re.fullmatch(r"/runs/([^/?]+)", self.path)
        if not m or not self.server.hook:
            return self.reply(404, {"error": "neznámá adresa — stav běhu je na GET /runs/<run_id> "
                                             "nebo GET /projects/<projekt>/runs/<run_id>"})
        self.safe(self.server.hook.status, self.headers.get("Authorization"), m.group(1))

    def static(self, path: str):
        """GUI bez tokenu (token chrání jen /projects… a /runs…); cesta bez přípony → index.html (hash routing)."""
        if not (UI / "index.html").is_file():
            return self.reply(404, NO_UI)
        f = (UI / path.lstrip("/")).resolve()
        if f.is_relative_to(UI) and f.is_file():
            return self.reply(200, f)
        if "." in path.rsplit("/", 1)[-1]:
            return self.reply(404, {"error": f"soubor {path} v GUI není"})
        self.reply(200, UI / "index.html")

    def do_OPTIONS(self):
        """CORS preflight — jen s `serve --cors <origin>` (vývoj GUI z vite dev)."""
        if not self.server.cors:
            return self.reply(404, {"error": "CORS je vypnuté (agencast serve --cors <origin>)"})
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def end_headers(self):
        if self.server.cors:
            self.send_header("Access-Control-Allow-Origin", self.server.cors)
            self.send_header("Vary", "Origin")
        super().end_headers()

    def safe(self, fn, *args):
        try:
            status, body = fn(*args)
        except Exception as e:
            traceback.print_exc()
            status, body = 500, {"error": f"chyba serveru: {type(e).__name__}: {e}"}
        self.reply(status, body)

    def reply(self, status: int, body: dict[str, Any] | Path):
        if isinstance(body, Path):  # soubor ze složky běhu (api.run_file ho ověřil)
            data, ctype = body.read_bytes(), mimetypes.guess_type(body.name)[0] or "application/octet-stream"
            ctype += "; charset=utf-8" if ctype.startswith("text/") else ""
        else:
            data, ctype = json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, hook: Webhook | None, host: str, port: int, projects: Projects | None = None,
                 cors: str | None = None):
        """`hook` = jeden projekt (POST /runs, GET /runs/<id>); None = režim registru s `projects`.
        `cors` = origin, kterému prohlížeč smí číst odpovědi (vývoj GUI); None = žádné CORS hlavičky."""
        self.hook, self.cors = hook, cors
        self.projects = projects or Projects(hook)
        super().__init__((host, port), Handler)
