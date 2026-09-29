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
