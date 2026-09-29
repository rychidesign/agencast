"""Webhook server (webhook.md, D2): `POST /runs` immediately returns 202 + run_id;
the result arrives later at `callback_url`. `GET /runs/<run_id>` returns the status.
The `/projects/...` endpoints (api.md, since 0.4.0) read projects for the GUI —
a single project, or a registry (projects.md) with the server token `AGENCAST_TOKEN`;
since 0.5.0 they also support editing (PUT/PATCH/DELETE, api.md “Editing”) via `api` → edit.py.

Stdlib `ThreadingHTTPServer`: threads handle requests; `workers` worker threads
process runs from a single queue (default 1 → sequential runs; more → completion
order is not guaranteed). The queue and request_key are stored in files, so
they survive server restarts:

    <runs>/_queue/<run_id>.json        queued request (deleted after the callback)
    <runs>/_queue/keys/<sha256>.json   request_key → run_id (valid until deleted)
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
from .projects import NAME, default_name, error_fields, registry_path
from .record import INTERRUPTED_BY_RESTART, _events
from .validate import Project, require_config, resolve_inputs

FIELDS = ("scenario", "inputs", "callback_url", "request_key")
CALLBACK_PREFIXES = ("https://", "http://127.0.0.1:", "http://127.0.0.1/")  # 127.0.0.1 for tests only (ISSUES)
MAX_BODY = 1_000_000
UNAUTHORIZED = {"error": "missing or invalid token (Authorization: Bearer … header)"}
UI = Path(__file__).resolve().parent / "ui"  # built GUI (ui/ → npm run build); not tracked in git
NO_UI = {"error": "GUI is not built — run npm install and npm run build in the repository's ui/ directory "
                  f"(output belongs in {UI})"}


class Webhook:
    """Request acceptance, queue and worker thread; HTTP is a thin `Handler` layer."""

    def __init__(self, workflows: Path, *, fake=None, callback_transport=None, workers: int = 1,
                 token: str | None = None):
        """`token` = server token in registry mode; otherwise read from the project's `webhook.token_env`."""
        self.config = c = require_config(workflows)
        need = ([] if token else [c["webhook"]["token_env"]]) + (
            [] if fake else [c["openrouter"]["api_key_env"]])
        if missing := [n for n in need if not os.environ.get(n)]:
            raise ConfigErrors([f"missing environment variable {n} (.env or environment)" for n in missing])
        self.token = token or os.environ[c["webhook"]["token_env"]]
        self.wf, self.fake, self.callback_transport, self.workers = workflows, fake, callback_transport, workers
        self.runs = workflows.parent / c["runs_dir"]
        self.qdir = self.runs / "_queue"
        (self.qdir / "keys").mkdir(parents=True, exist_ok=True)
        # ponytail: one lock for request acceptance and validation in worker threads (validation takes ms)
        self.lock = threading.Lock()
        self.q: queue.Queue = queue.Queue()
        with self.lock:
            for e in sorted(self.entries(), key=lambda e: e["queued_ns"]):  # restore the queue after a restart
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
                pass  # the run just finished
        return out

    def key_file(self, key: str) -> Path:
        return self.qdir / "keys" / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def authorized(self, auth: str | None) -> bool:
        return hmac.compare_digest((auth or "").encode(), f"Bearer {self.token}".encode())

    # --- POST /runs -----------------------------------------------------------------------
    def accept(self, auth: str | None, raw: bytes, gui: bool = False) -> tuple[int, dict]:
        """(status, body): 401/422 without run_id or callback, 202 new run, 200 repeated request_key.
        `gui` = POST /projects/<p>/runs (api.md): optional callback_url, `dry_run: true` → plan only (200)."""
        if not self.authorized(auth):
            return 401, UNAUTHORIZED
        try:
            body = json.loads(raw)
        except ValueError:
            return 422, {"error": "body is not valid JSON", "details": []}
        if not isinstance(body, dict):
            return 422, {"error": "body must be a JSON object", "details": []}
        fields = FIELDS + ("dry_run",) if gui else FIELDS
        name, inputs, url, key = (body.get(f) for f in FIELDS)
        dry = body.get("dry_run", False)
        inputs = {} if inputs is None else inputs
        errs = [f"unknown field '{k}' (allowed: {', '.join(fields)})" for k in body if k not in fields]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9-]+", name):
            errs.append("scenario: missing or invalid scenario name (lowercase letters, digits, hyphens)")
        if not isinstance(inputs, dict):
            errs.append("inputs: must be an object")
        if not (gui and url is None) and (not isinstance(url, str) or not url.startswith(CALLBACK_PREFIXES)):
            errs.append("callback_url: does not start with https://" if gui else "callback_url: missing or does not start with https://")
        if not dry and isinstance(url, str) and url.startswith(CALLBACK_PREFIXES):
            secret = self.config["callback"]["secret_env"]
            if not os.environ.get(secret):
                errs.append(f"missing environment variable {secret} (callback signature)")
        if key is not None and not (isinstance(key, str) and key):
            errs.append("request_key: must be a non-empty string")
        if not isinstance(dry, bool):
            errs.append("dry_run: must be true/false")
        elif dry and (url is not None or key is not None):
            errs.append("dry_run: cannot be combined with callback_url or request_key — a dry run does not execute anything")
        with self.lock:
            if isinstance(key, str) and key and (kf := self.key_file(key)).is_file():
                return 200, {"run_id": json.loads(kf.read_text(encoding="utf-8"))["run_id"], "queue_position": None}
            path = self.wf / "scenarios" / f"{name}.yaml"
            known = not any(e.startswith("scenario:") for e in errs) and path.is_file()
            if errs:  # BUGS 9: include scenario and input errors so n8n can fix everything in one pass
                more = self.check(path, inputs) if known and isinstance(inputs, dict) else []
                return 422, {"error": "invalid request", "details": errs + more}
            if not known:
                return 422, {"error": f"unknown scenario '{name}'", "details": []}
            if errs := self.check(path, inputs):
                return 422, {"error": f"scenario '{name}' or its inputs failed validation", "details": errs}
            if not dry:
                return self.enqueue(name, inputs, url, key)
            p = api.load(path, fake=self.fake)
        # outside the lock: a dry run starts MCP servers to list tools (takes seconds)
        return 200, {"run_id": api.dry_run(p, inputs).dir.name, "dry_run": True}

    def enqueue(self, name: str, inputs: dict[str, Any], url: str | None, key: str | None) -> tuple[int, dict[str, Any]]:
        """Enqueue a new run; called under `self.lock` (request_key was checked under the same lock)."""
        for _ in range(RUN_ID_TRIES):  # ISSUES 35: run_id collisions must not overwrite another request
            run_id = new_run_id(name)
            if not (self.qdir / f"{run_id}.json").exists() and not (self.runs / run_id).exists():
                break
        else:
            raise AgencastError("internal", f"{RUN_ID_TRIES} run_id collisions in queue {self.qdir}")
        entry = {"run_id": run_id, "scenario": name, "inputs": inputs, "callback_url": url, "request_key": key,
                 "queued_ns": time.time_ns()}
        if key:
            self.key_file(key).write_text(json.dumps({"run_id": run_id, "request_key": key}, ensure_ascii=False))
        tmp = self.qdir / f"{run_id}.tmp"
        tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.qdir / f"{run_id}.json")  # GET reads the queue without a lock → never a partial file
        position = len(self.entries())  # queued + running (up to `workers` at once), including this run
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
            return 404, {"error": f"run {run_id} does not exist"}
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
        return 404, {"error": f"run {run_id} does not exist"}

    # --- worker thread --------------------------------------------------------------------
    def work(self):
        while True:
            entry = self.q.get()
            try:
                self.execute(entry)
            except Exception:  # error outside a run (e.g. an environment variable disappeared): log it and keep processing the queue
                print(f"run {entry['run_id']} did not start:\n{traceback.format_exc()}", file=sys.stderr)
            finally:
                (self.qdir / f"{entry['run_id']}.json").unlink(missing_ok=True)

    def execute(self, entry: dict):
        """One queued run. A callback is always sent once run_id is assigned (webhook.md)."""
        path = self.wf / "scenarios" / f"{entry['scenario']}.yaml"
        kw = dict(fake=self.fake, callback_url=entry["callback_url"], request_key=entry["request_key"],
                  run_id=entry["run_id"], callback_transport=self.callback_transport)
        run_dir = self.runs / entry["run_id"]
        if run_dir.exists():
            try:
                events = list(_events(run_dir))
            except OSError:
                events = []
            if any(e.get("type") == "run_started" for e in events) and not any(
                    e.get("type") == "run_finished" for e in events):
                step = next((e.get("step") for e in reversed(events) if e.get("type") == "step_started"), None)
                return api.run(self.stub(path, entry), entry["inputs"], error=AgencastError(
                    "internal", INTERRUPTED_BY_RESTART, step=step), resume=True, **kw)
            # ponytail: report interrupted runs without retrying (side effects); a run may have finished without a callback
            return api.run(self.stub(path, entry), entry["inputs"], error=AgencastError(
                "internal", "run interrupted — server stopped during the run; completed work is in the run record (check manually)"), **kw)
        try:
            with self.lock:
                p = api.load(path, fake=self.fake)
            inputs = resolve_inputs(p.scenario, entry["inputs"])
        except ConfigErrors as e:
            return api.run(self.stub(path, entry), entry["inputs"], error=AgencastError(
                "config", "scenario failed validation after being dequeued:\n" + "\n".join(e.errors)), **kw)
        return api.run(p, inputs, **kw)

    def stub(self, path: Path, entry: dict) -> Project:
        """Project for a run that cannot start: scenario name and config from server startup."""
        sc = {"version": None, "name": entry["scenario"], "description": "Run did not start — see Error.", "steps": []}
        return Project(path, self.wf, sc, self.config, {}, {})


