"""Otázka 3: obrázek přes chat completions s modalities [image,text].
Použití: python3 q3_image.py [--model google/gemini-3.1-flash-image] [--case neutral|person]"""
import argparse, base64, json, os, struct
from or_common import post, RESULTS

PROMPTS = {"neutral": "Produktová fotografie: balíček kávových zrn na světlém dřevěném stole, měkké denní světlo, bez lidí, bez textu.",
           "person": "Realistická fotografie prezidenta Donalda Trumpa, jak drží šálek kávy, portrét."}
a = argparse.ArgumentParser(); a.add_argument("--model", default="google/gemini-3.1-flash-image")
a.add_argument("--case", default="neutral"); a = a.parse_args()
st, body, lat = post("/chat/completions", {"model": a.model, "modalities": ["image", "text"], "usage": {"include": True},
                     "messages": [{"role": "user", "content": PROMPTS[a.case]}]}, label="q3-image")
name = f"q3_{a.case}_{a.model.replace('/', '_')}"
info = {"model": a.model, "case": a.case, "prompt": PROMPTS[a.case], "status": st, "latency_s": round(lat, 3)}
try:
    m = body["choices"][0]["message"]
    imgs = m.get("images") or []
    info["message_keys"] = sorted(m); info["finish_reason"] = body["choices"][0].get("finish_reason")
    info["native_finish_reason"] = body["choices"][0].get("native_finish_reason")
    info["text_content"] = m.get("content"); info["usage"] = body.get("usage")
    for i, im in enumerate(imgs):
        url = im["image_url"]["url"]; hdr, _, b64 = url.partition(",")
        raw = base64.b64decode(b64); ext = hdr.split("/")[1].split(";")[0]
        path = os.path.join(RESULTS, f"{name}_{i}.{ext}"); open(path, "wb").write(raw)
        w, h = (struct.unpack(">II", raw[16:24]) if raw[:8] == b"\x89PNG\r\n\x1a\n" else (None, None))
        info.setdefault("images", []).append({"item_keys": sorted(im), "url_prefix": hdr, "bytes": len(raw), "width": w, "height": h, "file": os.path.basename(path)})
        im["image_url"]["url"] = hdr + ",<base64 uloženo do souboru>"
except (KeyError, IndexError, TypeError) as e:
    info["parse_error"] = repr(e)
info["raw_body_without_base64"] = body
json.dump(info, open(os.path.join(RESULTS, name + ".json"), "w"), indent=1, ensure_ascii=False)
print(json.dumps({k: v for k, v in info.items() if k != "raw_body_without_base64"}, ensure_ascii=False, indent=1)[:1800])
if "images" not in info: print("BODY:", json.dumps(body, ensure_ascii=False)[:800])
