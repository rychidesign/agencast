"""Falešný poskytovatel: deterministický, bez sítě, zdarma (DESIGN §5.6).

Je to `httpx.MockTransport` místo sítě, takže konformační testy i `--fake`
jdou přesně stejným kódem jako ostré volání (kaskáda, finish_reason, cena).

Skript = mapa `cesta kroku: [odpověď, …]`; každé volání kroku vezme další
odpověď, poslední se opakuje. Bez skriptu se odpověď vyrobí z požadavku
(JSON podle schématu, Jev: noul 0.5 / první možnost / score 0, obrázek PNG
v poměru `aspect_ratio`). Tvary odpovědi ve skriptu:

    json: {...}            strukturovaný výstup (u tool_wrapper jako volání _submit_output)
    text: "..."            textová odpověď
    answers: {q: hodnota}  odpovědi Jev (chybějící otázky se doplní výchozí)
    image: {width, height} obrázek PNG daných rozměrů
    status: 429            chybový HTTP status (volitelně error: "zpráva")
    finish_reason: error   jiný finish_reason (obsah prázdný)
    refusal: "..."         odmítnutí
    cost: null             odpověď bez usage.cost
    sleep: 1.5             zdržení v sekundách (timeouty)
    body: {...}            celé tělo odpovědi doslova
"""
import asyncio
import base64
import json
import struct
import zlib

import httpx

from .providers import PROMPT_SCHEMA_MARKER, SUBMIT_TOOL


def png(width: int, height: int) -> bytes:
    """Nejmenší platné PNG (šedá plocha) daných rozměrů."""
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    raw = b"".join(b"\x00" + b"\x80" * (3 * width) for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def dummy(schema: dict, name: str = "hodnota"):
    """Deterministická hodnota podle JSON Schema."""
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
    return f"falešný text ({name})"


class Fake:
    def __init__(self, script: dict | None = None, models=()):
        self.script = script or {}
        self.models = list(models)
        self.calls: list[tuple[str, str, dict]] = []  # (cesta kroku, endpoint, tělo požadavku)
        self._used: dict[str, int] = {}

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request):
        path = request.url.path
        if path.endswith("/models"):
            return httpx.Response(200, json={"data": [
                {"id": m, "architecture": {"output_modalities": ["image", "text"] if "image" in m else ["text"]},
                 "supported_parameters": ["max_tokens", "response_format", "structured_outputs", "tool_choice",
                                          "tools"]} for m in self.models]})
        step = request.extensions.get("maw_step", "")
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
                                                                  "message": spec.get("error", "falešná chyba")}},
                                  headers={"retry-after": "0"})
        cost = spec.get("cost", 0.0001)
        if path.endswith("/systemone"):
            return httpx.Response(200, json={
                "model": "typesafe/jev-fake", "answers": self._answers(body["questions"], spec.get("answers") or {}),
                "usage": {"input_tokens": 50, "output_tokens": 5, "cost": cost}, "id": f"gen-fake-{n}"})
        msg = {"role": "assistant", "content": None, "refusal": spec.get("refusal"),
               "reasoning_details": [{"type": "reasoning.text", "signature": "falešný-podpis" * 8}]}
        fr = spec.get("finish_reason", "stop")
        if "modalities" in body:
            if fr == "stop" and not spec.get("refusal"):
                w, h = self._size(body, spec.get("image"))
                url = "data:image/png;base64," + base64.b64encode(png(w, h)).decode()
                msg["images"] = [{"type": "image_url", "image_url": {"url": url}}]
            cost = spec.get("cost", 0.04)
        elif fr == "stop" and not spec.get("refusal"):
            fr = self._content(body, spec, msg)
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
        return 352, 192  # poměr výchozích 1408×768 (spike (a))

    @staticmethod
    def _content(body, spec, msg):
        """Obsah odpovědi chatu podle úrovně kaskády; vrací finish_reason."""
        schema = None
        if "response_format" in body:
            schema = body["response_format"]["json_schema"]["schema"]
        elif body.get("tools"):
            args = spec.get("json", dummy(body["tools"][0]["function"]["parameters"]))
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
            msg["content"] = "Falešná odpověď."
        return "stop"
