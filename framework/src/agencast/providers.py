"""Providers via OpenRouter: chat completions (`ask`, `image`), Images API
(`image`) and Jev (`/systemone`). Plain HTTP via httpx (spike (a), DESIGN D3).

Only request construction and response parsing, including the error class;
the engine handles retries, budgets and records; `task.py` handles the `task` loop.
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
LEVELS = ("native_schema", "tool_wrapper", "prompt")  # structured output cascade (§5.5)
SUBMIT_TOOL = "_submit_output"
PROMPT_SCHEMA_MARKER = "Respond only with a JSON object matching this JSON Schema, without any additional text:"
MODELS_CACHE_S = 24 * 3600


# --- step schema (shorthand) ---------------------------------------------

def json_schema(shape) -> dict:
    """Shorthand `schema` → JSON Schema with a strict shape (scenario.md ask)."""
    if isinstance(shape, str):
        return {"type": shape}
    if isinstance(shape, list):
        return {"type": "array", "items": json_schema(shape[0])}
    return {"type": "object", "properties": {k: json_schema(v) for k, v in shape.items()},
            "required": list(shape), "additionalProperties": False}


def shape_type(shape):
    """Shorthand → static type for validate (integer is number)."""
    if isinstance(shape, str):
        return "number" if shape == "integer" else shape
    if isinstance(shape, list):
        return [shape_type(shape[0])]
    return {k: shape_type(v) for k, v in shape.items()}


# --- HTTP ---------------------------------------------------------------------

class Client:
    """One OpenRouter connection for the entire run. The key goes only in the header."""

    def __init__(self, base_url: str, api_key: str | None, transport=None):
        self.http = httpx.AsyncClient(
            base_url=base_url, transport=transport, timeout=httpx.Timeout(None, connect=15),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {})

    async def post(self, path: str, body: dict, step: str, timeout: float | None = None):
        """(status | None on network error, body as dict, headers). Expired `timeout` = network error → transient."""
        try:
            r = await self.http.post(path, json=body, extensions={"agencast_step": step},
                                     timeout=httpx.Timeout(timeout, connect=15 if timeout is None else min(15, timeout)))
        except httpx.HTTPError as e:
            return None, {"error": {"message": f"network error: {type(e).__name__}: {e}"}}, {}
        try:
            data = r.json()
        except ValueError:
            data = {"raw_text": r.text[:2000]}
        return r.status_code, data if isinstance(data, dict) else {"raw": data}, r.headers

    async def aclose(self):
        await self.http.aclose()


def list_models(base_url: str, runs_dir: Path, transport=None) -> list[dict]:
    """`GET /models` with a 24 h cache in `<runs>/_models.json` (scenario.md §7)."""
    cache = runs_dir / "_models.json"
    if transport is None and cache.is_file():
        try:
            c = json.loads(cache.read_text())
        except ValueError:  # corrupt cache = no cache (will be overwritten)
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
        raise AgencastError("transient", f"GET {base_url}/models failed ({getattr(r, 'status_code', r)}) and no valid "
                                    f"cache {cache} exists — checking models requires network access")
    data = [{"id": m["id"], "output_modalities": (m.get("architecture") or {}).get("output_modalities") or [],
             "supported_parameters": m.get("supported_parameters") or []} for m in data]
    if transport is None:
        runs_dir.mkdir(parents=True, exist_ok=True)
        # concurrent runs: temporary file in the same directory + os.replace → readers never see partial data
        fd, tmp = tempfile.mkstemp(dir=runs_dir, prefix="_models.", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"base_url": base_url, "fetched_at": time.time(), "data": data}))
        os.replace(tmp, cache)
    return data


def list_image_models(base_url: str, runs_dir: Path, transport=None) -> list[dict]:
    """`GET /images/models` with its own 24 h cache (OpenRouter Images API)."""
    cache = runs_dir / "_images_models.json"
    if transport is None and cache.is_file():
        try:
            c = json.loads(cache.read_text())
        except ValueError:
            c = {}
        if c.get("base_url") == base_url and time.time() - c.get("fetched_at", 0) < MODELS_CACHE_S:
            return c["data"]
    url = base_url.rstrip("/") + "/images/models"
    try:
        with httpx.Client(transport=transport, timeout=30) as http:
            r = http.get(url)
        data = r.json()["data"] if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError, KeyError) as e:
        data, r = None, e
    if data is None:
        raise AgencastError("transient", f"GET {url} failed ({getattr(r, 'status_code', r)}) and no valid "
                                    f"cache {cache} exists — checking models requires network access")
    data = [{"id": m["id"], "output_modalities": (m.get("architecture") or {}).get("output_modalities") or [],
             "supported_parameters": m.get("supported_parameters") or {}} for m in data]
    if transport is None:
        runs_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=runs_dir, prefix="_images_models.", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"base_url": base_url, "fetched_at": time.time(), "data": data}))
        os.replace(tmp, cache)
    return data


# --- errors and usage ---------------------------------------------------------

def _retry_after(headers) -> float | None:
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def http_error(status, body: dict, headers) -> AgencastError | None:
    """Error class from HTTP status and the `error` field (scenario.md §6). 200 without `error` = None."""
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
        return AgencastError("budget", text + " — credit exhausted or key limit reached", **kw)
    blob = json.dumps(body, ensure_ascii=False).lower()
    if code == 403 and any(w in blob for w in ("moderation", "content_policy", "refusal", "flagged")):
        return AgencastError("content", text, **kw)
    return AgencastError("config", text, **kw)


def usage(body: dict) -> dict:
    """Normalized usage (run-record.md): chat and Jev → input/output_tokens, cost_usd."""
    u = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    return {"input_tokens": u.get("prompt_tokens", u.get("input_tokens")),
            "output_tokens": u.get("completion_tokens", u.get("output_tokens")),
            "cost_usd": u.get("cost")}


def _no_cost(meta) -> AgencastError | None:
    if meta["usage"]["cost_usd"] is None:
        return AgencastError("transient", "unknown cost (response has no usage.cost)", final="budget")
    return None


def _choice(body: dict, meta: dict):
    """Shared chat completions checks: (message, finish_reason) or error."""
    choices = body.get("choices") or []
    if not choices:
        return None, None, AgencastError("transient", "response without choices (HTTP 200)")
    ch = choices[0]
    msg = ch.get("message") or {}
    fr = meta["finish_reason"] = ch.get("finish_reason")
    meta["native_finish_reason"] = ch.get("native_finish_reason")
    if msg.get("refusal"):
        return msg, fr, AgencastError("content", f"model refused: {msg['refusal']}")
    if fr == "content_filter":
        return msg, fr, AgencastError("content", "content blocked by the provider filter (finish_reason: content_filter)")
    if fr == "length":
        return msg, fr, AgencastError("config", "response truncated by the max_tokens limit (finish_reason: length) — "
                                           "increase the alias max_tokens in config.yaml")
    if fr == "error":
        return msg, fr, AgencastError("transient", "provider returned HTTP 200 with finish_reason: error")
    return msg, fr, None


def _meta(status, body):
    return {"http_status": status, "response_model": body.get("model"), "provider": body.get("provider"),
            "generation_id": body.get("id"), "finish_reason": None, "native_finish_reason": None,
            "usage": usage(body)}


# --- ask ------------------------------------------------------------------------

def prompt_level_suffix(schema: dict) -> str:
    """JSON description for the `prompt` cascade level (agent.md: appended to the system prompt)."""
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
        "name": SUBMIT_TOOL, "description": "Submit the result. Call exactly once, with arguments matching the schema.",
        "parameters": schema}}


def assistant_message(msg: dict) -> dict:
    """Model message for the next turn — pass `reasoning_details` back unchanged (§5.5)."""
    return {k: msg[k] for k in ("role", "content", "tool_calls", "reasoning_details") if msg.get(k) is not None}


def parse_chat(status, body, headers, level: str | None, schema: dict | None):
    """(meta, output, error). Success only after checking finish_reason, content, schema and cost (§5.1 item 8)."""
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
            return meta, None, AgencastError("transient", f"unexpected finish_reason: {fr}")
        if not calls:
            return meta, None, AgencastError("schema", f"model did not call tool {SUBMIT_TOOL}")
        raw = calls[0]["function"].get("arguments")
    else:
        if fr != "stop":
            return meta, None, AgencastError("transient", f"unexpected finish_reason: {fr}")
        raw = msg.get("content")
        if not isinstance(raw, str) or not raw.strip():
            return meta, None, AgencastError("transient", "empty response without refusal (HTTP 200)")
    value = raw
    if schema:
        text = raw.strip() if isinstance(raw, str) else raw
        if level == "prompt" and isinstance(text, str):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        try:
            value = json.loads(text) if isinstance(text, str) else text
        except (TypeError, ValueError) as e:
            return meta, None, AgencastError("schema", f"response is not JSON ({e}): {str(raw)[:200]}")
        errors = [f"{describe_error(e)} ({'.'.join(map(str, e.absolute_path)) or 'root'})"
                  for e in Draft202012Validator(schema).iter_errors(value)]
        if errors:
            return meta, None, AgencastError("schema", "response does not match schema: " + "; ".join(errors[:5]))
    return meta, value, _no_cost(meta)


# --- task -----------------------------------------------------------------------------

def task_body(model: str, system: str, messages: list, tools: list, level: str | None, schema: dict | None,
              max_tokens: int | None) -> dict:
    """Turn of a `task` step: MCP tools (+ load_skill); cascade like `ask`, but `_submit_output`
    is not forced (the model calls other tools in between) and ends the loop (scenario.md task)."""
    body = chat_body(model, system, messages, level if level != "tool_wrapper" else None, schema, max_tokens)
    tools = tools + ([submit_tool(schema)] if schema and level == "tool_wrapper" else [])
    if tools:
        body["tools"] = tools
    return body


def parse_task(status, body, headers, level: str | None, schema: dict | None):
    """(meta, {"calls": [...]} | {"final": output}, error). Tool calls = next turn;
    `_submit_output` (tool_wrapper) or a response without tools = end of loop."""
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
    """Output `{question: value, details: {question: {…}}}` (scenario.md jev)."""
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
            return meta, None, AgencastError("transient", f"Jev did not return a valid answer to question '{q}' ({t}): {a!r}")
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
        # ChatRequest.image_config (https://openrouter.ai/docs/llms-full.txt, downloaded 2026-09-25)
        body["image_config"] = {"aspect_ratio": aspect_ratio}
    return body


def images_body(model: str, prompt: str, aspect_ratio: str | None, quality: str | None = None,
                resolution: str | None = None) -> dict:
    body = {"model": model, "prompt": prompt}
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if quality:
        body["quality"] = quality
    if resolution:
        body["resolution"] = resolution
    return body


def parse_image(status, body, headers):
    """(meta, (bytes, media_type), error). No image: refusal → content, otherwise transient → content."""
    meta = _meta(status, body)
    err = http_error(status, body, headers)
    if err:
        return meta, None, err
    msg, fr, err = _choice(body, meta)
    if err:
        return meta, None, err
    images = msg.get("images") or []
    if not images:
        return meta, None, AgencastError("transient", "model returned no image", final="content")
    if fr != "stop":
        return meta, None, AgencastError("transient", f"unexpected finish_reason: {fr}")
    url = ((images[0] or {}).get("image_url") or {}).get("url") or ""
    head, _, b64 = url.partition(",")
    if not head.startswith("data:") or ";base64" not in head:
        return meta, None, AgencastError("transient", f"image is not a base64 data URL: {url[:60]}")
    try:
        data = base64.b64decode(b64, validate=True)
    except ValueError as e:
        return meta, None, AgencastError("transient", f"cannot decode image from base64: {e}")
    return meta, (data, head[5:].split(";")[0]), _no_cost(meta)


def parse_images(status, body, headers):
    """Parse Images API; empty output is retried as transient, then ends as content."""
    meta = _meta(status, body)
    err = http_error(status, body, headers)
    if err:
        refusal = body.get("refusal")
        detail = json.dumps(body, ensure_ascii=False).lower()
        if status is not None and status < 500 and (refusal or any(
                marker in detail for marker in ("moderation", "content_policy", "refusal", "flagged"))):
            return meta, None, AgencastError("content", f"model refused: {refusal or 'content blocked by the provider filter'}",
                                              http_status=status)
        return meta, None, err
    if body.get("refusal"):
        return meta, None, AgencastError("content", f"model refused: {body['refusal']}")
    images = body.get("data") or []
    if not images:
        return meta, None, AgencastError("transient", "model returned no image", final="content")
    item = images[0] if isinstance(images[0], dict) else {}
    try:
        data = base64.b64decode(item.get("b64_json", ""), validate=True)
    except (ValueError, TypeError) as e:
        return meta, None, AgencastError("transient", f"cannot decode image from base64: {e}")
    media = item.get("media_type")
    if not media:
        media = image_media_type(data)
        if not media:
            return meta, None, AgencastError("content", "unsupported image format")
    return meta, (data, media), _no_cost(meta)


def image_media_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def image_size(data: bytes) -> tuple[int | None, int | None]:
    """Dimensions from the PNG, JPEG or WebP header."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        if len(data) < 24:
            return None, None
        return struct.unpack(">II", data[16:24])
    if len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X":
            return (int.from_bytes(data[24:27], "little") + 1,
                    int.from_bytes(data[27:30], "little") + 1)
        if chunk == b"VP8L" and data[20] == 0x2F and len(data) >= 25:
            bits = int.from_bytes(data[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            return (int.from_bytes(data[26:28], "little") & 0x3FFF,
                    int.from_bytes(data[28:30], "little") & 0x3FFF)
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 <= len(data):
            if data[i] != 0xFF:
                break
            marker = data[i + 1]
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if length < 2 or i + 2 + length > len(data):
                break
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + length
    return None, None
