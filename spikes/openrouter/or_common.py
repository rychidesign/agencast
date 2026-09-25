"""Společné funkce spiku OpenRouter: holé HTTP přes urllib, klíč jen z prostředí."""
import json, os, statistics, sys, time
from urllib import request, error

BASE = "https://openrouter.ai/api/v1"
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
BUDGET_FILE = os.path.join(RESULTS, "_spend.json")
BUDGET_LIMIT = 0.50


def key():
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k:
        sys.exit("Chybí OPENROUTER_API_KEY v prostředí.")
    return k


def spent():
    try:
        return sum(json.load(open(BUDGET_FILE)).values())
    except FileNotFoundError:
        return 0.0


def add_spend(label, cost):
    d = {}
    if os.path.exists(BUDGET_FILE):
        d = json.load(open(BUDGET_FILE))
    d[label] = d.get(label, 0.0) + (cost or 0.0)
    json.dump(d, open(BUDGET_FILE, "w"), indent=1)


def post(path, payload, timeout=120, label="misc"):
    """Vrátí (status, tělo jako dict/text, latence s). Neskrývá chyby HTTP."""
    if spent() >= BUDGET_LIMIT:
        sys.exit(f"ROZPOČET PŘEKROČEN ({spent():.4f} USD) — zastaveno.")
    req = request.Request(BASE + path, data=json.dumps(payload).encode(),
                          headers={"Authorization": f"Bearer {key()}", "Content-Type": "application/json"})
    t = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read()
    except error.HTTPError as e:
        status, raw = e.code, e.read()
    except Exception as e:  # síť/timeout — ať to nezmizí potichu
        return None, {"transport_error": repr(e)}, time.perf_counter() - t
    lat = time.perf_counter() - t
    try:
        body = json.loads(raw)
    except ValueError:
        body = {"raw_text": raw.decode("utf-8", "replace")}
    if isinstance(body, dict) and isinstance(body.get("usage"), dict):
        add_spend(label, body["usage"].get("cost"))
    return status, body, lat


def median(xs):
    return round(statistics.median(xs), 3) if xs else None
