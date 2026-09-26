"""Poskytovatelé přes OpenRouter: chat completions (`ask`, `image`) a Jev
(`/systemone`). Holé HTTP přes httpx (spike (a), DESIGN D3).

Tady je jen stavba požadavků a čtení odpovědí včetně třídy chyby;
opakování, rozpočet a záznam dělá engine; smyčku `task` dělá `task.py`.
"""
import base64
import json
import os
import re
import struct
import tempfile
import time
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator

from . import AgencastError
from .loader import describe_error

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
LEVELS = ("native_schema", "tool_wrapper", "prompt")  # kaskáda strukturovaného výstupu (§5.5)
SUBMIT_TOOL = "_submit_output"
PROMPT_SCHEMA_MARKER = "Odpověz jen JSON objektem podle tohoto JSON Schema, bez dalšího textu:"
MODELS_CACHE_S = 24 * 3600


# --- schema kroku (zkrácený zápis) ---------------------------------------------

def json_schema(shape) -> dict:
    """Zkrácený zápis `schema` → JSON Schema se strict tvarem (scenario.md ask)."""
    if isinstance(shape, str):
        return {"type": shape}
    if isinstance(shape, list):
        return {"type": "array", "items": json_schema(shape[0])}
    return {"type": "object", "properties": {k: json_schema(v) for k, v in shape.items()},
            "required": list(shape), "additionalProperties": False}


def shape_type(shape):
    """Zkrácený zápis → statický typ pro validate (integer je number)."""
    if isinstance(shape, str):
        return "number" if shape == "integer" else shape
    if isinstance(shape, list):
        return [shape_type(shape[0])]
    return {k: shape_type(v) for k, v in shape.items()}


# --- HTTP ---------------------------------------------------------------------

class Client:
    """Jedno spojení na OpenRouter pro celý běh. Klíč jde jen do hlavičky."""

    def __init__(self, base_url: str, api_key: str | None, transport=None):
        self.http = httpx.AsyncClient(
            base_url=base_url, transport=transport, timeout=httpx.Timeout(None, connect=15),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {})

    async def post(self, path: str, body: dict, step: str, timeout: float | None = None):
        """(status | None při chybě sítě, tělo jako dict, hlavičky). Vypršení `timeout` = chyba sítě → transient."""
        try:
            r = await self.http.post(path, json=body, extensions={"agencast_step": step},
                                     timeout=httpx.Timeout(timeout, connect=15 if timeout is None else min(15, timeout)))
        except httpx.HTTPError as e:
            return None, {"error": {"message": f"chyba sítě: {type(e).__name__}: {e}"}}, {}
        try:
            data = r.json()
        except ValueError:
            data = {"raw_text": r.text[:2000]}
        return r.status_code, data if isinstance(data, dict) else {"raw": data}, r.headers

    async def aclose(self):
        await self.http.aclose()


def list_models(base_url: str, runs_dir: Path, transport=None) -> list[dict]:
    """`GET /models` s cache 24 h v `<runs>/_models.json` (scenario.md §7)."""
    cache = runs_dir / "_models.json"
    if transport is None and cache.is_file():
        try:
            c = json.loads(cache.read_text())
        except ValueError:  # poškozená cache = cache není (přepíše se)
            c = {}
        if c.get("base_url") == base_url and time.time() - c.get("fetched_at", 0) < MODELS_CACHE_S:
            return c["data"]
    try:
        with httpx.Client(transport=transport, timeout=30) as http:
            r = http.get(base_url.rstrip("/") + "/models")
        data = r.json()["data"] if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError, KeyError) as e:
        data, r = None, e
    if data is None:
        raise AgencastError("transient", f"GET {base_url}/models selhalo ({getattr(r, 'status_code', r)}) a platná "
                                    f"cache {cache} není — kontrola modelů potřebuje síť")
    data = [{"id": m["id"], "output_modalities": (m.get("architecture") or {}).get("output_modalities") or [],
             "supported_parameters": m.get("supported_parameters") or []} for m in data]
    if transport is None:
        runs_dir.mkdir(parents=True, exist_ok=True)
        # souběžné běhy: dočasný soubor ve stejné složce + os.replace → čtenář nikdy nevidí půlku
        fd, tmp = tempfile.mkstemp(dir=runs_dir, prefix="_models.", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"base_url": base_url, "fetched_at": time.time(), "data": data}))
        os.replace(tmp, cache)
    return data


