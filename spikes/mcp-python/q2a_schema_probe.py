"""Q2a: které konstrukce JSON Schema v `tools` snese OpenRouter + model (surově, bez normalizace).

Jeden požadavek na (model, varianta). Úspěch = HTTP 200, model zavolal očekávaný nástroj a
argumenty projdou validací proti původnímu schématu (jsonschema). Výsledek: results/q2a_schema_probe.json.
Použití: python q2a_schema_probe.py [--normalize] [--only varianta1,varianta2]
"""
import json, re, sys

import anyio
import jsonschema
from mcp import Client

from common import MODELS, SANDBOX, chat, everything_params, fs_params, mcp_tool_to_openai, save, spent

NORMALIZE = "--normalize" in sys.argv
ONLY = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None

# Syntetická schémata s konstrukcemi, které se v MCP serverech vyskytují (Pydantic/Zod výstupy).
S = "http://json-schema.org/draft-07/schema#"
SYNTH = {
    "anyOf_null": {"type": "object", "properties": {"title": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
                   "required": ["title"]},
    "type_array_null": {"type": "object", "properties": {"title": {"type": ["string", "null"]}}, "required": ["title"]},
    "ref_defs": {"type": "object", "$defs": {"Tag": {"type": "object", "properties": {"label": {"type": "string"}},
                                                     "required": ["label"]}},
                 "properties": {"tag": {"$ref": "#/$defs/Tag"}}, "required": ["tag"]},
    "additionalProperties_false_nested": {
        "type": "object", "additionalProperties": False,
        "properties": {"post": {"type": "object", "additionalProperties": False,
                                "properties": {"title": {"type": "string"}, "likes": {"type": "integer"}},
                                "required": ["title", "likes"]}},
        "required": ["post"]},
    "additionalProperties_schema_map": {"type": "object", "properties": {
        "labels": {"type": "object", "additionalProperties": {"type": "string"}}}, "required": ["labels"]},
    "oneOf_allOf": {"type": "object", "properties": {
        "value": {"oneOf": [{"type": "string", "maxLength": 20}, {"type": "integer"}]},
        "meta": {"allOf": [{"type": "object", "properties": {"a": {"type": "string"}}}]}}, "required": ["value"]},
    "format_pattern": {"type": "object", "properties": {
        "url": {"type": "string", "format": "uri"}, "when": {"type": "string", "format": "date-time"},
        "code": {"type": "string", "pattern": "^[A-Z]{3}$"}}, "required": ["url", "when", "code"]},
    "const_enum_int_default": {"type": "object", "properties": {
        "kind": {"const": "post"}, "level": {"type": "integer", "enum": [1, 2, 3], "default": 2}},
        "required": ["kind", "level"]},
    "const_only": {"type": "object", "properties": {"kind": {"const": "post"}, "title": {"type": "string"}},
                   "required": ["kind", "title"]},
    "enum_int_only": {"type": "object", "properties": {"level": {"type": "integer", "enum": [1, 2, 3]}},
                      "required": ["level"]},
    "no_properties_key": {"type": "object"},
    "schema_draft07_empty": {"$schema": S, "type": "object", "properties": {}},
    "schema_2020_12": {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
                       "properties": {"title": {"type": "string"}}, "required": ["title"]},
}
NAMES = {  # jméno funkce: MCP povoluje víc znaků/délky než API modelů
    "name_dot": "fs.list_directory",
    "name_double_underscore": "fs__list_directory",
    "name_70_chars": "fs__" + "x" * 66,
}


def probe(model, label, tools, expect, prompt, schema_by_name):
    status, body, lat = chat({"model": model, "max_tokens": 400, "tools": tools,
                              "messages": [{"role": "user", "content": prompt}]}, label=f"q2a:{model}")
    row = {"model": model, "variant": label, "status": status, "latency_s": round(lat, 2)}
    if status != 200 or "choices" not in body:
        row["error"] = body.get("error", body)
        return row
    ch = body["choices"][0]
    calls = ch["message"].get("tool_calls") or []
    row.update(finish_reason=ch.get("finish_reason"), cost=body.get("usage", {}).get("cost"),
               calls=[{"name": c["function"]["name"], "arguments": c["function"]["arguments"]} for c in calls],
               content=(ch["message"].get("content") or "")[:200])
    ok, why = False, "nezavolal nástroj"
    for c in calls:
        if c["function"]["name"] != expect:
            why = f"zavolal {c['function']['name']}"
            continue
        try:
            args = json.loads(c["function"]["arguments"] or "{}")
            jsonschema.validate(args, schema_by_name[expect])
            ok, why = True, ""
        except Exception as e:
            why = f"argumenty neprošly: {str(e)[:160]}"
    row.update(ok=ok, why=why)
    return row


async def main():
    async with Client(fs_params()) as fs, Client(everything_params()) as ev:
        fs_tools = (await fs.list_tools()).tools
        ev_tools = (await ev.list_tools()).tools
    cases = []
    real = {t.name: t.input_schema for t in fs_tools + ev_tools}
    cases.append(("real_filesystem_14_tools", [mcp_tool_to_openai(t, normalize=NORMALIZE) for t in fs_tools],
                  "list_directory", f"Vypiš obsah adresáře {SANDBOX}.", real))
    cases.append(("real_everything_13_tools", [mcp_tool_to_openai(t, normalize=NORMALIZE) for t in ev_tools],
                  "get-sum", "Sečti čísla 2 a 3 pomocí nástroje.", real))
    for key, sch in SYNTH.items():
        tool = {"name": "submit", "description": "Odešle záznam.", "inputSchema": sch}
        cases.append((f"synth_{key}", [mcp_tool_to_openai(tool, normalize=NORMALIZE)], "submit",
                      "Zavolej nástroj submit s libovolnými smysluplnými platnými hodnotami. Neptej se.",
                      {"submit": sch}))
    ld = next(t for t in fs_tools if t.name == "list_directory")
    for key, nm in NAMES.items():
        if NORMALIZE:
            nm = re.sub(r"[^a-zA-Z0-9_-]", "_", nm)[:64]
        cases.append((key, [mcp_tool_to_openai(ld, name=nm, normalize=NORMALIZE)], nm,
                      f"Vypiš obsah adresáře {SANDBOX}.", {nm: ld.input_schema}))

    if ONLY:
        cases = [c for c in cases if c[0] in ONLY]
    rows = []
    for model in MODELS:
        for label, tools, expect, prompt, sch in cases:
            r = probe(model, label, tools, expect, prompt, sch)
            rows.append(r)
            print(model.split("/")[1], label, r["status"], r.get("ok"), r.get("why") or "",
                  str(r.get("error", ""))[:200], flush=True)
    suffix = ("_normalized" if NORMALIZE else "") + ("_only" if ONLY else "")
    save(f"q2a_schema_probe{suffix}.json",
         {"normalize": NORMALIZE, "rows": rows, "spent_total_usd": spent()})
    print("spent_total_usd", round(spent(), 4))


if __name__ == "__main__":
    anyio.run(main)
