# AgenCast — design

This document captures the architectural decisions and constraints of the framework.
The current version and the implementation status are in the [README](../README.md) and the
[changelog](../framework/CHANGELOG.md); the formats are described by the [specification](spec/).

---

## 1. Goal

A framework in which workflows with LLM agents are written in easily readable
files (scenarios in YAML, agents in Markdown). The user is a beginner programmer:
from the scenario file and from the run record they must understand what is
going on. The framework's internals are of no interest to them. Models and Jev go through a single
provider (OpenRouter). Runs on your own server or on Modal.com,
triggered by a webhook (typically from n8n).

Reference case: an Instagram post (copywriter → Jev check →
image → draft for approval → publication).

---

## 2. Requirements

| # | Requirement |
|---|---|
| R1 | A workflow (scenario) is written in an easily readable file. |
| R2 | The user understands what the workflow does from the scenario file **and** from the run record. The framework's internals are of no interest to them. |
| R3 | Agents are defined centrally, each in its own file (model, instructions, MCP servers, skills, tools, limits). A scenario calls them by name. |
| R4 | The provider is hard-wired to OpenRouter: LLM, Jev (System One API), image generation. |
| R5 | Runs on your own server or on Modal.com; triggered by a webhook. Cron, events and approvals are handled by n8n outside the framework. |
| R6 | The framework is a tool the user does not touch. If it is your own, agents (workers) tune and develop it. |
| R7 | Updating the framework or its dependencies must not require changes to agents and scenarios. The formats are ours, versioned. |
| R8 | **Existing scenarios and agents must not fall apart when the framework is improved.** For the compatibility rules see §5.9. (Added 2026-09-25 when spec v1 was approved.) |

---

## 3. Decisions

### D1 — Formats

**D1a Agent = Markdown with frontmatter.** Configuration at the top (YAML
frontmatter), instructions as the body of the file. Illustratively:

```markdown
---
name: copywriter
description: Copywriter for social networks of the Lumen brand
model: smart                 # an alias from config.yaml, not a concrete model
skills: [marketing-copy]
mcp: []
tools: {}
limits: { max_turns: 8, budget_usd: 0.5 }
---
You are the copywriter of the brand … (instructions)
```

Note: the shape resembles Claude Code agents, but it is **not a compatible
format** (different fields, different tools). A converter may come later.

**D1b Two step types for an agent.** `ask` = one model call with the agent's
instructions (no tool loop). `task` = an autonomous model ↔ tools loop
with turn and money limits. In a scenario it is immediately visible where
what happens.

**D1c Expressions — decided 2026-09-25.** `{{ steps.copy.caption }}` is used
**only for inserting values** (prompts, parameters). For `when`, `switch` and
`set`, **safely evaluated Python-style expressions** are used,
e.g. `steps.tone_check.on_brand < 0.7 and inputs.language == "en"`:
dot access to `inputs`, `steps`, `item`; comparison, `and`/`or`/`not`,
arithmetic, indexing, a small set of allowed functions (`len`, `min`, `max`,
`round`, `str`, `int`, `float`, `join`). No access to the system, no
method calls, no import. The fixed rules are in §5.4.

Spike (c) 2026-09-25 (the expressions spike report, removed from the tree; in history up to commit fe90e05): decided on a **custom
evaluator over `ast`**, no library. Of 8 configurations (simpleeval, asteval,
evalidate, RestrictedPython, cel-python, cel-rust, custom) only the custom prototype
met D1c + §5.4 (207 lines; estimate with validation 350–500). The libraries
in Python syntax break dot access for a step named `copy`
(they return `dict.copy`) and silently return `False` for `3 == "3"`; asteval reads a
file through `open()`; CEL has a different syntax. Hence, firmly: **dot = key
read, not an attribute**; the expression length limit **before** the parser; `and/or/not`
only over bool; `round` half away from zero; `str(None)` = `"null"`; no ternary,
slices, `**` or method calls. An expression error at run time = class `expression`.

**D1d Step types.**

v1 (being implemented):

| Step | What it does |
|---|---|
| `ask` | one model call through an agent; `schema` enforces JSON output |
| `task` | an autonomous agent with tools/MCP/skills, turn and budget limits |
| `jev` | a decision through Jev (`noul` / `choice` / `score`), returns values and probabilities |
| `image` | image generation through OpenRouter; the result is a file in the run folder |
| `parallel` | concurrent branches within one run, named outputs |
| `switch` | branching by value; `default` is **mandatory** |
| `call` | a nested run of another scenario (see §5.3) |
| `set` | computing/transforming values without an LLM |
| `fail` | deliberately ending the run with an error and a message |
| `output` | what the run returns (JSON + files); files are uploaded to storage and the callback carries the URL |

