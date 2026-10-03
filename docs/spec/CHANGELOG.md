# Format changelog

Every change to the agent, scenario or configuration format is recorded here
(DESIGN §5.6). A format changes only by raising `version`; the framework can read
all released versions (R7).

Up to 0.2.5 the package and the command were called `maw`; older entries keep that name here.

## version 1 — 2026-09-25 (draft for approval)

The first specification. It contains:

- [agent.md](agent.md) — an agent as Markdown with frontmatter (D1a).
- [scenario.md](scenario.md) — the scenario, the 10 step types of v1 (D1d), templates
  and expressions (D1c, §5.4), `call` (§5.3), errors (§5.1).
- [config.md](config.md) — `config.yaml`, `mcp.yaml`, `commands.yaml`
  (structure only; the `run` step is not in v1).
- [run-record.md](run-record.md) — the run folder, `events.jsonl`,
  `summary.md`, the callback.
- [schema/](schema/) — JSON Schema draft 2020-12: `agent`, `scenario`,
  `config`, `mcp`, `skill`.

Deviations from the illustrative syntax in DESIGN (§3 D1a/D1d, §6) — for
approval in [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md):

- the instruction for the model in `ask` is called `prompt` (in §6 `task`, which collides
  with the `task` step type),
- `schema` is written inside `ask`/`task` (as in §6), not at the step level,
- a step's budget is written `budget_usd` (like `limits.budget_usd` on an agent),
- a scenario declares `outputs` in the header; the `output` step is last,
- new error classes `fail` and `internal`.

Added because DESIGN requires it, even though it is not in the D1d list: `default`
(§5.4), `dedupe_key` (§5.2). Added for the reference scenario: the
`aspect_ratio` field of the `image` step (IG 4:5) and `max_tokens` on a model alias
(reasoning models, `finish_reason: length`).

### Added 2026-09-25 — the expression language (spike (c))

- [scenario.md §5](scenario.md) describes the expression language exactly: what is in
  it (a list literal, `in`, `%`, a negative index, `["key"]`) and what is
  not (an `if/else` condition, slices, `**`, methods, assignment, `lambda`,
  comprehensions, attributes, `import`); a dot = reading a key; strict types
  (comparing across types is an error except `== null` / `!= null`, `boolean`
  is not a number, text + number is an error, `/` is always decimal); 8 functions
  with type checking; `round` rounds half away from zero; `str(null)` = `"null"`;
  limits of 2000 characters / depth 100; example messages.
