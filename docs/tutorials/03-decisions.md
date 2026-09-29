# Part 3 — Decisions

Run the commands from `examples/tutorial` (from the clone root: `cd examples/tutorial`).

**Time:** about 20 minutes · **Spend:** one live run for ~0.0007 USD
**You will learn to:** have Jev assess a text (`noul`, `choice`, `score`),
skip a step based on the result (`when`), end a run on purpose (`fail`),
branch (`switch`) and write expressions the framework understands.

Prerequisite: parts 1 and 2 (the agents `tutorial-namer`,
`tutorial-slogan-writer`, the `agencast` shortcut).

---

## Step 1 — what Jev is

Jev is a cheap and fast "referee" (~0.00002 USD, ~0.5 s per call).
It receives a text (`state`) and questions and returns a value for each. The
question types:

| Type | Returns | Example value | When |
|---|---|---|---|
| `noul` | a number 0–1 = "how much yes" | `0.85` | a yes/no question |
| `choice` | the key of one of the options in `criteria` | `"playful"` | a choice among named options |
| `score` | a number on a scale 0…n (may be in between) | `0.64` | a scale; `criteria` = descriptions of the levels starting from 0 |

**Jev never decides "yes" or "no" by itself.** It returns a number and you write
the threshold (`< 0.5`), always explicitly in the scenario. There is no default
threshold.

---

## Step 2 — the scenario

Create `workflows/scenarios/tutorial-03-decisions.yaml`:

```yaml
version: 1
name: tutorial-03-decisions
description: Comes up with a name, has Jev assess it and writes a slogan based on its tone (tutorial, part 3)

inputs:
  product:
    type: string
    required: true
    description: The product we are naming

outputs:
  name:
    type: string
  tone:
    type: string
    description: Tone of the name according to Jev (playful / serious)
  slogan:
    type: string
  memorability:
    type: integer
    description: How memorable the name is, in percent

steps:
  # 1. One name.
  - id: propose
    ask:
      agent: tutorial-namer
      prompt: "Come up with one name for this product: {{ inputs.product }}."
      schema:
        name: string

  # 2. Jev assesses the name: yes/no (noul), a choice (choice) and a scale (score).
  - id: check
    jev:
      state: "Product: {{ inputs.product }}. Proposed name: {{ steps.propose.name }}"
      questions:
        memorable:
          type: noul
          instructions: Is the name easy to remember and easy to pronounce?
        tone:
          type: choice
          instructions: What tone does the proposed name have?
          criteria:
            playful: Playful, witty, relaxed
            serious: Serious, elegant, matter-of-fact
        originality:
          type: score
          instructions: How original is the proposed name?
          criteria:
            - A common, ordinary name
            - An interesting name
            - An exceptionally original name

  # 3. The threshold is always explicit in the scenario.
  - id: stop
    when: steps.check.memorable < 0.5
    fail: "The name {{ steps.propose.name }} is not memorable (memorable = {{ steps.check.memorable }})"

  # 4. A different slogan depending on the tone.
  - id: by_tone
    switch:
      value: steps.check.tone
      cases:
        playful:
          - id: slogan_playful
            default: { slogan: "" }
            ask:
              agent: tutorial-slogan-writer
              prompt: "Write a playful, witty slogan for the product {{ inputs.product }} named {{ steps.propose.name }}."
              schema:
                slogan: string
        serious:
          - id: slogan_serious
            default: { slogan: "" }
            ask:
              agent: tutorial-slogan-writer
              prompt: "Write a serious, elegant slogan for the product {{ inputs.product }} named {{ steps.propose.name }}."
              schema:
                slogan: string
      default:
        - id: unknown_tone
          fail: "Unknown tone: {{ steps.check.tone }}"

  # 5. Only one branch ran; the other one has the output from default (empty text).
  - id: result
    set:
      slogan: steps.slogan_playful.slogan + steps.slogan_serious.slogan
      percent: round(steps.check.memorable * 100)

  - id: out
    output:
      name: "{{ steps.propose.name }}"
      tone: "{{ steps.check.tone }}"
      slogan: "{{ steps.result.slogan }}"
      memorability: "{{ steps.result.percent }}"
```