Step properties: `id`, `when` (every step); `retry`, `timeout`,
`budget_usd`, `on_error` (only steps where they make sense — set by the spec);
`schema` inside `ask`/`task`. (Refined by spec v1, see
`docs/spec/OPEN-QUESTIONS.md`.)

Planned (implemented **only when a concrete scenario needs it**):
`foreach`, `repeat`, `http`, `tool` (a direct MCP call without a model), `file`,
`run` (only named commands from `commands.yaml`), `state` (memory between
runs, atomic `claim`).

Rejected: `race`, `approve`/`human`, `wait` (approvals and waiting are handled by
n8n), `embed`/`search`.

### D2 — Run model

- **Runs go one after another** (a queue). Parallel steps *within* a run
  (`parallel`) remain. The design must not prevent parallel runs in the future:
  runs do not share files (except `state`, the output storage and `_dedupe` —
  keys of side effects, which are separate atomically created
  files, never one shared log; the only bounded exception is the daily
  spend ledger `_ledger/` since 0.3.1 — one line per finished run under
  `flock`, see ISSUES 40). The default stays one after another;
  `agencast serve --workers N` (since 0.3.0) optionally runs N runs over
  one queue — a `run_id` collision is resolved by a new suffix, the `/models` cache is
  written atomically, `_dedupe` sits behind the `DedupeStore` interface (ISSUES 39).
- **The webhook is asynchronous:** it immediately returns the `run_id` and the position in the queue,
  and the result arrives at the **callback URL** (n8n). The callback is sent **always**,
  on success and on error.
- A run takes minutes to an hour. The timeout in n8n must also account for waiting
  in the queue.
- **Human approval is not in the framework.** A workflow is split into parts,
  n8n holds the state between them. The hand-off contract: output = JSON + file URLs.
- Both agent modes: `ask` (one call) and `task` (autonomous).
- **The run record** is a folder: `events.jsonl` (a machine-readable log),
  the outputs of every step (prompt, response, model, tokens, cost, time),
  `summary.md` for humans and **one standalone HTML file** uploaded to
  storage (a link in the callback). A GUI over `events.jsonl` later.
- Scenarios are written by the user, their agents, possibly other people and their agents
  → strict JSON Schema of the formats, `validate` before a run, explicit permissions,
  secret keys never in workflow files.

### D3 — Engine — decided 2026-09-25 (after the spikes)

**Our own small framework.** We write the orchestration (step order, `parallel`,
`switch`, `call`, run record) and the thin agent runtime (the model ↔
tools loop, the structured output cascade, the MCP client) ourselves on top of
**protocols and small stable libraries**. No agent framework
(Mastra, LangGraph, Google ADK, CrewAI, MS Agent Framework) and no fork of
baton/zenflow.

Reasons: (1) the spikes showed that both OpenRouter and Modal can be handled with plain HTTP/SDK
and that the hard parts — checking `finish_reason`, the output cascade by model,
passing back `reasoning_details`, normalizing `usage` — are not solved for us by the big
frameworks; (2) their main benefits (pausing for a human, a durable graph state)
we do not need, because approvals are done by n8n and the queue by Modal (D2);
(3) R7 — depend only on things that change slowly.

Cost: maintenance is ours → conformance tests (§5.6) are an obligation, not
a wish. Estimate of the v1 core: 3–5 thousand lines, written and maintained by workers.

### D4 — Language — decided 2026-09-25: Python 3.12 + uv

Reasons: Modal is natively Python — the webhook, queue, Volume and secrets from
spike (b) become a direct part of the framework (in TypeScript there would be two
languages to maintain); the spikes and `jev-labs` are in Python; the advantage of the AI SDK in TS
is small when we write the cascade and the checks ourselves.

Default library set (changes only with a reason in the changelog): `httpx` (HTTP),
`mcp` (the official MCP SDK), `pydantic` (format validation, JSON Schema),
`pyyaml`, `modal` (deployment only), CLI via `typer` or `argparse`,
the expression evaluator per D1c. Distribution by `uv run`/`uvx` on the server and in the Modal
image; dependencies locked in `uv.lock`.

**Addendum 2026-09-26 (framework 0.5.0): `ruamel.yaml`** only for the GUI's
editing operations (`agencast/edit.py`, ISSUES 43). Reason: the GUI writes into
files that are also written by a human, and the write must preserve comments, key
order, blank lines and the quote style (`"{{ … }}"`) — PyYAML drops
comments. Reading and validation stay on PyYAML (YAML 1.2 core, `loader.py`);
after an edit the result is read by it again. ruamel rewrites spaces in flow
maps (`{ a: 1 }`) and the alignment, so unchanged lines are taken verbatim
from the original file.

