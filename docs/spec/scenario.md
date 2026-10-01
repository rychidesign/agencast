# Scenario format — specification v1

A scenario is a single file `workflows/scenarios/<name>.yaml`. It reads from
top to bottom: at the top what it receives (`inputs`) and what it returns
(`outputs`), below that the steps in the order in which they run.

Machine-readable form: [`schema/scenario.schema.json`](schema/scenario.schema.json).
Example: `examples/showcase/workflows/scenarios/ig-post.yaml`. Starting via webhook:
[webhook.md](webhook.md).

**How the file is read (B6):** as **YAML 1.2 core** — booleans are only
`true`/`false` (also `True`/`TRUE`), the words `yes`, `no`, `on`, `off` are
plain text, `4:5` is text (not a number), the date `2026-09-25` is text.
The same key twice in one map is a `config` error with a line number.
Only files directly in `workflows/scenarios/` are read; subdirectories are
ignored (useful e.g. for an archive). The examples are checked with the
same loading: [`tools/check.py`](tools/check.py). Run it from the
repository root with
`uv run --project framework python docs/spec/tools/check.py`.

Notation: **proposal** = not covered by DESIGN.md; a proposed default
behavior awaiting approval. § numbers refer to `docs/DESIGN.md`.

Contents:
1. [Scenario header](#1-scenario-header)
2. [How a scenario runs](#2-how-a-scenario-runs)
3. [Common step properties](#3-common-step-properties)
4. [Step types](#4-step-types) — `ask`, `task`, `jev`, `image`, `parallel`,
   `switch`, `call`, `set`, `fail`, `output`
5. [Values: `{{ }}` templates and expressions](#5-values---templates-and-expressions)
6. [Errors](#6-errors)
7. [What `validate` checks](#7-what-validate-checks)

---

## A complete small example

```yaml
version: 1
name: greeting
description: Writes a short greeting and returns it

inputs:
  name: { type: string, required: true }

outputs:
  text: { type: string }

steps:
  - id: write
    ask:
      agent: copywriter
      prompt: "Write a one-sentence greeting for {{ inputs.name }}."

  - id: out
    output:
      text: "{{ steps.write.text }}"
```

---

## 1. Scenario header

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `version` | yes | Version of the scenario format (R7). Only `1` so far. | `validate`: `config` error. | `version: 1` |
| `name` | yes | Scenario name; matches the file name without `.yaml`. The scenario is started and called (`call`) by this name. Lowercase letters, digits, hyphen. | `config` error. | `name: ig-post` |
| `description` | yes | One sentence for humans: what the scenario does. Appears in `summary.md`. | `config` error. | `description: Draft an IG post for approval` |
| `inputs` | no | What the scenario receives from outside (webhook, CLI, `call`). See below. | The scenario has no inputs. | see below |
| `outputs` | no | What the scenario returns — the contract for the callback and for `call` (§5.3). The values are supplied by the `output` step. When present, it has at least one entry. | The scenario returns nothing (the callback carries only the status). | see below |
| `callable` | no | `true` = another scenario may call this scenario with a `call` step. Every scenario can be started via webhook/CLI. Protects approvals: part 1 must not call part 2 (publishing) and bypass n8n (DESIGN §5.2). | `false` — a `call` to this scenario is a `config` error. | `callable: true` |
| `steps` | yes | List of steps. At least one. | `config` error. | see [§4](#4-step-types) |

No other top-level fields are allowed — a typo is an error, not a silently
ignored field. The same applies in every step.

### `inputs`

Every input has a name (lowercase letters, digits, `_`) and a description:

```yaml
inputs:
  topic:
    type: string
    required: true
    description: What the post should be about
  language:
    type: string
    default: en
```

| Input field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `type` | yes | Value type: `string`, `number`, `integer`, `boolean`, `list`, `object`, `file` (one image) and `files` (1–16 images; since 0.18.0). An image comes as a path from the CLI (`-i photo=a.jpg`; for `files` a JSON list or one path) or from Python (`Path`), or as a `file` value from `call`; a webhook cannot send files yet. PNG, JPEG, WebP, GIF or AVIF, at most 10 MB each — checked and copied into the run directory before the run starts (see [Type `file`](#type-file)). The value from outside is checked against the type before the run starts. | `config` error. | `type: string` |
| `required` | see text | `true` = the input must come from outside. | — | `required: true` |
| `default` | see text | Value when the input does not come. Must match `type`. | — | `default: en` |
| `description` | no | Explanation for humans. | Nothing. | `description: What to write about` |

Rule: every input has **either** `required: true` **or** `default` — never
both and never neither. Thanks to that the value of an input is never
“unknown”. A missing or wrong input at start → the run does not start at
all: the webhook responds immediately with HTTP 422 without a `run_id` and
without a callback ([webhook.md](webhook.md)), the CLI ends with a
`config` error.

### `outputs`

```yaml
outputs:
  caption:  { type: string, description: Post text }
  hashtags: { type: list }
  image:    { type: file, description: Photo — a URL in the callback }
```

| Output field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `type` | yes | As for inputs, including `file` (an image from an input or an `image` step) and `files` (a list of them; since 0.18.0 — every file gets its own URL in the callback, stored as `<name>-1`, `<name>-2`, …). | `config` error. | `type: file` |
| `description` | no | Explanation for humans. | Nothing. | |

A value of type `file` is uploaded at the end of the run to the storage
from `config.yaml`, and the callback carries a URL instead (§5.7). When the
scenario runs via `call`, the file is not uploaded — it is passed to the
calling scenario as a `file`. Rules for `file`: see [Type `file`](#type-file).

---

## 2. How a scenario runs

- Steps run **one after another** in the order they are written. Exception:
  branches inside `parallel`.
- A step sees the outputs only of steps that are **above it** in the file
  (and that ran or have a `default`).
- The run ends when:
  - an `output` step finishes → status `succeeded`,
  - a `fail` step finishes or a step fails → status `failed`,
  - the steps run out and the scenario has no `outputs` → status `succeeded`.
- The callback is **always** sent once the run has a `run_id` (D2), see
  [run-record.md](run-record.md#callback).
- Steps the run did not reach after a failure are not recorded;
  `summary.md` says “Run ended at step X.”

The output of a step is available as `steps.<id>.<field>`. What each step
type returns:

| Step | Output |
|---|---|
| `ask`, `task` without `schema` | `steps.<id>.text` — the response as text |
| `ask`, `task` with `schema` | fields from the schema, e.g. `steps.copy.caption` |
| `jev` | `steps.<id>.<question>` — the value; `steps.<id>.details.<question>` — probabilities etc. |
| `image` | `steps.<id>.file` — the saved image (type `file`) |
| `set` | named values, e.g. `steps.texts.length` |
| `call` | `outputs` of the called scenario |
| `parallel`, `switch`, `fail`, `output` | nothing (outputs belong to the steps inside the branches) |

---

## 3. Common step properties

Every step is an item of the `steps` list with its `id`, **exactly one**
step type key (`ask:`, `jev:`, …) and optionally common properties:

```yaml
- id: photo                 # step name
  when: steps.tone_check.on_brand >= 0.7
  timeout: 3m
  budget_usd: 0.10
  retry: 1
  on_error: continue
  default: { file: null }
  image:                   # step type and its fields
    model: gemini-image
    prompt: "{{ steps.photo_prompt.photo_description }}"
```

| Property | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `id` | yes | Step name; the output (`steps.<id>`) and the directory in the run record are under it. Lowercase letters, digits, `_`, starts with a letter; unique across the whole file (also inside branches). Must not be a Python keyword (`and`, `or`, `not`, `in`, `is`, `if`, …), otherwise it could not be used in an expression. | `config` error. | `id: copy` |
| `when` | no | Condition (an [expression](#expressions)). `false` → the step is skipped and the record has the reason `when: <expression> → false`. The result must be `true`/`false`, not text or a number. An error in `when` is an error of the step — the step's `on_error` covers it. | The step always runs. | `when: inputs.language == "en"` |
| `timeout` | no | Maximum step duration, format `<number>s`, `m`, `h`. Exceeding it → error of class `timeout`. For `parallel` and `call` = time from the start to the end of the last step inside. | Default: `ask` 2m, `task` 15m, `jev` 30s, `image` 3m (**proposal**); for an agent at most its `limits.timeout`. The limit of the whole run always applies too. | `timeout: 90s` |
| `budget_usd` | no | How many USD the step may cost (all calls including retries). For `parallel` and `call` = the sum of all steps inside. Checking rules: see [Budget](#budget). Exceeding it → error of class `budget`. | For `ask`/`task` the agent's budget; otherwise only the run budget. | `budget_usd: 0.10` |
| `retry` | no | How many times **one API call** is retried on a `transient` or `schema` error (§5.1). For `task` it applies to each turn separately; retries do not count towards `max_turns`, only towards `budget_usd`. Delay 2 s, 4 s, 8 s…, or according to the `Retry-After` header. | `2` (**proposal**). | `retry: 0` |
| `on_error` | no | `fail` = a step error ends the run. `continue` = the run continues, the step has the output `default` and the run summary has a **warning** (§5.1 item 4). | `fail`. | `on_error: continue` |
| `default` | see text | Output of the step in case the step does not run (skipped via `when`, a `switch` branch not taken, failed with `on_error: continue`). Must contain **all** output fields of the step (for `jev` all questions; `details` is filled in as `{}` automatically); a missing field is a `validate` error. | If another step refers to the output of a step that might not run, it is a `validate` error (§5.4). | `default: { on_brand: 0 }` |
| `dedupe_key` | no | Only for `task` (a step with a side effect, e.g. publishing). A template that produces text. Ensures the side effect happens at most once, even when n8n repeats the run — see [dedupe](#dedupe_key--once-and-only-once). (§5.2) | The step runs every time. | `dedupe_key: "ig-{{ inputs.post_id }}"` |
| `schema` | no | Only for `ask` and `task`; written **inside** the step block. See [`ask`](#ask). | The output is text. | |

Where each property makes sense (elsewhere it is a `config` error):

| | `when` | `timeout` | `budget_usd` | `retry` | `on_error` | `default` |
|---|---|---|---|---|---|---|
| `ask`, `task`, `jev`, `image` | yes | yes | yes | yes | yes | yes |
| `call` | yes | yes | yes | — | yes | yes |
| `parallel` | yes | yes | yes | — | — | — |
| `set` | yes | — | — | — | — | yes |
| `switch`, `fail` | yes | — | — | — | — | — |
| `output` | — | — | — | — | — | — |

Why only these combinations (and not “any step” from D1d): see
OPEN-QUESTIONS 13.

### `dedupe_key` — once and only once

Dedupe is the only exception to the rule “runs do not share files” (D2,
like `state`; OPEN-QUESTIONS 12):

- Every key is a **separate file**
  `<runs>/_dedupe/<sha256(scenario + "/" + step id + "/" + key)>.json`,
  created atomically (“create only if it does not exist”). Never a single
  shared log. The key is thus bound to the scenario and the step — the
  same text in another scenario does not get mixed up.
- Content: `{"state": "started" | "succeeded", "run_id": "…", "output": {…}}`.
- `started` is created **before the step's first tool call**; `succeeded`
  (with the output) after the step finishes successfully.
- On the next run:
  - `succeeded` → the step is not executed, the output is taken from the
    file, the record has `step_skipped` with the reason `dedupe`;
  - `started` without `succeeded` → the step is **not run**, `config`
    error: “step may have run only partially (dedupe_key …, run …), check
    manually and delete `<runs>/_dedupe/<…>.json`”. Nothing is silently
    repeated.
- A fake run (`--fake`) uses the same structure in `<runs>/_dedupe-fake/`;
  live and fake runs never read each other's records — a fabricated output
  must not skip a live side effect (since framework 0.2.2).

---

## 4. Step types

### `ask`

A single model call through an agent, without tools (D1b).

```yaml
- id: copy
  ask:
    agent: copywriter
    prompt: "Write an IG post about: {{ inputs.topic }}"
    schema:
      caption: string
      hashtags: [string]
      image_idea: string
```

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `agent` | yes | Name of an agent from `workflows/agents/`. The agent provides the model, instructions and skills (in `ask` inserted in full, see [agent.md](agent.md#how-the-system-prompt-is-built)). | `config` error. | `agent: copywriter` |
| `prompt` | yes | Message for the model (a [template](#templates--)). | `config` error. | `prompt: "Topic: {{ inputs.topic }}"` |
| `images` | no | Images the model sees with the message (since 0.18.0): one template or a list of templates, each leading to a `file` or a list of files (an input, `steps.<id>.file` from an `image` step, a `set` value). The message carries the prompt, then `Image 1 (photo.png, 1024×768):` and the image for each one, so the model can refer to them by number. At most 16; text instead of a file is a `validate` error; a `null` from an explicit `default` is skipped; an AVIF or SVG file is a `config` error at run time (see [Type `file`](#type-file)). `validate` checks (online) that the agent's model accepts image input. The record keeps `<file: inputs/photo.png, 12345 B>` instead of the data. | The message is plain text. | `images: ["{{ inputs.photo }}"]` |
| `schema` | no | Shape of the JSON the model must return. The framework enforces it with a cascade (native schema → tool wrapper → prompt + check, §5.5); an invalid response is a `schema` error and is retried with the error as feedback. | The output is `steps.<id>.text`. | see below |

`schema` notation (shorthand, **proposal**; the framework turns it into a
JSON Schema with `strict: true`):

| Notation | Means |
|---|---|
| `string`, `number`, `integer`, `boolean` | a value of the given type |
| `[string]` | a list of values of type `string` (works with every type) |
| nested map `{ a: string, b: number }` | an object with these fields |

**The root of `schema` is always a map** (the output is read as
`steps.<id>.<field>` and providers want an object as the root). All fields
are required, no other fields are allowed. A description of what a field
should contain belongs in the `prompt` or the agent's instructions.

#### Structured output cascade (§5.5)

- The level starts at `models.<alias>.structured_output` from
  `config.yaml`: `native_schema` (native JSON schema) | `tool_wrapper`
  (a tool as a wrapper) | `prompt` (description in the prompt + check).
  Default `native_schema`; the value is set by the project owner according
  to the alias's conformance scenario.
- After a `schema` error the next attempt goes **one level down**. The
  attempt counts towards `retry`. The level used is in the record
  (`model_call.structured_output`).
- At the `tool_wrapper` level the correct response is a call of the tool
  `_submit_output` with arguments according to `schema` (`finish_reason:
  tool_calls`). In `task` this call ends the loop. `_submit_output` is
  never sent to an MCP server and is not subject to the tool allowlist.

When `ask` succeeds (§5.1 item 8 — **HTTP 200 is not enough**): the
response has `finish_reason: stop` (at the `tool_wrapper` level
`tool_calls` with a call of `_submit_output`), non-empty content, and if
there is a `schema`, the content can be parsed and matches the schema.
What happens otherwise: see [§6](#6-errors).

### `task`

An autonomous agent: a model ↔ tools (MCP) loop with limits (D1b).

```yaml
- id: publish
  dedupe_key: "ig-publish-{{ inputs.post_id }}"
  budget_usd: 0.10
  task:
    agent: publisher
    prompt: |
      Publish the post.
      Text: {{ inputs.caption }}
      Image: {{ inputs.image_url }}
    max_turns: 4
    tools: { instagram: [create_media, publish_media] }
    schema: { post_url: string }
```

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `agent` | yes | Agent; its `mcp`, `tools` and `limits` are the **maximum** (§5.2). | `config` error. | `agent: publisher` |
| `prompt` | yes | The task assignment (a [template](#templates--)). | `config` error. | |
| `images` | no | As for `ask`: images sent with the first message (since 0.18.0). | The message is plain text. | `images: "{{ inputs.photos }}"` |
| `max_turns` | no | At most this many **turns** (model responses processed by the loop; retries after `transient`/`schema` do not count). May only be less than or equal to the agent's `limits.max_turns`. | The agent's `limits.max_turns` applies. An agent without `limits.max_turns` in `task` is a `config` error — so a turn limit always exists (§5.1 item 6). | `max_turns: 4` |
| `mcp` | no | A subset of the agent's `mcp`. | All of the agent's servers. | `mcp: [instagram]` |
| `tools` | no | Narrowing of the tools on a server (a subset of what the agent allows). | Tools according to the agent. | `tools: { instagram: [publish_media] }` |
| `schema` | no | Shape of the final response, same as for `ask`. | `steps.<id>.text`. | |

The loop ends when the model responds without a tool call (`finish_reason:
stop`), or calls `_submit_output` (cascade, see [`ask`](#ask)).
Reaching `max_turns` without a final response → error of class `budget`.
The model sees only allowed tools (agent ∩ step ∩ `mcp.yaml`) and the
`load_skill` tool if the agent has skills ([agent.md](agent.md)).

MCP servers and tool errors (DESIGN §5.8):

- Stdio servers start **once per run**, at the first `task` that needs
  them, and `parallel` branches share them. They are shut down at the end
  of the run.
- A tool returns `isError` → the result goes to the model, the step
  continues.
- Arguments from the model do not match the tool schema → the tool does
  not run, the model gets the validation error as the result (the turn
  counts).
- Tool call timeout (`mcp.yaml` → `timeouts.call`) → the step fails, class
  `timeout` (the tool may have run — hence `dedupe_key`).
- Failure to start the server or of the handshake → `transient` (network,
  5xx), otherwise `config` (the process is not running, 401, unknown
  command).
- An image in a tool result is saved as a file
  (`steps/<nn>-<id>/tool-<NN>-<k>.png`) and goes to the model in a user
  message right after the tool message; the tool message contains only
  the text “image in the next message: tool-<NN>-<k>.png” (Gemini rejects
  an image in a tool message).

### `jev`

A decision via Jev (OpenRouter `POST /api/v1/systemone`, DESIGN §9).
Cheap (~0.00003 USD) and fast (~0.3 s).

```yaml
- id: tone_check
  jev:
    state: "{{ steps.copy.caption }}"
    questions:
      on_brand:
        type: noul
        instructions: Does the text match the tone of the Lumen brand?
      kind:
        type: choice
        instructions: What kind of post is it?
        criteria:
          product: Product introduction
          promotion: Discount or contest
```

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `state` | yes | The text Jev assesses (a [template](#templates--)). When the template yields a list or an object, it is inserted as JSON text — always safely (§5.4). | `config` error. | `state: "{{ steps.copy.caption }}"` |
| `questions` | yes | Questions; key = output name (like `id`; `details` is reserved). | `config` error. | |
| `questions.<q>.type` | yes | `noul` (yes/no as a number 0–1), `choice` (a choice of options), `score` (scale 0…n). | `config` error. | `type: noul` |
| `questions.<q>.instructions` | yes | The question for Jev. | `config` error. | |
| `questions.<q>.criteria` | for `choice` and `score` | `choice`: a map `option: description`; `score`: a list of descriptions of the levels from 0. Not allowed for `noul`. | `config` error. | see the example |

Output:

| | Type | Example |
|---|---|---|
| `steps.<id>.<q>` for `noul` | `number` 0–1 | `0.97` |
| `steps.<id>.<q>` for `choice` | `string` (a key from `criteria`) | `"product"` |
| `steps.<id>.<q>` for `score` | `number` | `1.07` |
| `steps.<id>.details.<q>` | `object` — what else Jev returned (`probabilities`, `confidence`, `legend`) | `details.kind.probabilities.promotion` |

The threshold is always **explicit** in the scenario (`< 0.7`) — Jev has
no “correct” default threshold (DESIGN §9). The Jev model is in
`config.yaml` (`openrouter.jev_model`).

### `image`

Generates an image via OpenRouter and saves it to the run directory (§5.7).

```yaml
- id: photo
  image:
    model: gemini-image
    prompt: "{{ steps.photo_prompt.photo_description }}"
    aspect_ratio: "4:5"
```

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `model` | yes | Alias of an image model from `config.yaml`. | `config` error. A model alias without image output is caught by `validate` (§5.7). | `model: gemini-image` |
| `prompt` | yes | Image description (a [template](#templates--)). | `config` error. | |
| `images` | no | Reference images (since 0.18.0): one template or a list of templates, each leading to a `file` or a list of files — the model edits one image or composes a new one in the mood of several, depending on the prompt (refer to them as Image 1, 2, …). Only with an alias that has `api: images` (`input_references` of the Images API; the chat path with references is unverified) — otherwise a `validate` error; at most what the model accepts (`gemini-3.1-flash-image` 14). PNG, JPEG, WebP, GIF; the record keeps `<file: …>`. | Text-to-image. | `images: ["{{ inputs.photo }}"]` |
| `aspect_ratio` | no | Aspect ratio as the text `"width:height"`, `auto` or a template `"{{ inputs.aspect_ratio }}"` (for IG `"1:1"` or `"4:5"`). `auto` (since 0.18.0) = the aspect ratio of the first reference image in `images`, snapped to the nearest ratio the model supports (from `GET /images/models`; offline a built-in list; a model whose catalog lists no `aspect_ratio` gets none) — without references the model default. After saving, the framework compares the aspect ratio from the file header; a deviation > 2 % = `config` error (“model does not support aspect_ratio …”), nothing is silently cropped; for a ratio derived from a reference it is only a warning in the record. | With references `auto` (since 0.18.0); otherwise the model default (for `gemini-3.1-flash-image` 1408×768). | `aspect_ratio: "4:5"` |
| `quality` | no | Quality `auto`, `low`, `medium`, `high` or a template. | `models.<alias>.quality`, otherwise the model default. | `quality: "{{ inputs.quality }}"` |
| `resolution` | no | Resolution as the text `"512"`, `"1K"`, `"2K"`, `"4K"` or a template. | Model default. | `resolution: "1K"` |

Editing an uploaded photo (the ratio follows the photo unless the caller says
otherwise; `gemini-image-api` is an alias with `api: images`):

```yaml
version: 1
name: photo-edit
description: Re-renders an uploaded photo into a described scene, keeping its aspect ratio unless told otherwise
inputs:
  photo: { type: file, required: true }
  scene: { type: string, required: true }
  ratio: { type: string, default: auto, description: "auto = follow the photo; e.g. 9:16 overrides" }
outputs:
  image: { type: file }
steps:
  - id: edit
    image:
      model: gemini-image-api
      prompt: "Keep the subject exactly as in Image 1. New scene: {{ inputs.scene }}"
      images: ["{{ inputs.photo }}"]
      aspect_ratio: "{{ inputs.ratio }}"
  - id: out
    output:
      image: "{{ steps.edit.file }}"
```

Output `steps.<id>.file` — the file `steps/<nn>-<id>/image.png` in the run
directory. The record never contains base64, only the path (§5.7).

When the response contains no image: if `refusal` is non-empty or
`finish_reason: content_filter` → class `content`. Otherwise `transient`
(retried) and after `retry` is exhausted, class `content` with the message
“model returned no image”.

Careful: the provider does **not refuse** even likenesses of real people
(spike (a)). The content policy is enforced by the scenario — typically a
`jev` step over the prompt before `image` (see `ig-post.yaml`).

`aspect_ratio` is documented for the OpenRouter Image API
(`POST /api/v1/images`,
<https://openrouter.ai/docs/features/multimodal/image-generation>, verified
2026-09-27). The endpoint is determined by `models.<alias>.api` in
`config.yaml`: `chat` (default) uses chat completions with
`modalities: [image, text]`, `images` uses `POST /api/v1/images` and sends
`aspect_ratio`, `quality` and `resolution` directly. Quality precedence:
step > `models.<alias>.quality` > nothing. After templates are filled in,
the shape of the ratio and the listed enumerations are checked; an invalid
value ends with a `config` error showing the filled-in text. The chat API
sends the ratio via `image_config`, and ignores quality and resolution with
a warning in the run record (`summary.md` and events). The filled-in
parameters are also in the step's `prompt.md`. Static validation checks
fixed values against `supported_parameters` from `/images/models` if the
parameter lists `values`; it checks the `default` of an input in a single
template `{{ inputs.x }}` the same way. Validation on its own does not
support warnings; ignoring parameters of the chat API is reported only by
the run. The scenario format stays `version: 1`.

### `parallel`

Named branches that run concurrently within one run (D1d).

```yaml
- id: variants
  parallel:
    short:
      - id: short_text
        ask: { agent: copywriter, prompt: "Short text: {{ inputs.topic }}" }
    long:
      - id: long_text
        ask: { agent: copywriter, prompt: "Long text: {{ inputs.topic }}" }

- id: out
  output:
    short: "{{ steps.short_text.text }}"
    long: "{{ steps.long_text.text }}"
```

- The key under `parallel` is the **branch name** (lowercase letters,
  digits, `_`), the value is a list of steps that run one after another
  within the branch. At least two branches.
- **Naming outputs:** steps in branches have their own `id` (unique across
  the whole file) and their outputs are read normally via `steps.<id>`.
  The branch name serves only for readability and in the run record. The
  `parallel` step itself has no output.
- A step in a branch may read steps above `parallel` and steps above it in
  the **same** branch. A reference into another branch is a `validate`
  error (we do not know which one finishes first).
- The step after `parallel` starts once all branches have finished.
- When a step in a branch fails (without `on_error: continue`), the other
  branches are cancelled and the run ends `failed` (**proposal**). A
  started step cancelled this way gets `step_finished` with
  `status: cancelled` and the cost of the calls so far; a step that had
  not started gets `step_skipped` with the reason `cancelled`.
- When `parallel` is skipped (`when`), every step inside gets
  `step_skipped` with the same reason.
- There must be no `output` inside a branch.

### `switch`

Branching by value. `default` is **required** (D1d).

```yaml
- id: by_kind
  switch:
    value: steps.tone_check.kind
    cases:
      product:
        - id: product_text
          ask: { agent: copywriter, prompt: "Product text…" }
      promotion:
        - id: promotion_text
          ask: { agent: copywriter, prompt: "Promotion text…" }
    default:
      - id: unknown_kind
        fail: "Unknown kind of post: {{ steps.tone_check.kind }}"
```

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `value` | yes | An [expression](#expressions) whose result must be a `string`. `null` or another type = an `expression` error (not the `default` branch); when the type is known in advance, a `validate` error. | `config` error. | `value: steps.tone_check.kind` |
| `cases` | yes | A map `value: [steps]`. The steps under the value exactly equal to `value` run. At least one. | `config` error. | |
| `default` | yes | Steps when no value matches. A deliberate “do nothing” is `default: []`. | `config` error. | `default: []` |

- `cases` keys are always text (YAML 1.2: `yes`, `on` and `1` are text).
  When `value` is a `choice` answer from `jev`, `validate` checks that the
  `cases` keys are among the `criteria` keys.
- For numeric thresholds (`< 0.7`) use `when`, not `switch`.
- Steps in a branch that did not run (and in a whole skipped `switch`) are
  each recorded as skipped with the reason `switch: by_kind = "promotion"`.
  Whoever reads their output after the `switch` needs a `default` on them
  (§5.4).
- There must be no `output` inside a branch.

### `call`

Runs another scenario **within the same run** (§5.3).

```yaml
- id: propose
  call:
    scenario: ig-text        # ig-text.yaml has callable: true
    inputs:
      topic: "{{ inputs.topic }}"
```

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `scenario` | yes | Name of a scenario from `workflows/scenarios/` that has `callable: true` in its header. Otherwise a `config` error. | `config` error. | `scenario: ig-text` |
| `inputs` | no | Input values for the called scenario ([templates](#templates--)). | The called scenario gets only its `default` values. | `topic: "{{ inputs.topic }}"` |

Contract (§5.3):

- The output of the step is the `outputs` of the called scenario:
  `steps.propose.caption`.
- `validate` statically checks that the called scenario has
  `callable: true`, that the call provides all `required` inputs, no extra
  ones and with the correct types, and that only declared `outputs` are
  read. The type of an input that cannot be verified in advance is checked
  at `call`; a mismatch = `expression`.
- An input of type `file` or `files` is passed via `call` as a value (an image
  from one scenario to another); from outside it is a path (see [`inputs`](#inputs)).
- **Same run:** same budget and timeout, the record of the called scenario
  is a subdirectory `steps/<nn>-<id>/` (see [run-record.md](run-record.md)).
  The queue does not know about `call`.
- **Cycles** (A calls B, B calls A — also indirectly) are rejected by
  `validate`.
- The nesting **depth** is limited by `limits.max_call_depth` from
  `config.yaml` (default 3, **proposal**).
- Files (`file`) from the called scenario are not uploaded; only the
  top-level scenario uploads them, if it puts them in its `output`.
- A scenario **never starts a new framework run and never waits for one**
  (with a sequential queue it would deadlock). A new run can only be
  started “fire and forget” via n8n.

### `set`

Computes or transforms values without an LLM.

```yaml
- id: texts
  set:
    hashtag_line: join(steps.copy.hashtags, " ")
    length: len(steps.copy.caption)
    too_long: len(steps.copy.caption) > 2200
```

- Key = output name (`steps.texts.length`), value = an
  [expression](#expressions) (not a template). Numbers, `true`, `false`,
  `null` can be written directly; text as an expression must be in quotes
  inside the YAML: `label: '"new"'`.
- Values in one `set` do not refer to each other; if you need that, use
  two `set` steps in a row.

### `fail`

Deliberately ends the run with an error and a message.

```yaml
- id: stop
  when: steps.tone_check.on_brand < 0.7
  fail: "The text does not match the brand (on_brand = {{ steps.tone_check.on_brand }})"
```

The value of `fail` is the message (a [template](#templates--)). The run
ends `failed`, error class `fail` (**proposal** — a new class next to
§5.1, so that the callback can tell a deliberate stop from a malfunction),
the callback carries the step `id` and the message. Steps after an
unconditional `fail` in the same list are unreachable — a `validate`
error.

### `output`

What the run returns. The last step of the scenario.

```yaml
- id: out
  output:
    caption: "{{ steps.copy.caption }}"
    hashtags: "{{ steps.copy.hashtags }}"
    image: "{{ steps.photo.file }}"
```

- Keys = exactly those from `outputs` in the header, the types must match.
  A missing or extra key is a `validate` error.
- Values are [templates](#templates--) or fixed values; for an output of
  type `file` only a template that leads to a `file` (see
  [Type `file`](#type-file)).
- A failed upload of a file to storage = `transient` with retries, then the
  run is `failed`, class `transient`, step `output`.
- `output` may appear only once and only as the **last step** of the main
  `steps` list (not in branches, without `when`). A scenario with
  `outputs` must have it; a scenario without `outputs` must not have it.
  Different results depending on branches are handled with `default` and
  `set` before `output`.

---

## 5. Values: `{{ }}` templates and expressions

A scenario has two different notations (D1c). A simple rule:

| Where | Notation | Example |
|---|---|---|
| `when`, `switch.value`, values in `set` | **expression** — without braces | `steps.tone_check.on_brand < 0.7` |
| **only** in: `ask.prompt`, `task.prompt`, `ask.images`, `task.images`, `image.prompt`, `image.aspect_ratio`, `image.quality`, `image.resolution`, `jev.state`, `jev.questions.*.instructions`, `jev.questions.*.criteria` (values), `fail`, `output` values, `call.inputs`, `dedupe_key` | **template** — `{{ }}` only inserts a value | `"Topic: {{ inputs.topic }}"` |

`{{` anywhere else (names, `id`, step types, aliases, agents,
`max_turns`, `cases` keys, …) is a `validate` error.

### What is visible (names)

- `inputs.<name>` — scenario inputs.
- `steps.<id>.<field>` — outputs of steps above the current step.
- `item` is reserved for a future `foreach`; it does not exist in v1.

Nothing else (environment variables, files, configuration) is visible.
This way secret keys cannot get into a prompt, not even by mistake (§5.2).

### Templates `{{ }}`

- Inside `{{ }}` there may be **only a path to a value**, with the same
  rules as in expressions
  ([dot and square brackets](#path-to-a-value-dot-and-square-brackets)),
  e.g. `{{ steps.copy.hashtags[0] }}`. No operators or functions — any
  computation belongs in a `set` step.
- **The value is one whole template** (`"{{ steps.copy.hashtags }}"`) →
  the value is inserted **with its type** (a list stays a list, a number a
  number, a file a file).
- **A template inside text** (`"Topic: {{ inputs.topic }}"`) → the result is
  text; text is inserted unchanged, a number as a number (`0.62`), `true` /
  `false`, a list and an object as JSON.
- **`null` is not inserted silently.** A reference `{{ x }}` where `x` is
  `null` is an error — in `validate` (class `config`) when it can be
  detected in advance, otherwise at run time (class `expression`). This
  applies to a whole value and to a template in text. The only exception:
  the `null` comes from an explicit `default` of a step (the author chose
  it deliberately) — then `null` is inserted, in text as `null` (the same
  as `str(null)`). (§5.4; coordinator decision, see OPEN-QUESTIONS 10.)
- The result of a template is **never evaluated again** (§5.4): when the
  model writes `{{ inputs.x }}` into its text, it stays literally.
- Templates are evaluated over already-loaded YAML, so quotes or braces in
  text from the model cannot break the structure of the step or the JSON
  for Jev (§5.4). A scenario never builds JSON by hand.
- A literal `{{` cannot be written in v1 (**proposal**; it will be added
  when needed).

### Expressions

Safely evaluated Python-style expressions (D1c). This part describes the
**language** — what a scenario author may write and what happens.
Expressions are evaluated by the framework's own small evaluator (decision
after spike (c), report on the `spike-expressions` branch; the spike was
removed from the tree, its outputs are in the repository history up to
commit fe90e05); Python is never executed.

#### What the language has

| What | Example |
|---|---|
| path to a value | `steps.copy.caption`, `steps.copy.hashtags[0]`, `steps.copy.hashtags[-1]` |
| literals: text, number, `true`, `false`, `null` | `"en"`, `'en'`, `0.7`, `3`, `true`, `null` |
| list literal | `["en", "fr"]` |
| comparison | `==`, `!=`, `<`, `<=`, `>`, `>=` |
| contains | `in` — an item in a list, a substring in text: `inputs.language in ["en", "fr"]` |
| logic | `and`, `or`, `not` — only over `true`/`false` |
| arithmetic | `+`, `-`, `*`, `/`, `%` (`+` also joins two texts) |
| parentheses | `(a or b) and c` |
| functions | only `len`, `min`, `max`, `round`, `str`, `int`, `float`, `join` (below) |

The literals `true`, `false`, `null` are written the same as in YAML and
JSON, not Python's `True`/`False`/`None` (decided, OPEN-QUESTIONS 7).
`True` or `None` is an unknown name → `validate` error.

#### What the language does not have

A `validate` error, the run does not start: the conditional `x if c else y`,
slices `xs[1:3]`, exponentiation `**`, method calls (`"x".upper()`,
`steps.copy.caption.lower()`), assignment (`=`, `:=`), `lambda`,
comprehensions (`[x for x in …]`), attributes and dunders (`__class__`),
`import`, functions other than those in the table, `{{ }}` inside an
expression.

#### Path to a value: dot and square brackets

- **A dot reads a key from an object**, nothing else. `steps.copy.hashtags`
  works even for steps and fields named `copy`, `items`, `keys`, `get`,
  `values` … (a dot never reaches into Python internals).
- **Square brackets** are an index into a list (also negative: `[-1]` =
  the last item) or an object key as text:
  `steps.tone_check.details["on_brand"]`.
- A missing key or an index out of range is an error (see below), never a
  silent `null`.

#### Types (§5.4)

- The types `string`, `number` (integer and decimal), `boolean`, `null`,
  `list`, `object`, `file` do not mix. Conversion must be explicit:
  `float(x)`, `int(x)`, `str(x)`.
- **Comparison across types is an error** (`==` and `<`):
  `steps.tone_check.on_brand < "0.7"`, `inputs.limit == "3"`. The only
  exception: `x == null` and `x != null` are allowed for every type. When
  the types are not known in advance, the error is detected only at run
  time (OPEN-QUESTIONS 14).
- **`and`, `or`, `not` take only `true`/`false`.** No Python “truthiness”
  of text, numbers or lists: `steps.copy.hashtags and …` is an error with
  advice to write a comparison, e.g. `len(steps.copy.hashtags) > 0`.
  (Coordinator decision, OPEN-QUESTIONS 8.)
- **`boolean` is not a number:** `true + 1` is an error.
- **Operators and types:** `-`, `*`, `/`, `%` only number with number
  (`"a" * 3` is an error). `+` only number + number, text + text, list +
  list. **Text + number is an error:** `"on_brand = " + 0.9` → write
  `"on_brand = " + str(0.9)`. A resulting text or list longer than
  100,000 characters/items = `expression` error.
- **`/` always gives a decimal number:** `7 / 2` = `3.5`, `4 / 2` = `2.0`.
  `%` is the remainder after division. Division by zero is an error.
- **`x in y`:** `y` is a list (the items must have the type of `x`,
  otherwise an error — `3 in ["3"]` is an error, not `false`), text (`x` is
  text, a substring is searched for) or an object (`x` is text, a key is
  searched for).
- **Numbers:** an integer and a number with a zero fractional part (`2.0`)
  are accepted where an `integer` is expected. `nan` and infinity are not
  allowed — a result that would be one is an `expression` error. A number
  in text (template, `str`) has the shortest notation that reads back the
  same: `0.1 + 0.2` → `0.30000000000000004`, `4 / 2` → `2.0`.
- `when` and `switch.value` must give a `boolean` and a `string`,
  respectively.

#### Functions

| Function | What it does | Types |
|---|---|---|
| `len(x)` | length | `string`, `list`, `object` → `number` |
| `min(a, b, …)`, `max(a, b, …)` | smallest / largest | numbers (or one list of numbers) → `number` |
| `round(x)`, `round(x, n)` | rounds to `n` decimal places; `round(x)` without `n` gives an integer (`round(2.5)` = `3`, not `3.0`) | `number` → `number` |
| `str(x)` | conversion to text | anything → `string` |
| `int(x)` | cuts off the fractional part of a number (`int(2.7)` = `2`); from text accepts only an integer (`int("3")` = `3`, `int("2.7")` is an error) | `number`, `string` → `number` |
| `float(x)` | conversion to a decimal number (`float("0.7")`) | `number`, `string` → `number` |
| `join(list, separator)` | joins a list of texts | `list` of texts, `string` → `string` |

- **`round` rounds half away from zero:** `round(2.5)` = `3`,
  `round(-2.5)` = `-3`, `round(0.125, 2)` = `0.13`. This is an **explicit
  deviation from Python** (which rounds half to even: `round(2.5)` = `2`),
  because a scenario author expects school rounding. (Coordinator
  decision, OPEN-QUESTIONS 9.)
- `str` gives the same text as a template: `str(null)` = `"null"`,
  `str(true)` = `"true"`, `str(0.62)` = `"0.62"`.
- Functions check the types of their arguments; a wrong type is an error
  with a message.

#### Limits

An expression has at most **2000 characters** — checked **before** the
expression is parsed, so not even a huge expression can bring the framework
down. The nesting depth (parentheses, operators) is at most **100** —
checked after parsing, before evaluation. A resulting text or list has at
most 100,000 characters/items.

#### When an expression error is detected

| When | What | Class | Consequence |
|---|---|---|---|
| `validate` (statically, before the run) | syntax; a forbidden construct; an unknown function or name (`True`, `open`); an exceeded limit; a reference to a non-existent step, to a step below or in another `parallel` branch; a reference to a step that might not run, without `default`; an unknown field of a step whose output is known (`schema`, `jev`, `set`, `outputs` with `call`); a comparison or operation across types when the types are known in advance; `null` in a template when it is visible in advance | `config` | the run does not start at all |
| at run time | a missing key (e.g. in `details` from Jev), a wrong value type, an index out of range, division by zero, the conversion `int("abc")`, `nan`/infinity, a result that is too long, `null` in a template, `switch.value` is not text | `expression` | the step fails, **is not retried**; the run ends `failed` (like a `fail` step), unless the step has `on_error: continue` |

#### Error messages

Messages are in English, show the expression, mark the error position with
a caret `^` and, for a missing key, list the available keys. Examples:

```
config: ig-post.yaml: step "stop", when: comparing number with string — convert the type explicitly (float(), str())
  steps.tone_check.on_brand < "0.7"
                              ^
```

```
expression in step summary: set.certainty: 'steps.tone_check.details.kind' has no key 'probability' (available: probabilities, confidence)
  steps.tone_check.details.kind.probability
                                ^
```

```
config: ig-post.yaml: step "by_length", when: 'and' requires true/false, got list — compare explicitly (e.g. len(x) > 0)
  steps.copy.hashtags and inputs.language == "en"
  ^
```

#### YAML pitfalls

Wrap an expression that starts with a quote, `[` or `{`, or contains `: `
or ` #`, entirely in single quotes: `when: '"x" == inputs.language'`,
`when: '["en", "fr"] == inputs.languages'`.

### Type `file`

- A `file` value is created by an `image` step, by an image returned by a tool
  in `task` and (since 0.18.0) from an input of type `file`/`files`: the
  framework checks the file (format, size), copies it into the run directory as
  `inputs/<name>.<ext>` (`inputs/<name>-1.<ext>`, `-2`, … for `files`) and the
  scenario sees only that copy. It cannot be created from text: text in a place
  where a `file` is expected (`image: "/home/x/.env"`) is a `validate` error.
- The path is always inside the run directory; the framework verifies this
  before uploading or sending the file to a model (the real path after
  resolving links). Otherwise a `config` error.
- **Metadata** (since 0.18.0): `width`, `height` (pixels, after EXIF
  orientation) and `format` (the MIME subtype: `png`, `jpeg`, `webp`, `gif`,
  `avif`; an `image` step can also return `svg+xml`) are read with a dot or
  `["key"]`: `inputs.photo.width > inputs.photo.height`,
  `{{ steps.photo.file.format }}`. Any other key is a `validate` error; an
  unknown dimension (an SVG from an `image` step) is an `expression` error at
  run time. In text and in the callback a `file` is still its path (or URL);
  a `file` inside a `list` or `object` output is its path; `==` compares paths.
- **Sending to a model** (`images:`): PNG, JPEG, WebP and GIF go as they are.
  AVIF and SVG are accepted as inputs and as outputs (metadata, pass-through),
  but the framework has no image decoder, so sending one to a model is a
  `config` error — convert it to PNG/JPEG/WebP first.
- A list of files (a `files` input, `[inputs.a, steps.gen.file]` in `set`) is
  an ordinary list: `len()`, indexing (`inputs.photos[steps.pick.n - 1]` in
  `set`), `images:` of a step, a `files` output.
- `file: null` from an explicit `default` goes to the callback as `null`
  (nothing is uploaded).

```yaml
version: 1
name: photo-caption
description: Caption for an uploaded photo; the photo is returned as it is
inputs:
  photo: { type: file, required: true, description: "PNG, JPEG, WebP, GIF or AVIF" }
outputs:
  caption: { type: string }
  photo:   { type: file }
  wide:    { type: boolean }
steps:
  - id: shape
    set: { wide: inputs.photo.width > inputs.photo.height }
  - id: copy
    ask:
      agent: copywriter
      prompt: "Write a one-line Instagram caption for Image 1."
      images: ["{{ inputs.photo }}"]
  - id: out
    output:
      caption: "{{ steps.copy.text }}"
      photo:   "{{ inputs.photo }}"
      wide:    "{{ steps.shape.wide }}"
```

`agencast run photo-caption -i photo=./coffee.jpg`

### Skipped steps and `default` (§5.4)

A step “might not run” when it has `when`, is in a `switch` branch or has
`on_error: continue` (or is inside such a step, e.g. in a `parallel`
branch with `when`). A reference to the output of such a step is a
`validate` error unless the step has a `default`. When the step does not
run, its output is `default` and the record has the reason for the step.

---

## 6. Errors

Default behavior: **a step error ends the run** with the status `failed`
and the callback carries the error class, the step `id` and the message
(§5.1). Nothing fails silently.

### Error classes

| Class | When | What the framework does |
|---|---|---|
| `transient` | HTTP 408, 429, 5xx, network outage; HTTP 200 with `finish_reason: error`; HTTP 200 without content and without a refusal; missing `usage.cost`; MCP handshake failure due to network/5xx; file upload failure; `validate` without network and without the `/models` cache | retries the call (`retry`) with a delay, then an error |
| `schema` | the response cannot be parsed or does not match `schema` | retries the call (`retry`), the model gets the error as feedback |
| `content` | the model or a filter refused the content: HTTP 403 (`content_policy_violation`, `refusal`), HTTP 200 with `finish_reason: content_filter` or a filled-in `refusal`; `image` without an image after `retry` is exhausted (see [`image`](#image)) | no retry, error |
| `budget` | the step, agent or run budget is exhausted ([Budget](#budget)); `max_turns` without a response; HTTP 402 (credit ran out / key limit); the cost stayed unknown even after `retry` (“unknown cost”) | ends, no retry |
| `timeout` | the step or run `timeout` was exceeded; an MCP tool call timeout | ends, no retry |
| `config` | an error in the scenario, agent or configuration — mainly from `validate` before the run (including the static check of expressions and templates, see [§5](#when-an-expression-error-is-detected)); at run time HTTP 400/401/403 (except content)/404, failure to start an MCP server (the process is not running, 401), `dedupe` in the `started` state, the image aspect ratio does not match `aspect_ratio`, `finish_reason: length` (cut off by the `max_tokens` limit; a retry will not help — raise the alias's `max_tokens` in `config.yaml`) | ends, no retry |
| `expression` | an expression or template failed **at run time**: a missing key, a wrong value type, an index out of range, division by zero, `null` in a template (see [§5](#when-an-expression-error-is-detected)) | behaves like a `fail` step: no retry, ends (unless the step has `on_error: continue`) |
| `fail` | a `fail` step (**proposal**) | ends |
| `internal` | an error of the framework itself (**proposal**) — always with the full message in the record | ends |

Source of the `finish_reason` values (`stop`, `tool_calls`, `length`,
`content_filter`, `error`) and error codes:
<https://openrouter.ai/docs/api-reference/overview>,
<https://openrouter.ai/docs/api-reference/errors> (retrieved 2026-09-25).
Nobody has measured the shape of an image refusal yet (DESIGN §7 item 7).

### HTTP 200 is not success (§5.1 item 8)

A step with a model (`ask`, `task`, `jev`, `image`) succeeds only when:

1. the HTTP status is 200 **and** the body has no `error`,
2. `finish_reason` is `stop` (for `task`, `tool_calls` along the way too;
   at the `tool_wrapper` cascade level `tool_calls` with `_submit_output`),
3. there is content: text, JSON according to `schema`, Jev answers to all
   questions, for `image` at least one image.

In addition, the cost (`usage.cost`) must be known, otherwise the budget
cannot be tracked — see [Budget](#budget).

Example from spike (a): Gemini returned HTTP 200 with
`finish_reason: "error"`, `completion_tokens: 0` and truncated JSON →
class `transient`, retry.

### Budget

- **Before every call:** when the spend of the step, agent or run has
  already reached the budget, the call is not made → `budget` error.
- A call that **exceeds** the budget completes and its result counts; a
  warning “budget for … exceeded by X USD” is written.
- In `parallel` the same applies to each branch: the overrun is at most
  one call per branch.
- Missing `usage.cost` = retry as `transient`; after `retry` is exhausted,
  class `budget` with the message “unknown cost”. Nothing is estimated.
- Images are additionally guarded by `limits.run_image_budget_usd`; their
  time is reported separately in the record
  (`run_finished.image_duration_s`), v1 has no separate time limit for
  images.

### `on_error: continue`

Only explicitly, only for the steps in the table in
[§3](#3-common-step-properties). The failed step has the output `default`,
`events.jsonl` has `error` and `step_finished` with `status: failed`,
`continued: true`, and `summary.md` and the callback have a **warning**.
`on_error` does not override `budget` and `timeout` errors of the whole
run — the run always ends.

---

## 7. What `validate` checks

Before every run (and separately `validate`, `--dry-run`) — everything is
class `config`:

- the file matches the JSON Schema (unknown fields, missing required ones,
  types),
- `name` = file name, `version` is known,
- agents, scenarios (`call`), model aliases, MCP servers and tools exist;
  a step does not widen the agent's permissions,
- the file is read as YAML 1.2 core, without duplicate keys; only files
  directly in the directory are read, subdirectories are ignored (useful
  e.g. for an archive),
- `call` only to a scenario with `callable: true`,
- permissions according to `mcp.yaml`: an agent with a server that does
  not list it in `agents`; a scenario outside the server's `scenarios`; a
  tool outside the server's `tools` → error (see
  [config.md](config.md#mcpyaml--registry-of-mcp-servers)),
- `id` is unique; expressions and templates according to the table “When
  an expression error is detected” in [§5](#when-an-expression-error-is-detected)
  (syntax, forbidden constructs, functions, limits, references only to
  steps above and not into another `parallel` branch, types where they are
  known in advance),
- a reference to a step that might not run has a `default`,
- `output` is last and matches `outputs`; `call` matches the `inputs` and
  `outputs` of the called scenario; no cycles, depth within the limit,
- no unreachable step after an unconditional `fail`,
- `models.<alias>.id` exists in `GET /api/v1/models` (the result is cached
  for 24 h in `<runs>/_models.json`; without network and without a cache →
  `transient`; with the `base_url` of a fake provider it asks that
  provider's `/models`),
- image aliases support image output; the alias of an agent used in
  `task` has `tools` in `supported_parameters`; the alias of a step with
  `schema` has `structured_outputs` or `tools` (§5.5, §5.7),
- two allowed tools must not have the same name after name normalization
  (`server__tool`, only `[a-zA-Z0-9_-]`, max 64 characters, DESIGN §5.8).

`--dry-run` additionally prints the plan: the step order, the effective
tools of each `task`, the tools each MCP server offers (so that the
`tools` list can be written), and the limits.