Go through the new things:

### `jev`

- `state` — what Jev assesses (a template). Give it the context too (the
  product), not just the bare name.
- `questions` — key = the name of the output (`steps.check.memorable`).
  Every question has a `type` and `instructions`; `choice` and `score` also
  have `criteria`.
- `steps.check.details.<question>` — what else Jev returned
  (probabilities). You will see it in step 4.

### `when` + `fail`

`when` is an **expression** (without `{{ }}`) that must give `true`/`false`.
When it gives `false`, the step is skipped. `fail` ends the run with an error of
class `fail` and your message. Together: "when the name is not memorable, stop".

### `switch`

- `value` — an expression that gives a **text** (here the answer of a `choice`).
- `cases` — for each value, a list of steps.
- `default` — **required**: what to do when nothing matches. A conscious
  "nothing" is `default: []`. Here we would rather end with an error.

For numeric thresholds (`< 0.5`) use `when`, not `switch`.

### Why steps in branches have a `default`

The step `result` reads `steps.slogan_playful` **and** `steps.slogan_serious`,
but only one of them runs. The output of a step that did not run is its
`default` — here an empty text. `slogan_playful + slogan_serious` thus always
gives the one slogan that was written. Without `default`, `validate` would
reject the scenario (step 6).

This is a general pattern: **different results from different branches are
merged in a `set` before `output`** (there may be only one `output`, as the last
step).

---

## Step 3 — a fixture for Jev

`fake/tutorial-03-decisions.yaml`:

```yaml
# Scripted responses for tutorial-03-decisions.
# Jev gets answers: {question: value}; for choice the value is a key from criteria.
propose:
  - json:
      name: "Oatsy"
check:
  - answers:
      memorable: 0.835
      tone: playful
      originality: 1.4
slogan_playful:
  - json:
      slogan: "Oatsy — ice cream that grows in the field"
```

For `slogan_serious` you do not need a response — with `tone: playful` it is not
called.

```bash
agencast validate workflows/scenarios/tutorial-03-decisions.yaml
agencast run workflows/scenarios/tutorial-03-decisions.yaml -i product="vegan oat milk ice cream" --fake fake/tutorial-03-decisions.yaml
```

```
valid: tutorial-03-decisions (9 steps)
run 20260925-151444-tutorial-03-decisions-f56a: succeeded · 0.0 s · 0.0003 USD
run record: …/runs/20260925-151444-tutorial-03-decisions-f56a/summary.md
report: file:///…/outputs/20260925-151444-tutorial-03-decisions-f56a-9770c2b2304c92c8902241bc65d68c77/report.html
```

`9 steps` — the steps inside the `switch` branches are counted too. The steps
table in `summary.md`:

```
| # | Step | Type | Status | Time | Cost | Note |
|---|---|---|---|---|---|---|
| 1 | propose | ask | ✓ | 0.0 s | 0.0001 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | check | jev | ✓ | 0.0 s | 0.0001 | memorable = 0.83, tone = playful, originality = 1.40 |
| 3 | stop | fail | skipped |  |  | when: steps.check.memorable < 0.5 → false |
| 4 | by_tone | switch | ✓ | 0.0 s | 0.0001 | branch playful |
| 5 | slogan_playful | ask | ✓ | 0.0 s | 0.0001 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 6 | slogan_serious | ask | skipped |  |  | switch: by_tone = "playful" |
| 7 | unknown_tone | fail | skipped |  |  | switch: by_tone = "playful" |
| 8 | result | set | ✓ | 0.0 s | 0 |  |
| 9 | out | output | ✓ | 0.0 s | 0 |  |
| | Total | | | 0.0 s | 0.0003 |  |

## Warnings
none

## Output
- name: “Oatsy”
- tone: “playful”
- slogan: “Oatsy — ice cream that grows in the field”
- memorability: 84
```

Note:

- **Every skipped step has a reason** — `when: … → false` or
  `switch: by_tone = "playful"`. Nothing happens silently.
