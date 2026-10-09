# Part 1 — First agent and first scenario

**Time:** about 15 minutes · **Spend:** one live run for ~0.0002 USD
**You will learn to:** write an agent, write a one-step scenario, check it,
try it for free and run it live once.

The task in this part is deliberately primitive: a **namer** agent comes up
with three names for a product.

> Run all commands **from the `examples/tutorial` project** (from the clone
> root first `cd examples/tutorial`, from the package `cd ~/agencast-tutorial`).
> The outputs in this part are real runs of the tutorial project (run ids and
> timestamps from 25 Sep 2026); the only illustrative bit is the text of the
> live model response in step 8. Your `run_id`, times and model texts will be
> different. The real output prints absolute paths; they are shortened to `…/`
> here.

---

## Step 0 — a shortcut for the command

After you install the package, `agencast` is right on your PATH. Only when you
work from a clone without installing the tool, set up a shortcut (valid until
you close the terminal):

```bash
alias agencast="uv run --project ../../framework agencast"
agencast --help
```

```
usage: agencast [-h] [--project PATH]
                {validate,run,runs,serve,migrate,new,projects,rename,skills,docs}
                ...

AgenCast 0.19.1 — scenarios with LLM agents

positional arguments:
  {validate,run,runs,serve,migrate,new,projects,rename,skills,docs}
    validate            validate a scenario, agents, skills and config
    run                 run a scenario
    runs                run records
…
```

Three commands — `validate`, `run` and `runs` — are all you will need in parts
1–5.

---

## Step 1 — what goes where

```
workflows/
  agents/       ← you write agents here (*.md)
  scenarios/    ← you write scenarios here (*.yaml)
  skills/       ← skills (you do not need them in this part)
  config.yaml   ← models, limits, keys — changed by the owner only
```

`config.yaml` already exists. **You do not change it** — it belongs to the
project owner (that is you, of course, but in the role of the "administrator",
not the "scenario author"; we come back to this in part 5). For now you only
need to know one thing from it: which **model aliases** are available to you.

```bash
grep -A4 "^models:" workflows/config.yaml
```

```
models:
  smart:       { id: anthropic/claude-haiku-4.5 }
  fast:       { id: google/gemini-3.5-flash-lite, structured_output: tool_wrapper }
  gemini-image: { id: google/gemini-3.1-flash-image }
  gemini-image-api: { id: google/gemini-3.1-flash-image, api: images }   # Images API: reference images (image.images)
```

An agent never says "I want Claude Haiku 4.5". It says "I want `smart`".
Which model hides behind that name is decided by `config.yaml`.

---

## Step 2 — the first agent

Create the file `workflows/agents/tutorial-namer.md`:

```markdown
---
version: 1
name: tutorial-namer
description: Comes up with short product names (tutorial, part 1)
model: smart
limits:
  budget_usd: 0.01
---
You are an experienced product namer. You write in English.

Rules:
- Each name has at most two words and is easy to pronounce.
- Do not use existing well-known brands.
- Reply with the names only, without explanations.
```

The file has two parts:

1. **Frontmatter** — between two `---` lines. Configuration in YAML.
2. **Body** — below the second `---`. Instructions for the model (the system
   prompt), plain Markdown. It must not be empty.

Frontmatter fields that are **required**:

| Field | What it means |
|---|---|
| `version` | format version, always `1` |
| `name` | the agent's name — **the same as the file name** without `.md`; lowercase letters, digits, hyphen |
| `description` | one sentence for you; it is not sent to the model |
| `model` | an alias from `config.yaml` (here `smart`) |
| `limits.budget_usd` | how many USD a single step with this agent may cost |

Nothing else may appear in the frontmatter — not even a typo. That is good
news: the framework will not silently forgive a typo, it will tell you about
it (you will see that in step 4).

> Why the `tutorial-` prefix? So that the tutorial files do not get mixed up
> with your real agents. In your own work, name the agent whatever you like.

---

## Step 3 — the first scenario

Create `workflows/scenarios/tutorial-01-names.yaml`:

```yaml
version: 1
name: tutorial-01-names
description: Comes up with three names for a product (tutorial, part 1)

inputs:
  product:
    type: string
    required: true
    description: The product we are naming

outputs:
  names:
    type: string
    description: Three name ideas, each on its own line

steps:
  # 1. The agent comes up with names.
  - id: propose
    ask:
      agent: tutorial-namer
      prompt: "Come up with 3 names for this product: {{ inputs.product }}. Each on its own line."

  # 2. The result of the run.
  - id: out
    output:
      names: "{{ steps.propose.text }}"
```

Read it from top to bottom:

- **Header** — `version`, `name` (again = the file name without `.yaml`),
  `description`.
