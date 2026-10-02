---
name: agencast-run
description: Run, dry-run and inspect AgenCast scenarios and read their results (runs/<id>/summary.md, callback.json, cost). AgenCast is a CLI framework for LLM-agent scenarios written in YAML/Markdown (`agencast` command, folder with workflows/) — NOT the Claude Code Workflow tool. Use when asked to run/test/validate an AgenCast (formerly maw) scenario, check why a run failed, or find a run's output or cost.
---

# Running AgenCast scenarios

Command: `agencast`. If missing, see `docs/getting-started.md` on
https://github.com/rychidesign/agencast or install with
`uv tool install "git+https://github.com/rychidesign/agencast#subdirectory=framework"`.

## Find the project and the scenario

- A **project** is any folder containing `workflows/` with `config.yaml`,
  `agents/*.md` and `scenarios/*.yaml`. Every command walks up from the current
  directory, or takes `agencast --project <root> …`. Known projects and their
  paths: `agencast projects list`.
- Scenarios: `ls <root>/workflows/scenarios/`. A scenario is given by name
  (`ig-post`) or as an absolute path to its `.yaml`. Its inputs (name, type,
  `required` or `default`, description) are the `inputs:` block of that file —
  read it before running.
- Creating or editing agents/scenarios, new project, `rename`, `migrate`,
  registration for the GUI: skill `agencast-create`.

Create an example with `agencast new project <dir> --example showcase`,
then `cd <dir>`; its scripted answers are in `fake/<scenario>.yaml`.

## Order of work — always cheapest first

```bash
agencast validate ig-post                            # files, agents, aliases (GET /models); --offline skips models
agencast run ig-post -i topic="new coffee" --dry-run   # plan only: steps, models, tools, limits; no model calls (starts MCP servers to list their tools)
agencast run ig-post -i topic="new coffee" --fake fake/ig-post.yaml
agencast run ig-post -i topic="new coffee"             # live: real models, real money
```

- `-i key=value` per input; numbers, `true`/`false`, lists and objects as JSON
  (`-i tags='["a","b"]'`). Missing required input → `config: missing required input 'topic' (string)`.
- `--fake [fixture]` = fake model provider, no model API key or model cost. Fixtures for the
  repo's own scenarios live in `fake/<scenario>.yaml`. Without a
  fixture the fake invents values (text placeholders, JSON per schema, Jev
  answers 0.5), so threshold checks may `fail` — expected, not a bug. Own fixture:
  YAML map `step_id: [answer, …]` (last answer repeats; nested call step
  `call_id/step_id`), answer shapes `text: "…"`, `json: {…}`, `answers: {q: v}`
  (Jev), `image: {width, height}`, `status: 429`; details in the docstring of
  `framework/src/agencast/fake.py`.
- Go live only after validate + dry-run + fake pass, and ask the user first if
  the run could cost more than ~1 USD (dry-run shows per-step budgets; run cap
  is `limits.run_budget_usd` in `config.yaml`).
- A `run` (not `--dry-run`) in a project that is not registered yet registers
  it for the GUI and prints one stderr line about it — not an error.
- `config: … MCP servers (…) are disabled — project '<name>' (<root>) was
  registered through the API …`: the project came from the GUI and its owner
  has not allowed MCP servers yet. The fix is `agencast projects trust <name>`
  — the owner's decision (every `command` in `workflows/mcp.yaml` then runs on
  this machine): show them the message and ask, do not run it on your own. The
  command lists the root and the servers and asks for confirmation; it needs a
  terminal, or `--yes`.
- `--callback-url https://…` (HMAC-signed result) and `--request-key` are for
  webhook integrations; not needed from a terminal.

`--fake` replaces only model calls: no model cost and no OpenRouter key.
A `task` step still runs the real MCP servers from `mcp.yaml`; the example
`filesystem` uses `npx`, needs Node.js and downloads a package on first run.
`--callback-url` sends a real callback (and needs its signing secret).
Only scenarios without `task` (including called scenarios)
and without `--callback-url` are guaranteed to run offline, for example `ig-post`.

## What AgenCast does not do — the caller's job

