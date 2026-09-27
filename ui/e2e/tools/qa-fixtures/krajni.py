"""Krajní data pro QA: 40+ kroků, parallel se 6 větvemi, switch s 8 případy, dlouhá jména a texty, chyby."""
import sys
from pathlib import Path

wf = Path(sys.argv[1])
LONG = ("Tenhle popis je schválně hodně dlouhý, aby se ukázalo, jak karta, hlavička a panel zvládnou zalomení, "
        "výpustku a tooltip, když někdo napíše celý odstavec místo jedné věty. " * 3).strip()
PROMPT = "\n".join(f"Řádek {i}: " + "Napiš odstavec o tématu {{ inputs.tema }} a drž se stylu značky. " * 3 for i in range(1, 41))

agent = "ultra-dlouhy-agent-s-velmi-dlouhym-jmenem-ktery-se-nevejde-nikam"
(wf / "agents" / f"{agent}.md").write_text(f"""---
name: {agent}
description: {LONG}
model: chytry
budget_usd: 0.02
---
{PROMPT}
""")

steps = []
for i in range(1, 31):
    steps.append(f"""  - id: krok_{i:02d}
    ask:
      agent: pisatel
      prompt: "Krok {i}: {{{{ inputs.tema }}}} {'a ještě hodně dlouhého textu, který se na kartu nevejde ' * 3}"
""")
branches = "".join(f"""      vetev_{b}:
        - id: p_{b}
          ask:
            agent: pisatel
            prompt: "Větev {b}"
""" for b in range(1, 7))
steps.append(f"""  - id: paralelne
    parallel:
{branches}""")
cases = "".join(f"""        "hodnota-{c}":
          - id: s_{c}
            set:
              x: "{c}"
""" for c in range(1, 9))
steps.append(f"""  - id: rozcesti
    switch:
      value: inputs.tema
      cases:
{cases}      default:
        - id: s_jinak
          set:
            x: \'"jinak"\'
""")
for i in range(31, 41):
    steps.append(f"""  - id: dalsi_{i}
    set:
      hodnota: "{i}"
""")
steps.append("""  - id: zavolej
    call:
      scenario: ukazka
      inputs:
        tema: "{{ inputs.tema }}"
""")
steps.append("""  - id: vystup
    output:
      text: "{{ steps.krok_30.text }}"
""")
u = wf / "scenarios" / "ukazka.yaml"
u.write_text(u.read_text().replace("\ninputs:", "\ncallable: true\ninputs:", 1))
(wf / "scenarios" / "velky.yaml").write_text(f"""version: 1
name: velky
description: {LONG}
inputs:
  tema: {{ type: string, default: káva, description: "{LONG[:160]}" }}
outputs:
  text: {{ type: string }}
steps:
{''.join(steps)}""")

name = "scenar-s-opravdu-hodne-dlouhym-nazvem-ktery-se-do-karty-ani-hlavicky-nevejde"
(wf / "scenarios" / f"{name}.yaml").write_text(f"""version: 1
name: {name}
description: {LONG}
inputs:
  tema: {{ type: string, required: true }}
outputs:
  text: {{ type: string }}
steps:
  - id: {"napis_velmi_dlouhe_id_kroku_ktere_se_nevejde_do_karty_vubec"}
    ask:
      agent: {agent}
      prompt: "{{{{ inputs.tema }}}}"
  - id: vystup
    output:
      text: "{{{{ steps.napis_velmi_dlouhe_id_kroku_ktere_se_nevejde_do_karty_vubec.text }}}}"
""")
# scénář s chybami validace (víceřádková hláška se stříškou)
(wf / "scenarios" / "rozbity.yaml").write_text("""version: 1
name: rozbity
description: Scénář s chybami validace
inputs:
  tema: { type: string, default: káva }
outputs:
  text: { type: string }
steps:
  - id: napis
    ask:
      agent: nikdo
      prompt: "{{ steps.nic.text }}"
  - id: vystup
    output:
      text: "{{ steps.napis.text + }}"
""")
