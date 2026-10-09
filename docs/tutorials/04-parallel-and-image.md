# Part 4 — Parallel steps and an image

Run the commands from `examples/tutorial` (from the clone root: `cd examples/tutorial`).

**Time:** about 20 minutes · **Spend:** one live run with an image for ~0.07 USD
**You will learn to:** run two branches concurrently (`parallel`), generate
an image (`image`), guard money (`budget_usd`) and time (`timeout`),
set up retries (`retry`), survive a step failure (`on_error`) and read the
error classes in `summary.md`.

Prerequisite: parts 1–3.

---

## Step 1 — an agent with a different model

The photo description for the image generator is written by a cheaper and
faster model. `workflows/agents/tutorial-illustrator.md`:

```markdown
---
version: 1
name: tutorial-illustrator
description: Writes an English product photo description for the image generator (tutorial, part 4)
model: fast
limits:
  budget_usd: 0.01
---
You are a product photographer. From a product description you write a photo
description for the image generator:

- in English, 30 to 60 words,
- the product on a clean background, soft light, front view,
- no text, lettering or logos in the image, no people.
```

The only change compared to the agents so far: `model: fast` (Gemini
Flash-Lite).

---

## Step 2 — a scenario with `parallel` and `image`

`workflows/scenarios/tutorial-04-parallel.yaml`:

```yaml
version: 1
name: tutorial-04-parallel
description: Concurrently comes up with a name and a slogan and photographs the product (tutorial, part 4)

inputs:
  product:
    type: string
    required: true
    description: The product we are naming and photographing

outputs:
  name:
    type: string
  slogan:
    type: string
  photo:
    type: file
    description: Product photo 1:1

steps:
  # 1. Two branches run concurrently. budget_usd on parallel = the sum of everything inside.
  - id: concurrent
    budget_usd: 0.15
    parallel:
      texts:
        - id: propose
          ask:
            agent: tutorial-namer
            prompt: "Come up with 3 names for this product: {{ inputs.product }}."
            schema:
              names: [string]
        - id: slogan
          ask:
            agent: tutorial-slogan-writer
            prompt: "Write a slogan for the product {{ inputs.product }} named {{ steps.propose.names[0] }}."
            schema:
              slogan: string
      visual:
        - id: describe
          ask:
            agent: tutorial-illustrator
            prompt: "Product: {{ inputs.product }}"
            schema:
              description: string
        - id: photo
          budget_usd: 0.10
          timeout: 2m
          retry: 1
          image:
            model: gemini-image
            prompt: "{{ steps.describe.description }}"
            aspect_ratio: "1:1"

  # 2. Once both branches have finished.
  - id: out
    output:
      name: "{{ steps.propose.names[0] }}"
      slogan: "{{ steps.slogan.slogan }}"
      photo: "{{ steps.photo.file }}"
```

### `parallel`

- Under `parallel` there are **named branches** (`texts`, `visual`). Each is
  a list of steps that run one after another inside it.
- The branches run **concurrently**. The step after `parallel` (`out`) starts
  only when all of them have finished.
- You read the **outputs** of steps in branches normally, through their `id`
  (`steps.propose…`, `steps.photo…`). The branch name is only for readability
  and the run record; `parallel` itself has no output.
- A step in a branch may read steps **above the `parallel`** and steps above it
  **in the same branch** (`slogan` reads `propose`). It must not read into
  another branch — you don't know which one finishes first.

### `image`

- `model` — an alias of an **image** model from `config.yaml` (`gemini-image`).
- `prompt` — the image description (a template).
- `aspect_ratio` — the aspect ratio as **text in quotes** (`"1:1"`,
  `"4:5"`). After saving, the framework checks the ratio; a deviation over
  2 % is an error, nothing is silently cropped.
- Output: `steps.photo.file` — type `file`. It comes **only** from an `image`
  step; you cannot write a path into `output` as text.
