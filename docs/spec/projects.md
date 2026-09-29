# Projects — registry and `agencast new` (since framework 0.4.0)

Project = a directory with `workflows/` (the project root). The framework
does **not scan** the disk for projects; the ones it knows are kept in the
registry. Formats v1 do not change.

## Registry

`~/.config/agencast/projects.yaml` (the directory is overridden by the
`AGENCAST_CONFIG_DIR` variable, mainly for tests):

```yaml
projects_root: ~/workspace   # default location for new projects from the GUI
projects:
  - name: lumen              # project name in the registry and in the URL /projects/<name>
    root: ~/lumen  # absolute path to the root (the directory with workflows/)
```

| Field | What it does |
|---|---|
| `projects_root` | Default root for `POST /projects/new`; defaults to `~/workspace`. Paths are expanded and normalized. |
| `name` | Unique, same shape as scenario names (lowercase letters, digits, hyphen, starts with a letter). Default = the directory name converted to this shape (`My Project` → `my-project`). |
| `root` | Absolute path to the project root; a root appears in the registry at most once. |

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
  `DELETE /projects/<name>` does not delete any files.

### When the registry changes

| Command | What it does |
|---|---|
| `agencast new project <path> [--name N]` | Creates the project and registers it right away. |
| `agencast projects add <path> [--name N]` | Registers an existing project. |
| `agencast projects rm <name>` | Removes the entry; the project files stay. |
| successful `agencast run` | Adds a project that is not in the registry under its default name and prints once to stderr `project <name> added to the registry (<path to projects.yaml>)`. `validate` does not change the registry (since 0.15.1; before that it added projects too — project copies in tests and worktrees then stayed in the registry). |

Name collision → `config` error with the hint `agencast projects add <path>
--name <name>`. For `validate`/`run`, a registry error is only printed to
stderr and the command finishes with its own result.

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
`remove_project(name)`, `projects_root()`.