### D5 — Hosting

Your own server (CLI + webhook) and Modal. Trigger, cron and approvals: n8n.
Verified by spike (b), Modal SDK 1.5.5:

- **Queue:** `@app.function(max_containers=1)` + `.spawn()` from the endpoint
  = runs strictly one after another (3 runs without overlap), the webhook responds
  in < 1 s. Modal does not reliably give the position in the queue
  (`get_current_stats().backlog` is delayed) — the framework or n8n holds it.
- **Endpoint:** `@modal.fastapi_endpoint(method="POST")`; an HTTP request
  has a 150 s limit, so the submit only spawns and returns the `run_id`. Function timeout
  1 s – 24 h (`timeout=`), waiting in the queue is not counted. Read headers
  via `Header()`. Endpoints are public → your own token in a header from
  `modal.Secret`.
- **Callback** from a function to an HTTPS endpoint works without restrictions.
- **MCP servers:** a stdio `npx` server in a container works; **pre-install
  the packages into the image** (cold handshake 0.7 s vs. 3.8 s via
  `npx -y`). Container cold start 4–7 s, a cold web endpoint +4–5 s.
- **Files:** `modal.Volume` (`commit()` after writing, `reload()` before
  reading); reading locally via `modal volume get` and a public GET via the
  endpoint. But the URL is Modal-specific → for Instagram and permanent links
  Cloudflare R2 stays (S3 token + r2.dev/custom domain, `boto3`).
- **Secrets:** `modal.Secret.from_name` (rotation without a redeploy).
- **Deployment:** `modal deploy` over a running app need not replace warm
  containers → deploy as `app stop` + `deploy`, or verify the version.
- One shared Dockerfile for the server and Modal (`Image.from_dockerfile`,
  not tried), so that the installed tools do not diverge.

### Wrappers (since 0.3.0)

The CLI (`agencast`), the webhook (`agencast serve`), later Modal and an MCP server
are **thin wrappers over `agencast.api`** (`load`, `run`, `dry_run`,
`runs_list`, `run_status`):

- A wrapper contains no logic — it only converts the input (arguments, HTTP, a tool
  call) into a call to `api` and the result back. Anything with logic goes into the core
  and has a hermetic test.
- Secret keys only from the environment (`.env` only locally, on Modal
  `modal.Secret`), never in workflow files or in arguments.
- Shared state between runs sits behind an interface: `dedupe_key` via `DedupeStore`
  (`get`, `claim` — exclusively and atomically, `finish`) in `agencast/task.py`.
  The local implementation keeps files `<runs>/_dedupe/<sha256>.json`
  (`_dedupe-fake/` with `--fake`); **Modal will later plug in its own
  storage here** (`modal.Dict` etc.) via `Run.dedupe`. Likewise since 0.3.1
  the slots `limits.max_parallel_runs` (`SlotStore`: `acquire`, `release`;
  locally `flock` on `<runs>/_slots/<n>.lock`) and the daily spend ledger for
  `limits.daily_budget_usd` (`Ledger`: `total`, `add`; locally
  `<runs>/_ledger/<day>.jsonl`, `_ledger-fake/` with `--fake`) — ISSUES 40.
  Since 0.7.0 also the live-run lock (`hold_run_lock`, `run_locked`; locally
  `flock` on `<run>/run.lock`), by which the API distinguishes a running
  run from an interrupted one — ISSUES 45.
- The MCP tools will be “start and return the ID”, “status” and “wait” — a run takes
  minutes and Modal's web endpoint has a 150 s limit (D5), so a tool must not
  wait for the end of a run in a single call.

**GUI — decided 2026-09-26 (user + coordinator):**

- The GUI is a standalone wrapper `ui/` in this repo (React). It is served by
  `agencast serve`; Skynet Soul only embeds it in a tab (iframe).
- The GUI talks to the core **only through the `serve` HTTP API** (`/projects/...`,
  [spec/api.md](spec/api.md)) — no direct file access and no parser of its own
  for the formats.
- A scenario is a vertical list of step cards (a tree by `parallel`/`switch`),
  no canvas; the GUI is also a run viewer (step status, cost, run
  files, daily spend).