- Choosing the API and quality: [config.md](../spec/config.md#models--aliases-55).

Since 0.14.0 the ratio can be passed as `aspect_ratio: "{{ inputs.aspect_ratio }}"`;
`quality` (`auto|low|medium|high`) and `resolution`
(`"512"|"1K"|"2K"|"4K"`) work the same way. The step's quality overrides the
alias; the chat API ignores quality and resolution with a warning. A callable
example is
[`image.yaml`](../../examples/showcase/workflows/scenarios/image.yaml).

### New step properties

| Property | Here | What it does |
|---|---|---|
| `budget_usd` | `0.15` on `parallel`, `0.10` on `photo` | how much the step may cost; on `parallel` the sum of everything inside |
| `timeout` | `2m` | the longest time of a step (`s`, `m`, `h`) |
| `retry` | `1` | how many times **a single call** is repeated after a `transient` or `schema` error (default 2) |

Besides that, the limits of the whole run from `config.yaml` apply (the owner
changes them):

```bash
grep -A5 "^limits:" workflows/config.yaml
```

```
limits:
  run_budget_usd: 1.00
  run_image_budget_usd: 0.30
  run_timeout: 1h
  max_call_depth: 3
```

`run_image_budget_usd` guards images separately — they are two orders of
magnitude more expensive than text. The resulting limit of a step is always the
**smallest** of: the step limit, the agent limit, what is left of the run limit.

---

## Step 3 — the plan and a fake run

```bash
agencast validate workflows/scenarios/tutorial-04-parallel.yaml
agencast run workflows/scenarios/tutorial-04-parallel.yaml -i product="vegan ice cream made from oat milk" --dry-run
```

```
valid: tutorial-04-parallel (6 steps)
# Plan: tutorial-04-parallel

Concurrently comes up with a name and a slogan and photographs the product (tutorial, part 4)

Run limits: budget 1.0 USD (of which images 0.3 USD), time 1h. Jev: jev-1.13.

| # | Step | Type | Condition | Action | Limits |
|---|---|---|---|---|---|
| 1 | concurrent | parallel |  | branches: texts, visual | 0.15 USD |
| 2 | ↳ propose | ask |  | agent tutorial-namer → smart (anthropic/claude-haiku-4.5); schema: names (cascade from native_schema) | 0.01 USD, 2m |
| 3 | ↳ slogan | ask |  | agent tutorial-slogan-writer → smart (anthropic/claude-haiku-4.5); schema: slogan (cascade from native_schema) | 0.01 USD, 2m |
| 4 | ↳ describe | ask |  | agent tutorial-illustrator → fast (google/gemini-3.5-flash-lite); schema: description (cascade from tool_wrapper) | 0.01 USD, 2m |
| 5 | ↳ photo | image |  | gemini-image (google/gemini-3.1-flash-image), ratio 1:1 | 0.1 USD, 2m, retry 1 |
| 6 | out | output |  | name, slogan, photo |  |
```

(The CLI also prints the path to `plan.md` after the plan, and after a run the
path to `summary.md` and the `report:` address. I leave those lines out of the
outputs below.)

The fixture `fake/tutorial-04-parallel.yaml`:

```yaml
# Scripted responses for tutorial-04-parallel.
# The image step needs nothing: the fake provider produces a grey PNG in the aspect_ratio.
propose:
  - json:
      names: ["Oatsy", "Frost Oat", "Frozen Field"]
slogan:
  - json:
      slogan: "Ice cream that grows in the field"
describe:
  - json:
      description: "A pint of oat milk ice cream on a clean white background, soft light, front view, no text."
```

```bash
agencast run workflows/scenarios/tutorial-04-parallel.yaml -i product="vegan ice cream made from oat milk" --fake fake/tutorial-04-parallel.yaml
```

```
run 20260925-151749-tutorial-04-parallel-85a6: succeeded · 0.0 s · 0.0403 USD
```

The fake image “costs” 0.04 USD so that you can try out budgets (step 6).
It isn't paid for.

---

## Step 4 — a live run with an image

```bash
agencast run workflows/scenarios/tutorial-04-parallel.yaml -i product="vegan ice cream made from oat milk"
```

```
run 20260925-151755-tutorial-04-parallel-8c76: succeeded · 10.5 s · 0.0683 USD
run record: …/examples/tutorial/runs/20260925-151755-tutorial-04-parallel-8c76/summary.md
report: file:///…/outputs/20260925-151755-tutorial-04-parallel-8c76-6f88f7d39aeab16913150e899dfe8070/report.html
```

```
# tutorial-04-parallel — success

Concurrently comes up with a name and a slogan and photographs the product (tutorial, part 4)
Run `20260925-151755-tutorial-04-parallel-8c76` · 2026-09-25 15:17 UTC · 10.5 s · 0.0683 USD (of which images 0.0672 USD)

## Inputs
- product: vegan ice cream made from oat milk

## Steps
| # | Step | Type | Status | Time | Cost | Note |
|---|---|---|---|---|---|---|
| 1 | concurrent | parallel | ✓ | 10.5 s | 0.0683 |  |
| 2 | propose | ask | ✓ | 2.1 s | 0.0005 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 3 | slogan | ask | ✓ | 1.6 s | 0.0004 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 4 | describe | ask | ✓ | 1.2 s | 0.0002 | fast → google/gemini-3.5-flash-lite (tool_wrapper) |
| 5 | photo | image | ✓ | 9.2 s | 0.0672 | image.png, 1024×1024 |
| 6 | out | output | ✓ | 0.0 s | 0 |  |
| | Total | | | 10.5 s | 0.0683 | of which images 0.0672 |

## Warnings
none

## Output
- name: “Oat Paradise”
- slogan: “Oat Paradise - pure vegan sweetness without guilt”
- photo: file:///…/outputs/20260925-151755-tutorial-04-parallel-8c76-6f88f7d39aeab16913150e899dfe8070/photo.png
```

What you can read from it:

- **Concurrency works:** the steps in the branches took 2.1 + 1.6 + 1.2 +
  9.2 = 14.1 s in total, the whole `parallel` only 10.5 s. The `texts` branch
  finished while the photo was still being generated.
- **The image is 98 % of the cost** (0.0672 of 0.0683 USD). That is why it has
  its own limit.
- **1024×1024** — the 1:1 ratio checks out.
- **`photo`** is a `file://` path, because `config.yaml` has
  `storage.type: local` — the file was copied to `outputs/`. The image
  itself is also in the run folder: `steps/05-photo/image.png` (ours: a white
  bowl with a scoop of ice cream on a light grey background).

Concurrency is visible in `events.jsonl` too (time, event, step, branch):

```
15:17:55.402 step_started concurrent
15:17:55.402 step_started propose texts
15:17:55.416 step_started describe visual
15:17:56.655 step_finished describe
15:17:56.656 step_started photo visual
15:17:57.514 step_finished propose
15:17:57.514 step_started slogan texts
15:17:59.097 step_finished slogan
15:18:05.886 step_finished photo
15:18:05.886 step_finished concurrent
```

(I pulled this listing out of `events.jsonl` with a short Python script;
the `events.jsonl` format is covered in part 5.)

---

## Step 5 — error classes

Every error has a **class**. It tells the framework whether retrying makes
sense, and it tells you (or the caller) what to do:

| Class | What happened | Retried? |
|---|---|---|
| `transient` | overload (HTTP 429), an outage, 5xx, an empty response | yes (`retry`) |
| `schema` | the model's JSON does not match the `schema` (part 2) | yes (`retry`) |
| `content` | the model refused the content | no |
| `budget` | the money of the step, the agent or the run ran out | no |
| `timeout` | the time of the step or the run ran out | no |
| `config` | an error in the files, or HTTP 400/401/404 | no |
| `expression` | an expression failed at run time (parts 2, 3) | no |
| `fail` | your `fail` step (part 3) | no |

All the following examples are fake runs with a fixture saved in `/tmp/` —
they cost nothing.

### `transient` → retry

`/tmp/overload.yaml`:

```yaml
propose:
  - status: 429
    error: "Rate limit exceeded"
  - json:
      names: ["Oatsy", "Frost Oat", "Frozen Field"]
```

```bash
agencast run workflows/scenarios/tutorial-04-parallel.yaml -i product="ice cream" --fake /tmp/overload.yaml
```

```
run 20260925-151818-tutorial-04-parallel-42d6: succeeded · 0.0 s · 0.0403 USD
```

The run went through — the first attempt got HTTP 429, the second succeeded.
In `events.jsonl`:

```
{"ts":"2026-09-25T15:18:18.099Z","type":"error","step":"propose","class":"transient","message":"HTTP 429: Rate limit exceeded","attempt":1,"will_retry":true,"http_status":429}
```

In `summary.md` the warnings section says `none` — a rejected call costs
nothing, and a retry after `transient` is normal operation.

### `content` → the end

`/tmp/refusal.yaml`:

```yaml
photo:
  - refusal: "I can't generate this image."
```

```bash
agencast run workflows/scenarios/tutorial-04-parallel.yaml -i product="ice cream" --fake /tmp/refusal.yaml
```

```
content in step photo: model refused: I can't generate this image.
run 20260925-151818-tutorial-04-parallel-b318: failed · 0.0 s · 0.0403 USD
```

~~~
## Error
- class: `content`
- step: `photo`
- message:

```
model refused: I can't generate this image.
```

Run ended at step photo.
…
| 1 | concurrent | parallel | failed | 0.0 s | 0.0403 | see Error |
| 2 | propose | ask | ✓ | 0.0 s | 0.0001 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 3 | slogan | ask | ✓ | 0.0 s | 0.0001 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 4 | describe | ask | ✓ | 0.0 s | 0.0001 | fast → google/gemini-3.5-flash-lite (tool_wrapper) |
| 5 | photo | image | failed | 0.0 s | 0.0400 | see Error |
~~~

A refusal is not retried, even though the step has `retry: 1` — the same
prompt would end the same way. Note that the image generator itself hardly
refuses anything (not even real people). Content rules are therefore guarded by
the scenario — by Jev over the photo description, as
`workflows/scenarios/ig-post.yaml` does.

### When one branch fails

`/tmp/cancel.yaml` — `propose` gets HTTP 400 (a `config` error, not retried),
and the photo is still “generating” (`sleep: 1`):

```yaml
propose:
  - status: 400
    error: "Invalid request"
photo:
  - sleep: 1
```

```bash
agencast run workflows/scenarios/tutorial-04-parallel.yaml -i product="ice cream" --fake /tmp/cancel.yaml
```

```
config in step propose: HTTP 400: Invalid request
run 20260925-151846-tutorial-04-parallel-9332: failed · 0.0 s · 0.0001 USD
```

```
| 1 | concurrent | parallel | failed | 0.0 s | 0.0001 | see Error |
| 2 | propose | ask | failed | 0.0 s | 0 | see Error |
| 4 | describe | ask | ✓ | 0.0 s | 0.0001 | fast → google/gemini-3.5-flash-lite (tool_wrapper) |
| 5 | photo | image | cancelled | 0.0 s | 0 |  |
| | Total | | | 0.0 s | 0.0001 |  |
```

An error in one branch **cancels the others** (`cancelled`) and the run ends.
Step 3 (`slogan`) is missing from the table — the run never got to it, and such
steps are not recorded.

---

## Step 6 — `budget_usd` and `timeout` in action

Let's try stricter limits. **Temporarily** change `budget_usd: 0.10` to
`budget_usd: 0.03` on the `photo` step (the fake image costs 0.04):

```bash
agencast run workflows/scenarios/tutorial-04-parallel.yaml -i product="ice cream" --fake fake/tutorial-04-parallel.yaml
```

```
run 20260925-151828-tutorial-04-parallel-3d22: succeeded · 0.0 s · 0.0403 USD
```

```
## Warnings
- budget for step 'photo' exceeded by 0.0100 USD (step photo)
```

The run went through! The rule: **the budget is checked before each call.**
A call that started under the limit is finished and paid (the money is spent
anyway) — and a warning is recorded. But the next call won't start. You'll see
that when the first attempt fails and `retry` would like to try a second one —
`/tmp/no-image.yaml`:

```yaml
photo:
  - finish_reason: error
```

```bash
agencast run workflows/scenarios/tutorial-04-parallel.yaml -i product="ice cream" --fake /tmp/no-image.yaml
```

```
budget in step photo: budget for step 'photo' exhausted (0.0400 of 0.03 USD)
run 20260925-151828-tutorial-04-parallel-13cb: failed · 2.0 s · 0.0403 USD
```

The whole story is in `events.jsonl`: the first attempt ended as `transient`
(`will_retry: true`), after waiting 2 s it was supposed to try again, but the
step budget was already gone → `budget`:

```
{"ts":"2026-09-25T15:18:28.324Z","type":"error","step":"photo","class":"transient","message":"provider returned HTTP 200 with finish_reason: error","attempt":1,"will_retry":true,"http_status":null}
{"ts":"2026-09-25T15:18:30.326Z","type":"error","step":"photo","class":"budget","message":"budget for step 'photo' exhausted (0.0400 of 0.03 USD)","attempt":null,"will_retry":false,"http_status":null}
```

Restore `budget_usd: 0.10`. Now **temporarily** change `timeout: 2m` to
`timeout: 2s` and let the fake image “generate” for 5 seconds —
`/tmp/slow.yaml`:

```yaml
photo:
  - sleep: 5
```

```bash
agencast run workflows/scenarios/tutorial-04-parallel.yaml -i product="ice cream" --fake /tmp/slow.yaml
```

```
timeout in step photo: timeout exceeded for step (2s)
run 20260925-151839-tutorial-04-parallel-a82b: failed · 2.0 s · 0.0003 USD
```

Restore `timeout: 2m`. The real generation took 9.2 s, so 2 minutes is a safe
margin.

---

## What you remember

- `parallel`: named branches run concurrently; you read outputs through the
  step `id`s; you don't read into another branch; an error in one branch
  cancels the others.
- `image`: an image model alias, `aspect_ratio` in quotes, output
  `steps.<id>.file`. An image ≈ 0.07 USD.
- `budget_usd` is checked **before** a call; `timeout` cuts a step off;
  `retry` repeats only `transient` and `schema`.
- The error class in `summary.md` tells you what to do: for `transient` try
  again later, for `content` change the prompt, for `budget`/`timeout` adjust
  the limit, for `config` fix the file.

---

## Exercise

The image is a “bonus”: when it fails (say the model refuses it), you still
want at least the name and the slogan, and the run should end in **success**
with a warning. Modify the scenario so that `photo` is `null` in that case.
Save it as `workflows/scenarios/tutorial-04-exercise.yaml` with a fixture and
verify it with a fake run with a refused image.

Hint: `on_error` and `default` from [scenario.md §3](../spec/scenario.md#3-common-step-properties).

<details>
<summary>Solution</summary>

```bash
diff workflows/scenarios/tutorial-04-parallel.yaml workflows/scenarios/tutorial-04-exercise.yaml
```

```
2,3c2,3
< name: tutorial-04-parallel
< description: Concurrently comes up with a name and a slogan and photographs the product (tutorial, part 4)
---
> name: tutorial-04-exercise
> description: Concurrently comes up with a name and a slogan and photographs the product (tutorial, part 4 — exercise solution)
18c18
<     description: Product photo 1:1
---
>     description: Product photo 1:1 (null if it failed)
48a49,50
>           on_error: continue
>           default: { file: null }
```

- `on_error: continue` — an error in the step does not end the run.
- `default: { file: null }` — the output of the step when it fails. It must
  contain all the output fields (`image` has only `file`). A `null` from an
  explicit `default` may be put into the output — you chose it knowingly.

The fixture `fake/tutorial-04-exercise.yaml` is the same as for the main
scenario (the golden test verifies the success path):

```yaml
# Scripted responses for tutorial-04-exercise (exercise solution from part 4).
# The image step needs nothing: the fake provider produces a grey PNG in the aspect_ratio.
propose:
  - json:
      names: ["Oatsy", "Frost Oat", "Frozen Field"]
slogan:
  - json:
      slogan: "Ice cream that grows in the field"
describe:
  - json:
      description: "A pint of oat milk ice cream on a clean white background, soft light, front view, no text."
```

A refused image, `/tmp/refusal-exercise.yaml`:

```yaml
propose:
  - json:
      names: ["Oatsy", "Frost Oat", "Frozen Field"]
slogan:
  - json:
      slogan: "Ice cream that grows in the field"
photo:
  - refusal: "I can't generate this image."
```

```bash
agencast validate workflows/scenarios/tutorial-04-exercise.yaml
agencast run workflows/scenarios/tutorial-04-exercise.yaml -i product="ice cream" --fake /tmp/refusal-exercise.yaml
```

```
valid: tutorial-04-exercise (6 steps)
run 20260925-151900-tutorial-04-exercise-77d9: succeeded · 0.0 s · 0.0403 USD
```

```
| 5 | photo | image | failed, continuing | 0.0 s | 0.0400 | failed, default used |
| 6 | out | output | ✓ | 0.0 s | 0 |  |
| | Total | | | 0.0 s | 0.0403 | of which images 0.0400 |

## Warnings
- step photo failed (content: model refused: I can't generate this image.) — run continues with default (on_error: continue)

## Output
- name: “Oatsy”
- slogan: “Ice cream that grows in the field”
- photo: null
```

And in `callback.json`: `"status": "succeeded"`, `"photo": null` and the warning
in `"warnings"` — that way the caller knows to send the post without an image or hand
it back for manual work.

</details>

**Next part:** [From playground to production](05-from-playground-to-production.md).
