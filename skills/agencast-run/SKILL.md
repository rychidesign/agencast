---
name: agencast-run
description: Run, dry-run and inspect AgenCast scenarios and read their results (runs/<id>/summary.md, callback.json, cost). AgenCast is a CLI framework for LLM-agent scenarios written in YAML/Markdown (`agencast` command, folder with workflows/) — NOT the Claude Code Workflow tool. Use when asked to run/test/validate an AgenCast (formerly maw) scenario, check why a run failed, or find a run's output or cost.
---

# Running AgenCast scenarios

A **project** is any folder containing `workflows/` with `config.yaml`,
`agents/*.md` and `scenarios/*.yaml`. Every command finds the project by
walking up from the current directory, or takes `--project <root>`; a scenario
is given by name (`ig-post`) or as an absolute path to its `.yaml`.

Creating a project, agent or scenario, registering a project for the GUI,
`rename` and `migrate`: skill `agencast-create`. Known projects:
`agencast projects list`. A successful `run` registers the project itself.

Runs can also be started and inspected in the web GUI (`agencast.service`, only
over Tailscale at `http://<tailscale-host>:8090`; token in
`~/.config/agencast/serve.env`, never print it). It reads and writes the same
files as the CLI.

Command: `agencast` (on this host `~/.local/bin/agencast`). If missing, use
`uv run --project ~/workspace/multiagent-workflows/framework agencast`.

## Order of work — always cheapest first

```bash
agencast validate ig-post                            # files, agents, aliases (GET /models); --offline skips models
agencast run ig-post -i tema="nová káva" --dry-run   # plan only: steps, models, limits; no calls
agencast run ig-post -i tema="nová káva" --fake framework/tests/golden/ig-post.yaml
agencast run ig-post -i tema="nová káva"             # live: real models, real money
```

- `-i key=value` per input; numbers, `true`/`false`, lists and objects as JSON
  (`-i tags='["a","b"]'`). Missing required input → `config: chybí povinný vstup 'tema' (string)`.
- `--fake [fixture]` = fake provider, no network, no cost. Fixtures live in
  `framework/tests/golden/<scenario>.yaml` (repo only). Without a fixture the
  fake invents values (Jev answers 0.5), so threshold checks may `fail` — that
  is expected, not a bug.
- Go live only after validate + dry-run + fake pass, and ask the user first if
  the run could cost more than ~1 USD (dry-run shows per-step budgets; run cap
  is `limits.run_budget_usd` in `config.yaml`).

## Reading the result

The CLI prints one line and the paths:

```
běh 20260926-085911-ig-post-a248: úspěch · 0,0 s · 0,0404 USD
záznam: <project>/runs/20260926-085911-ig-post-a248/summary.md
```

`runs/<run_id>/` (under `runs_dir` from `config.yaml`, default `<project>/runs`):

- `summary.md` — human summary: steps table, cost, warnings, error, outputs. Read this first.
- `callback.json` — machine result: `status`, `outputs`, `error`, `warnings`, `cost_usd`, `duration_s`.
- `steps/<nn>-<id>/` — per step: `prompt.md` (exactly what the model got),
  `output.json`, `calls/NN.request|response.json`. Skipped steps have no folder.
- `events.jsonl`, `report.html`, `plan.md`; files from `output` are in `outputs/`.

```bash
agencast runs list            # all runs: id, status, duration, cost
agencast runs show <run_id>   # prints summary.md
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
the project root. Missing → `config: chybí proměnná prostředí OPENROUTER_API_KEY`.
Never print, cat, grep or log `.env` or key values. `validate`, `--dry-run`
and `--fake` need no key.

Details: `~/workspace/multiagent-workflows/docs/spec/run-record.md`
(record layout), `…/docs/spec/scenario.md` §6 (errors),
`~/workspace/multiagent-workflows/framework/README.md` (CLI, `serve`).
