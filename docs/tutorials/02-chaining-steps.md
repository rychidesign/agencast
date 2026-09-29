# Part 2 — Chaining steps

Run the commands from `examples/tutorial` (from the clone root: `cd examples/tutorial`).

**Time:** about 15 minutes · **Spend:** one live run for ~0.0008 USD
**You will learn to:** pass the output of one step to the next, get data
from the model instead of free text (`schema`), calculate without a model
(`set`), return several fields and read `validate` messages.

Prerequisite: part 1 (the agent `tutorial-namer`, the shortcut
`alias agencast="uv run --project ../../framework agencast"`).

---

## Step 1 — a second agent

Create `workflows/agents/tutorial-slogan-writer.md`:

```markdown
---
version: 1
name: tutorial-slogan-writer
description: Writes short advertising slogans for a product name (tutorial, part 2)
model: smart
limits:
  budget_usd: 0.01
---
You are a copywriter. You write short advertising slogans in English.

Rules:
- A slogan has at most 8 words.
- No quotation marks, no emoji, no hashtags.
```

Nothing new — the same shape as the namer.

---

## Step 2 — a scenario where step 2 reads step 1

Create `workflows/scenarios/tutorial-02-name-and-slogan.yaml`:

```yaml
version: 1
name: tutorial-02-name-and-slogan
description: Comes up with product names and writes a slogan for the first one (tutorial, part 2)

inputs:
  product:
    type: string
    required: true
    description: The product we are naming

outputs:
  name:
    type: string
    description: The chosen name (the first of the ideas)
  slogan:
    type: string
    description: Slogan for the chosen name
  all_names:
    type: string
    description: All ideas separated by commas
  count:
    type: integer
    description: How many names the agent proposed

steps:
  # 1. The agent comes up with names — thanks to schema as a list, not as free text.
  - id: propose
    ask:
      agent: tutorial-namer
      prompt: "Come up with 3 names for this product: {{ inputs.product }}."
      schema:
        names: [string]

  # 2. A second agent writes a slogan for the first name.
  - id: slogan
    ask:
      agent: tutorial-slogan-writer
      prompt: |
        Product: {{ inputs.product }}
        Name: {{ steps.propose.names[0] }}
        Write one slogan for it.
      schema:
        slogan: string

  # 3. Calculations without a model.
  - id: summary
    set:
      all_names: join(steps.propose.names, ", ")
      count: len(steps.propose.names)

  # 4. Result.
  - id: out
    output:
      name: "{{ steps.propose.names[0] }}"
      slogan: "{{ steps.slogan.slogan }}"
      all_names: "{{ steps.summary.all_names }}"
      count: "{{ steps.summary.count }}"
```

What is new:

### `{{ steps.<id>.<field> }}` — the output of another step

A step sees the outputs of the steps **above** it. `steps.propose.names` = the
field `names` from the output of the step `propose`. `[0]` = the first item of
the list (`[-1]` would be the last).

### `schema` — data instead of free text

In part 1, `ask` returned a single text (`steps.propose.text`). When you want to
keep working with the response — take the first name, count them — you need
**data**. `schema` says what JSON the model should return:

| Notation | Means |
|---|---|
| `string`, `number`, `integer`, `boolean` | a value of that type |
| `[string]` | a list of texts (works with every type) |
| `{ a: string, b: number }` | a nested object |

The root is always a map (the fields under `schema:`). All fields are required.
**What** goes into a field, you write in the prompt or in the agent — `schema`
only guards the shape.

How the framework does it: it sends the model a JSON Schema and checks the
response. If it does not match, it tries again and sends the model the error as
feedback (more in step 5).

### `set` — a calculation without a model

Every key under `set` is a new output (`steps.summary.count`), and the value is
an **expression**. An expression is written **without** `{{ }}` — that is the
only difference you need to remember for now:

| Where | Notation |
|---|---|
| `prompt`, values in `output`, `fail` | template `"{{ steps.propose.names[0] }}"` |
| `set`, `when` (part 3) | expression `len(steps.propose.names)` |

`join(list, separator)` joins a list of texts, `len(x)` computes the length.

### `output` with several fields

The keys under `output` are **exactly** those from `outputs` in the header. When
a value is one whole template (`"{{ steps.summary.count }}"`), it is inserted
with its type — `count` stays a number, not the text `"3"`.

---

## Step 3 — a fixture for a step with `schema`

A step with `schema` gets `json:` instead of `text:` in the fixture. Create
`fake/tutorial-02-name-and-slogan.yaml`:

```yaml
# Scripted responses for tutorial-02-name-and-slogan.
# A step with schema gets its response as json: {field: value}.
propose:
  - json:
      names: ["Oatsy", "Frost Oat", "Frozen Field"]
slogan:
  - json:
      slogan: "Ice cream that grows in the field"
```