- **The file is the truth:** scenarios and agents stay YAML/Markdown in
  `workflows/`; the GUI reads them and since 0.5.0 changes them only through the core's
  editing operations (`agencast/edit.py`, [spec/api.md](spec/api.md) “Editing”),
  which write into the same files (ISSUES 43):
  - **fingerprint** = the sha256 of the file content the client loaded (not mtime);
    a mismatch → 409 and nothing is written — a concurrent manual edit in an editor is
    not silently overwritten;
  - **validation before writing**: a copy of `workflows/` with the change goes through
    `validate` (without checking models); the change must not add a new error,
    earlier errors do not block it; then an atomic write (temp + `os.replace`);
  - the write preserves comments, key order, blank lines and quotes
    (`ruamel.yaml`, D4); unchanged lines stay verbatim;
  - the owner's rules apply: `config.yaml` and `mcp.yaml` only as a
    form without secrets (variable names), `.env` is never read or
    written; raw text only for files of the formats inside `workflows/`.
- Projects are **not scanned**, a registry
  `~/.config/agencast/projects.yaml` is kept ([spec/projects.md](spec/projects.md));
  `agencast serve` outside a project serves all projects from the registry
  with the server token `AGENCAST_TOKEN`; in a project or with `--project` it serves one
  project as before (n8n, Modal). ISSUES 41, 42.

---

## 4. Repository structure

```
agencast/
  framework/        the core (CLI, engine, adapters, webhook) — maintained by workers
  examples/         standalone example projects showcase/ and tutorial/
    <project>/workflows/  the project's agents, scenarios, skills and configuration
      agents/         *.md   — agents (D1a)
      scenarios/      *.yaml — scenarios (D1d)
      skills/         <name>/SKILL.md
      config.yaml     OpenRouter, model aliases, storage, limits      ← owner only
      mcp.yaml        MCP server registry + references to secret keys ← owner only
      commands.yaml   allowed commands for `run`                      ← owner only
  docs/             this design, format specifications, changelog
```

The files marked “owner only” decide what is allowed in the system at all.
Everything else can be written by other people and agents.

---

## 5. Fixed rules

### 5.1 Errors — nothing fails silently
1. Default behaviour: a step error ends the run with the status `failed`.
2. The callback is always sent: the status, which step failed, the error class, the message.
3. Error classes and their behaviour: `transient` (429, 5xx, network → retry
   with a delay), `schema` (the model output does not fit → retry, the model gets
   the error as feedback), `content` (the model refused the content, e.g.
   an image → do not retry), `budget` / `timeout` (end), `config`
   (caught by `validate` before the run).
4. `on_error: continue` is only allowed explicitly and is visible in the run summary as
   a warning.
5. Every skipped step has its reason stated in the record.
6. `repeat` and `task` have an iteration/turn limit that is **mandatory**.
7. A safeguard outside the framework: a timeout in n8n (“if no callback arrives within X
   minutes → alert”) and a spend limit directly on the OpenRouter key.
8. **HTTP 200 is not success.** A model step is successful only after checking
   `finish_reason`, parsing and schema validation. Spike (a): Gemini
   returned 200 with `finish_reason: "error"`, `completion_tokens: 0` and
   truncated JSON. A content refusal may also show up as a 200 without
   content (`refusal`, `finish_reason` ≠ `stop`).

### 5.2 Security
- Secret keys exist only in `config.yaml` / `mcp.yaml` (by reference to
  environment variables), never in scenarios, agents or prompts.
  The framework has nowhere to take them from to put them in a prompt.
- `run` executes only named commands from `commands.yaml`, without a shell,
  with an empty environment, validated arguments.
- An agent defines the **maximum** of permissions (tools, MCP, limits); a step in a
  scenario can only **narrow** them, never widen.
- An incoming webhook requires a token; the callback is signed (HMAC), n8n verifies it.
- Idempotence: the request key on the webhook (a repeated call does not start a second
  run) and `dedupe_key` on steps with a side effect (publication). The `started`
  record is created before the first tool call; `started` without `succeeded`
  on the next run = a `config` error “verify manually”, not a silent retry.
- **Who may use what is decided by the owner** in `mcp.yaml`: for each server
  `agents:` (which agents may use it), optionally `scenarios:` (which
  scenarios may run an agent with this server) and `tools:` (an upper allowlist).
  Agents and scenarios are files written by others, so these
  restrictions cannot live there. A scenario is callable via `call` only with
  `callable: true` (default `false`), so that part 1 cannot bypass an approval
  in n8n by calling part 2.
- Secret values (variables from `*_env` and `env`) are replaced by the framework before writing every
  record file and callback with the text `<secret: NAME>` — an MCP
  tool may return them in a result (spike (d): `get-env`).
- The file key in the output storage = `<run_id>-<32 random hex>/<name>`;
  the bucket is public because of Instagram, the `run_id` is guessable, the random part
  is only in the callback and the record.
