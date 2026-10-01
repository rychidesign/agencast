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
  then a warning. Without references nothing changes.
