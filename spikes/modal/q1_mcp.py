"""Q1: stdio MCP server (server-filesystem) v Modal kontejneru; initialize + tools/list přes JSON-RPC."""
import time
import modal

app = modal.App("spike-mcp")

base = modal.Image.debian_slim(python_version="3.12").apt_install("nodejs", "npm")
img_pre = base.run_commands("npm install -g @modelcontextprotocol/server-filesystem")
img_npx = base  # balíček se stahuje za běhu přes npx -y

RPC = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "spike", "version": "0"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
]


def _run(cmd):
    import json, subprocess
    t0 = time.time()
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    marks = {}
    for m in RPC:
        p.stdin.write(json.dumps(m) + "\n"); p.stdin.flush()
        if "id" in m:
            while True:
                line = p.stdout.readline()
                if not line:
                    raise RuntimeError("EOF: " + p.stderr.read()[:500])
                r = json.loads(line)
                if r.get("id") == m["id"]:
                    marks[m["method"]] = round(time.time() - t0, 2)
                    if m["method"] == "tools/list":
                        marks["tools"] = [t["name"] for t in r["result"]["tools"]]
                    break
    p.terminate()
    return marks


@app.function(image=img_pre, timeout=300)
def pre():
    return _run(["mcp-server-filesystem", "/tmp"])


@app.function(image=img_npx, timeout=300)
def npx():
    return _run(["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"])


@app.local_entrypoint()
def main():
    for name, f in (("preinstalled", pre), ("npx-y", npx)):
        for i in range(2):  # 1. = cold (nový kontejner), 2. = warm
            t = time.time()
            r = f.remote()
            print(name, "call", i + 1, "wall_s", round(time.time() - t, 2), r, flush=True)