- Files are read as **YAML 1.2 core**: only `true`/`false` are booleans
  (`yes`/`on` is text), `4:5` is text, a duplicate key = a `config` error
  with the line number. PyYAML does not do this by default (spec REVIEW B6) →
  a custom `SafeLoader` and verifying the examples with the same loader.

### 5.3 `call`
- `call` is a nested step **inside the same run**: the same budget,
  a subfolder in the run record. It does not create a new run, the queue does not know about it.
- The called scenario declares `inputs` (types, required, defaults) and
  `outputs`. `validate` checks the call sites statically.
- Validation rejects cycles; the nesting depth has a limit.
- Every scenario is both runnable standalone and callable. One
  file, one format.
- **A scenario must never start a new framework run and wait for it**
  (with a sequential queue = deadlock). Starting a new run is allowed
  only in the “send and don't wait” style (via n8n / webhook).

### 5.4 Expressions and templates
- `{{ }}` in a model response is **never evaluated again**.
- A reference to the output of a skipped step is a validation error unless the step has
  a `default`.
- Inserting text into JSON (e.g. `state` for Jev) is always JSON-safe;
  a scenario does not build JSON by hand.
- Types: number vs. text vs. bool vs. null are distinguished; comparison
  across types is a validation error.

### 5.5 Models
- Scenarios and agents refer to **aliases** (`smart`, `fast`,
  `gemini-image`), `config.yaml` maps them to concrete OpenRouter models.
  Swapping a model = one line.
- Each alias has a **conformance scenario** (can use a tool + JSON
  schema), which runs when the alias changes. Tool support declared by
  OpenRouter is not a guarantee of quality.
- Structured output: a cascade of native JSON schema → tool as a wrapper →
  prompt + validation + retry. The level used is written into the record.
  Spike (a): Claude Haiku 4.5 and Kimi K3 natively 10/10; Gemini 3.5
  Flash-Lite the schema alone 5/5, **schema + tool 4/5 natively, 5/5 via the
  tool wrapper**. The conformance scenario therefore tests the **combination** schema +
  tool, not each separately.
- For reasoning models (Gemini, Kimi) the `reasoning_details` from the response are
  sent back unchanged in the next turn (an OpenRouter recommendation).
- `usage` has a different shape for chat completions (`prompt_tokens`/`completion_tokens`) and
  for Jev (`input_tokens`/`output_tokens`); `cost` in USD is in both.
  The framework normalizes `usage` to a single form in the run record.
- The model id is verified against `GET /api/v1/models` (e.g.
  `anthropic/claude-haiku-4.5`, not `-4-5`). Jev is **not** in that list.

### 5.6 Versioning and tests — the specification is the product
- After the user's approval `docs/spec/` (formats v1) is binding too. A spec × DESIGN
  conflict is reported by a worker to the coordinator, who decides it, not the worker.
- `version: 1` in scenarios and agents from day one; a changelog of the formats.
- **Conformance scenarios** with a fake provider (model calls for free)
  run before every framework change. Without them R6 does not work. `--fake` alone
  does not replace MCP in `task` or the callback; the conformance tests replace them separately.
  An offline user run requires a scenario without `task` and without `--callback-url`.
- Dependencies locked in a lockfile; an update is a conscious decision in a branch
  with the conformance tests passed.

### 5.9 Compatibility (R8) — the approved spec v1 is frozen
1. **The `version: 1` format is only extended after approval:** new optional
   fields and new step types yes; renaming, removing or changing the meaning of
   an existing field no. A new field always has a default that preserves the
   existing behaviour.
2. **A breaking change = `version: 2`.** The framework supports the previous format
   version side by side and has a `migrate` command that converts the files and
   lists the changes. An old file runs unchanged until the user converts it themselves.
3. **Golden scenarios:** every approved scenario, agent and skill in `workflows/`
   and every example in `docs/spec/` is part of the conformance suite: it must pass
   `validate` and finish with a fake provider on every framework
   change. Adding a scenario to `workflows/` = adding a test.
4. **Deprecation with a warning:** a discouraged construct first triggers
   a warning in `validate` (the run continues), it may be removed only by the next version
   of the format.
5. **Framework version (semver):** a fix = patch, an addition = minor, a new
   format version = major. `CHANGELOG.md` of the framework and of the formats.
6. The framework rejects a file with a format version it does not know (`config`), never
   silently interprets it its own way.

