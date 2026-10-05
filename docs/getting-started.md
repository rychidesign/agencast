# Getting started with AgenCast

Verified on Linux and WSL with Python 3.12; use `uv`.
To build the GUI and to run the sample MCP server via `npx` you need Node.js
`^20.19.0 || >=22.12.0` (per `ui/package.json`, verified with Node 24).
Native Windows is not supported (`fcntl` in `projects.py` and `task.py`);
macOS is not verified.

The package contains the CLI, the API, the documentation, the skills and the examples.
Install straight from GitHub (without the GUI):

```bash
uv tool install "git+https://github.com/rychidesign/agencast#subdirectory=framework"
```

For the GUI, clone the repository and build the frontend with Node.js:

```bash
git clone https://github.com/rychidesign/agencast
cd agencast
(cd ui && npm install && npm run build)
uv tool install --editable framework
```

Create your own project with `agencast new project ~/my-project`.
You get a skeleton with the agent `writer` and the scenario `demo`.
For a finished example with deterministic responses, use:

```bash
agencast new project ~/agencast-demo --example showcase
cd ~/agencast-demo
agencast validate ig-post --offline
agencast run ig-post -i topic="new coffee" --dry-run --fake fake/ig-post.yaml
agencast run ig-post -i topic="new coffee" --fake fake/ig-post.yaml
```

`--dry-run` produces a plan; adding `--fake` also skips the network check of the models.
Without a fixture you can use `--fake` alone, but the made-up responses may not pass
the scenario's conditions. You can try the skeleton with `agencast run demo --fake`.

`--fake` replaces only the model calls: no model cost and no OpenRouter key.
A `task` step still starts the real MCP servers from `mcp.yaml`; the sample
`filesystem` server uses `npx`, needs Node.js and downloads its package on first start.
`--callback-url` sends a real callback (and needs its signing secret).
Only scenarios without `task` (including in called scenarios)
and without `--callback-url` are guaranteed to be offline, for example `ig-post`.

Only for a live run, copy `.env.example` to `.env` and fill in
`OPENROUTER_API_KEY`. Never commit or print keys.
After checking the plan and the result of the fake run, start:

```bash
agencast run ig-post -i topic="new coffee"
```

The record is in `runs/<run_id>/summary.md`, the machine-readable result in `callback.json`,
the report in `report.html`; exports are in `outputs/`. The CLI prints the exact paths.
`agencast runs list` and `agencast runs show <run_id>` show the history.

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

`agencast serve` starts the API and the built GUI, if there is one. New projects are added
to the registry for the GUI automatically. Expose the server and the GUI only on a private network;
for registry mode set `AGENCAST_TOKEN`, for a single project `WEBHOOK_TOKEN`
as in `.env.example`. Details: `agencast docs show spec/webhook.md`.

## Use from an MCP client

`agencast mcp` serves the registered projects (one with `--project`) to an MCP client: projects, scenarios,
runs and their results, and with `--allow edit` writing scenarios, agents and skills. A run started through it
goes on in a process of its own when the client disconnects or the server restarts. Details:
`agencast docs show spec/mcp-server.md` ([MCP server](spec/mcp-server.md)).

Claude Code starts the server itself over stdio; `--fake` leaves out live runs, so nothing can cost money:

```bash
claude mcp add --transport stdio agencast -- agencast mcp --fake
```

Image inputs are files on the server's machine inside a directory allowed with `--input-dir DIR` (a tool call
carries no bytes). Claude Code or Codex on another machine copies the user's images there over your own ssh
login first; the recipe is in the `agencast-run` skill (`agencast skills install` on that machine) and in
`get_guide("run")` on the server:

```bash
claude mcp add --transport stdio agencast -- ssh -T box /home/me/.local/bin/agencast mcp --input-dir /home/me/agencast-inputs
```

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

Expose it only on a private network — it speaks plain HTTP: keep `127.0.0.1` and publish it with
`tailscale serve`, never `tailscale funnel`. `--fake` stops model spending, but `task` steps still start their
MCP servers; only `--allow read` starts nothing. A run stops only when its own process does: a signal to it, or
the end of the control group it lives in (a unit without `KillMode=process`, a logout without lingering).