- `summary.md` shows numbers to 2 decimal places (`0.83`); the exact value
  (`0.835`) is in `steps/02-check/output.json`. That is why
  `round(0.835 * 100)` = `84`.

### The path to `fail`

A fixture does not have to list all the questions — the fake provider fills in
the missing ones (`noul` 0.5, `choice` the first option, `score` 0).
`/tmp/unmemorable.yaml`:

```yaml
propose:
  - json:
      name: "Xyzqwrt Ovsprl"
check:
  - answers:
      memorable: 0.12
```

```bash
agencast run workflows/scenarios/tutorial-03-decisions.yaml -i product="vegan oat milk ice cream" --fake /tmp/unmemorable.yaml
```

```
fail in step stop: The name Xyzqwrt Ovsprl is not memorable (memorable = 0.12)
run 20260925-151455-tutorial-03-decisions-967b: failed · 0.0 s · 0.0002 USD
run record: …/runs/20260925-151455-tutorial-03-decisions-967b/summary.md
report: file:///…/outputs/20260925-151455-tutorial-03-decisions-967b-6b023b2b60bcf6f6b9befebcb7402197/report.html
```

And this is exactly what n8n would receive (the file `callback.json` in the run
folder):

```
{
  "run_id": "20260925-151455-tutorial-03-decisions-967b",
  "scenario": "tutorial-03-decisions",
  "request_key": null,
  "status": "failed",
  "outputs": null,
  "error": {
    "class": "fail",
    "step": "stop",
    "message": "The name Xyzqwrt Ovsprl is not memorable (memorable = 0.12)"
  },
  "warnings": [],
  "cost_usd": 0.0002,
  "duration_s": 0.002,
  "report_url": "file:///…/outputs/20260925-151455-tutorial-03-decisions-967b-6b023b2b60bcf6f6b9befebcb7402197/report.html",
  "sent_at": "2026-09-25T15:14:55.963Z"
}
```

The class `fail` says "the scenario ended on purpose", not "something broke". In
n8n you use it to tell "the text did not pass the check" from a malfunction.

---

## Step 4 — a live run

```bash
agencast run workflows/scenarios/tutorial-03-decisions.yaml -i product="vegan oat milk ice cream"
```

```
run 20260925-151536-tutorial-03-decisions-b547: succeeded · 5.9 s · 0.0007 USD
run record: …/runs/20260925-151536-tutorial-03-decisions-b547/summary.md
report: file:///…/outputs/20260925-151536-tutorial-03-decisions-b547-ce225553b8f799173e5f6450fe257c0a/report.html
```

The model texts below are illustrative; the times, costs and Jev's numbers are
from the real run:

```
| 1 | propose | ask | ✓ | 3.6 s | 0.0003 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | check | jev | ✓ | 0.5 s | 0.00002 | memorable = 0.85, tone = playful, originality = 0.64 |
| 3 | stop | fail | skipped |  |  | when: steps.check.memorable < 0.5 → false |
| 4 | by_tone | switch | ✓ | 1.8 s | 0.0004 | branch playful |
| 5 | slogan_playful | ask | ✓ | 1.8 s | 0.0004 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 6 | slogan_serious | ask | skipped |  |  | switch: by_tone = "playful" |
| 7 | unknown_tone | fail | skipped |  |  | switch: by_tone = "playful" |
| 8 | result | set | ✓ | 0.0 s | 0 |  |
| 9 | out | output | ✓ | 0.0 s | 0 |  |
| | Total | | | 5.9 s | 0.0007 |  |
…
## Output
- name: “Oatopia”
- tone: “playful”
- slogan: “Oatopia - plant-based silkiness that melts hearts”
- memorability: 85
```

Jev cost 0.00002 USD (the table shows the whole cost). What it really
returned:

```bash
cat runs/20260925-151536-tutorial-03-decisions-b547/steps/02-check/output.json
```

