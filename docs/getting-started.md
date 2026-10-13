# Getting started with AgenCast

AgenCast lets your agent create, validate and run reusable workflows through MCP or the CLI, then read the
results. Start with a prepared project and a run with scripted model answers. The project owner configures
models, permissions and limits; the optional GUI helps people review and edit files and inspect runs.

## Install the runtime

Verified on Linux, macOS and WSL with Python 3.12; use `uv`.
To run the sample MCP server via `npx` you need Node.js
`^20.19.0 || >=22.12.0` (per `ui/package.json`, verified with Node 24).
Native Windows is not supported (`fcntl` in `projects.py` and `task.py`).

The package contains the CLI, the MCP server, the API, the built GUI, the documentation, the skills and the examples.
Install it from PyPI to operate workflows through your agent or a terminal:

```bash
uv tool install agencast
```

Update with `uv tool upgrade agencast`; symlinked skills follow the update.

## Prepare a project

Create your own project with `agencast new project ~/my-project`.
You get a skeleton with the agent `writer` and the scenario `demo`.
For a finished example with scripted responses, use:

```bash
agencast new project ~/agencast-demo --example showcase
cd ~/agencast-demo
```

## Connect your agent

For Claude Code, connect the prepared project over MCP:

```bash
claude mcp add --transport stdio agencast -- \
  agencast --project ~/agencast-demo mcp --allow edit --fake ~/agencast-demo/fake/ig-post.yaml
```

Then ask your agent:

> Use AgenCast to find the ig-post scenario, validate it, check its plan and run it for the topic
> "coffee" with fake_run. Return the outputs, model cost and run summary.

