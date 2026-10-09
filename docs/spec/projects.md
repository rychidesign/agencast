# Projects — registry and `agencast new` (since framework 0.4.0)

Project = a directory with `workflows/` (the project root). The framework
does **not scan** the disk for projects; the ones it knows are kept in the
registry. Formats v1 do not change.

## Registry

`~/.config/agencast/projects.yaml` (the directory is overridden by the
`AGENCAST_CONFIG_DIR` variable, mainly for tests):

```yaml
projects_root: ~/agencast-projects   # default location for new projects from the GUI
projects:
  - name: lumen              # project name in the registry and in the URL /projects/<name>
    root: ~/lumen  # absolute path to the root (the directory with workflows/)
  - name: from-gui
    root: ~/agencast-projects/from-gui
    trusted: false           # registered through the API: no MCP servers until `agencast projects trust from-gui`
```

| Field | What it does |
|---|---|
| `projects_root` | Default root for `POST /projects/new`; defaults to `~/agencast-projects` (up to 0.19.0 `~/workspace`). Paths are expanded and normalized. |
| `name` | Unique, same shape as scenario names (lowercase letters, digits, hyphen, starts with a letter). Default = the directory name converted to this shape (`My Project` → `my-project`). |
| `root` | Absolute path to the project root; a root appears in the registry at most once. |
| `trusted` | Optional, since 0.18.0. `false` = the entry was written by the API (`POST /projects`, `POST /projects/new`): the project may not use MCP servers ([Trust](#trust-projects-registered-through-the-api)). Without the key the project is trusted — every entry written from a terminal, and every entry from before 0.18.0. Only `true` or `false`; anything else is a `config` error. |

- The registry contains no keys or secrets, only names and paths.
- A project that is missing `workflows/config.yaml` (deleted, disk
  disconnected) **stays** in the registry with the flag `available: false`
  (`agencast projects list`, `GET /projects`).
- Writes are atomic (temporary file + rename); `serve` reads the registry
  on every request.
- The GUI can create a project with `POST /projects/new` (see [api.md](api.md));
  a `root` without a value points to `<projects_root>/<name>`. The path `~`
  is expanded, a relative path is resolved against `projects_root` and must
  not contain `..` or escape this root via a symlink. Absolute paths are
  allowed, even outside the server's home directory; the GUI has the same
  file permissions as the user that runs `agencast serve`.
- A new project does not overwrite an existing `workflows/`; instead, a
  directory with a project can be registered with `POST /projects` if it
  contains `workflows/config.yaml`. Unregistering with
  `DELETE /projects/<name>` does not delete any files. Both ways of
  registering write `trusted: false` (since 0.18.0, below).

### When the registry changes

| Command | What it does |
|---|---|
| `agencast new project <path> [--name N]` | Creates the project and registers it right away. |
| `agencast projects add <path> [--name N]` | Registers an existing project. |
| `agencast projects rm <name>` | Removes the entry; the project files stay. |
| `agencast projects trust <name>` | Since 0.18.0: removes `trusted: false` from the entry — the project may use the MCP servers in its `workflows/mcp.yaml`. Terminal only; there is no HTTP route for it. `agencast projects list` marks the entries it applies to. |
| `agencast run` that passes validation | Adds a project that is not in the registry under its default name and prints once to stderr `project <name> added to the registry (<path to projects.yaml>)` — before the run starts, whatever its result. `validate` and `run --dry-run` do not change the registry (`validate` since 0.15.1, `--dry-run` since 0.18.0; before that they added projects too — project copies in tests and worktrees then stayed in the registry). |

Name collision → `config` error with the hint `agencast projects add <path>
--name <name>`. For `validate`/`run`, a registry error is only printed to
stderr and the command finishes with its own result.

## Trust: projects registered through the API

Since 0.18.0. `workflows/mcp.yaml` names programs that the framework starts
on the host and remote servers that receive tokens from its environment
([config.md](config.md)); that file is the project owner's decision. The
API token can be held by more than the owner (the GUI, an automation tool), and a
directory on disk can be written by others — an agent with a filesystem
server writes into its run's `work/` folder. So:

- An entry written by the API — `POST /projects` (an existing directory)
  and `POST /projects/new` (a new project from the templates, into which
  files can be written later) — gets `trusted: false`. Entries from a
  terminal (`agencast new project`, `agencast projects add`, the automatic
  registration by `agencast run`) have no such key and are trusted. No HTTP
  route sets or clears the key; removing an entry and adding it again
  through the API leaves it untrusted.
- A project whose entry has `trusted: false` uses **no MCP server**, local
  or remote. `validate`, `run`, `run --dry-run`, `run --fake` and the same
  requests over HTTP end, for a scenario with a `task` step that would use
  a server, with one `config` error before anything starts:

  ```
  config: test.yaml: MCP servers (filesystem) are disabled — project 'from-gui' (/srv/projects/from-gui) was registered through the API and is not trusted to run them (trusted: false in the project registry). The project owner allows them in a terminal: agencast projects trust from-gui
  ```

  Scenarios without such a step run as before.
- The entry is looked up on every validation — when a run is accepted and
  again when it starts — by the project root as it was addressed and as it
  resolves (a symlinked `workflows/` or `scenarios/` does not lead around
  it). A project that is not in the registry is the terminal user's own and
  is trusted; `agencast serve` in registry mode serves registered projects
  only, so there a project that left the registry while its run was queued
  gets no MCP servers either. An unreadable registry counts as not trusted.
- Before `agencast projects trust <name>`, read the project's
  `workflows/mcp.yaml`: every `command` in it will run with the
  permissions of the user that runs `agencast`. The command shows what it
  is about to trust — the project root and, for every server of its
  `mcp.yaml`, the command line or the host of the remote server — and asks
  for confirmation; outside a terminal it changes nothing unless `--yes`
  is given. Control characters in a root or in a command line are shown
  escaped (`\r`, `\x1b`), here and in `agencast projects list`, so they
  cannot redraw the terminal line. Trust goes to the root that was shown:
  when the name points to another directory by then (removed and added
  again through the API while the owner was reading), the command fails
  and nothing is trusted.

  ```
  $ agencast projects trust from-gui
  project from-gui: /srv/projects/from-gui
  MCP servers in /srv/projects/from-gui/workflows/mcp.yaml:
    filesystem: npx -y @modelcontextprotocol/server-filesystem '{run_dir}/work'
    search: remote server mcp.example.com
  Allow this project to start these servers? [y/N]
  ```

## `agencast new`

Templates are part of the framework (not a copy of `workflows/`). Nothing
is overwritten: an existing file or `workflows/` = `config` error.

- **`new project <path>`** creates
  - `workflows/config.yaml` — OpenRouter (`OPENROUTER_API_KEY`), aliases
    `smart`, `fast`, `gemini-image`, `runs_dir: ./runs`,
    `storage.type: local` (`./outputs`), run limits, `webhook` and `callback`,
  - `workflows/agents/writer.md` and `workflows/scenarios/demo.yaml`
    (input `topic` with a default value → `ask` → `output`); they pass
    `validate --offline` and `run demo --fake`,
  - `.env.example` (`OPENROUTER_API_KEY=`, for `serve` `WEBHOOK_TOKEN=`,
    `CALLBACK_SECRET=`) and `.gitignore` (`.env`, `runs/`, `outputs/`),
    if not there yet.
- **`new agent <name>`** — `workflows/agents/<name>.md`: `model` = the first
  alias from the project's `config.yaml` (the others in a comment),
  `budget_usd: 0.02`, body and `description` to be filled in.
- **`new scenario <name>`** — `workflows/scenarios/<name>.yaml`: input →
  `ask` with the project's first agent (alphabetically) → `output`. A
  project without an agent = `config` error.

The project is located as for the other commands (current directory
upwards, or `--project`). Public API: `agencast.api.new_project(root, name=None)`,
`new_agent(project_root, name)`, `new_scenario(project_root, name)` return
a list of created paths; `projects()`, `add_project(path, name=None)`,
`remove_project(name)`, `projects_root()`; since 0.18.0 `trust_project(name)`
and the keyword `trusted=False` of `new_project` and `add_project` (what the
HTTP layer passes).
