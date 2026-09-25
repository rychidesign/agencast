"""Společné funkce spiku (d): parametry MCP serverů, OpenRouter přes httpx, rozpočet, výsledky.

Klíč jen z prostředí (OPENROUTER_API_KEY), nikdy se nevypisuje ani neukládá.
"""
import json, os, subprocess, sys, time
from pathlib import Path

import httpx
from mcp import StdioServerParameters

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
RESULTS.mkdir(exist_ok=True)
BIN = HERE / "node_modules" / ".bin"
SANDBOX = HERE / "sandbox"  # kořen pro server-filesystem (jen tahle složka je mu povolená)

OR_BASE = "https://openrouter.ai/api/v1"
BUDGET_FILE = RESULTS / "_spend.json"
BUDGET_LIMIT = 0.20
MODELS = ["anthropic/claude-haiku-4.5", "google/gemini-3.5-flash-lite"]


def fs_params(via_npx=False):
    if via_npx:
        return StdioServerParameters(command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", str(SANDBOX)])
    return StdioServerParameters(command=str(BIN / "mcp-server-filesystem"), args=[str(SANDBOX)])


def everything_params():
    return StdioServerParameters(command=str(BIN / "mcp-server-everything"), args=["stdio"])


def descendants(pid=None):
    """Všechny potomky procesu (pid, stav, příkaz) — kontrola, že po ukončení nic nezůstalo."""
    pid = pid or os.getpid()
    out = subprocess.run(["ps", "-e", "-o", "pid=,ppid=,stat=,args="], capture_output=True, text=True).stdout
    rows = [l.split(None, 3) for l in out.splitlines() if l.strip()]
    kids, frontier = [], {str(pid)}
    while frontier:
        new = [r for r in rows if r[1] in frontier and r[0] != str(os.getpid())]
        kids += new
        frontier = {r[0] for r in new}
    return [{"pid": int(r[0]), "stat": r[2], "cmd": r[3][:120]} for r in kids if "ps -e -o" not in r[3]]


def save(name, data):
    (RESULTS / name).write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str))


# --- OpenRouter -----------------------------------------------------------------

def _key():
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k:
        sys.exit("Chybí OPENROUTER_API_KEY v prostředí (set -a; . ./.env; set +a).")
    return k


def spent():
    return sum(json.loads(BUDGET_FILE.read_text()).values()) if BUDGET_FILE.exists() else 0.0


def _add_spend(label, cost):
    d = json.loads(BUDGET_FILE.read_text()) if BUDGET_FILE.exists() else {}
    d[label] = d.get(label, 0.0) + (cost or 0.0)
    BUDGET_FILE.write_text(json.dumps(d, indent=1))


def mcp_tool_to_openai(tool, name=None, normalize=True):
    """MCP Tool → položka `tools` pro chat completions (function calling)."""
    schema = tool.input_schema if hasattr(tool, "input_schema") else tool["inputSchema"]
    desc = tool.description if hasattr(tool, "description") else tool.get("description")
    tname = name or (tool.name if hasattr(tool, "name") else tool["name"])
    if normalize:
        schema = normalize_schema(schema)
    return {"type": "function", "function": {"name": tname, "description": desc or "", "parameters": schema}}


