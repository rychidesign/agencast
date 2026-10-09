# AgenCast

[![CI](https://github.com/rychidesign/agencast/actions/workflows/ci.yml/badge.svg)](https://github.com/rychidesign/agencast/actions/workflows/ci.yml)

AgenCast is an open-source framework for defining and running LLM-agent workflows. Scenarios use YAML, agents use Markdown, and each run leaves a readable record.

AgenCast is for developers and teams who want to compose repeatable LLM-agent tasks from files that can be read, versioned and reviewed. A scenario describes the flow of work; an agent describes its role and tools.

## Why AgenCast

- **Workflows are files, not code.** A scenario is YAML and an agent is Markdown. There is no graph to assemble
  in a programming language and no classes to subclass, so a workflow can be read in a minute, reviewed in a pull
  request and written by a coding agent.
- **The flow is explicit.** The scenario fixes the steps, branches and calls; the model works inside a step and
  never invents the route. You can read every possible path before anything runs.
- **Check before you pay.** `validate` finds mistakes without calling a model, `--dry-run` prints the plan and
  `--fake` runs the whole scenario with scripted answers — no key, no cost. The same fixtures serve as regression tests.
- **Every run explains itself.** The run folder keeps each prompt and response, a timeline, the cost of every
  step, `summary.md` and a standalone `report.html`. No tracing service and no account are needed.
- **Costs have hard limits.** Budgets per step, per run and per day, a separate cap for images and a timeout on
  every step. A limit that is hit stops the run with a named error class; nothing fails silently.
- **Permissions belong to the owner.** Which tools and servers an agent may use is decided in the project owner's
  files; a scenario can only narrow them. Secrets are referenced by variable name and masked in every record.
- **Any model, one line to switch.** Agents refer to aliases; `config.yaml` maps them to models. Changing a model
  touches one line and no scenario.
- **Made to sit behind automation.** A token-protected webhook, signed callbacks, idempotent requests and
  protection against repeating a step with a side effect. No web framework of its own and no database: the files are the state,
  and the GUI is only a view of them.

AgenCast is deliberately small. It runs workflows you can describe step by step; it is not a library for
free-form conversations between agents written in code.

## Quick start

Tested on Linux/WSL with Python 3.12 and `uv`; native Windows is unsupported, macOS untested.
GUI builds and example MCP servers need Node `^20.19.0 || >=22.12.0` (tested: 24).

```bash
uv tool install "git+https://github.com/rychidesign/agencast#subdirectory=framework"
agencast new project ~/demo --example showcase
cd ~/demo
agencast run ig-post -i topic="coffee" --fake fake/ig-post.yaml
```

This example needs no model key or payment; `--fake` still uses real MCP servers and callbacks.
Offline runs require no `task` steps (including called scenarios) and no `--callback-url`, as above.
The GUI is English by default with a Czech translation. Deploy the GUI only on a private network.
The command above installs the CLI/API; build the GUI from a clone as described below.

## What it does

- Scenarios in YAML, agents and skills in Markdown.
- Ten step types: `ask`, `task`, `jev`, `image`, `parallel`, `switch`, `call`, `set`, `fail` and `output`.
- `task` calls permitted MCP tools; `parallel`, `switch` and `call` compose branches and scenarios.
- Images as inputs: `file` and `files` inputs (PNG, JPEG, WebP, GIF, AVIF) come from the CLI, the API, the GUI or an MCP
  client (from a directory the owner allows with `agencast mcp --input-dir`);
  `ask` and `task` can look at them, `image` can edit one or compose a new one from several.
- Permissions belong to the project owner: MCP servers are set only in `workflows/mcp.yaml` on disk —
  the API and the GUI cannot change them.
- A fake provider replaces model calls with no cost and no key; MCP and callbacks stay real.
- Every run stores `summary.md`, `callback.json` and a standalone `report.html`.
- `agencast serve` accepts webhooks and offers a GUI for registered projects.
- `agencast mcp` is an MCP server: Claude Code, Claude Desktop, Open WebUI or another agent can list, run and
  build scenarios through it.
- Skills for coding agents help both run and create scenarios.

![The ig-post scenario editor in the AgenCast GUI](docs/ui/screenshots/editor.png)

## Installation

Verified on Linux and WSL with Python 3.12; use `uv`.
To build the GUI and run the example MCP server via `npx` you need Node.js
`^20.19.0 || >=22.12.0` (per `ui/package.json`, verified with Node 24).
Native Windows is not supported (`fcntl` in `projects.py` and `task.py`);
macOS is not verified.

From a clone of the repository, including the GUI:

```bash
git clone https://github.com/rychidesign/agencast
cd agencast
(cd ui && npm install && npm run build)   # builds the GUI into the package
uv tool install --editable framework
```

Directly from GitHub without a clone, only the `agencast` command and the server
with the API are installed, without the GUI:

```bash
uv tool install "git+https://github.com/rychidesign/agencast#subdirectory=framework"
```

Examples, tutorials, documentation and skills are bundled even without a clone.

## Getting started

The whole procedure for the package and for a clone: [Getting started with AgenCast](docs/getting-started.md).

`--fake` replaces only model calls: no model cost and no OpenRouter key.
A `task` step still runs the real MCP servers from `mcp.yaml`; the example
`filesystem` uses `npx`, needs Node.js and downloads a package on first run.
`--callback-url` sends a real callback (and needs its signing secret).
Only scenarios without `task` (including called scenarios)
and without `--callback-url` are guaranteed to run offline, for example `ig-post`.

You can run the `ig-post` example from a clone offline (it has no `task`; do not add `--callback-url`):

```bash
agencast --project examples/showcase run ig-post -i topic="new coffee" --fake examples/showcase/fake/ig-post.yaml
```

More examples are in [examples/](examples/). For your own work, create a project, add your OpenRouter key to `.env` and go through the checks without a live call first:

```bash
agencast new project ~/my-project
cd ~/my-project
cp .env.example .env
# Set OPENROUTER_API_KEY in .env.
agencast validate demo
agencast run demo --dry-run
agencast run demo --fake
agencast run demo
```

## Use from an MCP client

`agencast mcp` serves the registered projects (one with `--project`) to an MCP client: it lists projects and
scenarios, runs them, reads results and, with `--allow edit`, writes scenarios, agents and skills. A run started
through it executes in a process of its own and goes on when the client disconnects or the server restarts.
Everything below is specified in [the MCP server specification](docs/spec/mcp-server.md).

Claude Code starts the server itself (stdio):

```bash
claude mcp add --transport stdio agencast -- agencast mcp           # dry, fake and live runs (--allow run)
claude mcp add --transport stdio agencast -- agencast mcp --fake    # no live runs: nothing can cost money
```

In a client that renders MCP Apps (Claude Desktop; Codex Desktop implements the extension too), starting a run also shows a **run card** in the
chat, in the AgenCast look, that follows the run on its own: an animated segmented progress bar, the steps with
their type icons, elapsed time and cost, and at the end the outputs with inline images. It changes nothing for
other clients. Open WebUI renders it through the community
[MCP App Bridge](https://github.com/Classic298/open-webui-plugins/tree/main/mcp-app-bridge) tool (Open WebUI
0.11.4), configured with the server URL and the bearer token; the model then starts runs through its
`call_mcp_tool`.

Claude Desktop starts stdio servers only (`claude_desktop_config.json`, absolute paths, restart the app); on
another machine it starts the server over ssh — no token and no open port:

```json
{"mcpServers": {"agencast": {"command": "/home/me/.local/bin/agencast", "args": ["mcp"]},
                "agencast-box": {"command": "ssh", "args": ["-T", "box", "/home/me/.local/bin/agencast", "mcp"]}}}
```

Clients on other machines or in containers use streamable HTTP: `agencast mcp --http` serves
`http://127.0.0.1:8765/mcp` (`--host`, `--port`) and needs a bearer token of at least 32 characters
(`openssl rand -hex 32`), read from `AGENCAST_MCP_TOKEN` at start. Claude Code takes the URL from `.mcp.json`
and expands `${AGENCAST_MCP_TOKEN}` from its own environment, so the token is in no file:

```json
{"mcpServers": {"agencast": {"type": "http", "url": "http://127.0.0.1:8765/mcp",
                             "headers": {"Authorization": "Bearer ${AGENCAST_MCP_TOKEN}"}}}}
```

```bash
claude mcp add --transport http --scope user agencast http://127.0.0.1:8765/mcp \
  --header 'Authorization: Bearer ${AGENCAST_MCP_TOKEN}'                       # single quotes: stored unexpanded
```

Never let the shell expand the token into a `claude mcp add` command: it would stay in plain text in Claude
Code's configuration and the shell history.

**Images as inputs from another machine.** A tool call carries no bytes, so an image input is a file on the
server's machine inside a directory the owner allows with `--input-dir DIR`. Claude Code or Codex on your laptop
copies the user's images there over your own ssh login first: `list_projects` tells the agent the host, the
user and the directories, and the `agencast-run` skill gives it the recipe (one `mktemp` subfolder per job,
files checked by content, removed again after the run has started). On the laptop:

```bash
ssh box mkdir -p /home/me/agencast-inputs     # the directory must exist on box before the server starts
claude mcp add --transport stdio agencast -- ssh -T box /home/me/.local/bin/agencast mcp --input-dir /home/me/agencast-inputs
uv tool install "git+https://github.com/rychidesign/agencast#subdirectory=framework" && agencast skills install
```

Then "here are the photos in ~/Desktop/ig, make an Instagram post with the scenario product-post" is enough —
for a scenario whose `photos` input has the type `files`.

In Open WebUI (0.6.31 or newer), add an external tool server of type
MCP (Streamable HTTP) with the URL and Bearer authentication with the token. Open WebUI in Docker reaches
`http://127.0.0.1:8765/mcp` with `--network=host`; otherwise start the container with
`--add-host=host.docker.internal:host-gateway`, the server with `agencast mcp --http --host 172.17.0.1 --allow-host host.docker.internal`
(the Docker bridge) and use `http://host.docker.internal:8765/mcp`.

The HTTP server as a systemd user service, `~/.config/systemd/user/agencast-mcp.service`:

```ini
[Unit]
Description=AgenCast MCP server (streamable HTTP)

[Service]
# Only AGENCAST_MCP_* in this file (mode 600), no provider keys: a key set here wins over
# every project's .env and pays for the runs of all projects.
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
loginctl enable-linger "$USER"                  # the service and its runs outlive your logins
tailscale serve --bg 8765                       # https://box.<tailnet>.ts.net/mcp for the tailnet
```

Behind `tailscale serve` add `--allow-host box.<tailnet>.ts.net` to `ExecStart` (the name clients use; without it
they get 421), and point `.mcp.json` at `https://box.<tailnet>.ts.net/mcp`.

Expose the server only on a private network: it speaks plain HTTP, so keep `127.0.0.1` and publish it with
`tailscale serve` (never `tailscale funnel`). Whoever has the token has the server's level; `--fake` stops model
spending but `task` steps still start their MCP servers — only `--allow read` starts nothing. Runs end only when
their own process is stopped: a signal to it, or the end of the control group it lives in (a unit without
`KillMode=process`, a stopped container, a logout without lingering).

## Skills for coding agents

`agencast skills install` installs the skills for the Claude Code, Codex,
OpenCode and OMP tools it finds; `--to all` selects all of them. More: [skills/](skills/).

## Repository structure

| Path | Contents |
|---|---|
| `framework/` | Python package and the `agencast` command |
| `ui/` | GUI source code |
| `examples/` | Standalone showcase and tutorial projects |
| `docs/` | Specification, design and tutorials |
| `skills/` | Skills for coding agents |

## Documentation

- [Format specification](docs/spec/)
- [Tutorials](docs/tutorials/)
- [Framework design](docs/DESIGN.md)
- [Framework README](framework/README.md)
- [GUI README](ui/README.md)
- [Skills for coding agents](skills/)

## GUI and server

`agencast serve` can run in project registry mode. On the host, set
`AGENCAST_TOKEN`, `AGENCAST_HOST` and `AGENCAST_PORT` in
`~/.config/agencast/serve.env` (systemd `EnvironmentFile`). Expose the GUI
only on a private network. You can find the address by reading only the host and port:

```bash
grep -E '^AGENCAST_(HOST|PORT)=' ~/.config/agencast/serve.env
```

Never print the token value.

The GUI shows MCP servers read-only: `workflows/mcp.yaml` is edited by the project owner on the server,
the API neither reads nor writes it. A project added or created through the GUI or the API uses no MCP
server until its owner allows it in a terminal:

```bash
agencast projects trust <name>
```

The GUI is English by default. The Czech translation is in `ui/src/locales/cs.json`;
choose the language in the GUI.

## Status and license

The current framework version is **0.19.0** (the 0.19.x line); the history of changes is in
the [changelog](framework/CHANGELOG.md). The project is available under the
[WTFPL version 2](LICENSE) license.

This program comes without any warranty, to the extent permitted by applicable law.

[Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)
