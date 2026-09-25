"""Q2–Q4: webhook → spawn → fronta (max_containers=1) → callback; Volume; secrets."""
import json, os, struct, time, uuid, zlib
import modal
from fastapi import Header

app = modal.App("spike-flow")
image = modal.Image.debian_slim(python_version="3.12").pip_install("fastapi[standard]", "httpx")
vol = modal.Volume.from_name("flow-runs", create_if_missing=True)
cb_log = modal.Dict.from_name("spike-callbacks", create_if_missing=True)
# token endpointů ze secretu (modal secret create spike-token FLOW_TOKEN=...)
tok = modal.Secret.from_name("spike-token")
# Q4: OPENROUTER_API_KEY jednou přes from_name, jednou přes from_dict (hodnota z lokálního env při deployi)
or_named = modal.Secret.from_name("spike-openrouter")
or_dict = modal.Secret.from_dict({"OR_KEY_FROM_DICT": os.environ.get("OPENROUTER_API_KEY", "")})


def _png():
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    w = h = 16
    raw = b"".join(b"\x00" + bytes([200, 40, 40]) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _auth(x_token):
    from fastapi import HTTPException
    if x_token != os.environ["FLOW_TOKEN"]:
        raise HTTPException(401, "bad token")


@app.function(image=image, secrets=[tok, or_named, or_dict], volumes={"/runs": vol},
              max_containers=1, timeout=600)
def run_flow(run_id: str, payload: dict, callback_url: str):
    import httpx
    started = time.time()
    d = f"/runs/{run_id}"
    os.makedirs(d, exist_ok=True)
    sleep_s = payload.get("sleep", 60)
    events = [{"t": started, "ev": "start", "run_id": run_id}]
    time.sleep(sleep_s)
    events.append({"t": time.time(), "ev": "end"})
    with open(f"{d}/events.jsonl", "w") as f:
        f.write("".join(json.dumps(e) + "\n" for e in events))
    open(f"{d}/summary.md", "w").write(f"# Běh {run_id}\n\nSpánek {sleep_s} s, payload: {payload}\n")
    open(f"{d}/image.png", "wb").write(_png())
    vol.commit()
    ended = time.time()
    body = {"run_id": run_id, "status": "ok", "started": started, "ended": ended,
            "container_env": {  # jen přítomnost, nikdy hodnota
                "OPENROUTER_API_KEY_named": len(os.environ.get("OPENROUTER_API_KEY", "")) > 0,
                "OR_KEY_FROM_DICT": len(os.environ.get("OR_KEY_FROM_DICT", "")) > 0},
            "files": {"png": f"{os.environ.get('FILE_BASE','')}/{run_id}/image.png"}}
    r = httpx.post(callback_url, json=body, headers={"x-token": os.environ["FLOW_TOKEN"]}, timeout=30)
    return {"callback_status": r.status_code}


@app.function(image=image, secrets=[tok])
@modal.fastapi_endpoint(method="POST", label="spike-submit")
def submit(payload: dict, x_token: str = Header(None)):
    _auth(x_token)
    run_id = uuid.uuid4().hex[:8]
    cb = callback.get_web_url()
    call = run_flow.spawn(run_id, payload, cb)
    try:
        backlog = run_flow.get_current_stats().backlog
    except Exception as e:
        backlog = f"n/a: {e}"
    return {"run_id": run_id, "call_id": call.object_id, "backlog_at_submit": backlog, "t": time.time()}


@app.function(image=image, secrets=[tok])
@modal.fastapi_endpoint(method="POST", label="spike-callback")
def callback(body: dict, x_token: str = Header(None)):
    _auth(x_token)
    body["received"] = time.time()
    print("CALLBACK", json.dumps(body))
    cb_log[body["run_id"]] = body
    return {"ok": True}


@app.function(image=image, volumes={"/runs": vol})
@modal.fastapi_endpoint(method="GET", label="spike-file")
def file(run_id: str, name: str):
    """Veřejný GET (bez tokenu — jen pro test URL; run_id je náhodný)."""
    from fastapi import HTTPException
    from fastapi.responses import Response
    if not run_id.isalnum() or "/" in name or ".." in name:
        raise HTTPException(400, "bad path")
    vol.reload()
    p = f"/runs/{run_id}/{name}"
    if not os.path.isfile(p):
        raise HTTPException(404, "nenalezeno")
    ct = {"png": "image/png", "md": "text/markdown", "jsonl": "application/x-ndjson"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
    return Response(open(p, "rb").read(), media_type=ct)