```bash
agencast validate workflows/scenarios/tutorial-02-name-and-slogan.yaml
agencast run workflows/scenarios/tutorial-02-name-and-slogan.yaml -i product="vegan oat milk ice cream" --fake fake/tutorial-02-name-and-slogan.yaml
```

```
valid: tutorial-02-name-and-slogan (4 steps)
run 20260925-151207-tutorial-02-name-and-slogan-6952: succeeded · 0.0 s · 0.0002 USD
run record: …/runs/20260925-151207-tutorial-02-name-and-slogan-6952/summary.md
report: file:///…/outputs/20260925-151207-tutorial-02-name-and-slogan-6952-266515b74a65f0d8e96e2dcfc87b0561/report.html
```

```bash
cat runs/20260925-151207-tutorial-02-name-and-slogan-6952/summary.md
```

```
# tutorial-02-name-and-slogan — success

Comes up with product names and writes a slogan for the first one (tutorial, part 2)
Run `20260925-151207-tutorial-02-name-and-slogan-6952` · 2026-09-25 15:12 UTC · 0.0 s · 0.0002 USD

**Fake run** (`--fake`) — model responses are fabricated, dedupe in `_dedupe-fake/`.

## Inputs
- product: vegan oat milk ice cream

## Steps
| # | Step | Type | Status | Time | Cost | Note |
|---|---|---|---|---|---|---|
| 1 | propose | ask | ✓ | 0.0 s | 0.0001 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | slogan | ask | ✓ | 0.0 s | 0.0001 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 3 | summary | set | ✓ | 0.0 s | 0 |  |
| 4 | out | output | ✓ | 0.0 s | 0 |  |
| | Total | | | 0.0 s | 0.0002 |  |

## Warnings
none

## Output
- name: “Oatsy”
- slogan: “Ice cream that grows in the field”
- all_names: “Oatsy, Frost Oat, Frozen Field”
- count: 3
```

`(native_schema)` in the note says how the framework enforced JSON from the
model — here with a native JSON Schema. Look at what exactly step 2 received:

```bash
sed -n '/# Message/,$p' runs/20260925-151207-tutorial-02-name-and-slogan-6952/steps/02-slogan/prompt.md
```

```
# Message

Product: vegan oat milk ice cream
Name: Oatsy
Write one slogan for it.
```

And the outputs of steps 1 and 3:

```bash
cat runs/20260925-151207-tutorial-02-name-and-slogan-6952/steps/01-propose/output.json
cat runs/20260925-151207-tutorial-02-name-and-slogan-6952/steps/03-summary/output.json
```

```
{
  "names": [
    "Oatsy",
    "Frost Oat",
    "Frozen Field"
  ]
}
{
  "all_names": "Oatsy, Frost Oat, Frozen Field",
  "count": 3
}
```

Tip: `--fake` **without** a fixture for a step with `schema` produces the values
from the schema by itself — `name: “fake text (names)”`, `count: 1`. To check
that a scenario runs through, that is enough.

---

## Step 4 — a live run

```bash
agencast run workflows/scenarios/tutorial-02-name-and-slogan.yaml -i product="vegan oat milk ice cream"
```

```
run 20260925-151245-tutorial-02-name-and-slogan-8c39: succeeded · 4.2 s · 0.0008 USD
run record: …/runs/20260925-151245-tutorial-02-name-and-slogan-8c39/summary.md
report: file:///…/outputs/20260925-151245-tutorial-02-name-and-slogan-8c39-a7d633feb6bfdaf592a061ad9c1384e2/report.html
```

From `summary.md` (the model texts are illustrative; the times and costs are
from the real run):

```
| 1 | propose | ask | ✓ | 2.0 s | 0.0004 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | slogan | ask | ✓ | 2.2 s | 0.0004 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 3 | summary | set | ✓ | 0.0 s | 0 |  |
| 4 | out | output | ✓ | 0.0 s | 0 |  |
| | Total | | | 4.2 s | 0.0008 |  |

## Warnings
none

## Output
- name: “OatCloud”
- slogan: “OatCloud - plant-based goodness, zero guilt”
- all_names: “OatCloud, PlantFrost, Creamy Oat”
- count: 3
```

`set` and `output` always cost 0 — they do not call a model.

---

## Step 5 — what if the model breaks the JSON

A fixture can simulate a model that answers with text instead of JSON on the
first attempt. Save this anywhere (for example `/tmp/bad-json.yaml`):

```yaml
propose:
  - text: "Here are the names: Oatsy, Frost Oat, Frozen Field"
  - json:
      names: ["Oatsy", "Frost Oat", "Frozen Field"]
slogan:
  - json:
      slogan: "Ice cream that grows in the field"
```

