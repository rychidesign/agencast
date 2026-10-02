# Run record — specification v1

Every run has its own directory (D2). It must show what happened without
knowledge of the framework internals (R2): `summary.md` is read by humans,
`events.jsonl` by machines (and the future GUI), `report.html` is a single
self-contained file in storage with a link in the callback.

Notation: **proposal** = not covered by DESIGN.md; proposed default behavior.

## Run directory

```
runs/20260925-140311-ig-post-a1b2/
  plan.md              plan from validate: step order, tools, limits; for --dry-run also what each
                       MCP server offers and allowed tools it does not offer (scenario.md §7)
  inputs.json          run inputs (after filling in defaults); images as paths inputs/…
  inputs/              copies of file/files inputs: <name>.<ext>, <name>-1.<ext>, … (since 0.18.0;
                       a dry run only plans the paths); the record never holds the caller's path
  events.jsonl         machine log — one event per line
  summary.md           summary for humans
  report.html          the same as a single HTML file (uploaded to storage)
  callback.json        exactly what was sent in the callback
  run.lock             lock of a live run (since framework 0.7.0), empty
  scenario/            snapshot of the scenarios at start (since framework 0.7.0)
    ig-post.yaml
  mcp/                 stderr of local MCP servers: <server>.stderr.log (secret values masked;
                       written when the server stops, absent after a killed run)
  steps/
    01-copy/
      prompt.md        system prompt + message, exactly as the model received them
      calls/01.request.json
      calls/01.response.json
      output.json      step output (steps.copy)
    02-tone_check/
      calls/01.request.json
      calls/01.response.json
      output.json
    04-photo_prompt/ …  (03-stop was skipped → has no directory)
    05-image_check/ …
    07-photo/
      prompt.md
      calls/01.request.json
      calls/01.response.json
      image.png
      output.json      { "file": "steps/07-photo/image.png" }
    08-out/
      output.json
```

