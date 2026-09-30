"""Fake provider: deterministic, offline, free (DESIGN §5.6).

Uses `httpx.MockTransport` instead of the network, so conformance tests and `--fake`
follow exactly the same code as real calls (cascade, finish_reason, cost).

Script = map `step path: [response, …]`; each step call takes the next
response, repeating the last one. Without a script, the response is generated from the request
(JSON matching the schema, Jev: noul 0.5 / first choice / score 0, PNG image
with `aspect_ratio`). Script response shapes:

    json: {...}            structured output (as an _submit_output call for tool_wrapper)
    tool_calls: [{name, arguments}]  tool calls (task step turn)
    text: "..."            text response (for tool_wrapper = model did not call _submit_output)
    answers: {q: value}    Jev answers (missing questions get defaults)
    image: {width, height} PNG image of given dimensions
    status: 429            error HTTP status (optionally error: "message")
    finish_reason: error   another finish_reason (empty content)
    refusal: "..."         refusal
    cost: null             response without usage.cost
    sleep: 1.5             delay in seconds (timeouts)
    body: {...}            literal full response body
"""
import asyncio
import base64
import json
import struct
import zlib

import httpx

from .providers import PROMPT_SCHEMA_MARKER, SUBMIT_TOOL


def png(width: int, height: int) -> bytes:
    """Smallest valid PNG (gray fill) of given dimensions."""
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    raw = b"".join(b"\x00" + b"\x80" * (3 * width) for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def dummy(schema: dict, name: str = "value"):
    """Deterministic value matching JSON Schema."""
    match schema.get("type"):
        case "object":
            return {k: dummy(v, k) for k, v in schema["properties"].items()}
        case "array":
            return [dummy(schema["items"], name)]
        case "number":
            return 1.5
        case "integer":
            return 1
        case "boolean":
            return True
    return f"fake text ({name})"


class Fake:
    def __init__(self, script: dict | None = None, models=(), image_models=()):
        self.script = script or {}
        self.models = list(models)
        self.image_models = list(image_models)
        self.calls: list[tuple[str, str, dict]] = []  # (step path, endpoint, request body)
        self._used: dict[str, int] = {}

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request):
        path = request.url.path
        if path.endswith("/images/models"):
            return httpx.Response(200, json={"data": [
                {"id": m, "architecture": {"output_modalities": ["image"]},
                 "supported_parameters": {
                     "aspect_ratio": {"type": "enum", "values": ["1:1", "3:2", "2:3", "4:3", "3:4",
                                                                       "16:9", "9:16", "21:9", "auto"]},
                     "quality": {"type": "enum", "values": ["auto", "low", "medium", "high"]},
                     "resolution": {"type": "enum", "values": ["512", "1K", "2K", "4K"]}}}
                for m in self.image_models]})
        if path.endswith("/models"):
            return httpx.Response(200, json={"data": [
                {"id": m, "architecture": {"output_modalities": ["image", "text"] if "image" in m else ["text"],
                                           "input_modalities": ["text", "image"]},
                 "supported_parameters": ["max_tokens", "response_format", "structured_outputs", "tool_choice",
                                          "tools"]} for m in self.models]})
        step = request.extensions.get("agencast_step", "")
        body = json.loads(request.content)
        self.calls.append((step, path.rsplit("/", 1)[-1], body))
        plan = self.script.get(step) or [{}]
        plan = plan if isinstance(plan, list) else [plan]
        n = self._used.get(step, 0)
        self._used[step] = n + 1
        spec = plan[min(n, len(plan) - 1)] or {}
        resp = self._respond(path, body, spec, n + 1)
        if spec.get("sleep"):
            return self._later(resp, spec["sleep"])
        return resp

    async def _later(self, resp, seconds):
        await asyncio.sleep(seconds)
        return resp

    def _respond(self, path, body, spec, n):
        if "body" in spec:
            return httpx.Response(spec.get("status", 200), json=spec["body"])
        if spec.get("status", 200) != 200:
            return httpx.Response(spec["status"], json={"error": {"code": spec["status"],
                                                                  "message": spec.get("error", "fake error")}},
                                  headers={"retry-after": "0"})
        cost = spec.get("cost", 0.0001)
        if path.endswith("/images"):
            if spec.get("refusal"):
                return httpx.Response(403, json={"error": {"code": 403,
                                                              "message": f"content_policy_violation: {spec['refusal']}"}})
            w, h = self._image_size(body, spec.get("image"))
            image = {"b64_json": base64.b64encode(png(w, h)).decode()}
            if not spec.get("omit_media_type"):
                image["media_type"] = spec.get("media_type", "image/png")
            return httpx.Response(200, json={"data": [image], "usage": {"cost": spec.get("cost", 0.04)}})
        if path.endswith("/systemone"):
            return httpx.Response(200, json={
                "model": "typesafe/jev-fake", "answers": self._answers(body["questions"], spec.get("answers") or {}),
                "usage": {"input_tokens": 50, "output_tokens": 5, "cost": cost}, "id": f"gen-fake-{n}"})
        msg = {"role": "assistant", "content": None, "refusal": spec.get("refusal"),
               "reasoning_details": [{"type": "reasoning.text", "signature": "fake-signature" * 8}]}
        fr = spec.get("finish_reason", "stop")
        if "modalities" in body:
            if fr == "stop" and not spec.get("refusal"):
                w, h = self._size(body, spec.get("image"))
                url = "data:image/png;base64," + base64.b64encode(png(w, h)).decode()
                msg["images"] = [{"type": "image_url", "image_url": {"url": url}}]
            cost = spec.get("cost", 0.04)
        elif fr == "stop" and not spec.get("refusal"):
            fr = self._content(body, spec, msg, n)
        return httpx.Response(200, json={
            "id": f"gen-fake-{n}", "model": body["model"], "provider": "Fake",
            "choices": [{"index": 0, "finish_reason": fr, "native_finish_reason": str(fr).upper(), "message": msg}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": cost}})

    @staticmethod
    def _answers(questions, given):
        out = {}
        for q, spec in questions.items():
            t = spec["type"]
            if t == "choice":
                keys = list(spec["criteria"])
                v = given.get(q, keys[0])
                out[q] = {"type": t, "choice": v, "probabilities": {k: float(k == v) for k in keys}, "confidence": 1}
            else:
                out[q] = {"type": t, t: given.get(q, 0.5 if t == "noul" else 0.0)}
        return out

    @staticmethod
    def _size(body, image):
        if image and "width" in image:
            return image["width"], image["height"]
        ratio = (body.get("image_config") or {}).get("aspect_ratio")
        if ratio:
            a, b = map(int, ratio.split(":"))
            return a * 64, b * 64
        return 352, 192  # ratio of the default 1408×768 (spike (a))

    @staticmethod
    def _image_size(body, image):
        if image and "width" in image:
            return image["width"], image["height"]
        ratio = body.get("aspect_ratio")
        if ratio and ratio != "auto":
            a, b = map(int, ratio.split(":"))
            return a * 64, b * 64
        return 352, 192

    @staticmethod
    def _content(body, spec, msg, n):
        """Chat response content by cascade level; returns finish_reason."""
        if "tool_calls" in spec:
            msg["tool_calls"] = [{"id": f"call_{n}_{i}", "type": "function",
                                  "function": {"name": c["name"], "arguments": c["arguments"] if isinstance(
                                      c.get("arguments"), str) else json.dumps(c.get("arguments") or {}, ensure_ascii=False)}}
                                 for i, c in enumerate(spec["tool_calls"])]
            return "tool_calls"
        tools = {t["function"]["name"]: t["function"] for t in body.get("tools") or []}
        schema = None
        if "response_format" in body:
            schema = body["response_format"]["json_schema"]["schema"]
        elif SUBMIT_TOOL in tools and "text" not in spec:  # text = model did not call _submit_output
            args = spec.get("json", dummy(tools[SUBMIT_TOOL]["parameters"]))
            msg["tool_calls"] = [{"id": "call_fake", "type": "function",
                                  "function": {"name": SUBMIT_TOOL, "arguments": json.dumps(args, ensure_ascii=False)}}]
            return "tool_calls"
        else:
            system = body["messages"][0]["content"]
            if PROMPT_SCHEMA_MARKER in system:
                schema = json.loads(system.split(PROMPT_SCHEMA_MARKER, 1)[1])
        if "text" in spec:
            msg["content"] = spec["text"]
        elif schema or "json" in spec:
            msg["content"] = json.dumps(spec.get("json", dummy(schema or {})), ensure_ascii=False)
        else:
            msg["content"] = "Fake response."
        return "stop"