- Decided: the literals `true` / `false` / `null` (OPEN-QUESTIONS 7).
- A new error class `expression` (an expression or template error at run time; behaves
  like a step's `fail`, is not retried). The static check of expressions in
  `validate` stays class `config`. The class was also added to the list in
  [run-record.md](run-record.md).
- `null` in a template is an error, the exception being an explicit `default`.
- New open questions 8–10 (coordinator decisions with a default choice).
- JSON Schema unchanged (expressions are strings).

### Fixes after the independent review — 2026-09-25

According to [REVIEW.md](REVIEW.md) (41 findings) and the coordinator's decisions; the status
of each finding is at the end of REVIEW.md.

- **Verification:** the examples and snippets are verified by [`tools/check.py`](tools/check.py)
  — **with the same loader the framework will use** (PyYAML `SafeLoader` without
  YAML 1.1 resolvers, a duplicate key check, `jsonschema` Draft
  2020-12). The earlier verification through `check-jsonschema` (ruamel) hid the
  PyYAML problems with `4:5`, `yes`/`on` and duplicate keys. Run it with:
  `uv run docs/spec/tools/check.py`.
- **YAML 1.2 core** for all files: booleans only `true`/`false`,
  `4:5` and `yes` are text, a duplicate key = a `config` error.
- **Skills:** the new [skill.md](skill.md) and `schema/skill.schema.json`; for
  `task` a list + the `load_skill` tool, for `ask` the whole skill (OPEN-QUESTIONS 11).
  The example `workflows/skills/thtd-voice/`.
- **Permissions:** every server from an agent's `mcp` has a mandatory `tools` list;
  the owner in `mcp.yaml` determines `agents` (mandatory), `scenarios` and `tools`
  of the server; a scenario has `callable` (default
  `false`) and `call` may target only a callable scenario.
- **New:** [webhook.md](webhook.md) (`POST /runs`, 202/200/401/422);
  the structured-output cascade (`models.<alias>.structured_output`,
  `_submit_output`); `dedupe` as separate `_dedupe/` files with the state
  `started`/`succeeded` (OPEN-QUESTIONS 12); `runs_dir`; `transport` and
  `timeouts` on an MCP server; `{run_dir}` in `args`; an input of type `file` through
  `call`.
- **Run record:** the storage key `<run_id>-<32 hex>/<name>`; secret
  values in the record and the callback are replaced by `<secret: NAME>`; the events
  `mcp_server`, `callback_failed`; `step_finished.status: cancelled`;
  `tool_call.invalid_args`; `<nn>` = order in the file.
- **Clarifications:** the budget (checked before a call, a missing cost), `max_turns`
  vs. `retry`, `image` without an image and the `aspect_ratio` check, a complete
  `default`, `switch` over `null`, a closed list of fields with templates,
  operator types and `in`, numbers (`int`, `round`, `nan`), the `file` type,
  the `validate` check against `/models` with a cache.
- **Schemas:** the root of `schema` in `ask`/`task` is a map; `outputs` at least
  one item; `limits.max_turns` mandatory only with `mcp`; `base_url` only
  OpenRouter or localhost; a server's `env` without `PATH`, `LD_PRELOAD`, ….
- **Renamed in the example:** the photographer's output `prompt` → `photo_description`.
- OPEN-QUESTIONS: 6 resolved per DESIGN §5.8; new 11–14.

## version 1 — backward-compatible addition (framework 0.2.1)

- [run-record.md](run-record.md): the `timeout_s` field in the `model_call`
  and `jev_call` events (the HTTP call timeout, ISSUES 34). Older
  records do not have it; a reader may ignore it.

## version 1 — backward-compatible relaxation (framework 0.2.3)

- [agent.md](agent.md), [scenario.md](scenario.md): subfolders in
  `workflows/agents/` and `workflows/scenarios/` are no longer a `config` error
  but are silently ignored (handy for an archive, say). Only files
  directly in the folder are still read. What used to pass still passes (ISSUES 37, REVIEW M9).

## version 1 — backward-compatible refinement (framework 0.2.4)

- [run-record.md](run-record.md): call costs are stored exactly as
  the provider returned them, totals are rounded only to 10 decimal
  places (previously 8). The shape of the fields does not change, only the precision. `summary.md` and
  `report.html` show the full cost (`0.000004482` instead of `0.0000`) and at
  the end of the step table a **Total** row (ISSUES 38).

## version 1 — backward-compatible refinement (framework 0.2.5)

- [run-record.md](run-record.md): the **Total** row in `summary.md` and
  `report.html` has in the Time column the time of the whole run (`duration_s`
  from `run_finished`), not the sum of the steps (ISSUES 38).

## version 1 — no format change (framework 0.3.0)

- The framework is called AgenCast, the command `maw` → `agencast` (in the text of
  [run-record.md](run-record.md) and ISSUES). No format contained the name:
  the run record, the callback (`X-Run-Id`, `X-Signature`) and the fake
  scripts do not change.
- [webhook.md](webhook.md): `agencast serve --workers N` (default 1) —
  N runs at a time over one queue; `queue_position` counts waiting
  and running requests, the completion order with N > 1 is not guaranteed (ISSUES 39). The shape of the
  request, the responses and the callback does not change.
- A `run_id` collision (ISSUES 35) is handled by a new suffix; the id format does not change.

## version 1 — backward-compatible addition (framework 0.3.1)

- [config.md](config.md), [schema/config.schema.json](schema/config.schema.json):
  optional `limits.max_parallel_runs` (an integer ≥ 1, a cap on concurrent
  runs across processes, waiting at most `run_timeout`, then `timeout`) and
  `limits.daily_budget_usd` (a number > 0, a daily spend cap in UTC, checked
  only at start, then `budget`). Without them the behavior does not change; what used to
  pass still passes (ISSUES 40).
- [run-record.md](run-record.md): next to the run folders `_slots/<n>.lock`
  and the daily ledger `_ledger/<YYYY-MM-DD>.jsonl` (`_ledger-fake/` for `--fake`);
  a new event `run_waiting` (`waited_s`, `max_parallel_runs`). Older
  records do not have it; a reader may ignore unknown events.
- [webhook.md](webhook.md): waiting for a slot and the `timeout`/`budget` classes
  for a run that did not start. The shape of the request, the responses and the callback does not change.

## version 1 — no format change (framework 0.4.0)

- The new [projects.md](projects.md): the project registry
  `~/.config/agencast/projects.yaml` and the `agencast new` templates (ISSUES 41).
- The new [api.md](api.md): the `serve` read API (`/projects/...`), registry
  mode with `AGENCAST_TOKEN`, `POST /projects/<p>/runs` (ISSUES 42).
  [webhook.md](webhook.md) refers to it; `POST /runs`, `GET /runs/<id>`
  and the callback do not change.
- The `agent`, `scenario`, `config`, `mcp` formats, the run record and the JSON Schema
  do not change.

## version 1 — no format change (framework 0.5.0)

- [api.md](api.md) “Editing”: `serve` editing operations for the GUI —
  the scenario header and steps (add, edit, move, delete), an agent,
  a skill, `config.yaml`, the raw text of files in `workflows/` and `new`
  over HTTP. The step address (`address` in `GET …/scenarios/<s>`), the
  `etag` fingerprint (sha256 of the content) and in `GET /projects/<p>` the `etag` field on scenarios,
  agents and skills — new fields in responses, the existing ones do not change
  (ISSUES 43).
- Writing preserves comments, key order, blank lines and quotes;
  files stay in the v1 format, the JSON Schema does not change.

## version 1 — backward-compatible addition (framework 0.6.0)

- [api.md](api.md) “GUI additions” (ISSUES 44): `POST
  /projects/<p>/validate` (validation without writing), `env` in `GET
  /projects/<p>` (only a flag that the variable is set, never the value), in the
  run list and detail `scenario`, `started_at`, `finished_at`,
  `current_step`, `steps_total`; `POST /projects/<p>/runs` with an optional
  `callback_url` and `dry_run`; `serve` serves the GUI (`GET /`, `/assets/…`
  without a token) and has `--cors <origin>`.
- **API shape change (0.5.0 → 0.6.0):** the items of the `errors` arrays are objects
  `{message, file?, step?, field?, line?}` instead of texts; `message` =
  the former text. It concerns `GET /projects/<p>` (project, scenarios, agents,
  skills), `GET …/scenarios/<s>`, `GET …/files/<path>` and the 200/422 responses of
  editing operations. The only client of those fields is the GUI; `details`, the CLI
  and the Python API stay texts.
- [run-record.md](run-record.md): `run_started` has the new fields `steps_total`
  and `callback_url` (without the query, `null` = no callback). Older records do not
  have them; a reader treats a missing field as `null`.
- [webhook.md](webhook.md) only a reference; the `POST /runs` contract does not change.
  The `agent`, `scenario`, `config`, `mcp` formats and the JSON Schema do not change.

## version 1 — backward-compatible addition (framework 0.7.0)

- [api.md](api.md) “Additions from GUI findings” (ISSUES 45): `state`
  (`running` × `interrupted` by the run lock), `fake`,
  `queue_position`, `current_nn`, `steps_done` in the run list,
  `?scenario=&limit=`, `last_run`, `types` and
  `links.scenario_step_agent` in the project description, `reason` and `registry`
  in `GET /projects`, step details (`nn`, `dir`, `error`,
  `continued`, `default_used`, `calls`, …) and a new `GET
  …/runs/<id>/steps/<path>`, the run step tree (`tree`, `callees`,
  `tree_source`), `errors` objects also in 422 and all errors of
  `config.yaml`/`mcp.yaml` in `files/`. New fields, the existing ones do not change;
  the textual `status` “running or interrupted” is split into `running` and
  `interrupted`.
- [run-record.md](run-record.md): in the run folder `run.lock` and the snapshot
  `scenario/<name>.yaml`; `step_started` has `nn` and `dir`,
  `step_skipped` has `nn`, `step_finished` with `continued: true` has
  `default_used`. Older records do not have them; a reader treats a missing field
  as `null`.
- The `agent`, `scenario`, `config`, `mcp` formats, the JSON Schema and the
  `POST /runs` contract + callback do not change.

## version 1 — backward-compatible addition (framework 0.8.0)

The agent, scenario, configuration and run record formats are unchanged. The API
([api.md](api.md) “Batch, preview and additions from GUI findings, part 2”),
all additive:

- `POST …/scenarios/<s>/batch` (a batch of operations, one validation, one
  write; the new operations `replace_step`, `rename_step`, `add_branch`),
  `POST …/scenarios/<s>/render` (a preview without writing), `PUT …/steps/<address>`
  (the whole step).
- `HEAD …/files/<path>` and `?etag_only=1`; `errors` in `GET …/files/<path>`
  = the `validate` errors of the file.
- `description` (and for an agent `model`) in `POST …/scenarios` and `POST …/agents`.
- `links.scenario_model` and `models_used` in `GET /projects/<p>`.
- `PUT …/config` also allows `runs_dir` and `openrouter.jev_model`.
- `state`: a `serve` queue entry → `queued`; `dry_run` only without
  `run.lock` ([run-record.md](run-record.md) — only a clarification, the file
  and the write order are from 0.7.0).

## version 1 — backward-compatible addition (framework 0.9.0)

The agent, scenario, configuration and run record formats are unchanged. The API
([api.md](api.md)): `POST /projects/new` creates and registers a project,
`POST /projects` registers an existing project, `DELETE /projects/<p>`
removes only the registry entry; `GET /projects` adds `projects_root` and
`writable`. The root for new projects is optionally configurable in the registry;
for the write behavior and paths see [projects.md](projects.md).

## version 1 — backward-compatible addition (framework 0.10.0)

The agent, scenario, configuration and run record formats stay backward
compatible. The API ([api.md](api.md)) adds counts and today's spend to
`GET /projects`, run pagination, `tree` when validating/rendering text,
the line of config schema errors and the step/field on a batch operation error.
A run interrupted by a restart keeps its original `run_started` and has `state: interrupted`
in the API. The `POST /runs` and callback contract does not change.

## version 1 — backward-compatible addition (framework 0.12.0)

- `config.yaml`: a model alias may have an optional `api: chat|images` (default
  `chat`) and, with `api: images`, an optional `quality: auto|low|medium|high`;
  the format of the `image` step stays unchanged.

## version 1 — backward-compatible addition (framework 0.14.0)

- `image.aspect_ratio` now accepts a template; the optional `quality` and
  `resolution` accept a fixed value or a template. A step's quality overrides the
  alias, the chat API ignores quality and resolution with a warning in the run record.
  Existing scenarios and the default behavior stay valid (R8).

## version 1 — no format change (English as the primary language)

All formats, keys and enum values are unchanged. Only human-readable texts and
the names in the examples are English now:

- the run `status` text in the API and in `agencast runs list` (`running`,
  `interrupted`, `failed (<class> in <step>)`; clients should read the machine
  field `state`) and the message stored for a run interrupted by a `serve`
  restart (`run interrupted by server restart`; older records with a different
  message are read as `failed`);
- `summary.md` and `report.html`: a decimal point and dates as
  `YYYY-MM-DD HH:MM UTC`;
- the files created by `agencast new` (the `writer` agent, the `demo` scenario
  with the steps `write` and `result` and the input `topic`) and the example
  projects (model aliases `smart` and `fast`).

## version 1 — backward-compatible addition (framework 0.18.0, images as inputs)

- `inputs.<name>.type: file` is accepted from the CLI and Python as a path
  (checked and copied into `runs/<id>/inputs/`); new input and output type
  `files` = a list of 1–16 images. Over HTTP a file is `{"upload_id"}` from the
  new `POST …/uploads` (api.md); a JSON string is never a path.
- A `file` value carries `width`, `height` and `format`, read with a dot
  (`inputs.photo.width`); before 0.18.0 a dot on a `file` was always an error,
  so no existing scenario changes meaning.
- New optional `images:` on `ask` and `task` (one template or a list, each
  leading to a file or a list of files); without it the request body is
  unchanged.
- `files` output: every file is uploaded under `<name>-<i>` and the callback
  carries a list of URLs.
- `image.images` (reference images; only aliases with `api: images`) and
  `aspect_ratio: auto`. With references and no explicit ratio the output follows
  the first reference, snapped to a ratio the model supports; a ratio mismatch is
  then a warning. Without references nothing changes. Every image sent is
  labelled `Image <k> (<path>, <W>×<H>)` (for `image` in a legend at the top of
  the prompt), the path a template renders — a prompt names an image with
  `{{ inputs.shirt }}`.

## version 1 — no format change (framework 0.19.0, MCP server)

The agent, scenario, skill, `config.yaml`, `mcp.yaml`, registry and run-record formats
are unchanged; existing files keep their meaning.

- New: [mcp-server.md](mcp-server.md) — `agencast mcp`, AgenCast as an MCP server over
  stdio or streamable HTTP (`--http`, bearer token `AGENCAST_MCP_TOKEN`): its tools,
  permission levels, the run object, runs in worker processes that outlive the client
  and the server, file inputs from `--input-dir`, masking, trust rules and limits. It
  adds no file format, no record field and no registry key.
- Run directory (run-record.md): `<runs>/_mcp-slots/<n>.lock`, n = 1..4 — the `flock`
  locks of runs and dry runs started through MCP, next to `_slots/`; each file holds the
  `run_id` of the run that holds it (empty for a dry run). Nothing else reads or writes
  them, and a run's own directory is the same as for any run.
- Note — YAML aliases are bounded: a workflow file (or a draft sent to `validate` /
  `write_*`) whose aliases (`*name`) expand to more than 100,000 values is a `config`
  error (`cannot read YAML — aliases expand to too many values`), in every reader. No
  sensible file comes near it; a file without aliases is never refused.
- `agencast serve` refuses a scenario that is a link out of the project's own
  `workflows/scenarios/` (webhook.md): 422 `unknown scenario`, as for a missing one; a
  link to another scenario of the same directory still works. The files API
  (api.md “Editing”) serves no file of a linked `workflows/` (404).
- An agent, skill or called scenario that is a link out of the project's own
  `workflows/` (a called scenario: out of its `scenarios/`) does not exist — the
  validation error of a missing one; a link that stays inside still works.
- An unquoted `{{ … }}` value in a block mapping is the usual `cannot read YAML … must be
  quoted` error with its line (`found unhashable key`); 0.18.0 crashed on it.
- Run lock order (run-record.md): `run.lock` is now taken right after the run
  directory is created, before input images are staged into `inputs/` — as
  run-record.md already said; 0.18.0 copied the images first, so a run with images read
  `interrupted` meanwhile. A run's `scenario/<name>.yaml` is the text the run loaded.

## version 1 — backward-compatible addition (framework 0.18.0, MCP servers are the owner's)

The agent and scenario formats are unchanged, and `config.yaml` and `mcp.yaml`
have no new or changed key; existing files keep their meaning, with one
exception: the pattern of a plain `http://` URL is narrower, so a file that used
what it no longer admits fails validation. Additions are optional. Four
behaviours change for existing users and are marked **changed**.

- **Changed — the files API no longer serves or writes `mcp.yaml`** (api.md “MCP
  servers are the owner's”, config.md): `GET`, `HEAD` and `PUT …/files/mcp.yaml`
  and `POST …/validate` with `path: "mcp.yaml"` → 404; the GUI can no longer edit
  the file, its owner edits it on disk. `GET /projects/<p>` lists the servers
  without `command`, `args`, `url`, `env` and `bearer_token_env` and carries the
  file's errors in the project-level `errors` (`file: "mcp.yaml"`, `line`,
  `field`; an argument is named by its place, `servers.<name>.args[1]`, never
  quoted). The one write left is `POST …/agents/<a>/rename`: only the agent's
  name in the `agents` lists, the file's permission bits kept, 409 when the file
  changed on disk meanwhile, a `mcp.yaml` that is a link left alone.
- **Changed — projects registered through the API need trust** (projects.md
  “Trust”): new optional registry key `projects[].trusted`. `POST /projects` and
  `POST /projects/new` write `trusted: false`; without the key — every entry from
  a terminal and every existing entry — the project is trusted. An untrusted
  project uses no MCP server: `validate`, `run`, `--dry-run`, `--fake` and the
  same requests over HTTP (422) end with one `config` error that names the new
  command `agencast projects trust <name>` (terminal only; shows the root and the
  servers, asks, `--yes` outside a terminal). No HTTP route sets the key.
- **Changed — `agencast run --dry-run` no longer adds the project to the
  registry** (projects.md); a `run` that passes validation still does.
- API fields (api.md): `trusted` (read-only) in every item of `GET /projects`, in
  `GET /projects/<p>` and in the 201 bodies of `POST /projects` and
  `POST /projects/new`; `mcp_servers[]` in `GET /projects/<p>` gains
  `description`, `transport` (`stdio`, `streamable-http`, `sse`; `type` stays)
  and `env_missing` (names of the server's variables that are not set). A
  scenario, agent or skill file that cannot be read (a link that leads nowhere)
  is listed with that error and `etag: ""` instead of failing the request.
- Run record (run-record.md): `tool_call` and `calls/NN.tool.json` gain `error`
  for a call that did not return (timeout, dropped connection, cancelled step;
  `result: null`, `is_error: true`). `mcp_server` `failed` is written for every
  failed start attempt and, at the end of the run, for a server that dropped the
  connection during a tool call (instead of `stopped`); `stopped` without
  `started` = the run ended while the server was starting. `stderr_file` exists
  for local servers only, once the server has stopped, and a later start in the
  same run appends to it. `error.attempt` also counts MCP server starts.
  `image_saved.bytes` and the `<file: …, N B>` note are the size of the file as
  stored (after masking).
  `step_skipped.reason` names an interrupt (`cancelled — the run was interrupted
  (SIGTERM)`; `reason_code` unchanged).
- Handshake retry (scenario.md `retry`, the `task` step; config.md): a
  `transient` failure to start an MCP server — a network error, HTTP 408, 429 or
  5xx — is retried according to the step's `retry`, with the delay 2 s, 4 s,
  8 s… or the server's `Retry-After`; everything else is `config`. The message
  names the HTTP status (`http_status` in the `error` event), the last stderr
  lines of a local server, or a stdout line that is not JSON-RPC. A remote
  server's session is ended with one request that gets 5 s as a whole; a failed
  start reaches the step before it.
- `task` (scenario.md): once the step has called an MCP tool, the retry after a
  `schema` error only allows the answer (`tool_choice`); tool calls in it are
  not executed. `--fake` fakes only the model: scripted tool calls are real.
- Signals (scenario.md, api.md “Stopping `serve`”): SIGINT/SIGTERM cancel
  `agencast run` once, stop its MCP servers and exit with 130/143; the record is
  that of an interrupted run. A stopped `agencast serve` does the same for its
  runs in flight; the next start reports them and sends again a callback that
  was cut short (new `callback_sent` events after `callback_failed`; only a
  delivered attempt clears `callback_failed` in `GET /runs/<run_id>`). A
  cancellation that arrives while a failed `parallel` branch cancels the others
  is not lost: a cancelled branch never goes on past a `call` step with
  `on_error: continue`.
- Masking rules (run-record.md): longer values are replaced first; the escaped
  forms of a value too — JSON-escaped once or twice, also `/` as `\/` (PHP),
  `&`, `<`, `>`, U+2028, U+2029 as `\u0026`, `\u003c`, `\u003e`, `\u2028`,
  `\u2029` (Go) and with uppercase hex, `"`, `'`, `+` and `` ` `` included
  (`\u002B`, `\u0022`; .NET), and HTML-escaped; JSON is masked per
  string before it is written (always valid JSON); a number whose digits hold a
  value becomes the replaced string; the bytes of a saved file (a tool's image
  block) are masked; `mcp/<server>.stderr.log` is masked and never raw in the
  run directory. Errors quote a remote server's URL without userinfo and query
  and the MCP library's errors without the server's input values.
- **Changed — the pattern of plain `http://` URLs is narrower**
  (`config.schema.json` `openrouter.base_url`, `mcp.schema.json` `url`; was
  `http://(127.0.0.1|localhost)[:/]`): plain `http://` only for `127.0.0.1` or
  `localhost`, an optional numeric port, then `/` or the end. A file with
  `http://127.0.0.1:1@example.com/` (userinfo — the host is `example.com`),
  `http://localhost:abc` or `http://localhost:8080?x=1` was valid and now fails
  validation (`servers.<name>.url: value does not match pattern …`);
  `http://localhost` without a `/` is accepted now. `callback_url` gets the
  same shape check already when the run is accepted (422), with plain `http://`
  only for `127.0.0.1` (not `localhost`), as before.
- `mcp.yaml` errors (config.md) name the field and the line; an error in one
  server entry leaves the others known to the checks of agents and scenarios; a
  value pasted where a variable name belongs is never printed; a file that
  cannot be read is a `config` error.
- Editing rule for step headers (api.md): the blank lines and comments directly
  above a step belong to it — deleted with it, moved with it (re-indented), kept
  by a replacement; a new step goes above the header of the next one. A comment
  never becomes a part of a `|` or `>` text. Writes keep the permission bits of
  the replaced file and follow no link, also when `POST …/scenarios`,
  `POST …/agents` and `POST /projects/new` create files; `files/` follows a link
  only to a file it serves under its own name.
- Dry run (scenario.md §7): `plan.md` marks an allowed tool the server does not
  offer (`(NOT OFFERED by the server)`) and lists a server that does not start
  with the reason.