- **`inputs`** — what the scenario receives from outside. Every input has a
  `type` and either `required: true` **or** `default` (never both, never
  neither).
- **`outputs`** — what the scenario returns. It is a "contract": the caller (or
  anyone who runs the scenario) can rely on getting exactly these fields.
- **`steps`** — the steps run from top to bottom, one after another.
  - `ask` = one model call through an agent. Without `schema` it returns text,
    which is then visible as `steps.propose.text`.
  - `output` = the last step; it fills the fields from `outputs`.
- **`{{ … }}`** is a **template**: it only inserts a value. `{{ inputs.product }}`
  inserts the input, `{{ steps.propose.text }}` inserts the response of the step
  `propose`.

---

## Step 4 — `agencast validate`

Before you run anything, have the scenario checked:

```bash
agencast validate workflows/scenarios/tutorial-01-names.yaml
```

```
valid: tutorial-01-names (2 steps)
```

`validate` checks the scenario, the agent and `config.yaml`, and it also asks
OpenRouter whether the model `anthropic/claude-haiku-4.5` really exists.
(Without a network add `--offline`; it then skips this last check and says so:
`valid: tutorial-01-names (2 steps, model checks skipped)`.)

Now break something on purpose so you know what an error looks like. Delete the
two lines `limits:` and `budget_usd: 0.01` from the agent and run `validate`
again:

```
config: agents/tutorial-namer.md: missing required field 'limits'
```

Put them back. Change `model:` to `modle:`:

```
config: agents/tutorial-namer.md: modle: unknown field 'modle' (typo?)
config: agents/tutorial-namer.md: missing required field 'model'
```

Fix that and write an alias with a typo, `model: smrt`:

```
config: agents/tutorial-namer.md: model 'smrt' is not an alias in config.yaml (aliases: smart, fast, gemini-image, gemini-image-api)
```

And in the scenario `agent: namer` (without the prefix):

```
config: tutorial-01-names.yaml: step "propose": agent 'namer' does not exist (agents/namer.md)
```

How to read a message: the **error class** (`config` = an error in the files),
the **file**, possibly the **step**, and what is wrong. Fix everything until
`validate` says `valid` again.

---

## Step 5 — `--dry-run`: what would happen

```bash
agencast run workflows/scenarios/tutorial-01-names.yaml -i product="vegan oat milk ice cream" --dry-run
```

```
project tutorial added to the registry (/home/you/.config/agencast/projects.yaml)
# Plan: tutorial-01-names

Comes up with three names for a product (tutorial, part 1)

Run limits: budget 1.0 USD (of which images 0.3 USD), time 1h. Jev: jev-1.13.

| # | Step | Type | Condition | Action | Limits |
|---|---|---|---|---|---|
| 1 | propose | ask |  | agent tutorial-namer → smart (anthropic/claude-haiku-4.5); text | 0.01 USD, 2m |
| 2 | out | output |  | names |  |


plan: …/runs/20260925-150947-tutorial-01-names-3c6f/plan.md
```

- The first line (printed to stderr) appears only once: the first `run` in a
  project adds it to the project registry.
- `-i key=value` passes an input. More inputs = more `-i`.
- `--dry-run` calls nothing and costs nothing. It only saves `plan.md` (and
  `inputs.json`) into a new folder in `runs/`.
- In the plan you can see which **real model** the alias resolved to and which
  limits apply: 0.01 USD from the agent, and 2 minutes is the default timeout
  of an `ask` step.

Try leaving out `-i`:

```
config: missing required input 'product' (string)
```

The run does not even start.

---

## Step 6 — `--fake`: model responses for free

`--fake` replaces only the model calls: no model cost and no OpenRouter key.
A `task` step still starts the real MCP servers from `mcp.yaml`; the sample
`filesystem` uses `npx`, needs Node.js and downloads a package on the first run.
`--callback-url` sends a real callback (and needs its signing secret).
Guaranteed offline are only scenarios without `task` (also in called scenarios)
and without `--callback-url`, for example `ig-post`.

```bash
agencast run workflows/scenarios/tutorial-01-names.yaml -i product="vegan oat milk ice cream" --fake
```

```
run 20260925-150949-tutorial-01-names-b761: succeeded · 0.0 s · 0.0001 USD
run record: …/runs/20260925-150949-tutorial-01-names-b761/summary.md
report: file:///…/outputs/20260925-150949-tutorial-01-names-b761-487c1d49d9ff8d4dda3b9105eb7e8c29/report.html
```

Instead of OpenRouter, `--fake` uses a **fake provider**: the whole framework
runs (templates, steps, the record), only the model's response is made up. The
cost of 0.0001 USD is made up too — nothing is paid.