# --- chyby a spotřeba ---------------------------------------------------------

def _retry_after(headers) -> float | None:
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def http_error(status, body: dict, headers) -> AgencastError | None:
    """Třída chyby z HTTP statusu a pole `error` (scenario.md §6). 200 bez `error` = None."""
    err = body.get("error")
    if status == 200 and not err:
        return None
    msg = err.get("message") if isinstance(err, dict) else (err or body.get("raw_text") or "")
    meta = err.get("metadata") if isinstance(err, dict) else None
    code = status if status != 200 else (err.get("code") if isinstance(err, dict) else None)
    text = f"HTTP {status}" + (f" (error.code {code})" if code != status else "") + f": {msg}"
    if meta:
        text += f" {json.dumps(meta, ensure_ascii=False)[:500]}"
    kw = {"http_status": status, "retry_after": _retry_after(headers)}
    if status is None:
        return AgencastError("transient", msg, **kw)
    if not isinstance(code, int) or code in (408, 429) or code >= 500:
        return AgencastError("transient", text, **kw)
    if code == 402:
        return AgencastError("budget", text + " — došel kredit nebo limit klíče", **kw)
    blob = json.dumps(body, ensure_ascii=False).lower()
    if code == 403 and any(w in blob for w in ("moderation", "content_policy", "refusal", "flagged")):
        return AgencastError("content", text, **kw)
    return AgencastError("config", text, **kw)


def usage(body: dict) -> dict:
    """Normalizovaná spotřeba (run-record.md): chat i Jev → input/output_tokens, cost_usd."""
    u = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    return {"input_tokens": u.get("prompt_tokens", u.get("input_tokens")),
            "output_tokens": u.get("completion_tokens", u.get("output_tokens")),
            "cost_usd": u.get("cost")}


def _no_cost(meta) -> AgencastError | None:
    if meta["usage"]["cost_usd"] is None:
        return AgencastError("transient", "cena neznámá (odpověď nemá usage.cost)", final="budget")
    return None


def _choice(body: dict, meta: dict):
    """Společné kontroly chat completions: (message, finish_reason) nebo chyba."""
    choices = body.get("choices") or []
    if not choices:
        return None, None, AgencastError("transient", "odpověď bez choices (HTTP 200)")
    ch = choices[0]
    msg = ch.get("message") or {}
    fr = meta["finish_reason"] = ch.get("finish_reason")
    meta["native_finish_reason"] = ch.get("native_finish_reason")
    if msg.get("refusal"):
        return msg, fr, AgencastError("content", f"model odmítl: {msg['refusal']}")
    if fr == "content_filter":
        return msg, fr, AgencastError("content", "obsah zablokoval filtr poskytovatele (finish_reason: content_filter)")
    if fr == "length":
        return msg, fr, AgencastError("config", "odpověď useknutá limitem max_tokens (finish_reason: length) — "
                                           "zvyš max_tokens aliasu v config.yaml")
    if fr == "error":
        return msg, fr, AgencastError("transient", "poskytovatel vrátil HTTP 200 s finish_reason: error")
    return msg, fr, None


def _meta(status, body):
    return {"http_status": status, "response_model": body.get("model"), "provider": body.get("provider"),
            "generation_id": body.get("id"), "finish_reason": None, "native_finish_reason": None,
            "usage": usage(body)}


# --- ask ------------------------------------------------------------------------

