"""Otázka 2: Jev přes POST /api/v1/systemone (model jev-1.13): noul + choice + score v jednom požadavku.
Použití: python3 q2_jev.py [--reps 5]. Plus jeden záměrně chybný požadavek (chybí questions)."""
import argparse, json, os
from or_common import post, median, RESULTS

STATE = "Dobrý den, objednávka měla dorazit včera. Potřebuji ji do pátku. Kde je? Je to už potřetí, co píšu!"
QUESTIONS = {
    "department": {"type": "choice",
                   "instructions": "Které oddělení má řešit hlavní požadavek zákaznické zprávy? Při nedostatku kontextu zvol other.",
                   "criteria": {"billing": "Platby, faktury a vrácení peněz.",
                                "technical": "Technické chyby aplikace, přihlášení a integrace.",
                                "delivery": "Doručení, sledování zásilky a změna doručovací adresy.",
                                "sales": "Dotazy na produkty, ceny a dostupnost před nákupem.",
                                "other": "Ostatní požadavky nebo chybějící kontext."}},
    "dissatisfaction": {"type": "score",
                        "instructions": "Jakou míru nespokojenosti zákazník vyjadřuje? Hodnoť tón zprávy.",
                        "criteria": ["Klidný, neutrální nebo spokojený tón.", "Zřetelná nespokojenost, ale zdvořilý tón.",
                                     "Silný hněv, urážky nebo velmi ostrá stížnost."]},
    "deadline": {"type": "noul",
                 "instructions": "Požaduje zákazník vyřízení do konkrétního termínu? Ano zahrnuje dnes, zítra nebo do pátku."},
}
a = argparse.ArgumentParser(); a.add_argument("--reps", type=int, default=5); a = a.parse_args()
recs = []
for i in range(a.reps):
    st, body, lat = post("/systemone", {"model": "jev-1.13", "state": STATE, "questions": QUESTIONS}, label="q2-jev")
    recs.append({"status": st, "latency_s": round(lat, 3), "body": body})
    print(i, st, round(lat, 3), json.dumps(body, ensure_ascii=False)[:300], flush=True)
st, body, lat = post("/systemone", {"model": "jev-1.13", "state": STATE}, label="q2-jev")
if isinstance(body, dict) and "user_id" in body: body["user_id"] = "<redacted>"  # identifikátor účtu
err = {"status": st, "latency_s": round(lat, 3), "body": body}
print("CHYBA", st, json.dumps(body, ensure_ascii=False)[:400])
ok = [r for r in recs if r["status"] == 200]
costs = [r["body"].get("usage", {}).get("cost") for r in ok]
print(f"ok {len(ok)}/{a.reps} med {median([r['latency_s'] for r in recs])}s cost {sum(c or 0 for c in costs):.6f}")
json.dump({"ok_requests": recs, "error_request_missing_questions": err},
          open(os.path.join(RESULTS, "q2_jev.json"), "w"), indent=1, ensure_ascii=False)