A run executes one scenario once. Scheduling ("every Monday"), event triggers,
approvals and any state that must survive between runs belong to whoever calls
`agencast` (n8n, cron, a scheduled Claude Code task, …). The only cross-run
state inside the framework is `dedupe_key` on a side-effect step: the side
effect happens at most once per key even if the trigger repeats the run.
Pattern for "one item per run from a pool": keep the pool as a folder outside
`runs/`, pick one item, pass it (or its name) as an input, move it to a `done/`
folder after a successful run, and put the item into the publishing step's
`dedupe_key`. Image inputs (`file`, `files`): `-i photo=./a.jpg`,
`-i 'refs=["a.png","b.webp"]'` — PNG/JPEG/WebP/GIF/AVIF ≤ 10 MB, copied into
`runs/<id>/inputs/`. Over HTTP: `POST /projects/<p>/uploads` with the raw bytes
→ `{"upload_id"}`, then `"inputs": {"photo": {"upload_id": "up_…"}}` (api.md Uploads).

## Reading the result

The CLI prints one line and the paths:

```
run 20260929-190533-ig-post-74b2: succeeded · 0.0 s · 0.0404 USD
run record: <project>/runs/20260929-190533-ig-post-74b2/summary.md
report: file://<project>/outputs/20260929-190533-ig-post-74b2-…/report.html
```

On failure a second line goes to stderr: `<class> in step <step>: <message>`.

`runs/<run_id>/` (under `runs_dir` from `config.yaml`, default `<project>/runs`):

- `summary.md` — human summary: steps table, cost, warnings, error, outputs. Read this first.
- `callback.json` — machine result: `status`, `outputs`, `error`, `warnings`, `cost_usd`, `duration_s`.
- `steps/<nn>-<id>/` — per step: `prompt.md` (exactly what the model got),
  `output.json`, `calls/NN.request|response.json`. Skipped steps have no folder.
- `events.jsonl` (timeline), `report.html`, `plan.md`; files from `output` are in `outputs/`;
  `mcp/<server>.stderr.log` for `task` steps.

```bash
agencast runs list            # all runs: id, status, duration, cost (incl. runs started from the GUI)
agencast runs show <run_id>   # prints summary.md (plan.md for a dry run) and the paths
```

Exit code: 0 success, 1 run failed, 2 `config` error (nothing ran).

## Error classes (`callback.json` → `error: {class, step, message}`)

- `config` — bad files, inputs, env or permissions; fix the files, rerun `validate`.
- `transient` — network/429/5xx, already retried; rerun later.
- `schema` — model output didn't match `schema` after retries.
- `content` — model or filter refused the content.
- `budget` — step/agent/run budget or `max_turns` exhausted, or HTTP 402.
- `timeout` — step or run time limit exceeded.
- `expression` — `{{ }}`/`when` failed at runtime (missing key, null, wrong type).
- `fail` — the scenario's own `fail` step stopped the run on purpose (e.g. a Jev threshold).
- `internal` — framework bug; report the full message.

## Secrets

The key is `OPENROUTER_API_KEY`, read from the environment or from `.env` in
the project root. Missing → `config: missing environment variable OPENROUTER_API_KEY (OpenRouter key; .env or environment)`.
Never print, cat, grep or log `.env` or key values. `validate --offline`,
`--dry-run` and `--fake` need no OpenRouter key; real MCP servers and callbacks may require their own secrets.

## Web GUI

Runs can also be started and inspected in the web GUI (`agencast serve` in
registry mode, typically managed by systemd). `AGENCAST_HOST` and
`AGENCAST_PORT` in `~/.config/agencast/serve.env` determine its address; read
only those lines with `grep -E '^AGENCAST_(HOST|PORT)=' ~/.config/agencast/serve.env`.
`AGENCAST_TOKEN` is also configured in that file. Keep the GUI on a private
network and never print the token. The GUI reads and writes the same files as
the CLI, so its runs appear in `runs list` too.

Details: `agencast docs show spec/run-record.md`
(record layout), `agencast docs show spec/scenario.md` §6 (errors),
`agencast docs show getting-started.md` (CLI, `serve`).
