# AgenCast framework

Version 0.19.0, Python 3.12 + uv. Formats per `docs/spec/` (v1), design
in `docs/DESIGN.md`. The package and the command are both called `agencast` (until 0.2.5
`maw`); the command name is in `pyproject.toml` (`[project.scripts]`).

The package also contains the skills, documentation and examples: [guide](../docs/getting-started.md).

## Usage

Run the commands from the root of the repository clone.

```
uv run --project framework agencast --project examples/showcase validate ig-post
uv run --project framework agencast --project examples/showcase run ig-post -i topic="new coffee" --dry-run
uv run --project framework agencast --project examples/showcase run ig-post -i topic="new coffee" --fake examples/showcase/fake/ig-post.yaml
uv run --project framework agencast --project examples/showcase run ig-post -i topic="new coffee"
uv run --project framework agencast --project examples/showcase run demo-task -i books="Austen: Pride and Prejudice (1813)" --fake examples/showcase/fake/demo-task.yaml
uv run --project framework agencast --project examples/showcase runs list
uv run --project framework agencast --project examples/showcase runs show <run_id>
uv run --project framework agencast --project examples/showcase serve --host 127.0.0.1 --port 8080 [--workers 2] [--cors http://localhost:5173]
uv run --project framework agencast --project examples/showcase mcp [--allow read|run|edit] [--input-dir DIR]... [--fake [SCRIPT]] [--http [--host H] [--port P] [--allow-host H]...]
uv run --project framework agencast --project examples/showcase migrate examples/showcase/workflows/scenarios/ig-post.yaml
uv run --project framework agencast new project ~/my-project [--example showcase|tutorial]
uv run --project framework agencast new agent reviewer | new scenario check [--project <path>]
uv run --project framework agencast skills list | path | install [--to all] [--prefix DIR] [--copy] [--force]
uv run --project framework agencast docs [show spec/scenario.md]
uv run --project framework agencast projects list | add <path> [--name N] | rm <name> | trust <name> [--yes]
```

- A scenario can be given by name (`ig-post`) or by the path to its `.yaml`. The project
  root = the first folder with `workflows/` going up from the current folder, or
  `--project <path>` on any command — everything works from any
  folder.

- Configuration `workflows/config.yaml` (template `config.example.yaml`) and the
  MCP server registry `workflows/mcp.yaml` (template `mcp.example.yaml`; only the
  owner changes both — `mcp.yaml` only on disk: the API never reads or writes the file, the GUI shows its servers read-only). Keys only from the environment or from `.env` in the project
  root.
- A `task` step starts the MCP servers from `mcp.yaml` once per run (stdio via
  `npx` needs Node; on Modal, preinstall the package). The servers' stderr
  is in the run record in `mcp/<server>.stderr.log`.
- `--fake` replaces model calls with no model cost and no OpenRouter key;
  an optional YAML contains scripted answers (described in `src/agencast/fake.py`).
  The MCP servers from `mcp.yaml` in a `task` step are real even with `--fake`; the example
  `filesystem` via `npx` needs Node.js and downloads a package on first run.
  The callback is really sent and needs a signing secret. Only scenarios without
  `task` (including called scenarios) and without `--callback-url` are guaranteed to run offline, e.g. `ig-post`.
- Inputs of type `file` and `files` are images (PNG, JPEG, WebP, GIF, AVIF; at most 10 MB each, up to 16):
  `-i photo=a.jpg`, `-i 'refs=["a.png","b.webp"]'`. They are copied into `runs/<id>/inputs/` and carry
  `width`, `height` and `format`; `images:` on `ask`/`task` shows them to the model, on `image` they are
  reference images (only an alias with `api: images`). Over HTTP an image is uploaded first and passed as
  `{"upload_id": …}` (docs/spec/scenario.md, Type `file`; docs/spec/api.md, Uploads).
- `--callback-url https://…` sends the result signed with HMAC after the run
  (`callback.secret_env`).
- Run records are in `runs/` (in `.gitignore`), files from `output`
  in `outputs/` (`storage.type: local`).
- Every run has a `report.html` (a single file, CSS inside, no external
  resources, prompts and responses in `<details>`); a copy goes to storage and its
  URL is in the callback as `report_url` (`storage.type: local` → `file://`).
