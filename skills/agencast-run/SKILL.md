---
name: agencast-run
description: Run, dry-run and inspect AgenCast scenarios and read their results (runs/<id>/summary.md, callback.json, cost) — with the `agencast` CLI, or through a connected `agencast` MCP server (tools list_projects, run_scenario, wait_run), including getting the user's images onto the server as inputs. AgenCast is a CLI framework for LLM-agent scenarios written in YAML/Markdown (`agencast` command, folder with workflows/) — NOT the Claude Code Workflow tool. Use when asked to run/test/validate an AgenCast (formerly maw) scenario, check why a run failed, or find a run's output or cost.
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

## Through the MCP server (`agencast mcp`)

When an MCP server named `agencast` is connected (tools `list_projects`,
`list_scenarios`, `fake_run`, `run_scenario`, `wait_run`, `get_run_file`, …), use it
instead of the CLI: the projects live on the machine that runs the server, which may
not be yours. Order of work: `get_guide(topic="start")` (the server's own manual),
`list_projects`, `list_scenarios(project)` (each scenario's inputs with their types and
bounds), `fake_run` (free), then `run_scenario` (real money, no cancel) only after the
user has confirmed the inputs, the cost and any side effect of the scenario (a step
that publishes); then `wait_run` in a loop. A required input the user did not give:
propose a value and have it confirmed, do not invent it silently. A run keeps going
when you disconnect. What the server cannot tell you is how to get the user's
images there:

**An image input (`file`/`files`) is a file on the server's machine**, inside one of
`server.input_dirs` from `list_projects`. A tool call carries no bytes and there is
no upload, so when the user hands you images ("here are the photos", a folder, paths),
copy them there first:

1. `list_projects` → `server.host`, `server.user`, `server.input_dirs`. Empty
   `input_dirs`: stop and tell the user — the owner must start the server with
   `--input-dir <dir>`.
2. Check the files by content, not by extension: `file <paths>` must say PNG, JPEG,
   WebP, GIF or AVIF, `ls -l` at most 10 MB each; a `files` input takes 1–16 or the
   bounds `list_scenarios` shows. Anything else (HEIC from a phone) or anything too
   big: convert or shrink into a temporary folder of your own, never next to the
   user's originals (macOS `sips -s format jpeg in.heic --out <tmp>/x.jpg`, elsewhere
   `magick in.heic -resize 2048x2048\> <tmp>/x.jpg`), check the result again, and if
   no tool is installed stop and tell the user. Phone photos carry the place they were
   taken in EXIF and the server keeps every input for good in `runs/<id>/inputs/`:
   strip metadata from your copies when you can (`exiftool -all= …` or `magick … -strip …`).
3. Where: the **first** input dir, one fresh subfolder per job made by `mktemp`, so
   a retry or a second agent never shares or deletes another job's files. Never copy
   anywhere else.
   - Same machine (the server is a local stdio command, or `hostname` equals
     `server.host` and `whoami` equals `server.user`):
     `dest=$(mktemp -d <input_dir>/$(date +%Y%m%d)-<scenario>-XXXX) && cp <files> "$dest"/`
   - Another machine: over your own ssh login to the server, which exists apart from
     MCP. Probe it first: `ssh -n -o BatchMode=yes <user>@<host> echo ok` must print
     `ok`; if it hangs, errors or prints anything else, that route is a key restricted to
     the command `agencast mcp` (it cannot copy) or `server.host` does not resolve from
     your machine — stop and ask the user for the ssh name of that machine. Then
     `dest=$(ssh <user>@<host> mktemp -d <input_dir>/$(date +%Y%m%d)-<scenario>-XXXX)`
     and `scp <files> <user>@<host>:"$dest"/`.
4. Pass the paths as the server sees them: `"photo": "<dest>/front.jpg"`,
   `"refs": ["<dest>/a.png", "<dest>/b.png"]` — absolute, no `~`, never your local path.
5. The server reads each file when the tool is called and the run keeps its own copy,
   so the subfolder is needed only until the **last** call that names those paths has
   returned a run id — `fake_run` and then `run_scenario` both read it. Then remove
   exactly the subfolder you made (`rm -r -- "$dest"`, over ssh when the server is on
   another machine) and your temporary folder; never touch other folders there. Tell
   the user that the run keeps its own copy of the images.

Results: `wait_run` returns `outputs`; a file output is in `output_files[name]`
and `get_run_file(project, run_id, <that path>)` returns it (a small image inline);
`get_run_file(project, run_id, "summary.md")` is the summary.

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
