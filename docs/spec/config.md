# Configuration — specification v1

Three files that **only the project owner** changes (DESIGN §4). They decide
what is allowed in the system at all; agents and scenarios only refer to
them.

| File | What it contains | Example |
|---|---|---|
| `workflows/config.yaml` | OpenRouter, model aliases, output storage, run limits, webhook and callback | `examples/showcase/workflows/config.example.yaml` |
| `workflows/mcp.yaml` | registry of MCP servers | `examples/showcase/workflows/mcp.example.yaml` |
| `workflows/commands.yaml` | named commands for the future `run` step | `examples/showcase/workflows/commands.example.yaml` |

Machine-readable form: [`schema/config.schema.json`](schema/config.schema.json),
[`schema/mcp.schema.json`](schema/mcp.schema.json).

The files are read as **YAML 1.2 core** (booleans only `true`/`false`, a
duplicate key = `config` error with a line number; see
[scenario.md](scenario.md)).

Notation: **proposal** = not covered by DESIGN.md; proposed default behavior.

## Secret keys: always just the name of an environment variable (§5.2)

No file ever contains the value of a key. Where a secret is needed, the
field ends in `_env` and contains the **name** of an environment variable:

```yaml
api_key_env: OPENROUTER_API_KEY     # correct: the variable name
```

The value of `_env` fields must look like a variable name
(`UPPERCASE_AND_DIGITS`). When someone pastes the key itself there by
mistake (`sk-or-…`), `validate` rejects it — and does **not print** the key
in the error message. Two different `_env` fields with the same value
(e.g. webhook token = OpenRouter key) are a `config` error — otherwise n8n
would get the OpenRouter key.

