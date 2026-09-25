"""Otázka 1: strukturovaný výstup a nástroj na 3 modelech, s kaskádou.
Použití: python3 q1_structured.py [--reps 5] [--models id1,id2]
Úrovně kaskády: L1 nativní response_format json_schema strict;
L2 nástroj jako obal schématu (vynucené volání submit_post); L3 prompt + validace + 1 oprava.
"""
import argparse, json, os
from or_common import post, median, RESULTS

MODELS = ["anthropic/claude-haiku-4.5", "moonshotai/kimi-k3", "google/gemini-3.5-flash-lite"]
SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["caption", "hashtags", "image_prompt"],
          "properties": {"caption": {"type": "string"},
                         "hashtags": {"type": "array", "items": {"type": "string"}},
                         "image_prompt": {"type": "string"}}}
RF = {"type": "json_schema", "json_schema": {"name": "post", "strict": True, "schema": SCHEMA}}
TASK = "Napiš krátký příspěvek na Instagram (česky) o nové kávě z pražírny Zrno."
TASK_TOOL = TASK + " Nejdřív zavolej nástroj get_brand_guidelines a řiď se jím."
GUIDE = "Tón: přátelský, hravý, tykání. Max 1 emoji. Nepoužívej slovo 'nej'. Vždy 3 hashtagy."
TOOL_GUIDE = {"type": "function", "function": {"name": "get_brand_guidelines",
              "description": "Vrátí pravidla značky pro tvorbu příspěvků.",
              "parameters": {"type": "object", "properties": {}}}}
TOOL_SUBMIT = {"type": "function", "function": {"name": "submit_post",
               "description": "Odešli hotový příspěvek. Zavolej jako poslední krok.", "parameters": SCHEMA}}
KEEP = ("role", "content", "tool_calls") + (("reasoning_details",) if os.environ.get("ECHO_REASONING") else ())
COMMON = {"usage": {"include": True}, "max_tokens": 3000, "temperature": 0}


def validate(v):
    if not isinstance(v, dict): return "není objekt"
    if set(v) != set(SCHEMA["properties"]): return f"klíče {sorted(v)}"
    if not isinstance(v["caption"], str) or not isinstance(v["image_prompt"], str): return "typ string"
    if not isinstance(v["hashtags"], list) or not all(isinstance(h, str) for h in v["hashtags"]): return "hashtags"
    return None


def parse(text):
    try: return json.loads(text), None
    except (TypeError, ValueError) as e: return None, f"neplatný JSON: {str(text)[:80]!r}"


def run_case(model, case, level, extra_hint=""):
    """Vrátí záznam: ok, chyba, latence, cena, surové odpovědi."""
    msgs = [{"role": "user", "content": (TASK_TOOL if case == "tool" else TASK) + extra_hint}]
    calls, raws, cost, lat, tool_called, err, out = 0, [], 0.0, 0.0, False, None, None
    if level == "L1":
        base = {"response_format": RF}; tools = [TOOL_GUIDE] if case == "tool" else None
    elif level == "L2":
        base = {}; tools = ([TOOL_GUIDE] if case == "tool" else []) + [TOOL_SUBMIT]
        msgs[0]["content"] += " Výsledek odevzdej voláním nástroje submit_post."
    else:  # L3
        base = {}; tools = [TOOL_GUIDE] if case == "tool" else None
        msgs[0]["content"] += ' Odpověz POUZE JSON objektem {"caption": str, "hashtags": [str], "image_prompt": str}, bez markdownu.'
    for turn in range(4):
        p = {"model": model, "messages": msgs, **COMMON, **base}
        if tools: p["tools"] = tools
        st, body, l = post("/chat/completions", p, label=f"q1-{model}")
        lat += l; raws.append({"status": st, "body": body})
        if st != 200 or "choices" not in body:
            err = f"HTTP {st}: {json.dumps(body, ensure_ascii=False)[:200]}"; break
        cost += (body.get("usage") or {}).get("cost") or 0
        m = body["choices"][0]["message"]
        msgs.append({k: v for k, v in m.items() if k in KEEP and v is not None})
        tcs = m.get("tool_calls") or []
        if not tcs:
            if level == "L2": err = "L2: model nezavolal submit_post"; break
            out, err = parse(m.get("content"))
            if out is not None: err = validate(out)
            break
        for tc in tcs:
            n = tc["function"]["name"]
            if n == "get_brand_guidelines":
                tool_called = True
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": GUIDE})
            elif n == "submit_post":
                out, err = parse(tc["function"]["arguments"])
                if out is not None: err = validate(out)
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": "ok"})
            else:
                err = f"neznámý nástroj {n}"
        if level == "L2" and out is not None: break
        if err: break
    else:
        err = err or "smyčka bez výsledku"
    if case == "tool" and not tool_called and not err: err = "nástroj nebyl zavolán"
    return {"model": model, "case": case, "level": level, "ok": err is None, "error": err,
            "latency_s": round(lat, 3), "cost": cost, "output": out, "raw": raws}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--models", default=",".join(MODELS)); a = ap.parse_args()
    allrec = []
    for model in a.models.split(","):
        for case in ("schema", "tool"):
            for level in ("L1", "L2", "L3"):
                recs = [run_case(model, case, level) for _ in range(a.reps)]
                allrec += recs
                ok = [r for r in recs if r["ok"]]
                print(f"{model:32} {case:6} {level} {len(ok)}/{a.reps} med {median([r['latency_s'] for r in recs])}s "
                      f"cost {sum(r['cost'] for r in recs):.5f} err {[r['error'] for r in recs if not r['ok']][:2]}", flush=True)
                if len(ok) == a.reps: break  # tato úroveň stačí, kaskáda dál nejde
    json.dump(allrec, open(os.path.join(RESULTS, os.environ.get("Q1_OUT", "q1_structured.json")), "w"), indent=1, ensure_ascii=False)


main()