### 5.7 Images and files
- Since 0.18.0 images are also **inputs**: `file`/`files` inputs come as host paths from the CLI or Python, or over HTTP as `{"upload_id": "up_…"}` from `POST …/uploads` (api.md; a JSON string is never a path), are checked (PNG/JPEG/WebP/GIF/AVIF, ≤ 10 MB, headers parsed without Pillow, EXIF orientation applied to the dimensions) and copied into `runs/<id>/inputs/` before the run starts, so the record never holds the caller's path. A `file` value carries `width`, `height`, `format`; `images:` on `ask`/`task` sends files as `image_url` data URLs after the prompt with `Image k (…)` labels (the same shape as tool images, §5.8), the record keeps `<file: …>`. Input images cost only the model's vision tokens (`usage.cost`), no separate budget (additive, version 1).
- Since 0.18.0 the `image` step takes **reference images** (`images:`) — only through the Images API (`input_references`; `GET /images/models` gives `input_references.max` and the supported `aspect_ratio` values, `validate` keeps that catalog on `Project` for the run). The chat path with references is unverified and rejected by `validate`. The Images API takes references as a bare list, so with references the prompt sent (and `prompt.md`) starts with a legend `Reference images, in the order attached:` and one `Image k (<run-relative path>, W×H)` line per image — the labels `ask`/`task` send, and the path a template such as `{{ inputs.shirt }}` renders, so a prompt can name an image. `aspect_ratio: auto`, or no ratio with references, = the first reference's ratio snapped (log-nearest) to a supported value; a mismatch after saving is then only a warning, not a `config` error (additive, version 1).
- Since 0.14.0 the `image` step accepts templates in `aspect_ratio`, `quality` and `resolution`; the step's quality overrides the alias, the chat API ignores quality and resolution with a warning (additive, version 1).
- `image` returns base64 → the framework saves a file into the run folder → the step
  returns the path. Files in `output` are uploaded at the end of the run to the storage
  from `config.yaml`; the callback carries the URL. The Instagram Graph API requires
  a public URL and a Business/Creator account linked to a Facebook page
  (outside the framework).
- Spike (a), `google/gemini-3.1-flash-image` via chat completions
  with `modalities: ["image","text"]`: the image is in
  `choices[0].message.images[].image_url.url` as a **base64 data URL**
  (~1.5 MB PNG), never a URL. Base64 is **not** put into `events.jsonl` or into the step
  outputs, only the file path.
- The cost is **0.04–0.07 USD and 6–11 s per image** — two orders of magnitude more than a text
  step (0.0005–0.01 USD). Image steps are counted separately toward the budget and
  the run time limit. Default size 1408×768; the aspect ratio for
  IG (1:1, 4:5) via `image_config` — **unverified**.
- **The provider does not refuse content:** the likeness of a real public
  figure was generated on both models (HTTP 200). The content policy
  (people, third-party brands) must be enforced by the framework itself — typically a `jev`
  check of the prompt before the `image` step (cheap, 0.3 s).
- A model without image output with `modalities: ["image"]` → HTTP 404
  `No endpoints found that support the requested output modalities`
  (class `config`, caught by `validate` against `/models`).
- `models.<alias>.api` selects for `image` chat completions (the default, the existing behaviour) or the dedicated Images API; the optional `quality` applies only to the Images API.

### 5.8 MCP servers, tools and skills (spike (d), `mcp` SDK 2.2)
- The client = the official `mcp` SDK (pin `2.2.*`); stdio, Streamable HTTP
  and SSE. A stdio server is started **per run** (start ~140 ms for a local
  package, ~300 ms `npx -y`), packages pre-installed (matches D5).
- **Timeouts always explicit:** `read_timeout_seconds` for the handshake and
  `call_tool` + an outer safeguard (`fail_after`); without them the SDK waits
  indefinitely. The default `mode="auto"` adds a fixed 10 s for a dead server
  (`server/discover`) → for servers from `mcp.yaml` `mode="legacy"` until
  they are on protocol 2026-07-28. Handshake errors arrive in two
  layers of `ExceptionGroup` — the framework unwraps them into the classes of §5.1.
- **Error mapping:** `isError: true` from a tool = feedback to the model (the step
  continues); `timed out` = class `timeout`; a handshake failure =
  `config`/`transient`.
- **Tool schemas → OpenRouter `tools`** are normalized (~50 lines):
  the name `server__tool` (only `[a-zA-Z0-9_-]`, max 64, otherwise Claude returns
  400), inlining `$ref`, `allOf`/`oneOf` → `anyOf`, `const` → `enum`,
  a non-string `enum` → into `description`. Gemini **silently
  ignores** parts of the schema (HTTP 200 and wrong arguments) → **arguments are validated
  on the client against the original schema**, the error goes to the model as a tool
  result. The alias conformance scenario (§5.5) contains `$ref`, `const`
  and a numeric `enum`.
