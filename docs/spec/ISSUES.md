# Ambiguities in the v1 spec found during implementation (Phase 2)

The v1 spec is frozen; none of this changes it. For each item there is the interpretation
by which framework 0.1.0 behaves. None of it blocked the work;
the coordinator or the user decides.

1. **`tool_wrapper` and `finish_reason`** (scenario.md ask, §6): the spec wants
   `tool_calls`. The framework also accepts `stop` when the response contains a call to
   `_submit_output` (with a forced `tool_choice` some providers
   report this as `stop`). Any other `finish_reason` → `transient`. Live, Gemini
   3.5 Flash-Lite returned `tool_calls` (natively `STOP`).
2. **Which environment variables are mandatory before a run** (config.md “A missing
   variable → config”): the framework checks only those the run will actually
   use: `OPENROUTER_API_KEY` (not with `--fake`), `callback.secret_env` only
   with `--callback-url`. `webhook.token_env` only with the webhook server, R2 keys
   only with R2.
3. **A relative `runs_dir` and `storage.local.path`** — the spec does not say relative
   to what. The framework takes them relative to the project root (the folder above `workflows/`),
   because the framework never writes into `workflows/`.
4. **`aspect_ratio` in chat completions** (scenario.md image): the framework
   sends `image_config: {aspect_ratio}` (the field `ChatRequest.image_config`,
   <https://openrouter.ai/docs/llms-full.txt>, downloaded 2026-09-25) and
   checks the ratio against the file header (±2 %). **Verified live
   2026-09-25:** `google/gemini-3.1-flash-image` with `"4:5"` returned
   928×1152 (deviation 0.7 %), the endpoint does not ignore `aspect_ratio`.
   The spec mentions only the Image API (`POST /api/v1/images`); the decision “chat
   completions” was made in Phase 2 per the assignment.
5. **`report_url`**: Phase 2 does not generate `report.html`, `report_url` is
   `null` without a warning. The spec expects `null` + a warning only when the
   upload fails. *(Resolved in 3b: the report is generated and uploaded.)*
6. **`callback.json` without `--callback-url`**: it is always written (the body that
   would have been sent), although the spec says “exactly what was sent in the callback”.
7. **`details` in the `default` of a `jev` step**: the spec says “`details` is filled in as
   `{}`”. The framework fills in `{question: {}}` for each question so that
   `steps.x.details.<q>` exists; a missing key inside is then an `expression`
   error.
8. **Extra fields in `default`** (a field the step does not return) are a
   `validate` error — the spec explicitly says only “must contain all fields”.
9. **Functions and indexes**: `join` requires both arguments (the spec table
   `join(list, separator)`); `min`/`max` only numbers; `[]` over text
   (`"abc"[0]`) is an error, because the spec knows `[]` only for a list and an object.
   The index `2.0` is allowed (a number with a zero fractional part = integer).
10. **Examples in the spec as conformance tests** (§5.9 point 3): step snippets
    without a header refer to steps that are not in the snippet, so they pass
    only the JSON Schema and the expression/template syntax. Fully (validate + a run
    with a fake provider) only the whole scenario `greeting` is tested.
11. **`when` with an expression error** (§3 “an error in `when` is a step error”):
    the step gets `step_started`, `error` and `step_finished` with
    `status: failed` (not `step_skipped`).
12. **Step timeout with an agent**: the step's `timeout`, otherwise the agent's
    `limits.timeout`, otherwise the default by type, always at most the agent's `limits.timeout`.

## Phase 3b (call, webhook, report.html)

13. **The `call` step folder**: the 3b assignment mentions `steps/<nn>-<id>/call/`,
    the spec (run-record.md) `steps/03-propose/steps/01-copy/`. The framework follows the spec;
    in addition it writes `steps/<nn>-<id>/inputs.json` (the call inputs)
    and `output.json` (the output = the `outputs` of the called scenario). `summary.md`
    has in its table only the steps of the calling scenario (for `call` a note with
    the scenario name), nested steps are in `events.jsonl` and `report.html`.
14. **`callback_url` on `http://127.0.0.1`**: the spec wants “only `https://`”.
    The framework also allows `http://127.0.0.1:<port>/…` (tests, a local
    receiver per the 3b assignment) — in the webhook and in `agencast run --callback-url`.
    Not `localhost` or any other `http://`.
15. **`queue_position`**: the number of requests in the queue including the one currently
    running and this one (1 = starts immediately). The spec says only “position in the queue”.
16. **`GET /runs/<run_id>`** is not in the spec (it is in the 3b assignment): wants the same
    token; returns `{status: queued, queue_position}`, `{status: running}`,
    or the body of `callback.json` + `callback_failed`; an unknown run 404.
17. **The webhook body**: an unknown field is 422 (like “a typo is an error”
    for the formats). A repeated `request_key` returns 200 with the original `run_id`
    even when the rest of the body differs (it is checked right after the token).
18. **A run that does not start** (validate fails after pick-up from the queue, or a
    server restart interrupted the run): the folder has `run_started` with
    `scenario_version: null` and no steps, `error` and `run_finished`
    with class `config` / `internal`, `report.html` and a callback. An interrupted
    run is not repeated (it may have had side effects) and the callback carries
    `internal`, even when the run may have finished and only the callback was not sent.
19. **`on_error: continue` on `call`** also covers an error of a step inside
    the called scenario (`error.step` stays the path `propose/copy`) and
    the exhaustion of the `call` step's own `budget_usd`/`timeout`; not the run's budget
    and time (scenario.md §6).
20. **`report.html` is created before `run_finished`**, so that the warning
    about a failed upload is in `run_finished` and in the callback; the callback
    delivery state is therefore not in the report (it is in `summary.md`
    and `events.jsonl`).

21. **The `retry` delay on a `schema` error** (scenario.md §3 `retry`: “on an
    error `transient` or `schema` … Delay 2 s, 4 s, 8 s…”): the framework
    waits only after `transient`; after `schema` it immediately tries the next cascade level
    (the run `tutorial-02-name-and-slogan` with the fixture `text:` instead of `json:`
    took 0.003 s). Waiting on `schema` brings nothing, but the spec reads it differently.
    (Found while writing the tutorials.)
22. **The callback URL in the record without a port** (run-record.md “Only
    `scheme://host/path` is logged from the callback URL”): `--callback-url
    https://127.0.0.1:8443/webhook-waiting/4711` is in `callback_sent` as
    `https://127.0.0.1/webhook-waiting/4711`. Literally per the spec, but when
    debugging n8n on a non-standard port the port is missing. (Found while writing the
    tutorials.)

## Phase 3a (the `task` step, MCP, skills, `dedupe_key`; framework 0.2.0)

23. **The root `{run_dir}/…` does not exist:** server-filesystem rejects a nonexistent
    allowed folder. Before starting a stdio server the framework creates a
    folder for each argument that starts with `{run_dir}` (for the example
    `runs/<run>/work`).
24. **When the `dedupe` `started` is created:** before the first call of an **MCP** tool
    (a side effect), not before `load_skill`. A step that called no MCP tool
    writes `succeeded` directly. The file contains exactly
    `{state, run_id, output}`. The key is computed from the name of the scenario the step
    is in (for `call` the name of the called scenario and the `id` of the step in its file).
25. **The last turn of `max_turns`:** when the model in the last allowed turn
    wants more tools, the framework **does not run** them (the model would not
    see the result, a side effect without control) and the step ends with `budget`.
26. **An MCP handshake failure**: the step fails with class `transient` (a remote server:
    network, 408, 429, 5xx, timeout) or `config` (stdio: an unknown command, the process
    exited, did not answer the handshake; remote: any other 4xx). *(Changed in 0.18.0:
    a `transient` failure is first retried according to the step's `retry`, like a model
    call, `Retry-After` included — scenario.md, the `task` step; before that it was not
    retried and retrying the run was up to n8n. Network errors after the connection was
    made — a reset, a server that closes without an answer — are `transient` too, and an
    HTTP status of the SSE message POST is reported as that status, not as a timeout.)*
27. **A JSON-RPC error on `tools/call`** (not `isError`, e.g. an unknown tool
    −32602) goes to the model as a tool error (`is_error: true`, the step
    continues) — the server rejected the call. A dropped connection = `config`, a timeout
    = `timeout`.
28. **`_submit_output` together with other tools in one turn:** the result is
    `_submit_output`, the other tools are not run and a warning is written.
    Tool calls with `finish_reason: stop` are accepted (as in point 1).
29. **`task` at the `tool_wrapper` level:** `_submit_output` is among the tools,
    but `tool_choice` is not forced (the model calls other tools in the meantime).
    A text answer instead of `_submit_output` = a `schema` error → the cascade goes to
    `prompt`.
30. **Variables from `mcp.yaml`** (`env`, `bearer_token_env`) must not be the same
    as the `*_env` from `config.yaml` (the OpenRouter key would go to the MCP server) —
    a `config` error. Sharing among servers in `mcp.yaml` is allowed. A missing
    variable is reported before the run only for servers the run will actually use
    (as in point 2).
31. **`scenarios` of a server** is checked for servers the step will actually
    use (`task.mcp`, otherwise the agent's `mcp`), not for all servers of the agent.
    `ask` connects no MCP, so nothing is checked there.
32. **A tool from the allowlist that the server does not offer** → the step fails with `config`
    at run time (the list of offered tools is in the message). The spec wants
    `--dry-run` to show it: `agencast run … --dry-run` starts the servers the run may
    start, because of `tools/list`, in a temporary folder (the plan folder
    keeps only `plan.md`) and `plan.md` lists what they offer and the resulting
    tool set of each `task` (added when merging 3a + 3b). *(Since 0.18.0 the plan
    marks such a tool `(NOT OFFERED by the server)` in the step row and lists it after
    the server's offer as `allowed but NOT OFFERED: …`.)*
33. **Contents of a tool result:** text and image are passed on, other types
    (`resource`, `audio`, …) as the text `[content of type X is not forwarded
    by the framework]`; `structuredContent` is not passed on (the text usually carries it).
    `calls/NN.tool.json` (proposal): `{turn, name, server, tool, arguments,
    allowed, invalid_args, is_error, result, files}`.
34. **A stuck provider call** (measured in a live 3a run: an HTTP
    connection without a response for 160 s, the same request immediately afterwards 2.1 s) is
    recognized only by the step's time limit — the HTTP client has no read
    timeout for a single call (Phase 2, `Timeout(None, connect=15)`), so it is not
    retried as `transient`. Proposal: a read timeout of the call (e.g. 120 s) → `transient`
    with `retry`; watch out for slow reasoning models with a large `max_tokens`.
    The coordinator decides.
    **Resolved in 0.2.1:** the timeout of each call = min(remaining step time,
    120 s chat/image/`task` turn, 30 s Jev), expiry = `transient`
    (retried per `retry`), the value in `model_call`/`jev_call` as
    `timeout_s`. It is an httpx read timeout (silence between bytes of the response),
    not the total duration — that is still guarded by the step's timeout.

35. **A `run_id` collision** (run-record.md: `<time>-<scenario>-<4 hex>`): two runs of
    the same scenario in the same second have the same id with probability
    1 : 65,536; with a batch of 50 requests per second from n8n that is ≈ 2 %.
    Consequence: `agencast serve` overwrites the queue entry `<run_id>.json` of another
    request, `agencast run` crashes on the existing run folder. Proposal: a longer
    random part, or a new id when the folder/queue entry already exists.
    Not fixed (outside the 0.2.1 assignment). (Found while hunting unstable
    tests.) **Resolved in framework 0.3.0 by retrying** (point 39): the id
    format does not change; on a collision a new suffix is generated, at most 5×, then an
    `internal` error.
36. **`task` with `schema` always starts the cascade at `tool_wrapper`** (an interpretation,
    decided by the coordinator 2026-09-25, framework 0.2.2). The spec (scenario.md,
    the cascade) says “the level starts at `models.<alias>.structured_output`”,
    but does not address the combination with the tool loop. Native JSON schema
    (`response_format`) sent in every turn together with `tools` tempts
    some models to answer directly with JSON without calling tools — Haiku 4.5
    in 3 of 3 live runs (BUGS 7): the loop ended in “success”
    with an invented output and the side effect did not happen. Therefore in `task`
    the framework does not send `response_format`; it enforces structured output
    with the `_submit_output` tool (point 29), a text answer = a `schema` error
    → the cascade goes to `prompt`. `models.<alias>.structured_output` still applies
    only to `ask`. The level used is in `model_call.structured_output`
    and in the step note in `summary.md`, `plan.md` shows “cascade from
    tool_wrapper”.
37. **Subfolders in `agents/` and `scenarios/` are ignored** (decided by the
    coordinator and the user 2026-09-25, framework 0.2.3). The rule
    from REVIEW M9 “a subfolder is a `config` error” stopped every run as soon as
    a user moved old files into `archive/`. Same-named files
    in subfolders do not matter, because subfolders are not read at all (agents,
    `call` targets, the webhook, `check.py`). The relaxation is backward compatible
    (DESIGN §5.9). Only a scenario stored directly in
    `workflows/scenarios/` can still be run. When an agent or a `call` target does not exist, but a
    same-named file lies one level down in a subfolder, the message adds:
    “(file is in subfolder agents/archive/, subfolders are not read)”.
38. **Whole costs, a Total row** (decided by the coordinator and the user
    2026-09-25, framework 0.2.4). A run on `mistralai/mistral-nemo` cost
    4.482e-06 USD, `summary.md` and `report.html` showed “0.0000 USD”
    (4 places) and `callback.json` 4.48e-06 (`round(…, 8)`) — the report did not
    show how much the run cost (R2). Now: the call cost = exactly `usage.cost`
    from the provider, totals rounded only to 10 places because of float
    noise, for humans decimal with a point, at least 4 places, more only for
    stored digits, an actual zero `0`. The step table ends with a row
    **Total** = the run cost (the same number as `cost_usd` in `run_finished`
    and the callback), for images with the note “of which images …”; the time empty.
    The JSON format does not change, only precision → backward compatible.
    Added in framework 0.2.5 at the user's request: the Time column in the Total
    row = the time of the whole run (`duration_s` from `run_finished`, the same number
    as in the header), not the sum of the column — `parallel` branches run concurrently
    and nested steps are already in the time of the parent step.
39. **Concurrent runs** (coordinator's assignment 2026-09-26, framework 0.3.0).
    `agencast serve --workers N` runs N runs at a time over one queue
    (default 1 = the existing behavior, D2); `api.run` from multiple threads or
    processes over the same `runs/` folder too. What concurrency broke:
    (a) **`run_id`** (point 35) — `Record` with the folder `exist_ok=False` on
    `FileExistsError` tries a new suffix, at most 5×, then `internal`;
    the webhook on acceptance skips an id that already has a queue entry
    or a run folder anyway. Recovery after a server restart (`exist_ok=True`) does not
    change. (b) The **`/models` cache** (`<runs>/_models.json`) is written
    to a temporary file in the same folder and `os.replace`d; a corrupted JSON is
    treated by a reader as “no cache”. (c) **`dedupe_key`** is behind the
    `DedupeStore` interface (`get`, `claim` exclusively and atomically via `O_EXCL`,
    `finish` via rename); local files and the paths
    `<runs>/_dedupe/<sha256>.json` and `_dedupe-fake/` stay unchanged,
    old records stay valid. On Modal its own storage is plugged in here
    (DESIGN “Wrappers”). Queue recovery and `request_key` (`_queue/keys/`)
    are still under a lock; `queue_position` counts waiting and running requests,
    the completion order with N > 1 is not guaranteed (webhook.md).
40. **A cap on concurrent runs and a daily spend limit** (decided by the user
    2026-09-26, framework 0.3.1). With `--workers` (point 39), manual CLI, n8n
    and cron over one `runs/` there was no way to limit how many runs would go at once
    or how much would be spent per day — `run_budget_usd` guards only a single
    run. Now two **optional** `limits` keys (without them nothing changes, R8):
    (a) **`max_parallel_runs: N`** — slots `<runs>/_slots/<n>.lock`
    (`flock`, shared by all processes; the lock is released even when the process
    crashes). A slot is taken before the run folder is created and is always released. Full → stderr
    “waiting for a free slot (max_parallel_runs=N)”, polling every 0.5 s,
    at most `run_timeout`, then `timeout` (“no slot became available within
    run_timeout … — run did not start”). The wait is in the record as `run_waiting`
    with `waited_s`. Fake runs take part in the slots. No new error class is created.
    (b) **`daily_budget_usd: X`** — the daily ledger
    `<runs>/_ledger/<YYYY-MM-DD>.jsonl` (UTC by the end of the run), a row
    `{run_id, cost_usd, finished_at}` for each finished run, appended under
    `flock`; `--fake` goes to `_ledger-fake/`. At run start (after acquiring a
    slot) a sum ≥ X → `budget` before the first call (“daily spend limit
    exhausted: already … today (… UTC) of X USD (daily_budget_usd) — run did not
    start”). The check is only at start — a run may exceed the limit by at most
    its `run_budget_usd`. The ledger has existed since 0.3.1 and is always written.
    A run that did not start because of (a) or (b) takes the same path as a run
    the webhook did not start (`run_scenario(error=…)`): a folder with only the
    record and `summary.md`, without `plan.md`/`inputs.json`, `run_finished`
    with `error` (`step: null`) and a callback. Both slots and the ledger are behind an interface
    next to `DedupeStore` (`SlotStore.acquire/release`,
    `Ledger.total/add` in `task.py`) — Modal plugs its own storage in here
    (DESIGN “Wrappers”). Note: the ledger is a shared append-only file, which
    D2 (“never one shared log”) formally does not anticipate; a write is
    one line under `flock`.
    **Decision (coordinator, 2026-09-26):** both accepted. The ledger is
    always written, because it also serves as a daily spend overview and a limit turned on
    during the day should count the runs so far as well. The exception to D2 is bounded:
    one row per finished run, one file per day, under `flock`;
    run records stay separate. On Modal the wrapper replaces the ledger through the
    `Ledger` interface.
41. **The project registry and `agencast new`** (decided by the user and the coordinator
    2026-09-26, framework 0.4.0; [projects.md](projects.md)). A GUI on top of
    AgenCast needs a list of projects; scanning the disk was rejected,
    a registry is kept in `~/.config/agencast/projects.yaml`
    (`AGENCAST_CONFIG_DIR`), `projects: [{name, root}]` without secrets.
    It is filled by `new project`, `projects add` and a successful `validate`/`run`
    (a message once on stderr); a name collision → `config` with the hint
    `--name`, for `validate`/`run` only a printout, the command completes. A missing
    `workflows/config.yaml` = `available: false`, the entry stays.
    `new project|agent|scenario` creates files from templates in the framework
    and overwrites nothing. v1 formats unchanged.
42. **The `serve` read API for the GUI** (decided by the user and the coordinator
    2026-09-26, framework 0.4.0; [api.md](api.md)). The GUI (`ui/`, DESIGN
    “Wrappers”) talks to the core only over HTTP. The `/projects/...` family is
    additive: `POST /runs`, `GET /runs/<id>` and the callbacks do not change (n8n).
    `serve` in a project or with `--project` = a single project with its
    `webhook.token_env`; outside a project = registry mode with one server token
    `AGENCAST_TOKEN` (the coordinator's variant A: per-project
    tokens would collide by variable names in one process). In the registry the
    secrets are taken from the server's environment (and `.env` in the cwd), the variable names
    from the project's `config.yaml`. The project and scenario description is read by the loader and
    `validate` (`check_models=False`), not by a custom parser; errors are
    in the `errors` field, a broken file is shown as far as possible. `files/` lets through only
    files inside the run folder (otherwise 404), `spend` only the live ledger.
    An unknown project/scenario/run → 404 with a JSON error.
43. **Editing operations for the GUI** (coordinator's assignment 2026-09-26,
    framework 0.5.0; [api.md](api.md) “Editing”). The GUI changes files only through
    core operations (`agencast/edit.py`) over `serve`; the file stays
    the truth. The version fingerprint = sha256 of the content (not mtime — easy to compare
    in tests and in the GUI); a mismatch → 409, nothing is written. Validation before
    writing = a copy of `workflows/` with the change + `validate(check_models=False)`
    (the cheapest correct route: validation works over files, not over
    in-memory data); only a **new** error blocks — if every one blocked,
    two broken files that refer to each other (a scenario and its `call`)
    could not be fixed one after the other. Writing round-trips through `ruamel.yaml`
    (DESIGN D4), unchanged lines verbatim from the original (ruamel otherwise changes
    spacing in flow maps). A step address = a path in the document
    (`["steps", 2, "parallel", "a", 0]`), the same in `GET …/scenarios/<s>`
    (`address`) and in the operation URLs. Field changes are a merge patch (RFC 7396);
    a `null` value cannot be written with it (a whole step via `POST …/steps` or
    text via `files/`). Deleting an agent, a skill and a scenario refuses a file
    that is in use, based on the links from 0.4.0 (`links`). Raw text only for
    `agents/*.md`, `scenarios/*.yaml`, `skills/*/SKILL.md`, `config.yaml`,
    `mcp.yaml`; never `.env`. `config` through the form only `models`,
    `limits`, `storage`, `webhook`, `callback` and `openrouter.api_key_env`.
    v1 formats unchanged. *(Since 0.18.0 `mcp.yaml` is no longer among the raw-text
    files — item 49.)*
44. **API additions for the GUI** (coordinator's assignment 2026-09-26, framework
    0.6.0; [api.md](api.md) “GUI additions”, GUI design
    `docs/ui/gui-design.md` §7.2–7.4, §8.4–8.5). Errors as objects
    `{message, file?, step?, field?, line?}`: the fields are read from the start of the
    message (`<file>[, line N][: step "id"][, field]: …`) in one place
    in the HTTP layer (`projects.error_fields`) — so the `validate` and loader messages
    stay the only source and the CLI does not change; carrying the structure
    from every place an error originates (`_Checker.err`, `schema_errors`,
    `load_yaml`, …) would mean changing dozens of calls. A known ceiling: a scenario
    named `config` or `mcp` gets `file: config.yaml`/`mcp.yaml`.
    `POST …/validate` = the same copy of `workflows/` as the editing operations
    (`edit._errors_with`), returns all errors. `env` = only `true/false`
    (a non-empty variable in the `serve` environment), never the value. Runs: the source is
    `events.jsonl`, `steps_total` from the new field `run_started.steps_total`
    (a plan as a file would have to be parsed). Starting from the GUI: `callback_url`
    optional only in `POST /projects/<p>/runs`, without it
    `run_started.callback_url: null`; `dry_run` synchronously (200), with
    `callback_url`/`request_key` 422. The GUI is served without a token (static
    files without data; the token still protects `/projects…` and `/runs…`), CORS only
    with `--cors <origin>`. The change of the `errors` shape is the only non-additive change;
    the GUI is the only client.
45. **API from GUI findings** (coordinator's assignment 2026-09-26, framework
    0.7.0; `docs/ui/api-findings.md`, [api.md](api.md) “Additions from
    GUI findings”). Running × interrupted: `flock` on `<run>/run.lock` for the life of the
    process (like the `max_parallel_runs` slots — a crash releases the lock, nothing
    needs cleaning up); a reader tries the shared lock without waiting, so a run takes
    the exclusive lock blocking (a reader holds it for microseconds). A file, not a PID:
    PIDs are recycled and make no sense on Modal. The machine `state` next to the
    textual `status`; `cancelled` is only reserved (a v1 run does not end that way).
    Step details, a run step and `current_nn` from `events.jsonl`
    — `step_started`/`step_skipped` now have `nn` and `dir` (for older
    runs derived from file paths, `current_nn` is `null`). The run step tree
    from the snapshot `<run>/scenario/` (a copy of the files, not a tree in
    `run_started`: the same parser as `GET …/scenarios/<s>`, no new format);
    runs without a snapshot have the tree from the current file
    with `tree_source: current`. `last_run` and the `scenario` filter by the name
    in `run_id` — without reading records; the limit is applied before reading. Reading
    runs takes only `runs_dir` from `config.yaml` (otherwise `./runs`), so a
    broken config does not hide old runs. `links.scenario_step_agent`
    additively, because GUI part 1 reads `scenario_agent` as pairs.
    A loader fix: “first at line N” for a duplicate key in `.md` frontmatter
    now accounts for the `---` line. All additive.
46. **API from GUI findings, part 2** (coordinator's assignment 2026-09-26,
    framework 0.8.0; `docs/ui/api-findings.md` items 10–20, [api.md](api.md)
    “Batch, preview and additions…”). A batch instead of `PATCH` with `rename_refs`:
    solves renaming and deleting a read step, an incomplete new step,
    an empty branch and atomicity with one mechanism; the individual endpoints
    call the same operations over an in-memory document. An operation error (address,
    field) in a batch is 422 with `op`, not 404 — it is a request body error.
    `rename_refs` rewrites only expressions (`when`, `switch.value`, `set`)
    and the content of `{{ }}` with the regex `steps.<id>.` with a boundary before `steps` —
    prompt text outside a template and comments stay. `render` returns
    all errors (like `validate`), not just new ones, and 200 even with errors.
    State of a fresh run: `dry_run` = without `run.lock` (a dry run never had a lock)
    instead of a new marker — zero format change and old dry run
    folders are still read correctly; a queue entry overrides `interrupted`
    with `queued`. `models_used` as file paths (like `errors[].file`),
    keys also unused aliases. `PUT …/config`: `runs_dir` and `jev_model`
    allowed, `base_url` and `version` not (a key / the format); `runs_dir` while
    `serve` runs needs a restart because of the queue. The `description` of a new
    file is written as a JSON string (valid YAML, no extra
    escaping).
47. **Projects from the GUI** (assignment 2026-09-26, framework 0.9.0, [api.md](api.md)
    and [projects.md](projects.md)). `serve` in registry mode can create a
    project from the existing templates, register a project with
    `workflows/config.yaml` or remove an entry without deleting files.
    The default root `projects_root` is `~/workspace` (`~/agencast-projects` after 0.19.0); the API expands `~`,
    normalizes paths, forbids `..` and a relative escape through a symlink.
    Writing outside the server's home directory stays allowed and runs with the permissions of the
    `serve` user; in single-project mode writes are 405.
48. **API additions from GUI findings 21–28** (framework 0.10.0,
    [`docs/ui/api-findings.md`](../ui/api-findings.md)). Recovery of an interrupted run
    keeps `run_started`, writes `run_finished failed` with the last
    step and returns `state: interrupted`; orphaned steps are `interrupted`.
    Config schema errors get a YAML line; `/projects` adds counts
    and the day's spend; runs have the cursor `before` and `next_before`; `render` and
    `validate` can return a tree from scenario text; batch operation errors
    carry the step and field. `callback.secret_env` is checked only with
    a callback and `webhook.token_env` only in single-project mode. Formats
    v1, `POST /runs` and the callback contract do not change.
49. **`mcp.yaml` is the owner's alone, also towards the API** (decided by the user
    2026-10-01 — “the GUI does not need to configure MCP servers” —, framework 0.18.0;
    DESIGN §5.2, [config.md](config.md), [projects.md](projects.md), [api.md](api.md)
    “MCP servers are the owner's”). Until then the token of `serve` could write
    `mcp.yaml` as raw text (`PUT …/files/mcp.yaml`) and a run — a dry run was enough —
    started the `command` written there; a `url` with `bearer_token_env` sent any
    variable of the host away. The second door: `POST /projects` registered any
    directory with `workflows/config.yaml`, including a project tree that an agent with a
    filesystem server had written into its run's `work/` folder. Now no route serves
    or writes `mcp.yaml` (the exception: an agent rename rewrites that agent's name in
    the `agents` lists and verifies that nothing else changed), and every entry the API
    writes into the registry has `trusted: false` — also `POST /projects/new`, although
    the templates contain no `mcp.yaml`: the new tree can sit where an agent writes
    later. An untrusted project gets a `config` error from `validate` for every scenario
    that would use an MCP server, until `agencast projects trust <name>`. The lookup is
    by the root as addressed and as resolved; a project that is not in the registry is
    trusted for the CLI and for single-project `serve` (the terminal user's own), but
    not for `serve` in registry mode, where it can only be a project removed while its
    run was queued. The registry key is additive (no key = trusted). What the token can
    still change in `config.yaml` (`*_env` names, `runs_dir`, `storage`, `limits`) is
    unchanged and left for a later decision.