Look at what the "model" answered:

```bash
cat runs/20260925-150949-tutorial-01-names-b761/steps/01-propose/output.json
```

```
{
  "text": "Fake response."
}
```

To check that a scenario **can run through**, that is enough. But "Fake
response." does not look like three names. If you want the fake model to answer
realistically, you write it a **fixture** — a file with predefined responses.

### The fixture

Create `fake/tutorial-01-names.yaml`:

```yaml
# Scripted fake-provider responses for tutorial-01-names.
# Key = step id, below it a list of responses (each call takes the next one).
propose:
  - text: "Oatsy\nFrost Oat\nFrozen Field"
```

and run with it:

```bash
agencast run workflows/scenarios/tutorial-01-names.yaml -i product="vegan oat milk ice cream" --fake fake/tutorial-01-names.yaml
```

```
run 20260925-150957-tutorial-01-names-c3a6: succeeded · 0.0 s · 0.0001 USD
run record: …/runs/20260925-150957-tutorial-01-names-c3a6/summary.md
report: file:///…/outputs/20260925-150957-tutorial-01-names-c3a6-133fa5cdaf2b36f9f69945523e989f39/report.html
```

Why into `fake/`, and why the same name as the scenario? Because **every
scenario in the examples of the clone in `workflows/scenarios/` is also a
framework test** (a so-called golden scenario). The tests run it with `--fake`
and when they find a fixture with the same name, they use it and expect
success. That way, when someone improves the framework, they immediately see
whether your scenario still runs. More in part 5.

The fixture rules you need so far:

- key = the step's `id`,
- `text: "…"` = a text response (for `ask` without `schema`),
- a list = the response to the 1st, 2nd, … call of the step; the last one repeats.

---

## Step 7 — the run folder and `summary.md`

Every run (even a fake one) has its own folder in `runs/`:

```bash
find runs/20260925-150949-tutorial-01-names-b761 -type f | sort
```

```
runs/20260925-150949-tutorial-01-names-b761/callback.json
runs/20260925-150949-tutorial-01-names-b761/events.jsonl
runs/20260925-150949-tutorial-01-names-b761/inputs.json
runs/20260925-150949-tutorial-01-names-b761/plan.md
runs/20260925-150949-tutorial-01-names-b761/report.html
runs/20260925-150949-tutorial-01-names-b761/run.lock
runs/20260925-150949-tutorial-01-names-b761/scenario/tutorial-01-names.yaml
runs/20260925-150949-tutorial-01-names-b761/steps/01-propose/calls/01.request.json
runs/20260925-150949-tutorial-01-names-b761/steps/01-propose/calls/01.response.json
runs/20260925-150949-tutorial-01-names-b761/steps/01-propose/output.json
runs/20260925-150949-tutorial-01-names-b761/steps/01-propose/prompt.md
runs/20260925-150949-tutorial-01-names-b761/steps/02-out/output.json
runs/20260925-150949-tutorial-01-names-b761/summary.md
```

Three files are enough for now:

| File | What it is for |
|---|---|
| `summary.md` | a summary for humans — always read it first |
| `steps/01-propose/prompt.md` | **exactly** what the model received: the system prompt (the agent's body) + the message (the step's prompt after substitution) |
| `steps/01-propose/output.json` | the step's output — what you see as `steps.propose` |

`01` is the step's order in the scenario file. We will go through the rest
(`events.jsonl`, `calls/`, `callback.json`, `report.html`) in parts 5 and 7.

```bash
cat runs/20260925-150949-tutorial-01-names-b761/steps/01-propose/prompt.md
```

```
# System prompt

You are an experienced product namer. You write in English.

Rules:
- Each name has at most two words and is easy to pronounce.
- Do not use existing well-known brands.
- Reply with the names only, without explanations.

# Message

Come up with 3 names for this product: vegan oat milk ice cream. Each on its own line.
```

When the model answers strangely, **this** is where you look for why: what
exactly it received.

---

## Step 8 — one live run

The `OPENROUTER_API_KEY` key is in the `.env` file in the `examples/tutorial`
project; the framework loads it by itself (and never prints it anywhere). Run
without `--fake`:

```bash
agencast run workflows/scenarios/tutorial-01-names.yaml -i product="vegan oat milk ice cream"
```

```
run 20260925-151000-tutorial-01-names-8d6a: succeeded · 1.6 s · 0.0002 USD
run record: …/runs/20260925-151000-tutorial-01-names-8d6a/summary.md
report: file:///…/outputs/20260925-151000-tutorial-01-names-8d6a-ac84f994cef7d8b66082e2f51b941ff9/report.html
```

```bash
agencast runs show 20260925-151000-tutorial-01-names-8d6a
```