- **Images from tools** are sent in a following user message (works with
  Claude and Gemini); in a tool message Gemini rejects them (400). They are saved as a
  file, not as base64 in the record.
- **Skills:** `skills/<name>/SKILL.md` with `name` + `description`; the system
  prompt carries only a list of `name: description`, the body is loaded by the tool
  `load_skill(name)` (an `enum` of names, an unknown name → an error with the list).
  The step output is enforced by `schema`, not by a skill.
- **Permissions (§5.2 concretely):** an allowlist of tools by name;
  the effective set = step ⊆ agent, otherwise a `validate` error; only the allowed
  tools go into `tools` and dispatch (a side effect of −66 to −81 % prompt
  tokens). The second layer = the server arguments in `mcp.yaml` (e.g. the
  allowed filesystem root). A stdio server inherits only 6 safe environment
  variables; keys for servers are passed explicitly via `env` in
  `mcp.yaml`. The servers' `stderr` goes into the run record.

---

## 6. Reference scenario (illustrative, the syntax will be refined in the specification)

```yaml
version: 1
name: ig-post
description: Draft IG post for approval (part 1; part 2 publishes it via n8n)

inputs:
  topic: { type: string, required: true }

steps:
  - id: copy
    ask:
      agent: copywriter
      task: "Write an IG post about: {{ inputs.topic }}"
      schema: { caption: string, hashtags: [string], image_prompt: string }

  - id: tone_check
    jev:
      state: "{{ steps.copy.caption }}"
      questions:
        on_brand: { type: noul, instructions: "Does the text match the brand tone?" }

  - id: stop
    when: steps.tone_check.on_brand < 0.7
    fail: "The text does not match the brand (on_brand = {{ steps.tone_check.on_brand }})"

  - id: photo
    image:
      model: gemini-image
      prompt: "{{ steps.copy.image_prompt }}"

  - id: out
    output:
      caption: "{{ steps.copy.caption }}"
      hashtags: "{{ steps.copy.hashtags }}"
      image: "{{ steps.photo.file }}"     # → uploaded, the callback carries the URL
```

Expected run record: a folder with the plan (`--dry-run`), the output of each
step, the reason for skipping, the cost and time, `summary.md` and HTML.

---

## 7. Known risks (in hindsight, 2026-09-25)

1. The scope of v1 — watch it, don't add steps without a scenario that needs them.
2. `task` is the hardest part; the heterogeneity of models behind OpenRouter —
   **confirmed** by spike (a) (Gemini: tool + schema 4/5, 200 with an error).
3. ~~Unverified assumptions~~ → verified by the 2026-09-25 spikes: Jev through
   OpenRouter works (the word “beta” is not in the documentation, 6/6 OK); MCP
   servers on Modal work; the run record on Modal is available via
   Volume and endpoint.
4. The expression language is still undecided (D1c).
5. Observability on Modal (hence the HTML run record in storage).
6. Maintenance: without conformance tests regressions creep in within a month.
7. **New:** the `content` error class (content refusal) could not be
   measured — the provider refused nothing. We do not know the shape of a refusal.
8. **New:** a `.env` with CRLF line endings breaks tokens (Modal: “Invalid
   metadata value”); `.env` loading must tolerate CRLF.
9. **New:** R2 so far without keys — the public URL for Instagram is unverified.

---

## 8. Spikes (before finishing the specification)

Each spike: one worker, a clear question, a time limit of ~1 day, the output
a report with results (the spikes were removed from the tree; the outputs are in the repository history up to commit fe90e05) with a verdict *works / doesn't work / works
with a caveat* and measured facts (not impressions).

**(a) OpenRouter** — questions: (1) `ask` with a JSON schema and one
tool on 3 models (Claude, Kimi/GLM, Gemini) — reliability,
which cascade level was used; (2) Jev through
`https://openrouter.ai/api/v1/systemone` — response shape, errors, latency;
(3) image generation (`google/gemini-3.1-flash-image` or similar) —
response shape, saving the file, cost. Starting material:
`~/workspace/jev-labs` (existing experiments with Jev directly through the TypeSafe
API, `docs/findings.md`). Needs `OPENROUTER_API_KEY` in the environment;
cost in cents.

**(b) Modal** — questions: (1) a container with one stdio MCP server
(`npx`), cold start; (2) webhook → `.spawn()` → callback to a test
URL, `max_containers=1` (verify the parameter name), the queue; (3) a Volume for
the run record and uploading one file to R2 with a public URL. Needs a
Modal token and access to R2.