- `new project <path>` creates `workflows/` (config, agent `writer`,
  scenario `demo` — they pass `validate --offline` and `--fake`),
  `.env.example` and `.gitignore`; `new agent|scenario <name>` adds a
  minimal file to the project. It never overwrites anything (docs/spec/projects.md).
- The project registry `~/.config/agencast/projects.yaml` (`AGENCAST_CONFIG_DIR`)
  is filled by `new project`, `projects add` and a `run` that passed validation (not `--dry-run`; since 0.15.1
  `validate` does not change the registry); the GUI can
  write in registry mode — its entries are `trusted: false`: such a project uses no MCP server
  until `agencast projects trust <name>`, which shows the project root and its servers and asks first
  (`--yes` outside a terminal; docs/spec/projects.md). `projects_root` sets the default folder for
  new projects (default `~/workspace`).
- `migrate`: there is nothing to convert in v1; an unknown version = `config` error.
- Exit code: 0 success, 1 the run ended with an error, 2 `config` error
  (validate, inputs, environment).

## Webhook server (`agencast serve`)

Contract: `docs/spec/webhook.md`. Stdlib `ThreadingHTTPServer`, no
web framework.

```
POST /runs            Authorization: Bearer $WEBHOOK_TOKEN
{"scenario": "ig-post", "inputs": {"topic": "…"}, "callback_url": "https://…", "request_key": "n8n-4711"}
→ 202 {"run_id": "…", "queue_position": 1}   the run is queued, the result arrives at callback_url
→ 200 {"run_id": "<original>", "queue_position": null}   request_key was already used
→ 401 / 422 {"error": "…", "details": [...]}   nothing is created, no callback arrives
GET /runs/<run_id>    status: queued (+ queue_position) / running / callback body + callback_failed
GET /projects, /projects/<p>[/scenarios/<s>|/runs[/<id>[/files/<path>]]|/spend?day=]   read API (docs/spec/api.md)
POST /projects/<p>/runs   like POST /runs in project <p>; callback_url optional, "dry_run": true → plan only
POST /projects/<p>/uploads   raw bytes of one image → 201 {"upload_id"} for a file/files input (single project: POST /uploads)
POST /projects/<p>/validate   validation without writing ({path, text} or an empty body), errors as objects
POST /projects/new       creates a project from the template and writes it to the registry
POST /projects           registers an existing project with workflows/config.yaml
DELETE /projects/<p>     removes the project from the registry only, files stay
GET /, /assets/…      GUI (framework/src/agencast/ui/, no token)
```

- **GUI** (since 0.6.0): `serve` serves the built GUI from
  `framework/src/agencast/ui/` (output of `npm run build` in the repository's
  `ui/` folder; git ignores it, it goes into the wheel via `artifacts`). `GET /`
  and `/assets/…` need no token, the token protects only `/projects…` and `/runs…`;
  a path without an extension returns `index.html` (hash routing). Without a built
  GUI, `GET /` returns 404 with instructions. When developing the GUI from `vite dev` (another
  origin), run `serve --port 8787 --cors http://localhost:5173` — without the switch
  there are no CORS headers.

- In a project or with `--project`: one project (token `webhook.token_env`);
  **outside a project, registry mode**: all projects from the registry, the server
  token `AGENCAST_TOKEN`, secrets from the server's environment and `.env` in cwd,
  `/runs` only via `/projects/<p>/runs`.

- `--host` and `--port` override `AGENCAST_HOST` and `AGENCAST_PORT`; the defaults
  are `127.0.0.1` and `8080`. `AGENCAST_PORT` must be an integer 1–65535.
  These variables are read from the process environment while parsing arguments;
  `.env` in cwd is loaded only afterwards, so you cannot set the bind address or port from it.
- For registry mode, `~/.config/agencast/serve.env` can contain
  `AGENCAST_TOKEN`, `AGENCAST_HOST` and `AGENCAST_PORT`:

  ```dotenv
  AGENCAST_TOKEN=<secret-token>
  AGENCAST_HOST=127.0.0.1
  AGENCAST_PORT=8080
  ```

  For access from other devices, set `AGENCAST_HOST` to the private address
  of the Tailscale interface. A user systemd service:

  ```ini
  [Unit]
  Description=AgenCast server
  [Service]
  ExecStart=%h/.local/bin/agencast serve
  EnvironmentFile=%h/.config/agencast/serve.env
  Restart=on-failure
  [Install]
  WantedBy=default.target
  ```