```
{
  "memorable": 0.85,
  "tone": "playful",
  "originality": 0.64,
  "details": {
    "memorable": {},
    "tone": {
      "probabilities": {
        "playful": 0.66,
        "serious": 0.34
      },
      "confidence": 0.31
    },
    "originality": {
      "legend": {
        "0": "A common, ordinary name",
        "1": "An interesting name",
        "2": "An exceptionally original name"
      },
      "probabilities": {
        "0": 0.37,
        "1": 0.62,
        "2": 0.01
      },
      "confidence": 0.43
    }
  }
}
```

- `tone` = `"playful"`, but only with a probability of 0.66. If you want to be
  sure, you can also read `steps.check.details.tone.probabilities.playful` in
  `when`.
- `originality` = `0.64` — the scale is not an integer; it is a weighted
  average (0.37 × 0 + 0.62 × 1 + 0.01 × 2). So write the threshold on a `score`
  as `< 0.5`, not `== 0`.

---

## Step 5 — expression rules

Expressions (`when`, `switch.value`, `set`) look like Python but are stricter.
The fastest way to understand them is the **expression playground** — a scenario
without a model that costs nothing. `workflows/scenarios/tutorial-03-expressions.yaml`:

```yaml
version: 1
name: tutorial-03-expressions
description: Expression playground — only a set step, no model, costs nothing (tutorial, part 3)

inputs:
  language:
    type: string
    default: en
  divisor:
    type: number
    default: 2

outputs:
  results:
    type: object
    description: All computed values

steps:
  - id: examples
    set:
      # Rounding: a half always goes away from zero (unlike Python).
      round_2_5: round(2.5)
      round_minus_2_5: round(-2.5)
      round_0_125_to_2: round(0.125, 2)
      # Division always gives a decimal number.
      seven_div_two: 7 / 2
      four_div_two: 4 / 2
      div_by_input: 10 / inputs.divisor
      # Conversions must be explicit.
      text_plus_number: '"version " + str(2)'
      text_to_number: float("0.7") + 0.1
      and_rounded: round(float("0.7") + 0.1, 2)
      # in: an item in a list, a substring in a text.
      english_or_french: inputs.language in ["en", "fr"]
      contains_oat: '"oat" in "oat milk"'
      # null can be compared with anything.
      language_given: inputs.language != null
      # Logic only on true/false.
      both_conditions: len(inputs.language) == 2 and not (inputs.divisor < 0)

  - id: out
    output:
      results: "{{ steps.examples }}"
```

```bash
agencast run workflows/scenarios/tutorial-03-expressions.yaml --fake
cat runs/20260925-151532-tutorial-03-expressions-6194/steps/01-examples/output.json
```

```
run 20260925-151532-tutorial-03-expressions-6194: succeeded · 0.0 s · 0 USD
run record: …/runs/20260925-151532-tutorial-03-expressions-6194/summary.md
report: file:///…/outputs/20260925-151532-tutorial-03-expressions-6194-4eee9a9a2c2a427a751c1d50add3dcf6/report.html
{
  "round_2_5": 3,
  "round_minus_2_5": -3,
  "round_0_125_to_2": 0.13,
  "seven_div_two": 3.5,
  "four_div_two": 2.0,
  "div_by_input": 5.0,
  "text_plus_number": "version 2",
  "text_to_number": 0.7999999999999999,
  "and_rounded": 0.8,
  "english_or_french": true,
  "contains_oat": true,
  "language_given": true,
  "both_conditions": true
}
```

The rules that follow from it:

1. **`round` rounds "the school way"** — a half goes away from zero:
   `round(2.5)` = `3`, `round(-2.5)` = `-3`. (Python would give `2`.) `round(x)`
   without a number of places gives an integer.
2. **`/` always gives a decimal number** (`4 / 2` = `2.0`). Division by zero is
   an error.
3. **Decimal numbers are not exact** (`0.7 + 0.1` = `0.7999999999999999`).
   For output meant for humans, use `round(…, 2)`.
4. **Types do not mix.** Text + number does not work, convert explicitly:
   `str()`, `float()`, `int()`.
5. **A text as a value in `set` needs two sets of quotes:** the outer one for
   YAML, the inner one for the expression — `'"version " + str(2)'`. The same
   applies to every expression that starts with a quote, `[` or `{`.