### Results (2026-09-25, both spikes done)

| Spike | Verdict | Report |
|---|---|---|
| (a) OpenRouter — schema + tool | works with a caveat (Gemini needs a tool wrapper) | the openrouter/REPORT.md spike report (removed from the tree; in the repository history up to commit fe90e05) |
| (a) OpenRouter — Jev | works (5/5, 0.30 s, ~0.00003 USD) | ditto |
| (a) OpenRouter — image | works with a caveat (0.067 USD, refusal not triggered) | ditto |
| (b) Modal — MCP in a container | works (pre-install packages) | the modal/REPORT.md spike report (removed from the tree; in the repository history up to commit fe90e05) |
| (b) Modal — webhook + queue | works (caveat: redeploy = stop + deploy) | ditto |
| (b) Modal — Volume + public URL | works; R2 not implemented (no keys) | ditto |
| (b) Modal — Secrets | works | ditto |
| (c) expressions for D1c (2026-09-25, branch `spike-expressions`) | works: the custom evaluator 24/24 + 14/14 + 20/20; no library meets §5.4 | the expressions/REPORT.md spike report (removed from the tree; in the repository history up to commit fe90e05) |
| (d) MCP client + skills in Python (2026-09-25, branch `spike-mcp-python`) | works: `mcp` 2.2 stdio/HTTP/SSE, schemas after normalization 18/18, `load_skill` 12/12, the allowlist holds; 0.136 USD | the mcp-python/REPORT.md spike report (removed from the tree; in the repository history up to commit fe90e05) |

Spend: (a) 0.30 USD, (b) on the order of cents. The facts from both spikes are
incorporated in §5.1 (item 8), §5.5, §5.7, D5 and §7.

**Facts relevant to D3/D4** (without a choice): all three OpenRouter APIs
and Modal could be driven with plain HTTP/SDK without an agent framework; the hard
places are the structured output cascade, the `finish_reason` check, passing back
`reasoning_details`, normalizing `usage` and the MCP handshake — exactly the
agent runtime, not the orchestration. The decisions D3, D4 and D1c: **accepted
by the user 2026-09-25**, see §3.

---

## 9. Starting material (what we take from existing tools)

A GitHub survey 2026-09-25 (4× Haiku, 5× Sonnet xhigh, verified via
`gh api`): nothing meets R1–R7 at once. Inspiration:

- **foxzi/baton** (Go, MIT): scenarios in YAML, `validate` + `--dry-run`,
  a run folder, error classes, `dedupe_key`, a structured output cascade,
  “an agent may only do what you allow it”. It has no central agents; an `agent:` step =
  Claude Code/Codex CLI, not an API model.
- **zendev-sh/zenflow** (Go, Apache-2.0): an `agents:` block in YAML,
  `dependsOn`, `forEach`, `condition`, `include`. A hidden LLM coordinator.
- **johnlindquist/mdflow** (TS, MIT): a workflow as Markdown with `_steps` in the
  frontmatter — the most readable format; steps = CLI agents.
- **IBM/prompt-declaration-language** (Apache-2.0): `base_url` on calls,
  LiteLLM; more a programming language in YAML.
- OpenRouter: 460 models, 11 with image output, ~390 declare `tools`
  and `structured_outputs` (as of 2026-09-25). Jev: `/api/v1/systemone`,
  response `{ answers: { id: { type, noul|choice|score… } }, usage.cost }`.
- **`~/workspace/jev-labs`** (own, 2026-09-21): a Python CLI and Jev measurements
  directly through the TypeSafe API (`docs/findings.md`). Findings: Czech works
  (34/34 correct `choice`, the term `noul` 15/15), median latency 0.63 s,
  `score` for factual defect descriptions overestimates dissatisfaction, `confidence`
  is not the probability of being right, `noul=0.5` = uncertainty; API errors 401,
  422, 429, 529; limits 1,200 req/min. Thresholds for automation were not
  set — so in scenarios the threshold is always explicit (`< 0.7`), never
  implicit.
- **Jev through OpenRouter** (spike (a)): `POST /api/v1/systemone`, body
  `{model: "jev-1.13", state, questions}`; the response `model` is a dated
  version (`typesafe/jev-1.13-20260917`, `jev-latest` → the same; log it),
  `answers.<id>` = `{type, choice|score|noul, probabilities?, confidence?,
  legend?}`, `usage: {input_tokens, output_tokens, cost}`. A bad request
  → HTTP 400, `error.message` is a string with a JSON array from the validator, the body
  contains `user_id`. A nonexistent model → 400.