def prompt_level_suffix(schema: dict) -> str:
    """Popis JSON pro úroveň kaskády `prompt` (agent.md: připojí se na konec system promptu)."""
    return f"\n\n{PROMPT_SCHEMA_MARKER}\n{json.dumps(schema, ensure_ascii=False)}"


def chat_body(model: str, system: str, messages: list, level: str | None, schema: dict | None,
              max_tokens: int | None) -> dict:
    body = {"model": model, "messages": [{"role": "system", "content": system}, *messages],
            "usage": {"include": True}}
    if max_tokens:
        body["max_tokens"] = max_tokens
    if schema and level == "native_schema":
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "output", "strict": True, "schema": schema}}
    elif schema and level == "tool_wrapper":
        body["tools"] = [submit_tool(schema)]
        body["tool_choice"] = {"type": "function", "function": {"name": SUBMIT_TOOL}}
    return body


def submit_tool(schema: dict) -> dict:
    return {"type": "function", "function": {
        "name": SUBMIT_TOOL, "description": "Odevzdej výsledek. Zavolej právě jednou, argumenty podle schématu.",
        "parameters": schema}}


def assistant_message(msg: dict) -> dict:
    """Zpráva modelu pro další tah — `reasoning_details` beze změny zpět (§5.5)."""
    return {k: msg[k] for k in ("role", "content", "tool_calls", "reasoning_details") if msg.get(k) is not None}


def parse_chat(status, body, headers, level: str | None, schema: dict | None):
    """(meta, výstup, chyba). Úspěch až po finish_reason, obsahu, schématu a ceně (§5.1 bod 8)."""
    meta = _meta(status, body)
    meta["message"] = None
    err = http_error(status, body, headers)
    if err:
        return meta, None, err
    msg, fr, err = _choice(body, meta)
    meta["message"] = msg
    if err:
        return meta, None, err
    if schema and level == "tool_wrapper":
        calls = [c for c in msg.get("tool_calls") or [] if (c.get("function") or {}).get("name") == SUBMIT_TOOL]
        if fr not in ("tool_calls", "stop"):
            return meta, None, AgencastError("transient", f"neočekávaný finish_reason: {fr}")
        if not calls:
            return meta, None, AgencastError("schema", f"model nezavolal nástroj {SUBMIT_TOOL}")
        raw = calls[0]["function"].get("arguments")
    else:
        if fr != "stop":
            return meta, None, AgencastError("transient", f"neočekávaný finish_reason: {fr}")
        raw = msg.get("content")
        if not isinstance(raw, str) or not raw.strip():
            return meta, None, AgencastError("transient", "prázdná odpověď bez odmítnutí (HTTP 200)")
    value = raw
    if schema:
        text = raw.strip() if isinstance(raw, str) else raw
        if level == "prompt" and isinstance(text, str):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        try:
            value = json.loads(text) if isinstance(text, str) else text
        except (TypeError, ValueError) as e:
            return meta, None, AgencastError("schema", f"odpověď není JSON ({e}): {str(raw)[:200]}")
        errors = [f"{describe_error(e)} ({'.'.join(map(str, e.absolute_path)) or 'kořen'})"
                  for e in Draft202012Validator(schema).iter_errors(value)]
        if errors:
            return meta, None, AgencastError("schema", "odpověď nesedí na schema: " + "; ".join(errors[:5]))
    return meta, value, _no_cost(meta)


# --- task -----------------------------------------------------------------------------

def task_body(model: str, system: str, messages: list, tools: list, level: str | None, schema: dict | None,
              max_tokens: int | None) -> dict:
    """Tah kroku `task`: nástroje MCP (+ load_skill); kaskáda jako u `ask`, ale `_submit_output`
    se nevynucuje (model mezitím volá jiné nástroje) a ukončí smyčku (scenario.md task)."""
    body = chat_body(model, system, messages, level if level != "tool_wrapper" else None, schema, max_tokens)
    tools = tools + ([submit_tool(schema)] if schema and level == "tool_wrapper" else [])
    if tools:
        body["tools"] = tools
    return body