6. **The literals are `true`, `false`, `null`** (as in YAML), not
   `True`/`None`.
7. **The dot reads a key, nothing else** — `steps.check.tone`, never a method.

Try `divisor=0`:

```bash
agencast run workflows/scenarios/tutorial-03-expressions.yaml --fake -i divisor=0
```

```
expression in step examples: set.div_by_input: division by zero
  10 / inputs.divisor
       ^
run 20260925-151526-tutorial-03-expressions-9181: failed · 0.0 s · 0 USD
run record: …/runs/20260925-151526-tutorial-03-expressions-9181/summary.md
report: file:///…/outputs/20260925-151526-tutorial-03-expressions-9181-af1de3848c106e5d98d39637cc6d1bbe/report.html
```

`validate` does not know the input value in advance, so the error came only at
run time (class `expression`).

---

## Step 6 — real error messages

All of these messages come from `validate`, **before the run**. I tried each of
them by replacing the `when:` line in the step `stop` (and then put it back).

**Comparing a number with a text:** `when: steps.check.memorable < "0.5"`

```
config: tutorial-03-decisions.yaml: step "stop", when: comparing number with string — convert the type explicitly (float(), str())
  steps.check.memorable < "0.5"
                          ^
```

Likewise `steps.check.tone == 1` → `comparing string with number`.

**`when` without a comparison:** `when: steps.check.memorable`

```
config: tutorial-03-decisions.yaml: step "stop", when: expression must return true/false, got number
  steps.check.memorable
```

In Python `0.85` would be "truthy". Not here: write what you mean (`> 0.5`).

**`and` with a text:** `when: steps.propose.name and steps.check.memorable < 0.5`

```
config: tutorial-03-decisions.yaml: step "stop", when: 'and' requires true/false, got string — compare explicitly (e.g. len(x) > 0)
  steps.propose.name and steps.check.memorable < 0.5
  ^
```

**Pythonic `True`:** `… and True`

```
config: tutorial-03-decisions.yaml: step "stop", when: unknown name 'True' — literals are written as true, false, null
  steps.check.memorable < 0.5 and True
                                  ^
```

**A method:** `when: steps.propose.name.lower() == "x"`

```
config: tutorial-03-decisions.yaml: step "stop", when: method calls are not allowed
  steps.propose.name.lower() == "x"
  ^
```

**A conditional expression:** `… if true else false`

```
config: tutorial-03-decisions.yaml: step "stop", when: conditional 'x if c else y' is not allowed
  steps.check.memorable < 0.5 if true else false
  ^
```

**A typo in a key:** `steps.check.detail.tone…` (instead of `details`)

```
config: tutorial-03-decisions.yaml: step "stop", when: 'steps.check' has no key 'detail' (available: memorable, tone, originality, details)
  steps.check.detail.tone.probabilities.playful < 0.5
              ^
```

**A template in an expression:** `when: '{{ steps.check.memorable }} < 0.5'`

```
config: tutorial-03-decisions.yaml: step "stop", when: template {{ }} is not allowed here — allowed only in prompt, jev.state, jev.questions (instructions, criteria), fail, output values, call.inputs and dedupe_key
  {{ steps.check.memorable }} < 0.5
  ^
```

Without the quotes (`when: {{ … }} < 0.5`) it is even a YAML error — YAML reads
a `{` at the start of a value as a map:

```
config: tutorial-03-decisions.yaml, line 56: cannot read YAML — a value containing {, [, ': ' or ' #' must be quoted (scenario.md §5 'YAML pitfalls')
  expected <block end>, but found '<scalar>'
```

**`switch` without `default`:**

```
config: tutorial-03-decisions.yaml: step 'by_tone': switch: missing required field 'default'
```

**A case that Jev never returns** (`seriuos:` instead of `serious:`):

```
config: tutorial-03-decisions.yaml: step "by_tone", switch.cases: seriuos is not among the criteria choices for question 'tone' (playful, serious)
```

**A step in a branch without `default`** (delete `default:` of `slogan_playful`):

