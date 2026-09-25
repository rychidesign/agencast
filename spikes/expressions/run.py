"""Celá matice kandidát × výraz: `uv run python run.py` → results/*.json + tabulka.

Každý výraz běží v samostatném procesu (timeout 10 s, limit paměti 1,5 GB),
aby DoS případy neshodily měření.
"""
import io, json, resource, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path

from adapters import CANDIDATES, CEL
from cases import CASES, CTX, V, E, H

TIMEOUT_S = 10
MEM_BYTES = 1536 * 2**20
BY_ID = {c["id"]: c for c in CASES}


def norm(v):
    if type(v).__name__ == "BoolType":  # celpy
        return bool(v)
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, int):
        return int(v)
    if isinstance(v, float):
        return float(v)
    if isinstance(v, str):
        return str(v)[:200]
    if isinstance(v, (list, tuple)):
        return [norm(x) for x in v][:20]
    if isinstance(v, dict):
        return {str(k): norm(x) for k, x in list(v.items())[:20]}
    return repr(v)[:200]


def worker(cand, case_id):
    resource.setrlimit(resource.RLIMIT_AS, (MEM_BYTES, MEM_BYTES))
    case = BY_ID[case_id]
    expr = case.get("cel") or case["expr"] if cand in CEL else case["expr"]
    out = {"cand": cand, "id": case_id, "expr": expr if len(expr) < 200 else expr[:60] + f"… ({len(expr)} znaků)"}
    fn = CANDIDATES[cand](CTX)
    buf = io.StringIO()
    t = time.perf_counter()
    try:
        with redirect_stdout(buf):
            r = fn(expr)
        out["result"] = norm(r)
        out["result_type"] = type(r).__name__
    except BaseException as e:  # i RecursionError/MemoryError — chceme vidět vše
        out["error_type"] = f"{type(e).__module__}.{type(e).__name__}"
        out["error"] = str(e)[:600]
    out["ms"] = round((time.perf_counter() - t) * 1000, 3)
    if buf.getvalue():
        out["stdout"] = buf.getvalue()[:200]
    if "result" in out and case["cat"] == V:
        # determinismus + orientační čas: opakuj, max ~0,3 s
        vals, times = set(), []
        while len(times) < 300 and sum(times) < 0.3:
            t = time.perf_counter()
            vals.add(json.dumps(norm(fn(expr)), sort_keys=True))
            times.append(time.perf_counter() - t)
        times.sort()
        out["us_median"] = round(times[len(times) // 2] * 1e6, 1)
        out["deterministic"] = len(vals) == 1
    print(json.dumps(out, ensure_ascii=False))


def run_one(cand, case_id):
    try:
        p = subprocess.run([sys.executable, __file__, "--worker", cand, case_id],
                           capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"cand": cand, "id": case_id, "outcome": "timeout"}
    if p.returncode != 0 or not p.stdout.strip():
        return {"cand": cand, "id": case_id, "outcome": "crash", "returncode": p.returncode,
                "stderr": p.stderr[-400:]}
    return json.loads(p.stdout.strip().splitlines()[-1])


def same(a, b):
    if isinstance(b, bool) or isinstance(a, bool):
        return a is b
    if isinstance(b, (int, float)) and isinstance(a, (int, float)):
        return abs(a - b) < 1e-9
    return a == b


def grade(r):
    case = BY_ID[r["id"]]
    if "outcome" in r:  # timeout / crash
        return "FAIL" if case["cat"] == H else r["outcome"]
    raised = "error" in r
    match case["cat"]:
        case "platné":
            if raised:
                return "error"
            return "ok" if same(r["result"], case["expect"]) else "wrong"
        case "chybové":
            if not raised:
                return "silent"
            return "ok" if any(m in r["error"] for m in case["mention"]) else "ok-vague"
        case "škodlivé":
            if raised:
                return "ok"
            harmless = case.get("dos") or (case.get("cel_harmless") and r["cand"] in CEL)
            return "ok-computed" if harmless else "FAIL"


def main():
    jobs = [(c, k["id"]) for c in CANDIDATES for k in CASES]
    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(lambda j: run_one(*j), jobs))
    res = Path("results")
    res.mkdir(exist_ok=True)
    summary = {}
    for cand in CANDIDATES:
        mine = [r | {"grade": grade(r)} for r in rows if r["cand"] == cand]
        (res / f"{cand}.json").write_text(json.dumps(mine, indent=1, ensure_ascii=False) + "\n")
        s = summary[cand] = {}
        for cat in (V, E, H):
            g = [r["grade"] for r in mine if BY_ID[r["id"]]["cat"] == cat]
            s[cat] = {"total": len(g), **{k: g.count(k) for k in sorted(set(g))}}
        us = [r["us_median"] for r in mine if "us_median" in r]
        s["us_median_valid"] = sorted(us)[len(us) // 2] if us else None
        s["deterministic"] = all(r.get("deterministic", True) for r in mine)
        s["failures"] = {r["id"]: r["grade"] for r in mine if r["grade"] not in ("ok", "ok-computed")}
    (res / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")

    print("| kandidát | platné ok | chybové ok (čitelné) / tiché | škodlivé odmítnuté / FAIL | medián µs |")
    print("|---|---|---|---|---|")
    for cand, s in summary.items():
        v, e, h = s[V], s[E], s[H]
        print(f"| {cand} | {v.get('ok', 0)}/{v['total']} | {e.get('ok', 0) + e.get('ok-vague', 0)}/{e['total']}"
              f" ({e.get('ok', 0)}) / {e.get('silent', 0)} | {h.get('ok', 0) + h.get('ok-computed', 0)}/{h['total']}"
              f" / {h.get('FAIL', 0)} | {s['us_median_valid']} |")
    for cand, s in summary.items():
        print(cand, s["failures"])


if __name__ == "__main__":
    if sys.argv[1:2] == ["--worker"]:
        worker(sys.argv[2], sys.argv[3])
    else:
        main()