def structured(root: Path, errors: list[str]) -> list[dict[str, Any]]:
    """Validation messages as `{message, file?, step?, field?, line?}` objects (api.md, since 0.6.0)."""
    return [error_fields(e, root) for e in errors]


def with_structured(root: Path, body: dict[str, Any]) -> dict[str, Any]:
    """`errors` in the response and its scenarios, agents and skills as objects (`structured`)."""
    for x in [body, *(i for k in ("scenarios", "agents", "skills") for i in body.get(k) or [])]:
        if isinstance(x.get("errors"), list):
            x["errors"] = structured(root, x["errors"])
    return body


class Projects:
    """The `/projects/...` endpoints (api.md). Single project = `hook` and its token; registry = server `token`.
    Read the registry on each request; create the project Webhook at startup or on the first POST."""

    def __init__(self, hook: Webhook | None = None, *, token: str | None = None, fake=None, workers: int = 1,
                 callback_transport=None):
        """`fake` = function returning a new Fake for each project in registry mode."""
        self.hook, self.token, self.fake, self.workers = hook, token, fake, workers
        self.callback_transport = callback_transport
        self.hooks: dict[Path, Webhook] = {hook.wf.parent.resolve(): hook} if hook else {}
        self.lock = threading.Lock()

    def start(self):
        """Registry mode: start Webhooks for available projects immediately (restore the queue after a restart); log errors only."""
        for p in api.projects():
            if p["available"]:
                try:
                    self.webhook(Path(str(p["root"])))
                except ConfigErrors as e:
                    print(f"project {p['name']}: POST /projects/{p['name']}/runs is not available yet:\n  "
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

    def _registry_write(self, auth: str | None) -> tuple[int, dict[str, Any]] | None:
        if not self.authorized(auth):
            return 401, UNAUTHORIZED
        if self.hook:
            return 405, {"error": "project writes are only available in registry mode (serve started outside a project)"}
        return None

    def create_project(self, auth: str | None, raw: bytes) -> tuple[int, dict[str, Any]]:
        if result := self._registry_write(auth):
            return result
        try:
            body = json.loads(raw)
        except ValueError:
            return 422, {"error": "body is not valid JSON"}
        if not isinstance(body, dict):
            return 422, {"error": "body must be a JSON object"}
        if unknown := set(body) - {"name", "root"}:
            return 422, {"error": f"unknown field: {', '.join(sorted(unknown))}"}
        name = body.get("name")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            return 422, {"error": "name: must contain lowercase letters, digits and hyphens, starting with a letter"}
        if "root" in body and (not isinstance(body["root"], str) or not body["root"]):
            return 422, {"error": "root: must be a non-empty path"}
        try:
            base = api.projects_root()
            root = api.normalize_project_root(body.get("root", name), base)
            registered = api.projects()
        except ConfigErrors as e:
            return 422, {"error": "cannot read the project registry", "details": e.errors}
        if (root / "workflows").exists():
            return 409, {"error": f"{root}/workflows already exists — add the existing project via POST /projects"}
        if any(p["name"] == name for p in registered):
            return 409, {"error": f"project '{name}' is already in the registry"}
        if any(Path(str(p["root"])).resolve() == root for p in registered):
            return 409, {"error": f"{root}: already in the registry — add the existing project via POST /projects"}
        try:
            created = api.new_project(root, name)
        except api.ProjectConflict as e:
            return 409, {"error": str(e), "hint": "add the existing project via POST /projects"}
        except ConfigErrors as e:
            return 422, {"error": "cannot create the project", "details": e.errors}
        return 201, {"name": name, "root": str(root), "created": [str(p) for p in created]}

    def add_project(self, auth: str | None, raw: bytes) -> tuple[int, dict[str, Any]]:
        if result := self._registry_write(auth):
            return result
        try:
            body = json.loads(raw)
        except ValueError:
            return 422, {"error": "body is not valid JSON"}
        if not isinstance(body, dict):
            return 422, {"error": "body must be a JSON object"}
        if unknown := set(body) - {"root", "name"}:
            return 422, {"error": f"unknown field: {', '.join(sorted(unknown))}"}
        value, name = body.get("root"), body.get("name")
        if not isinstance(value, str) or not value:
            return 422, {"error": "root: a non-empty path is required"}
        if name is not None and (not isinstance(name, str) or not NAME.fullmatch(name)):
            return 422, {"error": "name: must start with a lowercase letter followed by lowercase letters, digits or hyphens"}
        try:
            root = api.normalize_project_root(value, api.projects_root())
            registered = api.projects()
        except ConfigErrors as e:
            return 422, {"error": "invalid registry or project path", "details": e.errors}
        if not (root / "workflows" / "config.yaml").is_file():
            return 422, {"error": f"{root}: missing workflows/config.yaml"}
        if any(Path(str(p["root"])).resolve() == root for p in registered):
            return 409, {"error": f"{root}: already in the registry"}
        candidate_name = name or default_name(root)
        if any(p["name"] == candidate_name for p in registered):
            return 409, {"error": f"project '{candidate_name}' is already in the registry"}
        try:
            saved_name = api.add_project(root / "workflows", name)
        except api.ProjectConflict as e:
            return 409, {"error": str(e)}
        except ConfigErrors as e:
            return 422, {"error": "cannot register the project", "details": e.errors}
        return 201, {"name": saved_name, "root": str(root)}

    def remove_project(self, auth: str | None, name: str) -> tuple[int, dict[str, Any]]:
        if result := self._registry_write(auth):
            return result
        try:
            if not any(p["name"] == name for p in api.projects()):
                return 404, {"error": f"project '{name}' is not in the registry"}
            api.remove_project(name)
        except ConfigErrors as e:
            return 404, {"error": str(e)}
        return 200, {"name": name, "removed": True, "files_deleted": False,
                     "message": "project removed from the registry; files are kept"}

    def listing(self) -> list[dict[str, str | bool]]:
        if not self.hook:
            return api.projects()
        root = self.hook.wf.parent.resolve()
        try:
            name = next((x["name"] for x in api.projects() if Path(str(x["root"])) == root), default_name(root))
        except ConfigErrors:  # a broken registry does not prevent single-project mode
            name = default_name(root)
        return [{"name": name, "root": str(root), "available": True}]

    def project(self, name: str) -> tuple[Path | None, dict[str, Any]]:
        """(root, None) or (None, 404 body)."""
        p = next((x for x in self.listing() if x["name"] == name), None)
        if p is None:
            return None, {"error": f"project '{name}' does not exist (GET /projects)"}
        if not p["available"]:
            return None, {"error": f"project '{name}' is unavailable — missing {p['root']}/workflows/config.yaml"}
        return Path(str(p["root"])), {}

    def get(self, auth: str | None, path: str, query: str) -> tuple[int, dict[str, Any] | Path]:
        if not self.authorized(auth):
            return 401, UNAUTHORIZED
        parts = [unquote(x) for x in path.strip("/").split("/")][1:]
        if not parts:  # 0.7.0: last_run for available projects, registry path
            try:
                projects_root = api.projects_root()
            except ConfigErrors:
                if not self.hook:
                    raise
                projects_root = (Path.home() / "workspace").resolve()
            today = f"{datetime.now(timezone.utc):%Y-%m-%d}"
            projects = []
            for x in self.listing():
                root = Path(str(x["root"]))
                wf = root / "workflows"
                counts = {"scenarios": sum(1 for _ in (wf / "scenarios").glob("*.yaml")),
                          "agents": sum(1 for _ in (wf / "agents").glob("*.md"))}
                available = bool(x["available"])  # without workflows/, spend/last_run would raise ConfigErrors → 500 (0.15.1)
                projects.append(x | {"last_run": api.last_run(root) if available else None, "counts": counts,
                                     "spend_today_usd": api.spend(root, today)["total_usd"] if available else 0})
            return 200, {"projects": projects, "registry": str(registry_path()),
                    "projects_root": str(projects_root),
                    "writable": self.hook is None and api.registry_writable()}
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
                        404, {"error": f"scenario '{s}' does not exist in project '{parts[0]}'"})
                case ["runs"]:
                    q = parse_qs(query)
                    limit = q.get("limit", [None])[0]
                    if limit is not None and not re.fullmatch(r"[1-9]\d*", limit):
                        return 422, {"error": f"limit must be a positive integer, got '{limit}'", "details": []}
                    before = q.get("before", [None])[0]
                    if before is not None and not RUN_ID.fullmatch(before):
                        return 422, {"error": "before must be a run_id", "details": []}
                    page_size = int(limit) if limit else None
                    runs = api.runs_list(root, q.get("scenario", [None])[0],
                                         page_size + 1 if page_size is not None else None, before)
                    body = {"runs": runs[:page_size] if page_size is not None else runs}
                    if page_size is not None and len(runs) > page_size:
                        body["next_before"] = body["runs"][-1]["run_id"]
                    return 200, body
                case ["runs", r]:
                    body = api.run_detail(root, r)
                    return (200, body) if body else (404, {"error": f"run {r} does not exist"})
                case ["runs", r, "steps", *rel] if rel:
                    body = api.step_detail(root, r, "/".join(rel))
                    return (200, body) if body else (404, {"error": f"step {'/'.join(rel)} does not exist in run {r}"})
                case ["runs", r, "files", *rel] if rel:
                    f = api.run_file(root, r, "/".join(rel))
                    return (200, f) if f else (404, {"error": "file does not exist in the run directory"})
                case ["files", *rel] if rel and parse_qs(query).get("etag_only") == ["1"]:
                    return 200, {"etag": api.file_etag(root, "/".join(rel))}
                case ["files", *rel] if rel:
                    return 200, with_structured(root, api.read_file(root, "/".join(rel)))
                case ["spend"]:
                    day = parse_qs(query).get("day", [f"{datetime.now(timezone.utc):%Y-%m-%d}"])[0]
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                        return 422, {"error": f"day must use YYYY-MM-DD format, got '{day}'", "details": []}
                    return 200, api.spend(root, day)
        except ConfigErrors as e:
            return 422, {"error": f"project '{parts[0]}' failed validation", "details": e.errors,
                         "errors": structured(root, e.errors)}
        except api.NotFound as e:
            return 404, {"error": str(e)}
        return 404, {"error": f"unknown URL {path} (api.md)"}

    def edit(self, method: str, auth: str | None, path: str, raw: bytes) -> tuple[int, dict[str, Any]]:
        """Editing operations (api.md “Editing”): JSON body with `etag`; 409 fingerprint mismatch, 422 validation failed."""
        if not self.authorized(auth):
            return 401, UNAUTHORIZED
        parts = [unquote(x) for x in path.strip("/").split("/")][1:]
        root, err = self.project(parts[0]) if parts else (None, {"error": "missing project in URL"})
        if root is None:
            return 404, err
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            return 422, {"error": "body is not valid JSON", "errors": []}
        if not isinstance(body, dict):
            return 422, {"error": "body must be a JSON object", "errors": []}
        try:
            status, out = self.route(method, parts[1:], root, body) or (
                404, {"error": f"unknown URL {method} {path} (api.md)"})
        except api.Conflict as e:
            return 409, {"error": "file has changed — reload it (etag = current fingerprint)", "etag": e.etag}
        except api.NotFound as e:
            return 404, {"error": str(e)}
        except api.OpError as e:  # 0.8.0: batch — index of the operation that could not be performed
            errors = structured(root, e.errors)
            for item in errors:
                if e.step:
                    item["step"] = e.step
                if e.field:
                    item["field"] = e.field
            return 422, {"error": f"batch operation {e.op} cannot be performed; nothing was written", "op": e.op,
                         "errors": errors}
        except ConfigErrors as e:
            return 422, {"error": "change failed validation; nothing was written", "errors": structured(root, e.errors)}
        return status, with_structured(root, out) if status == 200 else out

    def route(self, method: str, parts: list[str], root: Path, body: dict[str, Any]) -> tuple[int, dict[str, Any]] | None:
        tag, g = body.get("etag"), body.get
        match method, parts:
            case "POST", ["validate"]:  # no writes; scenario text also returns a tree
                rel, text = g("path"), g("text")
                m = re.fullmatch(r"scenarios/([a-z][a-z0-9-]*)\.yaml", rel) if isinstance(rel, str) else None
                if m and text is not None:
                    return 200, api.render_text(root, m[1], text)
                return 200, {"errors": api.validate_text(root, rel, text)}
            case "POST", [("scenarios" | "agents") as kind]:
                name = g("name")
                if not isinstance(name, str):
                    return 422, {"error": "name: missing name", "errors": []}
                if kind == "scenarios":
                    api.new_scenario(root, name, g("description"))
                else:
                    api.new_agent(root, name, g("description"), g("model"))
                rel = f"{kind}/{name}.{'yaml' if kind == 'scenarios' else 'md'}"
                return 200, {"name": name, "etag": api.read_file(root, rel)["etag"]}
            case "POST", ["scenarios", s, "rename"]:
                return 200, api.rename_scenario(root, s, tag, g("name"))
            case "POST", ["agents", a, "rename"]:
                return 200, api.rename_agent(root, a, tag, g("name"))
            case "PUT", ["scenarios", s]:
                return 200, api.set_header(root, s, tag, g("fields"))
            case "DELETE", ["scenarios", s]:
                return 200, api.delete_scenario(root, s, tag)
            case "POST", ["scenarios", s, "steps"]:
                return 200, api.add_step(root, s, tag, g("after", ["steps"]), g("step"))
            case "POST", ["scenarios", s, "batch"]:
                return 200, api.batch(root, s, tag, g("ops"))
            case "POST", ["scenarios", s, "render"]:  # no writes; etag is optional
                if "text" in body:
                    if "ops" in body:
                        raise ConfigErrors(["text and ops cannot be combined"])
                    if not (root / "workflows" / "scenarios" / f"{s}.yaml").is_file():
                        return 404, {"error": f"scenario '{s}' does not exist in the project"}
                    return 200, api.render_text(root, s, g("text"))
                return 200, api.render(root, s, tag, g("ops", []))
            case "PUT", ["scenarios", s, "steps", *a] if a:
                return 200, api.replace_step(root, s, tag, ["steps", *a], g("step"))
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
            return 422, {"error": f"project '{name}' cannot be run", "details": e.errors}
        return hook.accept(auth, raw, gui=True)