def normalize_schema(schema):
    """Normalizace podle měření q2a (viz REPORT): Gemini ignoruje $ref, allOf a const.

    Vloží $ref z $defs/definitions (rekurzivní $ref → ValueError), sloučí allOf, const → enum,
    oneOf → anyOf; kořen vždy {type: object, properties: {...}}. Původní schéma dál slouží
    k validaci argumentů na straně klienta.
    """
    defs = {**schema.get("definitions", {}), **schema.get("$defs", {})}

    def walk(node, seen):
        if isinstance(node, list):
            return [walk(x, seen) for x in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            ref = node["$ref"]
            name = ref.rsplit("/", 1)[-1]
            if not ref.startswith(("#/$defs/", "#/definitions/")) or name not in defs:
                raise ValueError(f"nepodporovaný $ref: {ref}")
            if name in seen:
                raise ValueError(f"rekurzivní $ref: {ref}")
            rest = {k: v for k, v in node.items() if k != "$ref"}
            return walk({**defs[name], **rest}, seen | {name})
        out = {}
        for k, v in node.items():
            if k in ("$schema", "$defs", "definitions"):
                continue
            if k == "allOf":
                for part in walk(v, seen):
                    out.update(part)  # ponytail: mělké sloučení; stačí pro allOf z Pydanticu (obal jednoho $ref)
            elif k == "oneOf":
                out["anyOf"] = walk(v, seen)
            elif k == "const":
                out["enum"] = [v]
            elif k == "properties":
                out[k] = {pk: walk(pv, seen) for pk, pv in v.items()}
            else:
                out[k] = walk(v, seen)
        if any(not isinstance(x, str) for x in out.get("enum", [])):
            # Gemini: enum jen pro řetězce; s číselným enum pošle {} (vlastnost zmizí). Hodnoty → popis.
            vals = ", ".join(json.dumps(x) for x in out.pop("enum"))
            out["description"] = (out.get("description", "") + f" Povolené hodnoty: {vals}.").strip()
        return out

    s = walk(schema, frozenset())
    s["type"] = "object"
    s.setdefault("properties", {})
    return s


def safe_tool_name(server, tool):
    """Jméno funkce pro API: `server__tool`, jen [a-zA-Z0-9_-], max 64 (Claude: vzor ^[a-zA-Z0-9_-]{1,128}$)."""
    import re
    return re.sub(r"[^a-zA-Z0-9_-]", "_", f"{server}__{tool}")[:64]


def chat(payload, label):
    """POST /chat/completions. Vrátí (status, body, latence_s). Chyby HTTP neskrývá."""
    if spent() >= BUDGET_LIMIT:
        sys.exit(f"ROZPOČET PŘEKROČEN ({spent():.4f} USD) — zastaveno.")
    payload = {"temperature": 0, "usage": {"include": True}, **payload}
    t = time.perf_counter()
    try:
        r = httpx.post(f"{OR_BASE}/chat/completions", json=payload, timeout=120,
                       headers={"Authorization": f"Bearer {_key()}"})
        status = r.status_code
        try:
            body = r.json()
        except ValueError:
            body = {"raw_text": r.text}
    except httpx.HTTPError as e:  # síť/timeout — ať to nezmizí potichu
        return None, {"transport_error": repr(e)}, time.perf_counter() - t
    lat = time.perf_counter() - t
    if isinstance(body, dict) and isinstance(body.get("usage"), dict):
        _add_spend(label, body["usage"].get("cost"))
    return status, body, lat


# --- Smyčka agenta (task) nad MCP -------------------------------------------------

def mcp_result_to_parts(res, image_mode):
    """CallToolResult → obsah tool zprávy. image_mode: 'tool_array' (obrázek přímo v tool zprávě)
    nebo 'user_followup' (v tool zprávě jen text, obrázek jde v následné user zprávě)."""
    parts, images = [], []
    for b in res.content:
        if b.type == "text":
            parts.append({"type": "text", "text": b.text})
        elif b.type == "image":
            url = f"data:{b.mime_type};base64,{b.data}"
            images.append({"type": "image_url", "image_url": {"url": url}})
        else:  # resource, resource_link, audio — pro spike jen popisek
            parts.append({"type": "text", "text": f"[{b.type} obsah vynechán]"})
    if res.is_error:
        parts.insert(0, {"type": "text", "text": "CHYBA NÁSTROJE:"})
    if image_mode == "tool_array":
        return parts + images, []
    if images:
        parts.append({"type": "text", "text": f"[{len(images)} obrázek/obrázky přiloženy v následující zprávě]"})
    return parts, images


async def run_agent(model, messages, tools, dispatch, label, max_turns=6, image_mode="tool_array"):
    """Smyčka model ↔ nástroje. dispatch(name, args) → CallToolResult nebo str (chyba klienta).
    Vrací záznam: tahy, volání, cena, latence, finální text. Nic nezahazuje potichu."""
    log = {"model": model, "turns": [], "cost": 0.0, "latency_s": 0.0, "final": None, "error": None}
    messages = list(messages)
    for turn in range(max_turns):
        payload = {"model": model, "max_tokens": 800, "messages": messages}
        if tools:
            payload["tools"] = tools
        status, body, lat = chat(payload, label=label)
        log["latency_s"] += lat
        if status != 200 or "choices" not in body:
            log["error"] = {"status": status, "body": body.get("error", body)}
            return log
        log["cost"] += body.get("usage", {}).get("cost") or 0
        ch = body["choices"][0]
        msg = ch["message"]
        calls = msg.get("tool_calls") or []
        log["turns"].append({"finish_reason": ch.get("finish_reason"), "latency_s": round(lat, 2),
                             "calls": [{"name": c["function"]["name"], "arguments": c["function"]["arguments"]}
                                       for c in calls]})
        if not calls:
            if ch.get("finish_reason") not in ("stop", "end_turn"):
                log["error"] = {"finish_reason": ch.get("finish_reason")}
            log["final"] = msg.get("content")
            return log
        # assistant zprávu vrátit beze změny (vč. reasoning_details — doporučení OpenRouteru)
        messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls", "reasoning_details")})
        followup_images = []
        for c in calls:
            try:
                args = json.loads(c["function"]["arguments"] or "{}")
            except ValueError as e:
                args, res = None, f"Neplatný JSON argumentů: {e}"
            if args is not None:
                res = await dispatch(c["function"]["name"], args)
            if isinstance(res, str):
                content, imgs = [{"type": "text", "text": "CHYBA: " + res}], []
            else:
                content, imgs = mcp_result_to_parts(res, image_mode)
            followup_images += imgs
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": content})
        if followup_images:
            messages.append({"role": "user", "content": [{"type": "text", "text": "Obrázky z výsledků nástrojů:"}]
                             + followup_images})
    log["error"] = {"max_turns": max_turns}
    return log


def make_dispatch(clients, allowed):
    """allowed: {api_name: (server_key, mcp_tool)}. Volá jen povolené nástroje, argumenty validuje
    proti původnímu schématu. Nepovolené jméno → chyba (nikdy se nepošle na server)."""
    import jsonschema

    async def dispatch(api_name, args):
        if api_name not in allowed:
            return f"Nástroj {api_name} není pro tohoto agenta povolen."
        server, tool = allowed[api_name]
        try:
            jsonschema.validate(args, tool.input_schema)
        except jsonschema.ValidationError as e:
            return f"Argumenty neprošly schématem: {e.message}"
        return await clients[server].call_tool(tool.name, args, read_timeout_seconds=30)

    return dispatch