The server uses the shipped fixture and exposes no live model run tool. The `ig-post` workflow has no
MCP task or callback and can run offline; the coding agent's own usage is separate. Other clients can
start the same `agencast` command over stdio. [Client configuration and remote servers](#use-from-an-mcp-client)
are below.

For a recurring task, ask your agent to read the guide with `get_guide("create")`, inspect the project with
`describe_project`, then create and validate a scenario using the configured model aliases, agents and tools.
`--allow edit` enables writing scenarios, agents and skills; the owner sets this level at server start.
The MCP server never edits owner configuration, credentials or the project registry.
Through the CLI, the bundled skills guide the same work.

For a different workflow, use its own fixture or start the server with `--fake` alone. Placeholder answers
may fail a workflow's conditions; prepared fixtures make its test results repeatable.

## Check the workflow from the CLI

The agent and a person can use the same commands to inspect the plan and exercise the flow:

```bash
cd ~/agencast-demo
agencast validate ig-post --offline
agencast run ig-post -i topic="new coffee" --dry-run --fake fake/ig-post.yaml
agencast run ig-post -i topic="new coffee" --fake fake/ig-post.yaml
```

`--dry-run` produces a plan; adding `--fake` also skips the network check of the models.
Without a fixture you can use `--fake` alone, but the made-up responses may not pass
the scenario's conditions. You can try the skeleton with `agencast run demo --fake`.

`--fake` replaces only the model calls: no model cost and no OpenRouter key.
It records simulated costs to exercise budget checks; these are not charges.
A `task` step still starts the real MCP servers from `mcp.yaml`; the sample
`filesystem` server uses `npx`, needs Node.js and downloads its package on first start.
`--callback-url` sends a real callback (and needs its signing secret).
Only scenarios without `task` (including in called scenarios)
and without `--callback-url` are guaranteed to be offline, for example `ig-post`.

## Use live models

Models executing workflow steps currently use OpenRouter; the coding agent connected through MCP or using
the CLI operates AgenCast itself. Its login does not supply the workflow's OpenRouter key.

Only for a live run, copy `.env.example` to `.env` and fill in
`OPENROUTER_API_KEY`. Never commit or print keys.
After checking the plan and the result of the fake run, start:

```bash
agencast run ig-post -i topic="new coffee"
```

For live runs through MCP, the owner also changes the server command to omit `--fake` and its fixture path.
The server then exposes `run_scenario` in addition to `fake_run`.

## Inspect and reuse the results

The record is in `runs/<run_id>/summary.md`, the machine-readable result in `callback.json`,
the report in `report.html`; exports are in `outputs/`. The CLI prints the exact paths.
`agencast runs list` and `agencast runs show <run_id>` show the history.

An agent can read outputs and records with `run_status` and `get_run_file` through MCP. Review the procedure
and its result, then run the same scenario with new inputs. The workflow fixes the steps and branching rules;
live model answers may vary.

## Skills and reference

Install the skills for Claude Code, Codex, OpenCode and OMP like this:

```bash
agencast skills list
agencast skills install                 # tools whose base folder already exists
agencast skills install --to all        # all four
```

Symlinks are the default; `--copy` creates copies, `--prefix DIR` changes the home
folder and `--force` allows overwriting existing copies. `agencast skills path`
prints the source folder. After updating the package, refresh the installed copies.

```bash
agencast docs
agencast docs show spec/scenario.md
agencast new project ~/agencast-tutorial --example tutorial
agencast docs show tutorials/01-first-agent-and-scenario.md
```

The [tutorials](tutorials/README.md) have seven parts; the formats are described by
the [scenario](spec/scenario.md), [agent](spec/agent.md) and
[config](spec/config.md) specifications. Source code: [GitHub](https://github.com/rychidesign/agencast).

## Optional GUI

The GUI is a human interface for reviewing and editing workflow files and inspecting run records.
It is included in the package. To develop AgenCast itself, clone the repository and build the frontend with Node.js:

```bash
git clone https://github.com/rychidesign/agencast
cd agencast
(cd ui && npm install && npm run build)
uv tool install --editable framework
```

`agencast serve` starts the API and the built GUI, if there is one. New projects are added
to the registry for the GUI automatically. Expose the server and the GUI only on a private network;
for registry mode set `AGENCAST_TOKEN`, for a single project `WEBHOOK_TOKEN`
as in `.env.example`. Details: `agencast docs show spec/webhook.md`.

## Use from an MCP client

`agencast mcp` serves the registered projects (one with `--project`) to an MCP client: projects, scenarios,
runs and their results, and with `--allow edit` writing scenarios, agents and skills. A run started through it
goes on in a process of its own when the client disconnects or the server restarts. Details:
`agencast docs show spec/mcp-server.md` ([MCP server](spec/mcp-server.md)).

Claude Code starts the server itself over stdio. To serve all registered projects with placeholder model
answers, use the following command; MCP tools still run for real:

```bash
claude mcp add --transport stdio agencast -- agencast mcp --fake
```

Image inputs are files on the server's machine inside a directory allowed with `--input-dir DIR` (a tool call
carries no bytes). Claude Code or Codex on another machine copies the user's images there over your own ssh
login first; the recipe is in the `agencast-run` skill (on that machine: `uv tool install
agencast`, then `agencast skills install`) and in
`get_guide("run")` on the server. The directory must exist on the server before the server starts:

```bash
ssh box mkdir -p /home/me/agencast-inputs
claude mcp add --transport stdio agencast -- ssh -T box /home/me/.local/bin/agencast mcp --input-dir /home/me/agencast-inputs
```

In a client that renders MCP Apps (Claude Desktop), `fake_run`, `run_scenario` and `run_status` also show a
**run card** in the chat that follows the run on its own: progress, steps, cost, and at the end the outputs with
inline images ([spec/mcp-server.md “Run card”](spec/mcp-server.md#run-card-mcp-apps)). Open WebUI shows it
through the community [MCP App Bridge](https://github.com/Classic298/open-webui-plugins/tree/main/mcp-app-bridge)
tool, configured with the server URL and the token.

Claude Desktop starts stdio servers only (`claude_desktop_config.json`, absolute paths, restart the app); on
another machine over ssh, without a token or an open port:

```json
{"mcpServers": {"agencast": {"command": "/home/me/.local/bin/agencast", "args": ["mcp"]},
                "agencast-box": {"command": "ssh", "args": ["-T", "box", "/home/me/.local/bin/agencast", "mcp"]}}}
```

For clients on other machines or in containers, `agencast mcp --http` serves streamable HTTP at
`http://127.0.0.1:8765/mcp` with a bearer token from `AGENCAST_MCP_TOKEN` (at least 32 characters,
`openssl rand -hex 32`). Claude Code reads it from `.mcp.json` and expands the variable from its own environment:

```json
{"mcpServers": {"agencast": {"type": "http", "url": "http://127.0.0.1:8765/mcp",
                             "headers": {"Authorization": "Bearer ${AGENCAST_MCP_TOKEN}"}}}}
```

The same for all your projects — in single quotes, so that Claude Code stores the variable, not the token (a
token the shell expands into the command stays in plain text in its configuration and the shell history):

```bash
claude mcp add --transport http --scope user agencast http://127.0.0.1:8765/mcp \
  --header 'Authorization: Bearer ${AGENCAST_MCP_TOKEN}'
```

Open WebUI (0.6.31 or newer): an
external tool server of type MCP (Streamable HTTP) with the URL and Bearer authentication. Open WebUI in Docker
uses the URL as is with `--network=host`; otherwise start it with `--add-host=host.docker.internal:host-gateway`,
the server with `--host 172.17.0.1 --allow-host host.docker.internal`, and use
`http://host.docker.internal:8765/mcp`.

As a systemd user service (`~/.config/systemd/user/agencast-mcp.service`; `mcp.env`, mode 600, holds only
`AGENCAST_MCP_*` — a provider key there would pay for the runs of every project):

```ini
[Unit]
Description=AgenCast MCP server (streamable HTTP)

[Service]
EnvironmentFile=%h/.config/agencast/mcp.env
ExecStart=%h/.local/bin/agencast mcp --http --allow run
# Runs are processes of this unit: without this line a stop or restart interrupts them.
KillMode=process
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

```bash
(umask 077; mkdir -p ~/.config/agencast && printf 'AGENCAST_MCP_TOKEN=%s\n' "$(openssl rand -hex 32)" > ~/.config/agencast/mcp.env)
systemctl --user daemon-reload && systemctl --user enable --now agencast-mcp
loginctl enable-linger "$USER"     # the service and its runs outlive your logins
tailscale serve --bg 8765          # https://box.<tailnet>.ts.net/mcp; the server needs --allow-host box.<tailnet>.ts.net
```

On macOS the same server runs as a launchd agent with the same `mcp.env`
(`~/Library/LaunchAgents/agencast-mcp.plist`): the plist and its `launchctl` commands are in
[spec/mcp-server.md](spec/mcp-server.md#as-a-launchd-agent-macos).

Expose it only on a private network — it speaks plain HTTP: keep `127.0.0.1` and publish it with
`tailscale serve`, never `tailscale funnel`. `--fake` stops model spending, but `task` steps still start their
MCP servers; only `--allow read` starts nothing. A run stops only when its own process does: a signal to it, or
the end of the control group it lives in (a unit without `KillMode=process`, a logout without lingering).