```bash
agencast run workflows/scenarios/tutorial-02-name-and-slogan.yaml -i product="ice cream" --fake /tmp/bad-json.yaml
```

```
run 20260925-151235-tutorial-02-name-and-slogan-6286: succeeded · 0.0 s · 0.0003 USD
```

The run passed. In `summary.md` step 1 has `(tool_wrapper)` instead of
`(native_schema)`, and `events.jsonl` shows why:

```bash
grep '"error"' runs/20260925-151235-tutorial-02-name-and-slogan-6286/events.jsonl
```

```
{"ts":"2026-09-25T15:12:35.304Z","type":"error","step":"propose","class":"schema","message":"response is not JSON (Expecting value: line 1 column 1 (char 0)): Here are the names: Oatsy, Frost Oat, Frozen Field","attempt":1,"will_retry":true,"http_status":null}
{"ts":"2026-09-25T15:12:35.306Z","type":"run_finished","status":"succeeded","error":null,"warnings":[],"duration_s":0.003,"usage":{"input_tokens":300,"output_tokens":60,"cost_usd":0.0003},"image_cost_usd":0.0,"image_duration_s":0.0}
```

(The second line was caught by grep only because it contains `"error":null`.)
The first attempt ended with an error of class **`schema`**, `will_retry: true`.
The second attempt went "one level down" (JSON through a wrapper tool,
`tool_wrapper`) and passed. That is why the step folder holds two calls:
`calls/01.*` and `calls/02.*`. Both attempts are paid for — that is why the
step costs double.

**Without `schema`** none of this would happen: the output would be only
`steps.propose.text` and you could not work further with "Here are the names: …".
And `validate` would tell you that before you pay anything — see the next step.

---

## Step 6 — `validate` messages and how to read them

All messages have the same structure:

```
config: <file>: step "<id>", <where>: <what is wrong>
  <expression or template>
      ^ ← place of the error
```

Try them out — always one change, `validate`, and change it back.

**Delete `schema` from the step `propose`.** The output is then only `text`:

```
config: tutorial-02-name-and-slogan.yaml: step "slogan", ask.prompt: 'steps.propose' has no key 'names' (available: text)
  {{ steps.propose.names[0] }}
                   ^
config: tutorial-02-name-and-slogan.yaml: step "summary", set.all_names: 'steps.propose' has no key 'names' (available: text)
  join(steps.propose.names, ", ")
                     ^
config: tutorial-02-name-and-slogan.yaml: step "summary", set.count: 'steps.propose' has no key 'names' (available: text)
  len(steps.propose.names)
                    ^
config: tutorial-02-name-and-slogan.yaml: step "out", output.name: 'steps.propose' has no key 'names' (available: text)
  {{ steps.propose.names[0] }}
                   ^
```

Always read the **first** message; the others are often a consequence of the
same error. "(available: text)" tells you what the step really returns.

**A typo in a step id** — `{{ steps.propse.names[0] }}`:

```
config: tutorial-02-name-and-slogan.yaml: step "slogan", ask.prompt: step 'propse' does not exist (available: propose)
  {{ steps.propse.names[0] }}
           ^
```

**A missing field** — `slogan: "{{ steps.slogan.text }}"` (the step has a
`schema`, so it has no `text`):

```
config: tutorial-02-name-and-slogan.yaml: step "out", output.slogan: 'steps.slogan' has no key 'text' (available: slogan)
  {{ steps.slogan.text }}
                  ^
```

**A reference to a later step** — add `{{ steps.summary.count }}` to the prompt
of the step `slogan`:

```
config: tutorial-02-name-and-slogan.yaml: step "slogan", ask.prompt: step 'summary' comes later — expressions can only reference preceding steps
  {{ steps.summary.count }}
           ^
```

**`output` does not match the header** — delete the line `count:` from the step
`out`:

```
config: tutorial-02-name-and-slogan.yaml: step "out", output: missing outputs declared in the header: count
```

**A wrong output type** — `count: "{{ steps.summary.all_names }}"`:

```
config: tutorial-02-name-and-slogan.yaml: step "out", output.count: output has type integer, value is string
```

**`null`** — the framework never inserts `null` silently. Add the line
`note: null` to `set` and use `"{{ steps.summary.all_names }} {{ steps.summary.note }}"`
in the output:

```
config: tutorial-02-name-and-slogan.yaml: step "out", output.all_names: 'steps.summary.note' is always null — a template cannot insert null
  {{ steps.summary.note }}
     ^
```

**A template where an expression belongs** — `count: "{{ steps.propose.names }}"`
in `set`:

```
config: tutorial-02-name-and-slogan.yaml: step "summary", set.count: template {{ }} is not allowed here — allowed only in prompt, jev.state, jev.questions (instructions, criteria), fail, output values, call.inputs and dedupe_key
  {{ steps.propose.names }}
  ^
```

### An error `validate` cannot detect

`validate` does not know what the model will return. When it returns an empty
list, `[0]` has nothing to take. Simulate it with the fixture `/tmp/empty.yaml`:

```yaml
propose:
  - json:
      names: []
```

```bash
agencast run workflows/scenarios/tutorial-02-name-and-slogan.yaml -i product="ice cream" --fake /tmp/empty.yaml
```

```
expression in step slogan: ask.prompt: index 0 out of range for 'steps.propose.names' (length 0)
  {{ steps.propose.names[0] }}
                         ^
run 20260925-151229-tutorial-02-name-and-slogan-ec41: failed · 0.0 s · 0.0001 USD
run record: …/runs/20260925-151229-tutorial-02-name-and-slogan-ec41/summary.md
report: file:///…/outputs/20260925-151229-tutorial-02-name-and-slogan-ec41-e73dd66f902d269a51db5dc45850b668/report.html
```

The class **`expression`** = an expression error **at run time**. It is not
retried, the run ends. In `summary.md`:

```
# tutorial-02-name-and-slogan — failed
…
## Error
- class: `expression`
- step: `slogan`
- message:

…
Run ended at step slogan.
…
| 1 | propose | ask | ✓ | 0.0 s | 0.0001 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | slogan | ask | failed | 0.0 s | 0 | see Error |
| | Total | | | 0.0 s | 0.0001 |  |
```

A difference worth remembering:

| Class | When | Run |
|---|---|---|
| `config` | `validate`, **before** the run | does not start at all, costs nothing |
| `expression` | **at run time**, a value does not fit | ends in the step, steps already paid for stay paid |

---

## What you have learned

- `{{ steps.<id>.<field> }}` reads the output of a step **above** it.
- `schema` turns a response into data; without it you only have `steps.<id>.text`.
  In a fixture, `json:` instead of `text:`.
- `set` calculates with **expressions** (without `{{ }}`), for free.
- `output` = exactly the fields from `outputs`, with the right types.
- Messages: read the first one, look for the `^` and "(available: …)".

---

## Exercise

Add an output **`short_slogan`** (type `boolean`) to the scenario: `true` when
the slogan has at most 40 characters. Calculate it in the step `summary`. Save
it as `workflows/scenarios/tutorial-02-exercise.yaml` with a fixture.

<details>
<summary>Solution</summary>

The difference against `tutorial-02-name-and-slogan.yaml` (the whole file is in
`workflows/scenarios/tutorial-02-exercise.yaml`):

```bash
diff workflows/scenarios/tutorial-02-name-and-slogan.yaml workflows/scenarios/tutorial-02-exercise.yaml
```

```
2,3c2,3
< name: tutorial-02-name-and-slogan
< description: Comes up with product names and writes a slogan for the first one (tutorial, part 2)
---
> name: tutorial-02-exercise
> description: Comes up with product names and writes a slogan for the first one (tutorial, part 2 — exercise solution)
23a24,26
>   short_slogan:
>     type: boolean
>     description: Does the slogan have at most 40 characters?
49a53
>       short: len(steps.slogan.slogan) <= 40
57a62
>       short_slogan: "{{ steps.summary.short }}"
```

The comparison `<=` gives `true`/`false`, so the type `boolean` fits. The step
`summary` may read `steps.slogan` because `slogan` is above it.

The fixture `fake/tutorial-02-exercise.yaml` is the same as for the main
scenario (the steps did not change):

```yaml
# Scripted responses for tutorial-02-exercise (exercise solution from part 2).
# A step with schema gets its response as json: {field: value}.
propose:
  - json:
      names: ["Oatsy", "Frost Oat", "Frozen Field"]
slogan:
  - json:
      slogan: "Ice cream that grows in the field"
```

```bash
agencast validate workflows/scenarios/tutorial-02-exercise.yaml
agencast run workflows/scenarios/tutorial-02-exercise.yaml -i product="vegan ice cream" --fake fake/tutorial-02-exercise.yaml
```

```
valid: tutorial-02-exercise (4 steps)
run 20260925-151257-tutorial-02-exercise-1680: succeeded · 0.0 s · 0.0002 USD
```

The end of `summary.md`:

```
## Output
- name: “Oatsy”
- slogan: “Ice cream that grows in the field”
- all_names: “Oatsy, Frost Oat, Frozen Field”
- count: 3
- short_slogan: true
```

(“Ice cream that grows in the field” has 33 characters.)

</details>

**Next part:** [Decisions](03-decisions.md) — Jev, `when`, `fail`,
`switch` and the expression rules.