- Startup needs the variables `webhook.token_env`, `callback.secret_env`
  and (without `--fake`) the OpenRouter key; otherwise it ends with a `config` error.
- Runs go one after another (a single worker thread); `--workers N` starts
  N runs at once, and the completion order is then not guaranteed. The queue and
  `request_key` are files in `<runs>/_queue/` — after a server restart,
  waiting requests are processed; a run interrupted midway is not repeated,
  a callback `internal` is sent (verify manually). On SIGTERM or Ctrl-C `serve` first stops the MCP servers
  of the runs in flight; requests still waiting stay in the queue.
- The optional `limits.max_parallel_runs` and `limits.daily_budget_usd`
  in `config.yaml` (since 0.3.1) apply to all runs over one `runs/` —
  `serve`, the manual CLI and cron share one cap (docs/spec/config.md).
- Callback: `https://` (exception `http://127.0.0.1` for tests), signature
  `X-Signature: sha256=<HMAC>`, 3 attempts, then `callback_failed`.
- The server is HTTP without TLS and the GUI has no token protection. Never
  expose it publicly; bind only to localhost or a private network, for example
  Tailscale. Deployment on Modal is Phase 3c.

## MCP server (`agencast mcp`, since 0.19.0)

`agencast mcp` serves the registered projects (one with `--project`) to an MCP client over stdio, or over
streamable HTTP with `--http` and a bearer token from `AGENCAST_MCP_TOKEN`: tools to list projects and
scenarios, run them (`fake_run` free, `run_scenario` live), follow and read runs, and with `--allow edit`
write scenarios, agents and skills. Runs outlive the client and the server. Image inputs come from
directories the owner allows with `--input-dir`. Clients that render MCP Apps also get a run card. Everything
is specified in [docs/spec/mcp-server.md](../docs/spec/mcp-server.md); client setup is in the
[main README](../README.md#use-from-an-mcp-client).

## Tests

```
cd framework && uv run pytest
```

Conformance suite (DESIGN §5.6, §5.9): expressions (58 cases from spike (c)
adjusted per the spec + the spec rules), loader, validate, engine (error
classes, retry, cascade, parallel, switch, budget, timeout, callback,
masking), the `task` step with the fake MCP server `tests/fake_mcp_server.py`
(permissions, schema normalization, loop, skills, `dedupe_key`, leftover
processes) and golden scenarios — every file in `examples/*/workflows/` and every example
in `docs/spec/`. A new scenario in `examples/*/workflows/scenarios/` is tested automatically;
its scripted answers belong in `../examples/<project>/fake/<name>.yaml`.

## Structure (DESIGN D3 layers)

| File | Layer |
|---|---|
| `loader.py` | reading files: YAML 1.2 core, frontmatter, `.env`, JSON Schema from the spec |
| `validate.py` | static checks (scenario.md §7), inputs |
| `expressions.py` | expressions and templates (scenario.md §5) |
| `engine.py` | run: steps, retry, timeout, budget, callback |
| `providers.py` | OpenRouter chat / Jev / image, error classes, cascade |
| `fake.py` | fake provider (`httpx.MockTransport`) |
| `record.py` | run record, summary.md, plan.md, report.html |
| `server.py` | webhook server, queue, request_key, `/projects/...` API (read, edit, validate), GUI and `--cors` |
| `mcp_client.py` | `mcp.yaml`, the run's MCP servers (`mcp` SDK 2.2), tool schema normalization |
| `task.py` | the `task` step (model ↔ tools loop, `load_skill`), `dedupe_key` |
| `projects.py` | project registry, templates for `agencast new`, project and scenario descriptions for the GUI |
| `api.py` | public API for the shells (CLI, `serve`, `agencast mcp`, later Modal): `load`, `run`, `dry_run`, `runs_list`, `run_status`, `new_*` |
| `mcp_server.py` | `agencast mcp`: the MCP tools, run workers (`run --mcp-job`), the HTTP transport ([spec](../docs/spec/mcp-server.md)) |
| `mcp_app/run-card.html` | the run card, MCP Apps resource `ui://agencast/run-card.html` |
| `resources.py` | the bundled docs, skills and examples (`agencast docs`, `get_guide`) |
| `cli.py` | the `agencast` command |

Not yet: Modal and R2 storage (Phase 3c). Unclear points in the spec: `docs/spec/ISSUES.md`.

Historical logs are in the [archive of live runs](../docs/archive/live-runs-2026-09.md).
