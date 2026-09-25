"""Q3: skilly pro API modely — nástroj load_skill(name) + seznam skillů (jméno + description) v system promptu.

3 prompty × 2 modely × N opakování. Relevantní prompt → model má načíst správný skill a řídit se jím
(kontrolní znaky z SKILL.md); nerelevantní prompt → load_skill nevolat.
Použití: python q3_skills.py [--n 2]. Výsledek: results/q3_skills.json.
"""
import sys

import anyio
from mcp.types import CallToolResult

from common import HERE, MODELS, run_agent, save, spent

N = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 2
SKILLS_DIR = HERE / "skills"


def read_skills():
    """name → (description, celý text SKILL.md). Frontmatter jen `klíč: hodnota` (pro spike stačí)."""
    out = {}
    for f in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        text = f.read_text()
        meta = dict(l.split(":", 1) for l in text.split("---")[1].strip().splitlines())
        out[meta["name"].strip()] = (meta["description"].strip(), text)
    return out


SKILLS = read_skills()
LOAD_SKILL = {"type": "function", "function": {
    "name": "load_skill",
    "description": "Načte plný návod (skill) podle jména. Volej, když je skill relevantní pro úkol, ještě před odpovědí.",
    "parameters": {"type": "object", "properties": {"name": {"type": "string", "enum": sorted(SKILLS)}},
                   "required": ["name"]}}}
SYSTEM = ("Jsi asistent marketingu kavárny Lípa. Máš k dispozici skilly — podrobné návody k určitým úkolům. "
          "Když je některý skill relevantní pro zadání, nejdřív ho načti nástrojem load_skill a řiď se jím. "
          "Když relevantní není, odpověz rovnou bez něj.\n\nDostupné skilly:\n"
          + "\n".join(f"- {n}: {d}" for n, (d, _) in SKILLS.items()))

CASES = [
    {"id": "caption", "expect": "ig-caption",
     "prompt": "Napiš caption na Instagram k fotce našeho nového dýňového latté.",
     # obsah captionu podle skillu; zda model přidal obal („Tady je caption…“), měří `clean`
     "follows": lambda t: any(l.strip().startswith("🌿") for l in t.splitlines()) and "Uvidíme se u okna." in t,
     "clean": lambda t: t.strip().startswith("🌿") and t.strip().endswith("Uvidíme se u okna.")},
    {"id": "hashtags", "expect": "hashtag-check",
     "prompt": "Projdi hashtagy k příspěvku: #Kava #latte #follow4follow #brno #podzim #kavárna #coffee",
     "follows": lambda t: "VERDIKT: NEOK" in t},
    {"id": "irrelevant", "expect": None,
     "prompt": "Kolik minut má mléko v páře na 65 °C při 1,5 barech? Odpověz jednou větou, stačí odhad.",
     "follows": lambda t: True},
]


async def dispatch(name, args):
    if name != "load_skill":
        return f"Neznámý nástroj {name}."
    if args.get("name") not in SKILLS:
        return f"Skill {args.get('name')!r} neexistuje. Dostupné: {', '.join(SKILLS)}."
    return CallToolResult.model_validate({"content": [{"type": "text", "text": SKILLS[args["name"]][1]}]})


async def main():
    runs = []
    for model in MODELS:
        for case in CASES:
            for i in range(N):
                log = await run_agent(model, [{"role": "system", "content": SYSTEM},
                                              {"role": "user", "content": case["prompt"]}],
                                      [LOAD_SKILL], dispatch, label=f"q3:{model}", max_turns=4)
                loaded = [__import__("json").loads(c["arguments"]).get("name")
                          for t in log["turns"] for c in t["calls"] if c["name"] == "load_skill"]
                exp = case["expect"]
                log.update(case=case["id"], loaded=loaded,
                           ok_decision=(loaded == [exp]) if exp else not loaded,
                           ok_follows=bool(log["final"]) and case["follows"](log["final"]),
                           clean_output=bool(log["final"]) and case.get("clean", case["follows"])(log["final"]))
                runs.append(log)
                print(model.split("/")[1], case["id"], i, "decision", log["ok_decision"], "follows",
                      log["ok_follows"], "clean", log["clean_output"], loaded, f"{log['cost']:.4f}", log["error"] or "",
                      (log["final"] or "")[:140].replace("\n", " | "), flush=True)
    save("q3_skills.json", {"system_prompt": SYSTEM, "runs": runs, "spent_total_usd": spent()})
    print("spent_total_usd", round(spent(), 4))


if __name__ == "__main__":
    anyio.run(main)