class Handler(BaseHTTPRequestHandler):
    server: "Server"

    def body(self) -> bytes | None:
        """Request body; if too large, respond with 422 and return None."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if not 0 <= n <= MAX_BODY:
            self.reply(422, {"error": f"body is {n} B, maximum {MAX_BODY} B", "details": []})
            return None
        return self.rfile.read(n)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path in ("/projects", "/projects/new"):
            if (raw := self.body()) is None:
                return
            auth = self.headers.get("Authorization")
            method = self.server.projects.add_project if path == "/projects" else self.server.projects.create_project
            return self.safe(method, auth, raw)
        m = re.fullmatch(r"/projects/([^/]+)/runs", path)
        if path.startswith("/projects/") and not m:
            return self.do_edit()
        if path != "/runs" and not m:
            return self.reply(404, {"error": "unknown URL — start a run via POST /runs "
                                             "or POST /projects/<project>/runs"})
        hook = self.server.hook
        if not m and not hook:
            return self.reply(404, {"error": "server is in registry mode — start a run via "
                                             "POST /projects/<project>/runs"})
        if (raw := self.body()) is None:
            return
        auth = self.headers.get("Authorization")
        if m:
            return self.safe(self.server.projects.post_run, auth, unquote(m.group(1)), raw)
        assert hook
        self.safe(hook.accept, auth, raw)

    def do_DELETE(self):
        path = urlsplit(self.path).path
        if m := re.fullmatch(r"/projects/([^/]+)", path):
            return self.safe(self.server.projects.remove_project, self.headers.get("Authorization"),
                             unquote(m.group(1)))
        return self.do_edit()

    def do_edit(self):
        path = urlsplit(self.path).path
        if not path.startswith("/projects/"):
            return self.reply(404, {"error": f"unknown URL {self.command} {path} (api.md)"})
        if (raw := self.body()) is not None:
            self.safe(self.server.projects.edit, self.command, self.headers.get("Authorization"), path, raw)

    do_PUT = do_PATCH = do_edit

    def do_HEAD(self):
        """Only the workflows/ file fingerprint in the `ETag` header (0.8.0, `HEAD /projects/<p>/files/<path>`)."""
        path = urlsplit(self.path).path
        status, body = 404, {}
        if re.fullmatch(r"/projects/[^/]+/files/.+", path):
            try:
                status, body = self.server.projects.get(self.headers.get("Authorization"), path, "etag_only=1")
            except Exception:
                traceback.print_exc()
                status = 500
        self.send_response(status)
        if status == 200 and isinstance(body, dict):
            self.send_header("ETag", f'"{body["etag"]}"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        u = urlsplit(self.path)
        if u.path == "/projects" or u.path.startswith("/projects/"):
            return self.safe(self.server.projects.get, self.headers.get("Authorization"), u.path, u.query)
        if u.path != "/runs" and not u.path.startswith("/runs/"):
            return self.static(unquote(u.path))
        m = re.fullmatch(r"/runs/([^/?]+)", self.path)
        if not m or not self.server.hook:
            return self.reply(404, {"error": "unknown URL — run status is at GET /runs/<run_id> "
                                             "or GET /projects/<project>/runs/<run_id>"})
        self.safe(self.server.hook.status, self.headers.get("Authorization"), m.group(1))

    def static(self, path: str):
        """GUI without a token (only /projects… and /runs… require it); path without extension → index.html (hash routing)."""
        if not (UI / "index.html").is_file():
            return self.reply(404, NO_UI)
        f = (UI / path.lstrip("/")).resolve()
        if f.is_relative_to(UI) and f.is_file():
            return self.reply(200, f)
        if "." in path.rsplit("/", 1)[-1]:
            return self.reply(404, {"error": f"file {path} does not exist in the GUI"})
        self.reply(200, UI / "index.html")

    def do_OPTIONS(self):
        """CORS preflight — only with `serve --cors <origin>` (GUI development with vite dev)."""
        if not self.server.cors:
            return self.reply(404, {"error": "CORS is disabled (agencast serve --cors <origin>)"})
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def end_headers(self):
        if self.server.cors:
            self.send_header("Access-Control-Allow-Origin", self.server.cors)
            self.send_header("Access-Control-Expose-Headers", "ETag")
            self.send_header("Vary", "Origin")
        super().end_headers()

    def safe(self, fn, *args):
        try:
            status, body = fn(*args)
        except Exception as e:
            traceback.print_exc()
            status, body = 500, {"error": f"server error: {type(e).__name__}: {e}"}
        self.reply(status, body)

    def reply(self, status: int, body: dict[str, Any] | Path):
        if isinstance(body, Path):  # file from the run directory (checked by api.run_file)
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
        """`hook` = single project (POST /runs, GET /runs/<id>); None = registry mode with `projects`.
        `cors` = origin allowed to read responses in the browser (GUI development); None = no CORS headers."""
        self.hook, self.cors = hook, cors
        self.projects = projects or Projects(hook)
        super().__init__((host, port), Handler)