Before writing each record file and the callback, the framework replaces
the values of all variables from `_env` fields and from `env` in `mcp.yaml`
with the text `<secret: NAME>` (an MCP tool may return them in its result —
DESIGN §5.2,
[run-record.md](run-record.md#what-must-never-be-in-the-record)).

Variables come from the process environment: on the server from `.env`
(it is in `.gitignore`), on Modal from `modal.Secret.from_name` (D5).
Loading `.env` tolerates CRLF line endings (DESIGN §7 item 8). A missing
variable → `config` error before the run, with the variable name (not the
value).

---

## `config.yaml`

```yaml
version: 1

openrouter:
  api_key_env: OPENROUTER_API_KEY
  jev_model: jev-1.13

models:
  smart:        { id: anthropic/claude-haiku-4.5 }
  fast:         { id: google/gemini-3.5-flash-lite, structured_output: tool_wrapper }
  gemini-image: { id: google/gemini-3.1-flash-image }

runs_dir: ./runs

storage:
  type: r2
  r2:
    bucket: lumen-posts
    account_id_env: R2_ACCOUNT_ID
    access_key_id_env: R2_ACCESS_KEY_ID
    secret_access_key_env: R2_SECRET_ACCESS_KEY
    public_base_url: https://files.example.com

limits:
  run_budget_usd: 1.00
  run_image_budget_usd: 0.30
  run_timeout: 1h
  max_call_depth: 3

webhook:
  token_env: WEBHOOK_TOKEN

callback:
  secret_env: CALLBACK_SECRET
```

### `openrouter`

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `api_key_env` | yes | Variable with the OpenRouter API key (R4). | `config` error. | `api_key_env: OPENROUTER_API_KEY` |
| `base_url` | no | API address. Changed only for conformance tests with a fake provider (§5.6). Only `https://openrouter.ai/…` or `http://127.0.0.1` / `http://localhost` is allowed — anywhere else the key would leak. | `https://openrouter.ai/api/v1` | `base_url: http://127.0.0.1:8765/api/v1` |
| `jev_model` | no | Model for `jev` steps. Jev is not in `GET /models` (§5.5), hence set separately, not as an alias. The run record stores the actual dated version from the response. | `jev-1.13` (**proposal**) | `jev_model: jev-1.13` |

### `models` — aliases (§5.5)

A map `alias: { id, api, quality, max_tokens, structured_output }`. Agents and scenarios know only the alias;
swapping a model = changing one line here.

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `<alias>` | — | Alias name: lowercase letters, digits, hyphen. | Agent/step with an unknown alias → `config` error. | `smart` |
| `<alias>.id` | yes | Concrete OpenRouter model. `validate` checks it against `GET /api/v1/models` for `chat` or `/api/v1/images/models` for `images` (careful: `claude-haiku-4.5`, not `-4-5`). | `config` error. | `id: anthropic/claude-haiku-4.5` |
| `<alias>.api` | no | API for the `image` step: `chat` uses chat completions and `images` the dedicated Images API. | `chat` (the previous behavior). | `api: images` |
| `<alias>.quality` | only with `api: images` | Quality of the Images API request. | Model default. | `quality: low` |
| `<alias>.structured_output` | no | At which level of the structured output cascade (§5.5) to start: `native_schema`, `tool_wrapper`, `prompt`. Set according to the alias's conformance scenario (spike (a): Gemini flash-lite with tools needs `tool_wrapper`). See [scenario.md](scenario.md#structured-output-cascade-55). | `native_schema` | `structured_output: tool_wrapper` |
| `<alias>.max_tokens` | no | Cap on the response length. Needed mainly for reasoning models, which otherwise use up the limit on thinking (`finish_reason: length`, see scenario.md §6). | Provider default. | `max_tokens: 4000` |

Every alias has a conformance scenario (§5.5) that runs when the `id`
changes — that is the framework's job (Phase 2), not this file's.

### `runs_dir` — where run directories live

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `runs_dir` | no | Directory with run records ([run-record.md](run-record.md)), `_dedupe/`, `_slots/`, `_ledger/` and the `_models.json` cache. On Modal a path to a Volume. | `./runs` | `runs_dir: /runs` |

### `storage` — where files from `output` are uploaded (§5.7)

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `type` | yes | `local` or `r2`. | `config` error. | `type: r2` |
| `local.path` | for `local` | Directory the files are copied to. | `config` error. | `path: ./outputs` |
| `local.public_base_url` | no | Address at which the server exposes that directory. | The callback carries a `file://` path — useless for Instagram. | |
| `r2.bucket` | for `r2` | Bucket name (not secret). | `config` error. | `bucket: lumen-posts` |
| `r2.account_id_env`, `r2.access_key_id_env`, `r2.secret_access_key_env` | for `r2` | Variables with the Cloudflare R2 S3 token credentials. | `config` error. | |
| `r2.public_base_url` | for `r2` | Public address of the bucket (custom domain or `r2.dev`). Instagram needs a stable public URL. | `config` error. | `https://files.example.com` |

Key of a file in storage: `<run_id>-<32 random hex characters>/<output
name>.<extension>` — for **all** files including `report.html` (D2).
URL = `public_base_url` + `/` + key. The bucket is public (Instagram needs
a public URL) and `run_id` can be guessed, hence the random part: it is
created at run start and is **only** in the callback and in the run record
(DESIGN §5.2).

The R2 facts come from spike (b), which did not implement R2 (keys were
missing); verify them in the Cloudflare R2 documentation before
implementation (<https://developers.cloudflare.com/r2/>).

### `limits` — safeguards for the whole run

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `run_budget_usd` | yes | At most this many USD for the whole run including `call` and images. Exceeding it → `budget`. | `config` error — a run without a spending cap does not exist. | `run_budget_usd: 1.00` |
| `run_image_budget_usd` | no | Separate cap for `image` steps (two orders of magnitude more expensive than text, §5.7). Also counts towards `run_budget_usd`. | Images are guarded only by `run_budget_usd`. | `run_image_budget_usd: 0.30` |
| `run_timeout` | yes | Maximum run duration (without waiting in the queue). `s`/`m`/`h`. At most 24h on Modal (D5). | `config` error. | `run_timeout: 1h` |
| `max_call_depth` | no | Maximum nesting depth of `call` (§5.3). | `3` (**proposal**) | `max_call_depth: 3` |
| `max_parallel_runs` | no | At most this many runs at once over one `runs_dir` — shared by a manually started CLI, n8n, cron and `agencast serve --workers` (since framework 0.3.1). Integer ≥ 1. The next run waits for a free slot (on stderr `waiting for a free slot (max_parallel_runs=N)`), at most `run_timeout`; then a `timeout` error and the run does not start. The waiting is not part of the run's `run_timeout`. Fake runs (`--fake`) take part in the slots. | No cap — behavior as up to 0.3.0. | `max_parallel_runs: 2` |
| `daily_budget_usd` | no | Daily spending cap in USD (day = UTC) across all runs over one `runs_dir` (since framework 0.3.1). When the total of the daily spend ledger ([run-record.md](run-record.md#run-directory)) reaches the limit, a new run does not start — a `budget` error before the first call. Checked **only at start**: a run that started under the limit finishes and can exceed the limit by at most its `run_budget_usd` (concurrent runs each by their own). Fake runs have their own ledger. | No daily cap — behavior as up to 0.3.0. | `daily_budget_usd: 5.00` |

Example of both optional keys (since framework 0.3.1):

```yaml
limits:
  run_budget_usd: 1.00
  run_timeout: 1h
  max_parallel_runs: 2      # no more runs at once; the others wait (at most run_timeout)
  daily_budget_usd: 5.00    # today's (UTC) spend ≥ 5 USD → a new run does not start (budget)
```

The daily spend ledger exists since framework 0.3.1 — runs of older
versions do not count towards `daily_budget_usd`. It is always written,
even without `daily_budget_usd`, so a limit switched on during the day also
counts the runs made earlier that day.

Safeguard outside the framework: a spending limit directly on the
OpenRouter key and a timeout in n8n (§5.1 item 7).

### `webhook` and `callback`

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `webhook.token_env` | yes | Variable with the token that every incoming request to start a run must carry (Modal endpoints are otherwise public, D5). | `config` error. | `token_env: WEBHOOK_TOKEN` |
| `callback.secret_env` | yes | Variable with the secret for the HMAC callback signature (§5.2); n8n verifies the signature. | `config` error. | `secret_env: CALLBACK_SECRET` |

n8n sends the callback address with every request to start a run
(typically the resume URL of a waiting workflow), so it is not in
`config.yaml`. Shape of the callback body and signature:
[run-record.md](run-record.md#callback).

---

## `mcp.yaml` — registry of MCP servers

An agent may use only a server that is listed here, and only when the
project owner allowed it here. **Permissions are held by the project
owner** (DESIGN §5.2): agents and scenarios are files that others write
too, so "who may do what" restrictions cannot live in them. Transport types
per the MCP specification (stdio, Streamable HTTP, SSE;
<https://modelcontextprotocol.io/specification/latest/basic/transports>,
retrieved 2026-09-25; DESIGN §5.8):

```yaml
version: 1
servers:
  filesystem:
    description: Read and write in the workspace of the current run
    command: npx
    args: ["@modelcontextprotocol/server-filesystem", "{run_dir}/work"]
    agents: [publisher]

  instagram:
    description: Publishing to Instagram (remote server)
    url: https://mcp.example.com/instagram
    bearer_token_env: IG_MCP_TOKEN
    agents: [publisher]
    scenarios: [ig-publish]
    tools: [create_media, publish_media]
    timeouts: { handshake: 10s, call: 120s }
```

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `version` | yes | Format version. | `config` error. | `version: 1` |
| `servers.<name>` | — | Server name that agents refer to. Lowercase letters, digits, hyphen. | — | `instagram` |
| `description` | yes | What the server is for (for humans and `--dry-run`). | `config` error. | |
| `agents` | yes | Which agents may use the server. An agent with a server that does not list it here is a `config` error. | `config` error. | `agents: [publisher]` |
| `scenarios` | no | Which scenarios may run (`task`) an agent with this server. A scenario outside the list → `config` error. Prevents an arbitrary scenario from using the publishing agent and bypassing the approval in n8n. | Any scenario. | `scenarios: [ig-publish]` |
| `tools` | no | Upper list of tools the project owner allows. An agent may have in `tools` only tools from this list, otherwise a `config` error. | Only the list in the agent. | `tools: [publish_media]` |
| `command` | either `command` or `url` | Program of a local server (stdio). Started without a shell, **once per run** (at the first `task` that needs it). On Modal the package must be preinstalled in the image (D5: 0.7 s vs. 3.8 s). | — | `command: npx` |
| `args` | no | Program arguments, a list of strings. The only allowed substitution is `{run_dir}` = absolute path to the current run directory (so the server does not see other runs or `_dedupe`). Any other `{…}` is a `config` error. The root the server gets is the second permission layer (§5.8). | None. | `["…", "{run_dir}/work"]` |
| `env` | no | Variables for the server process: `NAME_FOR_SERVER: NAME_ON_HOST`. The value is taken from the framework's environment. The server gets only `HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, `USER` (the default set of the `mcp` SDK, DESIGN §5.8) and the variables from `env` — nothing else. The names `PATH`, `HOME`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, `NODE_OPTIONS`, `PYTHONPATH` are not allowed in `env`. | The server gets no secret. | `env: { GITHUB_TOKEN: GH_TOKEN }` |
| `url` | either `command` or `url` | Address of a remote server: `https://…`, or `http://127.0.0.1` / `http://localhost` (a sidecar in the same container). | — | |
| `transport` | no | Only with `url`: `streamable-http` or `sse`. | `streamable-http` | `transport: sse` |
| `bearer_token_env` | no | Variable with a token; sent as `Authorization: Bearer …`. Only with `url`. | No authorization. | `bearer_token_env: IG_MCP_TOKEN` |
| `timeouts.handshake` | no | Maximum duration of server start and handshake. Exceeding it → `transient` (network) or `config`. | `10s` | `handshake: 20s` |
| `timeouts.call` | no | Maximum duration of one tool call. Exceeding it → the step fails, class `timeout` (the tool may have run). | `60s` | `call: 120s` |

Timeouts are always explicit — without them the `mcp` SDK waits
indefinitely (DESIGN §5.8). The `stderr` of every server goes to the run
record (`mcp/<server>.stderr.log`). Fixed (non-secret) server settings
belong in `args`, not in `env`.

## `commands.yaml` — commands for the future `run` step

The `run` step is **planned** (D1d) and not implemented in v1. Only the
structure is here, so that it is clear what the permission will look like
(§5.2: only named commands, no shell, with an empty environment, with
validated arguments). The JSON Schema will be created together with the
`run` step.

```yaml
version: 1
commands:
  resize-image:
    description: Scales an image down to Instagram width
    program: /usr/bin/convert
    args: ["{{ params.input }}", "-resize", "{{ params.width }}x", "{{ params.output }}"]
    params:
      input:  { type: file }
      width:  { type: integer, min: 320, max: 1440 }
      output: { type: string, pattern: "^[a-z0-9_-]+\\.jpg$" }
    timeout: 60s
```

| Field | What it does |
|---|---|
| `commands.<name>` | Name the `run` step uses to call the command. |
| `description` | What the command is for. |
| `program` | Absolute path to the program; it is run directly, **never through a shell**. |
| `args` | Fixed arguments; `{{ params.x }}` is always **one** whole argument (spaces or quotes in the value do not split anything). |
| `params` | Description and constraints of each parameter; a value that does not pass does not run the command. |
| `timeout` | Maximum duration of the command. |

The program runs with an empty environment (not even `PATH`), in the
step's working directory.