```
config: tutorial-03-decisions.yaml: step "result", set.slogan: step 'slogan_playful' may not run (is in a switch branch 'by_tone') and has no default — add a default with all output fields (§5.4)
  steps.slogan_playful.slogan + steps.slogan_serious.slogan
        ^
```

---

## What you have learned

- `jev`: `noul` (0–1), `choice` (a key), `score` (0…n, also in between). You
  always write the threshold yourself.
- `when` = an expression that gives `true`/`false`; `false` → the step is
  skipped with a reason.
- `fail` = a deliberate end, class `fail`.
- `switch` = branches by text, `default` required; steps in branches that you
  read later need a `default`.
- Expressions: types do not mix, `and/or/not` only on `true/false`,
  `true/false/null` in lowercase, `round` the school way.

---

## Exercise

You do not want a name that Jev rates as ordinary (`originality` below 0.5).
Add a step that ends the run in that case with a message that contains the name
and the value. Save it as `workflows/scenarios/tutorial-03-exercise.yaml` with a
fixture that lets the run pass. Then verify with a fake run that a name with
`originality: 0.2` stops the run.

<details>
<summary>Solution</summary>

The difference against `tutorial-03-decisions.yaml`:

```bash
diff workflows/scenarios/tutorial-03-decisions.yaml workflows/scenarios/tutorial-03-exercise.yaml
```

```
2,3c2,3
< name: tutorial-03-decisions
< description: Comes up with a name, has Jev assess it and writes a slogan based on its tone (tutorial, part 3)
---
> name: tutorial-03-exercise
> description: Comes up with a name, has Jev assess it and writes a slogan based on its tone (tutorial, part 3 — exercise solution)
57a58,62
> 
>   # 3b. We do not want a name that is too ordinary either. Score 0 = common, 1 = interesting, 2 = exceptional.
>   - id: stop_originality
>     when: steps.check.originality < 0.5
>     fail: "The name {{ steps.propose.name }} is too ordinary (originality = {{ steps.check.originality }})"
```

The fixture `fake/tutorial-03-exercise.yaml` is the same as for the main
scenario (`originality: 1.4` → the run passes):

```yaml
# Scripted responses for tutorial-03-exercise (exercise solution from part 3).
# Jev gets answers: {question: value}; for choice the value is a key from criteria.
propose:
  - json:
      name: "Oatsy"
check:
  - answers:
      memorable: 0.835
      tone: playful
      originality: 1.4
slogan_playful:
  - json:
      slogan: "Oatsy — ice cream that grows in the field"
```

```bash
agencast validate workflows/scenarios/tutorial-03-exercise.yaml
agencast run workflows/scenarios/tutorial-03-exercise.yaml -i product="vegan ice cream" --fake fake/tutorial-03-exercise.yaml
```

```
valid: tutorial-03-exercise (10 steps)
run 20260925-151552-tutorial-03-exercise-7a12: succeeded · 0.0 s · 0.0003 USD
```

An ordinary name, `/tmp/ordinary.yaml`:

```yaml
propose:
  - json:
      name: "Ice cream"
check:
  - answers:
      memorable: 0.95
      originality: 0.2
```

```bash
agencast run workflows/scenarios/tutorial-03-exercise.yaml -i product="vegan ice cream" --fake /tmp/ordinary.yaml
```

```
fail in step stop_originality: The name Ice cream is too ordinary (originality = 0.2)
run 20260925-151553-tutorial-03-exercise-c3c6: failed · 0.0 s · 0.0002 USD
```

```
| 1 | propose | ask | ✓ | 0.0 s | 0.0001 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | check | jev | ✓ | 0.0 s | 0.0001 | memorable = 0.95, tone = playful, originality = 0.20 |
| 3 | stop | fail | skipped |  |  | when: steps.check.memorable < 0.5 → false |
| 4 | stop_originality | fail | failed | 0.0 s | 0 | see Error |
| | Total | | | 0.0 s | 0.0002 |  |
```

The step must be **after** `check` (it reads its output) and **before**
`by_tone` (so that a slogan is not paid for needlessly).

</details>

**Next part:** [Parallel steps and an image](04-parallel-and-image.md).
