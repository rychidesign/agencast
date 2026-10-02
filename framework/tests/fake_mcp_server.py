"""Fake MCP server for tests (stdio, line-delimited JSON-RPC), stdlib only.

    python fake_mcp_server.py [... ] <root>

The last argument is the allowed root (as with server-filesystem). Tools:
filesystem (list_allowed_directories, list_directory, write_file,
read_text_file — only inside the root), image (red_pixel), error with isError
(broken), slow tool (slow), environment variable value (get_env) and
schema with $ref, const and numeric enum (complex).
"""
import base64
import json
import os
import struct
import sys
import threading
import time
import zlib
from pathlib import Path

ROOT = Path(sys.argv[-1]).resolve() if len(sys.argv) > 1 else Path.cwd()


def png(w: int, h: int) -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def obj(props, required=()):
    return {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object", "properties": props,
            "required": list(required)}


PATH = {"path": {"type": "string"}}
TOOLS = {
    "list_allowed_directories": ("Return allowed directories.", obj({})),
    "list_directory": ("List a directory.", obj(PATH, ["path"])),
    "write_file": ("Write a file.", obj({**PATH, "content": {"type": "string"}}, ["path", "content"])),
    "read_text_file": ("Read a text file.", obj(PATH, ["path"])),
    "red_pixel": ("Return a red 2×2 image.", obj({})),
    "broken": ("Always return an error (isError).", obj({})),
    "slow": ("Wait for the given number of seconds.", obj({"seconds": {"type": "number"}}, ["seconds"])),
    "get_env": ("Return an environment variable value.",
                obj({"name": {"type": "string"}, "file": {"type": "boolean"}}, ["name"])),
    "complex": ("Schema with $ref, const and numeric enum.", {
        "type": "object", "$defs": {"Tag": {"type": "object", "properties": {"label": {"type": "string"}},
                                            "required": ["label"]}},
        "properties": {"tag": {"$ref": "#/$defs/Tag"}, "kind": {"const": "post"},
                       "level": {"type": "integer", "enum": [1, 2, 3]}},
        "required": ["tag", "kind", "level"]}),
}


def inside(p: str) -> Path:
    q = (ROOT / p).resolve()
    if not q.is_relative_to(ROOT):
        raise ValueError(f"Access denied - path outside allowed directories: {q} not in {ROOT}")
    return q


def call(name: str, args: dict):
    text = lambda t: [{"type": "text", "text": t}]  # noqa: E731
    match name:
        case "list_allowed_directories":
            return text(f"Allowed directories:\n{ROOT}")
        case "list_directory":
            return text("\n".join(("[DIR] " if c.is_dir() else "[FILE] ") + c.name
                                  for c in sorted(inside(args["path"]).iterdir())))
        case "write_file":
            inside(args["path"]).write_text(args["content"], encoding="utf-8")
            return text(f"Successfully wrote to {args['path']}")
        case "read_text_file":
            return text(inside(args["path"]).read_text(encoding="utf-8"))
        case "red_pixel":
            return text("Red image:") + [{"type": "image", "mimeType": "image/png",
                                                 "data": base64.b64encode(png(2, 2)).decode()}]
        case "broken":
            raise ValueError("tool is broken")
        case "slow":
            time.sleep(args["seconds"])
            return text("done")
        case "get_env":
            value = os.environ.get(args["name"], "")
            if args.get("file"):  # an image block is whatever bytes the server sends
                return [{"type": "image", "mimeType": "text/plain", "data": base64.b64encode(f"key={value}\n".encode()).decode()}]
            return text(value)
        case "complex":
            return text(json.dumps(args, ensure_ascii=False))
    raise KeyError(name)


LOCK = threading.Lock()


def reply(id_, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id_, **({"error": error} if error else {"result": result})}
    with LOCK:
        sys.stdout.write(json.dumps(msg) + "\n")
        sys.stdout.flush()


def tools_call(id_, params):
    name = params.get("name")
    if name not in TOOLS:
        return reply(id_, error={"code": -32602, "message": f"Tool {name} not found"})
    try:
        reply(id_, {"content": call(name, params.get("arguments") or {}), "isError": False})
    except Exception as e:  # tool error = isError, not a protocol error (like real servers)
        reply(id_, {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True})


def main():
    print(f"fake-mcp: root {ROOT}", file=sys.stderr, flush=True)
    for line in sys.stdin:
        if not line.strip():
            continue
        req = json.loads(line)
        method, id_, params = req.get("method"), req.get("id"), req.get("params") or {}
        if id_ is None:
            continue  # notification (notifications/initialized, …)
        if method == "initialize":
            reply(id_, {"protocolVersion": params.get("protocolVersion"), "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fake-mcp", "version": "1.0"}})
        elif method == "ping":
            reply(id_, {})
        elif method == "tools/list":
            reply(id_, {"tools": [{"name": n, "description": d, "inputSchema": s} for n, (d, s) in TOOLS.items()]})
        elif method == "tools/call":  # in a thread: a slow tool does not block subsequent calls
            threading.Thread(target=tools_call, args=(id_, params), daemon=True).start()
        else:
            reply(id_, error={"code": -32601, "message": f"Method not found: {method}"})


if __name__ == "__main__":
    main()