```
# tutorial-01-names — success

Comes up with three names for a product (tutorial, part 1)
Run `20260925-151000-tutorial-01-names-8d6a` · 2026-09-25 15:10 UTC · 1.6 s · 0.0002 USD

## Inputs
- product: vegan oat milk ice cream

## Steps
| # | Step | Type | Status | Time | Cost | Note |
|---|---|---|---|---|---|---|
| 1 | propose | ask | ✓ | 1.6 s | 0.0002 | smart → anthropic/claude-haiku-4.5 |
| 2 | out | output | ✓ | 0.0 s | 0 |  |
| | Total | | | 1.6 s | 0.0002 |  |

## Warnings
none

## Output
- names: “Oat Bliss
Frost Grain
Oaty Cloud”
```

**Where you see the cost:**

- on the first line after the run (`0.0002 USD`),
- in `summary.md` — the total in the header, per step in the **Cost** column,
- in the overview of all runs:

```bash
agencast runs list
```

```
20260925-151000-tutorial-01-names-8d6a        succeeded                         1.6 s   0.0002 USD 
20260925-150957-tutorial-01-names-c3a6        succeeded                         0.0 s   0.0001 USD 
20260925-150949-tutorial-01-names-b761        succeeded                         0.0 s   0.0001 USD 
20260925-150947-tutorial-01-names-3c6f        dry-run
```

OpenRouter calculates the cost; the framework only reads it from the response
(exactly: 0.000234 USD, 134 tokens in, 20 out). It never estimates it.

---

## What you have learned

- Agent = `workflows/agents/<name>.md`: frontmatter (`version`, `name`,
  `description`, `model`, `limits.budget_usd`) + instructions.
- Scenario = `workflows/scenarios/<name>.yaml`: header, `inputs`,
  `outputs`, `steps`; `ask` without `schema` gives `steps.<id>.text`.
- The procedure is always: **`validate` → `--dry-run` → `--fake` → live run.**
- The first thing you read after a run: `summary.md`. When something is off:
  `prompt.md`.

---

## Exercise

Add a second input **`style`** (text) to the scenario, which **does not have**
to be provided — when it is not, `playful` applies. Put it into the prompt. Save
the scenario as `workflows/scenarios/tutorial-01-exercise.yaml` and make a
fixture for it. Verify with a fake run that without `-i style=…` the model
received "playful" and with `-i style="luxury"` it received "luxury".

<details>
<summary>Solution</summary>

`workflows/scenarios/tutorial-01-exercise.yaml`:

```yaml
version: 1
name: tutorial-01-exercise
description: Comes up with three names for a product in a given style (tutorial, part 1 — exercise solution)

inputs:
  product:
    type: string
    required: true
    description: The product we are naming
  style:
    type: string
    default: playful
    description: The style of names we want

outputs:
  names:
    type: string
    description: Three name ideas, each on its own line

steps:
  - id: propose
    ask:
      agent: tutorial-namer
      prompt: "Come up with 3 names in a “{{ inputs.style }}” style for this product: {{ inputs.product }}. Each on its own line."

  - id: out
    output:
      names: "{{ steps.propose.text }}"
```

Watch out: `name` must change together with the file name. The `style` input has
a `default`, so it does **not** have `required`.

`fake/tutorial-01-exercise.yaml`:

```yaml
# Scripted responses for tutorial-01-exercise (exercise solution from part 1).
propose:
  - text: "Little Oatsy\nFrosty\nOat Scoop"
```

Verification:

```bash
agencast validate workflows/scenarios/tutorial-01-exercise.yaml
agencast run workflows/scenarios/tutorial-01-exercise.yaml -i product="vegan ice cream" --fake fake/tutorial-01-exercise.yaml
```

```
valid: tutorial-01-exercise (2 steps)
run 20260925-151019-tutorial-01-exercise-6b59: succeeded · 0.0 s · 0.0001 USD
run record: …/runs/20260925-151019-tutorial-01-exercise-6b59/summary.md
report: file:///…/outputs/20260925-151019-tutorial-01-exercise-6b59-c0f8f5d83b45c8395fa549206d5c6c9b/report.html
```

```bash
cat runs/20260925-151019-tutorial-01-exercise-6b59/inputs.json
```

```
{
  "product": "vegan ice cream",
  "style": "playful"
}
```

and in `steps/01-propose/prompt.md` under `# Message`:

```
Come up with 3 names in a “playful” style for this product: vegan ice cream. Each on its own line.
```

With `-i style="luxury"` the message contains `in a “luxury” style`.

</details>

**Next part:** [Chaining steps](02-chaining-steps.md) — the second step
reads the output of the first, and `schema` turns a response into data.