- `runs/` is `runs_dir` from `config.yaml` (default `./runs`), on Modal a
  Volume (D5). Next to the run directories there are only `_dedupe/`
  (separate key files,
  [scenario.md](scenario.md#dedupe_key--once-and-only-once)), the
  `_models.json` cache and, since framework 0.3.1:
  - `_slots/<n>.lock`, n = 1..`max_parallel_runs` — `flock` locks
    ([config.md](config.md#limits--safeguards-for-the-whole-run)). A run
    holds one slot from just before creating its directory until the end
    (even on error); a process crash releases the lock too. The files stay,
    they have no content. Only with `max_parallel_runs`.
  - `_ledger/<YYYY-MM-DD>.jsonl` — daily spend ledger (day = UTC by the end
    of the run), one line per finished run, append-only:
    `{"run_id": "…", "cost_usd": 0.0123, "finished_at": "2026-09-26T08:15:02.120Z"}`
    (`cost_usd` = `usage.cost_usd` from `run_finished`, including images).
    Always written; read by `daily_budget_usd`. Fake runs (`--fake`) write
    to `_ledger-fake/` (like `_dedupe-fake/`). Runs before 0.3.1 are not in
    the ledger.
- **`run_id`** = `YYYYMMDD-HHMMSS-<scenario>-<4 hex characters>` in UTC
  (**proposal**) — sorts by time and shows what ran. It can be guessed,
  which is why the storage key has an extra 32 random hex characters (see
  [Callback](#callback)).
- **`<nn>`** = the position of the step **in the scenario file**
  (depth-first, including steps in branches), fixed for the scenario — the
  same scenario has the same numbers on every run, and two runs can be
  compared. The actual start order is visible from `ts` in `events.jsonl`.
  It matches the number in `summary.md`. A skipped step has no directory;
  it is only in `events.jsonl` and in `summary.md` with a reason.
- **`calls/`** — every API call separately (retries and `task` turns too),
  number = order of the call within the step. For `task` also
  `calls/NN.tool.json` (tool arguments and result; a call that did not
  return has `result: null` and an `error`) and images from tools
  `tool-<NN>-<k>.png` in the step directory.
- **`call`** — the step directory contains the called scenario's own
  `steps/`: `steps/03-propose/steps/01-copy/…`. Events go into the single
  `events.jsonl` of the whole run; `step` has the path `propose/copy`.
- `--dry-run` creates a directory with only `plan.md` (and `inputs.json`).
- **`run.lock`** (since framework 0.7.0) — the run process holds an
  (exclusive) `flock` on the file from creating the directory until the end
  of the run (even on error); a process crash releases the lock too, and
  the file stays empty. A reader (`runs list`, `serve`) tries a shared lock
  without waiting: cannot get it = the run is alive (`state: running`),
  can get it and `run_finished` is missing = the run was interrupted
  (`interrupted`, [api.md](api.md)) — a killed process, or `agencast run`
  stopped by SIGINT/SIGTERM (it stops its MCP servers first: started steps
  have `step_finished` with `status: cancelled`, steps that had not started
  `step_skipped` with the reason `cancelled — the run was interrupted
  (SIGTERM)`, the servers `mcp_server` `stopped` — also one that was still
  starting; exit code 130/143), or a
  run in flight when `agencast serve` was stopped (the same record; the
  next start of the server finishes it, see `run_finished` below). On Modal the wrapper substitutes its
  own mechanism (like the `max_parallel_runs` slots). A dry run has no
  lock — since framework 0.8.0 this is how it is recognized: `plan.md`
  without `events.jsonl` and without `run.lock` = dry run; a live run
  creates `run.lock` before `plan.md`, so a live run that crashed before
  the first event is interrupted, not a dry run.
- **`scenario/<name>.yaml`** (since framework 0.7.0) — at run start (after
  `plan.md`), a copy of the started scenario and of all scenarios called
  via `call` (also nested), byte for byte except for masking secret
  values. The run detail draws the step tree from them as it was when the
  run happened. A run that did not start (no `plan.md`) and a dry run have
  no snapshot.

## What must never be in the record

- **base64** (§5.7): an image data URL is replaced with the text
  `"<file: steps/07-photo/image.png, 1510234 B>"`. This applies to **all**
  record files: `calls/NN.request.json` (an image from a tool in the user
  message of the next turn), `calls/NN.response.json`, `calls/NN.tool.json`,
  `events.jsonl`, `output.json`.
- **`reasoning_details`** (encrypted, ~1.4 MB for an image): the record
  holds only `"<omitted: reasoning_details, 1412345 B>"` — also in the
  `request.json` of the next turn, where they are sent back (§5.5). The
  framework keeps them in memory.
- **Secret keys and headers** of requests. `request.json` is the body only.
- **Secret values anywhere:** before writing each record file and the
  callback, the framework replaces every occurrence of the value of any
  variable from `*_env` fields (config.yaml, mcp.yaml) and from `env` in
  `mcp.yaml` (values of 8 characters or more) with the text
  `<secret: NAME>` and writes a warning. Longer values are replaced first:
  a value that contains another one (a connection URL and its user name)
  is replaced whole. An MCP tool can return a key in
  its result (spike (d): `get-env`; DESIGN §5.2). The escaped forms of a
  value are replaced too: JSON-escaped once or twice (a value with `"` or
  `\` inside JSON text; twice when a tool result is itself JSON) — also
  as other encoders write JSON: `/` as `\/` (PHP); `&`, `<`, `>`, U+2028
  and U+2029 as `\u0026`, `\u003c`, `\u003e`, `\u2028`, `\u2029` (Go);
  `\uXXXX` with uppercase hex, also for `"`, `'`, `+`, `` ` `` and every
  non-ASCII character (`\u002B`, `\u0022`, `\u00E9`; .NET's
  System.Text.Json) — and HTML-escaped (`report.html`). These are the
  default encoders of the languages with an MCP SDK; any other escaping
  of a value is not recognised.
  The bytes of a saved file (a tool's image block, whatever its
  `mimeType`) are replaced the same way; the model gets them as the tool
  sent them, and `image_saved.bytes` and the `<file: …, N B>` text give
  the size of the file as it is stored. In JSON files, `events.jsonl` and the
  callback the replacement is made in each string (keys too) before the
  JSON is written, so the result is always valid JSON; a number whose
  digits contain a value becomes the replaced string
  (`12345678` → `"<secret: NAME>"`).
- **What an MCP server sent that the framework could not read:** an error
  of the MCP library is quoted without the server's input values (a long
  value would be quoted cut to its start and end — part of a secret, which
  the replacement above cannot find), and every URL in it without userinfo
  and query (a key there is literal text in `mcp.yaml`, not an environment
  value). A stdout line that is no protocol message is quoted whole, after
  the replacement above.
- Only `scheme://host/path` without the query is logged from the callback URL.

## `events.jsonl`

Every line is one JSON object. Common fields:

| Field | What it is | Example |
|---|---|---|
| `ts` | event time, ISO 8601 in UTC with milliseconds | `"2026-09-25T14:03:12.481Z"` |
| `type` | event type (tables below) | `"step_started"` |
| `step` | path to the step (`id`, for `call` `propose/copy`); missing for run events | `"copy"` |

Durations are in seconds (`duration_s`), costs in USD (`cost_usd`).
The cost of a call is exactly the value returned by the provider
(`usage.cost`), without rounding. Totals (step, run, images,
`budget_exceeded_usd`) are rounded only to 10 decimal places because of
float noise (0.30000000000000004 → 0.3). In `summary.md`, `report.html`
and `agencast` listings the cost is shown as a decimal with a decimal
point (never an exponent), at least 4 places, more only when needed to show
all digits (`0.000004482`); an actual zero is `0` (since framework 0.2.4,
ISSUES 38).

### Normalized `usage` (§5.5)

Wherever there is consumption, it has one shape:

```json
"usage": { "input_tokens": 674, "output_tokens": 86, "cost_usd": 0.0000283 }
```

| Source | `input_tokens` ← | `output_tokens` ← | `cost_usd` ← |
|---|---|---|---|
| chat completions (`ask`, `task`, `image`) | `prompt_tokens` | `completion_tokens` | `cost` |
| Jev (`/systemone`) | `input_tokens` | `output_tokens` | `cost` |

When the provider does not return a cost, `cost_usd: null` and a warning
is created (the budget cannot be tracked precisely then) — it is never
estimated.

### Event types

**`run_started`** — the run started.

| Field | What it is |
|---|---|
| `run_id` | run id |
| `scenario`, `scenario_version` | name and `version` of the scenario |
| `request_key` | idempotency key from the webhook (§5.2), otherwise `null` |
| `inputs` | inputs after filling in `default` |
| `models` | alias → id map as it was at start (reproducibility) |
| `limits` | `run_budget_usd`, `run_image_budget_usd`, `run_timeout` |
| `framework_version` | framework version |
| `storage_prefix` | `<run_id>-<32 hex>` — prefix of files in storage |
| `fake` | `true` = fake provider (`--fake`), model responses are fabricated (since framework 0.2.2) |
| `steps_total` | number of scenario steps including those nested in `parallel`/`switch` branches, excluding steps of called scenarios; `null` for a run that did not start (since framework 0.6.0) |
| `callback_url` | where the callback goes, without the query (like `callback_sent.url`); `null` = run without a callback (CLI, GUI without `callback_url`) (since framework 0.6.0) |

**`run_waiting`** — the run waited for a free `max_parallel_runs` slot
(since framework 0.3.1). Only when it waited; it comes right after
`run_started`, even though the waiting happened before it (the run
directory is created only after the slot is obtained).

| Field | What it is |
|---|---|
| `waited_s` | how long the run waited for a slot |
| `max_parallel_runs` | the effective cap |

A slot not obtained in time (`timeout`) and an exhausted
`daily_budget_usd` (`budget`) are runs that did not start: the record has
only `run_started`, `error`, `run_finished` with `error` (`step: null`),
`callback.json` and `summary.md`, without `plan.md` and `inputs.json` —
just like a run the webhook did not start ([webhook.md](webhook.md)). The
callback is sent normally, `agencast run` prints `<class>: <message>` to
stderr and exits with code 1.

**`step_started`** — a step started.

| Field | What it is |
|---|---|
| `kind` | step type: `ask`, `task`, `jev`, `image`, `parallel`, `switch`, `call`, `set`, `fail`, `output` |
| `branch` | name of the `parallel` branch or the `switch` value the step is in; otherwise missing |
| `nn` | step number `<nn>` in its scenario (for a step of a called scenario, the number in the called scenario) (since framework 0.7.0) |
| `dir` | step directory within the run directory, e.g. `steps/03-propose/steps/01-copy` (since framework 0.7.0) |

**`step_skipped`** — a step did not run (§5.1 item 5: always with a reason).

| Field | What it is |
|---|---|
| `kind` | step type |
| `reason_code` | `when`, `switch`, `dedupe`, `cancelled` (a step that had not started, cancelled because another `parallel` branch failed or because the run was interrupted — `reason` says which: `cancelled — another parallel branch failed`, `cancelled — the run was interrupted (SIGTERM)`). Steps inside a skipped `parallel`/`switch` each get the same reason. |
| `reason` | a sentence for humans, e.g. `when: steps.tone_check.on_brand < 0.7 → false` |
| `default_used` | `true` if `default` was used as the output |
| `nn` | step number as in `step_started` (since framework 0.7.0) |

**`step_finished`** — a step finished.

| Field | What it is |
|---|---|
| `kind` | step type |
| `status` | `succeeded`, `failed`, or `cancelled` (a started step cancelled because another `parallel` branch failed or the run was interrupted; `cost_usd` = the calls so far) |
| `continued` | `true` when it failed with `on_error: continue` (→ warning) |
| `default_used` | only with `continued: true`: `true` when `default` was used as the output (since framework 0.7.0) |
| `duration_s` | duration |
| `cost_usd` | total of all calls of the step |
| `output_file` | path to `output.json` |

**`model_call`** — one chat completions call (`ask`, a `task` turn, `image`).

| Field | What it is |
|---|---|
| `attempt` | attempt 1, 2, … (retries via `retry`) |
| `turn` | only for `task`: turn number |
| `alias`, `model` | alias and id that were sent |
| `response_model`, `provider` | model and provider according to the response |
| `generation_id` | OpenRouter response `id` (for lookup in its log) |
| `http_status` | response status |
| `finish_reason`, `native_finish_reason` | how the call ended (§5.1 item 8) |
| `structured_output` | cascade level used (§5.5): `native_schema`, `tool_wrapper`, `prompt`; `null` without `schema` |
| `budget_exceeded_usd` | by how much the call exceeded the budget (the call completes and counts), otherwise missing |
| `timeout_s` | HTTP call timeout: min(remaining step time, 120 s); expiry = `transient` (since framework 0.2.1) |
| `duration_s`, `usage` | duration, normalized consumption |
| `request_file`, `response_file` | paths into `calls/` |

**`tool_call`** — `task` called a tool.

| Field | What it is |
|---|---|
| `turn` | turn in which the model called the tool |
| `server`, `tool` | MCP server and tool; for skills `server: "_skills"`, `tool: "load_skill"` |
| `allowed` | `false` when the tool was not allowed (it did not run, the model got an error) |
| `invalid_args` | `true` when the arguments did not pass validation against the tool schema (it did not run, the model got an error) |
| `is_error` | the tool returned an error (passed to the model, the step continues); also `true` for a call with `error` |
| `error` | only for a call that did not return (the step fails or was cancelled; the tool may have run): the timeout or dropped-connection message, or `cancelled before the tool answered (may have run)` when the step was cancelled during the call (step `timeout`, a failed `parallel` branch, an interrupt) |
| `duration_s` | duration |
| `call_file` | `calls/NN.tool.json` with arguments and result (for a call with `error`: `result: null` and `error`) |

**`jev_call`** — one Jev call.

| Field | What it is |
|---|---|
| `attempt` | attempt |
| `model`, `response_model` | model sent and the dated version from the response (`typesafe/jev-1.13-20260917`) |
| `http_status` | response status |
| `answers` | answer values, e.g. `{"on_brand": 0.91}` |
| `timeout_s` | HTTP call timeout: min(remaining step time, 30 s); expiry = `transient` (since framework 0.2.1) |
| `duration_s`, `usage` | duration, normalized consumption |
| `request_file`, `response_file` | paths into `calls/` |

**`image_saved`** — an image was saved to the run directory.

| Field | What it is |
|---|---|
| `path` | path relative to the run directory |
| `media_type`, `bytes` | file type and size of the file as stored (after a secret value in it was replaced) |
| `width`, `height` | dimensions from the file header |

**`error`** — an error (also one that will still be retried).

| Field | What it is |
|---|---|
| `class` | error class (scenario.md §6): `transient`, `schema`, `content`, `budget`, `timeout`, `config`, `expression`, `fail`, `internal` |
| `message` | the exact message (for the API including the provider's `error.message`) |
| `attempt` | attempt in which the error occurred (API call or MCP server start; `null` for other errors) |
| `will_retry` | `true` when another attempt follows |
| `http_status` | status, if it is HTTP |

**`mcp_server`** — start, stop or failure of an MCP server (DESIGN §5.8).

| Field | What it is |
|---|---|
| `server` | name from `mcp.yaml` |
| `action` | `started`, `stopped`, `failed` — `failed` for every failed start attempt, and at the end of the run for a server that dropped the connection during a tool call (instead of `stopped`). `stopped` without `started` = the run ended (interrupt, step or run `timeout`) while the server was still starting |
| `duration_s` | for `started` the handshake duration |
| `error` | message for `failed` |
| `stderr_file` | `mcp/<server>.stderr.log` — local (stdio) servers only; the file exists once the server has stopped. A server started more than once in a run (a retried or a later start after a failed one) appends to it |

**`file_uploaded`** — a file from `output` was uploaded to storage.

| Field | What it is |
|---|---|
| `output` | output name (`image`); for a `files` output `<name>-<i>` (`gallery-1`, since 0.18.0); `report` for the HTML record |
| `path`, `url` | from where and to where |

**`run_finished`** — the run finished.

| Field | What it is |
|---|---|
| `status` | `succeeded` or `failed` |
| `error` | `{class, step, message}` or `null` |
| `warnings` | list of sentences (steps with `on_error: continue`, missing cost, …) |
| `duration_s` | duration without waiting in the queue |
| `usage` | total of the whole run |
| `image_cost_usd` | of which images (§5.7 — counted separately) |
| `image_duration_s` | total duration of `image` steps (information only; v1 has no separate time limit for images) |

When a `serve` restart restores a queue entry with an existing
`run_started` and no `run_finished`, no second `run_started` is created.
The server adds an `error` event and `run_finished` with `status: failed`,
class `internal`, the `step` of the last started step and the message
`run interrupted by server restart` (a stored value the framework compares
when reading records). The original `run_started.ts` stays
`started_at`. In the API such a run has `state: interrupted` and a step
without `step_finished` has `status: interrupted`; the run record is kept.

**`callback_sent`** — one attempt to deliver the callback (every attempt =
one event).

| Field | What it is |
|---|---|
| `url` | address without the query |
| `attempt` | attempt 1–3 (**proposal**: 3 attempts, delays of 5 s and 30 s) |
| `http_status` | n8n response, `null` on a network error |
| `error` | message, if delivery failed |

**`callback_failed`** — after the third failed attempt (the last line of
the file), or when SIGINT/SIGTERM arrived while the callback was being sent
(`error`: `interrupted by SIGINT`, `attempts` = those made).
The run status **does not change**; `callback.json` stays in the
run directory. The CLI (`runs`) shows “callback not delivered” and
`summary.md` shows “Callback not delivered”. Recovery is handled by the
timeout in n8n (§5.1 item 7).

A callback given up because `agencast serve` was stopped is sent again
at the next start of the server: the same body, from `callback.json`,
with new `callback_sent` events after the `callback_failed` (and a new
`callback_failed` when these attempts fail too). Nothing else in the
record changes — no second `run_started` or `run_finished`, and
`summary.md` keeps its note. Once an attempt is delivered, `runs` and
`callback_failed` in `GET /runs/<run_id>` no longer report the callback
as not delivered: the last `callback_failed` or delivered `callback_sent`
decides, a refused attempt changes nothing.

| Field | What it is |
|---|---|
| `url` | address without the query |
| `attempts` | number of attempts |
| `error` | last message |

Example (shortened):

```json
{"ts":"2026-09-25T14:03:11.002Z","type":"run_started","run_id":"20260925-140311-ig-post-a1b2","scenario":"ig-post","scenario_version":1,"request_key":null,"inputs":{"topic":"new coffee"},"models":{"smart":"anthropic/claude-haiku-4.5"},"limits":{"run_budget_usd":1.0,"run_image_budget_usd":0.3,"run_timeout":"1h"},"framework_version":"0.1.0"}
{"ts":"2026-09-25T14:03:11.010Z","type":"step_started","step":"copy","kind":"ask"}
{"ts":"2026-09-25T14:03:14.720Z","type":"model_call","step":"copy","attempt":1,"alias":"smart","model":"anthropic/claude-haiku-4.5","response_model":"anthropic/claude-haiku-4.5","provider":"Anthropic","generation_id":"gen-…","http_status":200,"finish_reason":"stop","native_finish_reason":"end_turn","structured_output":"native_schema","duration_s":3.7,"usage":{"input_tokens":812,"output_tokens":214,"cost_usd":0.0015},"request_file":"steps/01-copy/calls/01.request.json","response_file":"steps/01-copy/calls/01.response.json"}
{"ts":"2026-09-25T14:03:14.731Z","type":"step_finished","step":"copy","kind":"ask","status":"succeeded","continued":false,"duration_s":3.72,"cost_usd":0.0015,"output_file":"steps/01-copy/output.json"}
{"ts":"2026-09-25T14:03:15.050Z","type":"step_skipped","step":"stop","kind":"fail","reason_code":"when","reason":"when: steps.tone_check.on_brand < 0.7 → false","default_used":false}
```

## `summary.md`

For humans, in English, always the same structure (**proposal**):

```markdown
# ig-post — success

Draft IG post for approval (part 1; part 2 publishes it via n8n)
Run `20260925-140311-ig-post-a1b2` · 2026-09-25 14:03 UTC · 17.5 s · 0.06934 USD (of which images 0.0672 USD)

## Inputs
- topic: new coffee

## Steps
| # | Step | Type | Status | Time | Cost | Note |
|---|---|---|---|---|---|---|
| 1 | copy | ask | ✓ | 3.7 s | 0.0015 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | tone_check | jev | ✓ | 0.3 s | 0.00002 | on_brand = 0.91 |
| 3 | stop | fail | skipped |  |  | when: steps.tone_check.on_brand < 0.7 → false |
| 4 | photo_prompt | ask | ✓ | 1.8 s | 0.0006 | fast → google/gemini-3.5-flash-lite (tool_wrapper) |
| 5 | image_check | jev | ✓ | 0.3 s | 0.00002 | real_person = 0.02, other_brand = 0.01 |
| 6 | stop_image | fail | skipped |  |  | when: … → false |
| 7 | photo | image | ✓ | 10.6 s | 0.0672 | image.png, 1408×768 |
| 8 | out | output | ✓ | 0.0 s | 0 |  |
| | Total | | | 17.5 s | 0.06934 | of which images 0.0672 |

## Warnings
none

## Output
- caption: “…”
- hashtags: #coffee, #lumen
- image: https://files.example.com/20260925-140311-ig-post-a1b2-3f9c1e7a0b5d4c2e8a6f1d9b7c3e5a0f/image.png
```

The header shows the start as `YYYY-MM-DD HH:MM UTC`; numbers use a decimal
point. The Status column is `✓` (succeeded), `failed`, `cancelled`, `skipped` or
`failed, continuing` (`on_error: continue`).

The last row of the table, **Total**, has the time and cost of the run
(`duration_s` and `cost_usd` in `run_finished`, the same numbers as in the
header and `callback.json`) and, for a run with images, the note “of which
images …”. The Total time is the time of the whole run, not the sum of the
steps: steps in `parallel` run concurrently and the time and cost of
`parallel`, `switch` and `call` already include the steps inside, so Total
is not a plain sum of the column. A failed run has a Total row too (time
and cost so far). Since framework 0.2.4, time since 0.2.5.

On error the heading is `— failed`, right below it is an **Error** block
with the class, the step and the exact message, and the steps table shows
where the run ended. A fake run (`--fake`) has a **Fake run** line below
the header (since framework 0.2.2).

`report.html` has the same content plus expandable prompts and responses
(without base64). The HTML layout is decided in Phase 2.

## Callback

It is sent **always** once the run has a `run_id` — on success and on
error, even when `validate` fails only after the run is taken from the
queue (D2, §5.1 item 2). Requests rejected immediately by the webhook
(401, 422) have neither a `run_id` nor a callback
([webhook.md](webhook.md)). `POST` to the `callback_url` from the request,
JSON body:

```json
{
  "run_id": "20260925-140311-ig-post-a1b2",
  "scenario": "ig-post",
  "request_key": "n8n-4711",
  "status": "succeeded",
  "outputs": {
    "caption": "…",
    "hashtags": ["#coffee", "#lumen"],
    "image": "https://files.example.com/20260925-140311-ig-post-a1b2-3f9c1e7a0b5d4c2e8a6f1d9b7c3e5a0f/image.png"
  },
  "error": null,
  "warnings": [],
  "cost_usd": 0.0693,
  "duration_s": 17.5,
  "report_url": "https://files.example.com/20260925-140311-ig-post-a1b2-3f9c1e7a0b5d4c2e8a6f1d9b7c3e5a0f/report.html",
  "sent_at": "2026-09-25T14:03:36.120Z"
}
```

On error:

```json
{
  "run_id": "20260925-141502-ig-post-9f3c",
  "scenario": "ig-post",
  "request_key": "n8n-4712",
  "status": "failed",
  "outputs": null,
  "error": {
    "class": "fail",
    "step": "stop",
    "message": "The text does not match the brand (on_brand = 0.42)"
  },
  "warnings": [],
  "cost_usd": 0.0016,
  "duration_s": 4.4,
  "report_url": "https://files.example.com/20260925-141502-ig-post-9f3c-8b2d6f0e4a1c7e9d3b5f2a8c6e0d4b1a/report.html",
  "sent_at": "2026-09-25T14:15:06.530Z"
}
```

| Field | What it is |
|---|---|
| `status` | `succeeded` / `failed` |
| `outputs` | values according to the scenario's `outputs`; a `file` is replaced with a **URL** in storage, a `files` output with a list of URLs (since 0.18.0); a file inside a `list`/`object` output stays a run-relative path. `null` on error. |
| `error` | `{class, step, message}` or `null`; `step` is a path (`propose/copy`) |
| `warnings` | the same as in `run_finished` |
| `report_url` | URL of `report.html`; when uploading the record fails, `null` and a warning |
| `sent_at` | send time — n8n can reject old messages |

File addresses have the form `<public_base_url>/<run_id>-<32 random hex
characters>/<name>` — for all files including `report.html` (DESIGN §5.2).
The random part is created at run start and is only in the callback and in
the record (`run_started.storage_prefix`), so that nobody can find
unapproved images or prompts by trying `run_id` values.

Signature (§5.2, **proposal** of the shape): header
`X-Signature: sha256=<hex>`, where `<hex>` = HMAC-SHA256 over the exact
bytes of the body with the secret from `callback.secret_env`. The
`X-Run-Id` header carries the `run_id`. n8n verifies the signature before
trusting the message.
