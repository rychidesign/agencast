"""Webhook server (webhook.md, D2): `POST /runs` hned odpoví 202 + run_id, výsledek
přijde později na `callback_url`. `GET /runs/<run_id>` vrací stav.

Stdlib `ThreadingHTTPServer`: požadavky obsluhují vlákna, běhy jedno pracovní
vlákno → jeden běh po druhém. Fronta a request_key jsou soubory, takže
přežijí restart serveru:

    <runs>/_queue/<run_id>.json        požadavek ve frontě (smaže se po callbacku)
    <runs>/_queue/keys/<sha256>.json   request_key → run_id (platí, dokud ho někdo nesmaže)
"""
import hashlib
import hmac
import json
import os
import queue
import re
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import ConfigErrors, MawError
from .engine import new_run_id, run_scenario
from .validate import Project, load_config, resolve_inputs, validate

FIELDS = ("scenario", "inputs", "callback_url", "request_key")
CALLBACK_PREFIXES = ("https://", "http://127.0.0.1:", "http://127.0.0.1/")  # 127.0.0.1 jen pro testy (ISSUES)
MAX_BODY = 1_000_000
RUN_ID = re.compile(r"\d{8}-\d{6}-[a-z0-9-]+-[0-9a-f]{4}")


class Webhook:
    """Přijetí požadavku, fronta a pracovní vlákno; HTTP je jen tenká vrstva `Handler`."""

    def __init__(self, workflows: Path, *, fake=None, callback_transport=None):
        errs = []
        self.config = c = load_config(workflows, errs)
        if errs:
            raise ConfigErrors(errs)
        need = [c["webhook"]["token_env"], c["callback"]["secret_env"]] + ([] if fake else [c["openrouter"]["api_key_env"]])
        if missing := [n for n in need if not os.environ.get(n)]:
            raise ConfigErrors([f"chybí proměnná prostředí {n} (.env nebo prostředí)" for n in missing])
        self.token = os.environ[c["webhook"]["token_env"]]
        self.wf, self.fake, self.callback_transport = workflows, fake, callback_transport
        self.runs = workflows.parent / c["runs_dir"]
        self.qdir = self.runs / "_queue"
        (self.qdir / "keys").mkdir(parents=True, exist_ok=True)
        # ponytail: jeden zámek na přijetí požadavku i validate v pracovním vlákně (validate trvá ms)
        self.lock = threading.Lock()
        self.q: queue.Queue = queue.Queue()
        for e in sorted(self.entries(), key=lambda e: e["queued_ns"]):  # obnova fronty po restartu
            self.q.put(e)

    def start(self):
        threading.Thread(target=self.work, name="maw-worker", daemon=True).start()

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

    def transport(self):
        return self.fake.transport() if self.fake else None

    def authorized(self, auth: str | None) -> bool:
        return hmac.compare_digest((auth or "").encode(), f"Bearer {self.token}".encode())

    # --- POST /runs -----------------------------------------------------------------------
    def accept(self, auth: str | None, raw: bytes) -> tuple[int, dict]:
        """(status, tělo): 401/422 bez run_id a bez callbacku, 202 nový běh, 200 opakovaný request_key."""
        if not self.authorized(auth):
            return 401, {"error": "chybí nebo nesedí token (hlavička Authorization: Bearer …)"}
        try:
            body = json.loads(raw)
        except ValueError:
            return 422, {"error": "tělo není platný JSON", "details": []}
        if not isinstance(body, dict):
            return 422, {"error": "tělo musí být JSON objekt", "details": []}
        name, inputs, url, key = (body.get(f) for f in FIELDS)
        inputs = {} if inputs is None else inputs
        errs = [f"neznámé pole '{k}' (povolená: {', '.join(FIELDS)})" for k in body if k not in FIELDS]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9-]+", name):
            errs.append("scenario: chybí nebo to není jméno scénáře (malá písmena, číslice, pomlčka)")
        if not isinstance(inputs, dict):
            errs.append("inputs: má být objekt")
        if not isinstance(url, str) or not url.startswith(CALLBACK_PREFIXES):
            errs.append("callback_url: chybí nebo nezačíná https://")
        if key is not None and not (isinstance(key, str) and key):
            errs.append("request_key: má být neprázdný text")
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
            run_id = new_run_id(name)
            entry = {"run_id": run_id, "scenario": name, "inputs": inputs, "callback_url": url, "request_key": key,
                     "queued_ns": time.time_ns()}
            if key:
                self.key_file(key).write_text(json.dumps({"run_id": run_id, "request_key": key}, ensure_ascii=False))
            tmp = self.qdir / f"{run_id}.tmp"
            tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.qdir / f"{run_id}.json")  # GET čte frontu bez zámku → nikdy půlka souboru
            position = len(self.entries())  # čekající + běžící, včetně tohoto
            self.q.put(entry)
        return 202, {"run_id": run_id, "queue_position": position}

    def check(self, path: Path, inputs: dict) -> list[str]:
        try:
            resolve_inputs(validate(path, transport=self.transport()).scenario, inputs)
        except ConfigErrors as e:
            return e.errors
        return []

    # --- GET /runs/<run_id> ---------------------------------------------------------------
    def status(self, auth: str | None, run_id: str) -> tuple[int, dict]:
        if not self.authorized(auth):
            return 401, {"error": "chybí nebo nesedí token (hlavička Authorization: Bearer …)"}
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
            return run_scenario(self.stub(path, entry), entry["inputs"], error=MawError(
                "internal", "běh přerušen — server skončil uprostřed běhu; co stihl, je v záznamu (ověř ručně)"), **kw)
        try:
            with self.lock:
                p = validate(path, transport=self.transport())
            inputs = resolve_inputs(p.scenario, entry["inputs"])
        except ConfigErrors as e:
            return run_scenario(self.stub(path, entry), entry["inputs"], error=MawError(
                "config", "scénář neprošel kontrolou po vyzvednutí z fronty:\n" + "\n".join(e.errors)), **kw)
        return run_scenario(p, inputs, **kw)

    def stub(self, path: Path, entry: dict) -> Project:
        """Projekt pro běh, který nezačne: jméno scénáře a config ze startu serveru."""
        sc = {"version": None, "name": entry["scenario"], "description": "Běh nezačal — viz Chyba.", "steps": []}
        return Project(path, self.wf, sc, self.config, {}, {})


class Handler(BaseHTTPRequestHandler):
    server: "Server"

    def do_POST(self):
        if self.path != "/runs":
            return self.reply(404, {"error": "neznámá adresa — běh se spouští přes POST /runs"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if not 0 <= n <= MAX_BODY:
            return self.reply(422, {"error": f"tělo má {n} B, nejvýš {MAX_BODY} B", "details": []})
        self.safe(self.server.hook.accept, self.headers.get("Authorization"), self.rfile.read(n))

    def do_GET(self):
        m = re.fullmatch(r"/runs/([^/?]+)", self.path)
        if not m:
            return self.reply(404, {"error": "neznámá adresa — stav běhu je na GET /runs/<run_id>"})
        self.safe(self.server.hook.status, self.headers.get("Authorization"), m.group(1))

    def safe(self, fn, *args):
        try:
            status, body = fn(*args)
        except Exception as e:
            traceback.print_exc()
            status, body = 500, {"error": f"chyba serveru: {type(e).__name__}: {e}"}
        self.reply(status, body)

    def reply(self, status: int, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, hook: Webhook, host: str, port: int):
        self.hook = hook
        super().__init__((host, port), Handler)