def parse_task(status, body, headers, level: str | None, schema: dict | None):
    """(meta, {"calls": [...]} | {"final": výstup}, chyba). Volání nástrojů = další tah;
    `_submit_output` (tool_wrapper) nebo odpověď bez nástrojů = konec smyčky."""
    meta, value, err = parse_chat(status, body, headers, level, schema)
    msg = meta["message"] or {}
    calls = msg.get("tool_calls") or []
    submit = schema and level == "tool_wrapper" and any(
        (c.get("function") or {}).get("name") == SUBMIT_TOOL for c in calls)
    if calls and not submit and meta["finish_reason"] in ("tool_calls", "stop") and not msg.get("refusal"):
        return meta, {"calls": calls}, _no_cost(meta)
    return meta, None if err else {"final": value}, err


# --- jev ----------------------------------------------------------------------------

def parse_jev(status, body, headers, questions: dict):
    """Výstup `{otázka: hodnota, details: {otázka: {…}}}` (scenario.md jev)."""
    meta = {"http_status": status, "response_model": body.get("model"), "usage": usage(body), "answers": None}
    err = http_error(status, body, headers)
    if err:
        return meta, None, err
    answers = body.get("answers") if isinstance(body.get("answers"), dict) else {}
    out, details = {}, {}
    for q, spec in questions.items():
        a = answers.get(q)
        t = spec["type"]
        v = a.get(t) if isinstance(a, dict) else None
        ok = isinstance(v, str) if t == "choice" else isinstance(v, (int, float)) and not isinstance(v, bool)
        if not ok:
            return meta, None, AgencastError("transient", f"Jev nevrátil platnou odpověď na otázku '{q}' ({t}): {a!r}")
        out[q] = v
        details[q] = {k: x for k, x in a.items() if k not in ("type", t)}
    meta["answers"] = dict(out)
    out["details"] = details
    return meta, out, _no_cost(meta)


# --- image --------------------------------------------------------------------------

def image_body(model: str, prompt: str, aspect_ratio: str | None) -> dict:
    body = {"model": model, "modalities": ["image", "text"], "usage": {"include": True},
            "messages": [{"role": "user", "content": prompt}]}
    if aspect_ratio:
        # ChatRequest.image_config (https://openrouter.ai/docs/llms-full.txt, staženo 2026-09-25)
        body["image_config"] = {"aspect_ratio": aspect_ratio}
    return body


def parse_image(status, body, headers):
    """(meta, (bajty, media_type), chyba). Bez obrázku: odmítnutí → content, jinak transient → content."""
    meta = _meta(status, body)
    err = http_error(status, body, headers)
    if err:
        return meta, None, err
    msg, fr, err = _choice(body, meta)
    if err:
        return meta, None, err
    images = msg.get("images") or []
    if not images:
        return meta, None, AgencastError("transient", "model nevrátil obrázek", final="content")
    if fr != "stop":
        return meta, None, AgencastError("transient", f"neočekávaný finish_reason: {fr}")
    url = ((images[0] or {}).get("image_url") or {}).get("url") or ""
    head, _, b64 = url.partition(",")
    if not head.startswith("data:") or ";base64" not in head:
        return meta, None, AgencastError("transient", f"obrázek není data URL base64: {url[:60]}")
    try:
        data = base64.b64decode(b64, validate=True)
    except ValueError as e:
        return meta, None, AgencastError("transient", f"obrázek nejde dekódovat z base64: {e}")
    return meta, (data, head[5:].split(";")[0]), _no_cost(meta)


def image_size(data: bytes) -> tuple[int | None, int | None]:
    """Rozměry z hlavičky PNG nebo JPEG."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                break
            marker, length = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + length
    return None, None
