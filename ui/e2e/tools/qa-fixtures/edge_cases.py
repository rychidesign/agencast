"""Edge-case QA data: 40+ steps, parallel with 6 branches, switch with 8 cases, long names and texts, errors."""
import sys
from pathlib import Path

wf = Path(sys.argv[1])
LONG = ("This description is deliberately very long, to show how the card, header and panel handle wrapping, "
        "an ellipsis and a tooltip when someone writes a whole paragraph instead of one sentence. " * 3).strip()
PROMPT = "\n".join(f"Line {i}: " + "Write a paragraph about {{ inputs.topic }} and stick to the brand style. " * 3 for i in range(1, 41))

agent = "ultra-long-agent-with-a-very-long-name-that-fits-nowhere"
(wf / "agents" / f"{agent}.md").write_text(f"""---
name: {agent}
description: {LONG}
model: smart
budget_usd: 0.02
---
{PROMPT}
""")

steps = []
for i in range(1, 31):
    steps.append(f"""  - id: step_{i:02d}
    ask:
      agent: writer
      prompt: "Step {i}: {{{{ inputs.topic }}}} {'and a lot more text that does not fit on the card ' * 3}"
""")
branches = "".join(f"""      branch_{b}:
        - id: p_{b}
          ask:
            agent: writer
            prompt: "Branch {b}"
""" for b in range(1, 7))
steps.append(f"""  - id: in_parallel
    parallel:
{branches}""")
cases = "".join(f"""        "value-{c}":
          - id: s_{c}
            set:
              x: "{c}"
""" for c in range(1, 9))
steps.append(f"""  - id: crossroads
    switch:
      value: inputs.topic
      cases:
{cases}      default:
        - id: s_otherwise
          set:
            x: \'"otherwise"\'
""")
for i in range(31, 41):
    steps.append(f"""  - id: next_{i}
    set:
      value: "{i}"
""")
steps.append("""  - id: invoke
    call:
      scenario: demo
      inputs:
        topic: "{{ inputs.topic }}"
""")
steps.append("""  - id: result
    output:
      text: "{{ steps.step_30.text }}"
""")
u = wf / "scenarios" / "demo.yaml"
u.write_text(u.read_text().replace("\ninputs:", "\ncallable: true\ninputs:", 1))
(wf / "scenarios" / "big.yaml").write_text(f"""version: 1
name: big
description: {LONG}
inputs:
  topic: {{ type: string, default: coffee, description: "{LONG[:160]}" }}
outputs:
  text: {{ type: string }}
steps:
{''.join(steps)}""")

name = "scenario-with-a-really-long-name-that-fits-neither-card-nor-header"
(wf / "scenarios" / f"{name}.yaml").write_text(f"""version: 1
name: {name}
description: {LONG}
inputs:
  topic: {{ type: string, required: true }}
outputs:
  text: {{ type: string }}
steps:
  - id: {"write_very_long_step_id_that_does_not_fit_on_the_card_at_all"}
    ask:
      agent: {agent}
      prompt: "{{{{ inputs.topic }}}}"
  - id: result
    output:
      text: "{{{{ steps.write_very_long_step_id_that_does_not_fit_on_the_card_at_all.text }}}}"
""")
# scenario with validation errors (multi-line message with a caret)
(wf / "scenarios" / "broken.yaml").write_text("""version: 1
name: broken
description: Scenario with validation errors
inputs:
  topic: { type: string, default: coffee }
outputs:
  text: { type: string }
steps:
  - id: write
    ask:
      agent: nobody
      prompt: "{{ steps.missing.text }}"
  - id: result
    output:
      text: "{{ steps.write.text + }}"
""")
