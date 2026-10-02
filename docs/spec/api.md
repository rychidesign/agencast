# `agencast serve` API — the `/projects/...` family (reading since framework 0.4.0, editing since 0.5.0, GUI additions since 0.6.0, 0.7.0, 0.8.0 and 0.9.0)

For the GUI (DESIGN “Wrappers”) and for anyone who wants to read and edit projects
and read runs over HTTP. Complements [webhook.md](webhook.md) — `POST /runs`, `GET /runs/<id>`
and the callbacks do not change. Projects: [projects.md](projects.md).

## Server modes

| Start | Mode | Token (`Authorization: Bearer …`) | `/runs` |
|---|---|---|---|
| `agencast serve` inside a project (a folder with `workflows/`, searched from the cwd upward) or `--project <path>` | single project (as up to 0.3.x; Modal) | the project's `webhook.token_env` value | yes, unchanged |
| `agencast serve` outside a project | registry | variable **`AGENCAST_TOKEN`** (required at start, otherwise `config`) | no — 404, run through `POST /projects/<p>/runs` |

- In single-project mode `/projects` contains exactly that project; its name
  comes from the registry, otherwise the default (the folder name, [projects.md](projects.md)).
- **Secrets in registry mode:** `serve` takes all secrets
  from its own process environment (and from `.env` in the current folder); the
  `.env` files of individual projects are not read in the registry. Variable
  names (`openrouter.api_key_env`, `callback.secret_env`) are still taken
  from the project's `config.yaml`, the values from the server's environment. `callback.secret_env`
  is required only for a run with `callback_url`; `webhook.token_env` is read
  only in single-project mode.
- The registry is read on every request. Each project has its own queue
  (`<runs>/_queue/`) and `--workers N` worker threads; the queues of available
  projects are restored at start, a project added later on its first `POST`.
- Reading and writing use the same token. A missing or mismatched token → 401.
- The token protects `/projects…`, `/runs…` and (since 0.18.0, single-project mode) `/uploads`;
  the GUI (`GET /`, `/assets/…`, section [GUI and CORS](#gui-and-cors-since-060)) needs no token.

## Endpoints

Responses are JSON (except `runs/<id>/files/`). Errors are `{"error": "…"}`, for 422
plus `"details": [...]` (for editing operations `"errors": [...]`, section
[Editing](#editing-since-050)). Since 0.6.0 the `errors` field contains **objects**
`{message, file?, step?, field?, line?}` ([Errors as objects](#errors-as-objects-since-060));
`details` stay plain texts.

| Method and path | Response |
|---|---|
| `GET /projects` | `{"projects": [{"name", "root", "available"}]}`; since 0.7.0 `reason` for `available: false`, `last_run` and `registry`; since 0.9.0 `projects_root` and `writable`; since 0.10.0 `counts` and `spend_today_usd`; since 0.18.0 `trusted` |
| `POST /projects/new` | `{name, root?}` — creates a project and registers it; 201 `{name, root, created}`; since 0.18.0 also `trusted: false` ([MCP servers are the owner's](#mcp-servers-are-the-owners-since-0180)) |
| `POST /projects` | `{root, name?}` — registers an existing project with `workflows/config.yaml`; 201 `{name, root}`; since 0.18.0 also `trusted: false` |
| `DELETE /projects/<p>` | Removes the project from the registry; 200 `{name, removed: true, files_deleted: false, message}`; the files stay |
| `GET /projects/<p>` | project description (below) |
| `GET /projects/<p>/scenarios/<s>` | scenario with the step tree (below) |
| `GET /projects/<p>/files/<path>` | a file from `workflows/` as text with a fingerprint (section [Editing](#editing-since-050); not `mcp.yaml`); since 0.8.0 `errors` = the file's `validate` errors and `?etag_only=1` → only `{"etag"}` ([Additions 0.8.0](#batch-preview-and-additions-from-gui-findings-part-2-since-080)) |
| `HEAD /projects/<p>/files/<path>` | since 0.8.0: only the fingerprint in the `ETag` header ([Additions 0.8.0](#batch-preview-and-additions-from-gui-findings-part-2-since-080)) |
| `GET /projects/<p>/runs` | `{"runs": [...]}` — items as in `agencast runs list`: queued `{"run_id", "status": "queued"}`, then `{"run_id", "status", "cost_usd", "duration_s", "callback", "scenario", "started_at", "finished_at", "current_step", "steps_total"}` (fields from `scenario` on since 0.6.0, [Runs for the GUI](#runs-for-the-gui-since-060)), newest first; since 0.7.0 `state`, `fake`, `current_nn`, `steps_done`, `queue_position` and `?scenario=&limit=`; since 0.10.0 `before` and `next_before` |
| `GET /projects/<p>/runs/<id>` | run status + steps + files (below); a run waiting in the queue `{"run_id", "status": "queued"}` (since 0.7.0 also `state`, `scenario`, `queue_position`); since 0.7.0 the step tree `tree` |
| `GET /projects/<p>/runs/<id>/steps/<path>` | one step of a run: its events, output and files (since 0.7.0, [below](#get-projectsprunsidstepspath-since-070)) |
| `GET /projects/<p>/runs/<id>/files/<path>` | contents of a file from the run directory (`summary.md`, `report.html`, `events.jsonl`, `steps/…`), `Content-Type` by extension |
| `GET /projects/<p>/spend?day=YYYY-MM-DD` | daily ledger of live-run spend: `{"day", "total_usd", "runs": [{"run_id", "cost_usd", "finished_at"}]}`; without `day` today (UTC); any other `day` format → 422 |
| `POST /projects/<p>/runs` | like `POST /runs` ([webhook.md](webhook.md)) in project `<p>` — same body, same 202/200/401/422 responses and callback; since 0.6.0 `callback_url` is optional and `dry_run` exists ([Starting from the GUI](#starting-from-the-gui-since-060)) |
| `POST /projects/<p>/uploads` | since 0.18.0: the raw bytes of one image (PNG, JPEG, WebP, GIF, AVIF; ≤ 10 MB) → 201 `{"upload_id", "format", "width", "height", "bytes"}`; a run's `file`/`files` input is then `{"upload_id": "up_…"}` ([Uploads](#uploads-since-0180)) |
| `POST /projects/<p>/validate` | validation without writing (since 0.6.0, [below](#post-projectspvalidate-since-060)) |

- **404** with a JSON error: unknown project, unavailable project
  (`available: false`), unknown scenario, run, file or address. A file path
  outside the run directory (`..`, an absolute path, a symlink pointing out) = 404.
- **422**: the project's `config.yaml` failed the check (`details` = the errors,
  since 0.7.0 `GET` also returns `errors` as objects); for `POST` also a missing
  project environment variable. `…/runs`, `…/runs/<id>…` and `spend`
  work since 0.7.0 even with an invalid `config.yaml` (they only need `runs_dir`).
- Writing projects is available only in registry mode. In single-project
  mode `POST /projects/new`, `POST /projects` and
  `DELETE /projects/<p>` return **405** with an explanation.
- `POST /projects/new` needs `name` and optionally `root`; without `root`
  `<projects_root>/<name>` is used. An existing `workflows/` or a name in
  the registry → **409**; for an existing folder the response advises adding it through
  `POST /projects`. `created` is the list of paths created on disk.
- `POST /projects` accepts a project root with `workflows/config.yaml`.
  `root` is expanded and normalized: `~` is expanded, an absolute path may
  point anywhere and a relative path is resolved against `projects_root`. Any
  `..` or a relative path leading outside through a symlink → **422**. A name
  or root collision → **409**.
- Writing outside the home directory of `serve` is allowed if the file
  system permissions allow it. The GUI has the permissions of the user under which `agencast serve`
  runs.
- `spend` reads only the ledger of live runs (`_ledger/`); fake runs
  (`--fake`) have their own `_ledger-fake/` and are not in `spend`.

### `GET /projects/<p>`

```json
{
  "name": "lumen", "root": "~/projects/lumen", "trusted": true,
  "models": {"smart": "anthropic/claude-haiku-4.5"},
  "limits": {"run_budget_usd": 1.0, "run_timeout": "1h", "max_call_depth": 3},
  "scenarios": [{"name": "ig-post", "etag": "9f2c…", "description": "…", "inputs": {…}, "outputs": {…},
                 "callable": false, "steps_count": 8, "errors": [],
                 "types": ["ask", "jev", "fail", "jev", "image", "output"],
                 "last_run": {"run_id": "20260926-120000-ig-post-ab12", "state": "succeeded",
                              "finished_at": "2026-09-26T12:01:10.500Z", "cost_usd": 0.0123}}],
  "agents": [{"name": "copywriter", "etag": "…", "description": "…", "model": "smart",
              "model_id": "anthropic/claude-haiku-4.5", "skills": ["lumen-voice"], "mcp": [], "tools": {},
              "errors": []}],
  "skills": [{"name": "lumen-voice", "etag": "…", "description": "…", "errors": []}],
  "mcp_servers": [{"name": "filesystem", "type": "stdio", "description": "Reading and writing in the run workspace",
                   "transport": "stdio", "agents": ["librarian"], "tools": ["read_text_file"], "scenarios": null,
                   "env_missing": []}],
  "links": {"scenario_agent": [["ig-post", "copywriter"]], "scenario_step_agent": [["ig-post", "copy", "copywriter"]],
            "scenario_scenario": [["demo-call", "tone-check"]],
            "agent_skill": [["copywriter", "lumen-voice"]], "agent_server": [["librarian", "filesystem"]]},
  "env": {"CALLBACK_SECRET": true, "OPENROUTER_API_KEY": true, "WEBHOOK_TOKEN": false},
  "errors": []
}
```

- Read through the loader and `validate` (without checking models against `GET /models`).
  `errors` = the `validate` messages for that file; a broken file is still
  shown, as far as it can be read. The project-level `errors` = errors of `mcp.yaml`.
- `steps_count` = all steps, including those nested in branches.
- `etag` (since 0.5.0) = the fingerprint of the scenario, agent or skill file (`SKILL.md`)
  for editing operations. A file that cannot be read (a link that leads nowhere, a directory
  under that name, no permission) is listed with that error and `etag: ""`.
- `trusted` (since 0.18.0, read-only) = `false` when the project was registered through the API
  and its owner has not run `agencast projects trust <p>` yet: its scenarios cannot use MCP
  servers ([MCP servers are the owner's](#mcp-servers-are-the-owners-since-0180)). The same field
  is in every item of `GET /projects`.
- MCP servers without secrets: only the name, `type` (`stdio`/`http`) and the permissions
  from `mcp.yaml` (`agents`, `tools`, `scenarios`; `tools: null` = the owner does not restrict
  the tools) — no `command`, `args`, `url`, `env` or `bearer_token_env`. This list is all the API
  tells about `mcp.yaml`; the file itself is not served (since 0.18.0). Since 0.18.0 also
  `description`, `transport` (`stdio`, `streamable-http` or `sse`; `type` stays for older clients)
  and `env_missing` = the names (never the values) of the server's variables (`env`,
  `bearer_token_env`) that are not set in the environment of `agencast serve` (the same check as
  the project-level `env`); `[]` = none missing.
- `links` = sorted [from, to] pairs: an `ask`/`task` step → agent,
  a `call` step → scenario, agent → skill, agent → MCP server. Since 0.7.0
  `scenario_step_agent` = [scenario, step id, agent] triples (including steps in
  branches); `scenario_agent` stays. Since 0.8.0 `scenario_model` =
  [scenario, alias] from `image` steps and the `models_used` field
  ([Additions 0.8.0](#batch-preview-and-additions-from-gui-findings-part-2-since-080)).
- `types` (since 0.7.0) = the step types of the main list in file order
  (`null` when the file does not determine the type); `last_run` (since 0.7.0) = the newest
  run of the scenario (shape [below](#additions-from-gui-findings-since-070)), `null` without runs.
- `env` (since 0.6.0) = all environment variables the project
  refers to (`*_env` fields in `config.yaml` — `openrouter.api_key_env`,
  `webhook.token_env`, `callback.secret_env`, storage variables — and
  `env`/`bearer_token_env` of the servers in `mcp.yaml`), sorted by name:
  `true` = it is non-empty in the environment of the `serve` process (in single-project
  mode after loading the project's `.env`, in registry mode only the server's environment and
  `.env` in the cwd). **The value is never returned.**

### `GET /projects/<p>/scenarios/<s>`

The header as in `scenarios` above (including `etag`) and `steps` — the step tree
for the cards:

```json
{"nn": 3, "address": ["steps", 2], "id": "stop", "type": "fail", "when": "steps.tone_check.on_brand < 0.7",
 "fields": {"fail": "The text does not match the brand (on_brand = {{ steps.tone_check.on_brand }})"},
 "refs": ["steps.tone_check.on_brand"]}
```

| Field | What it is |
|---|---|
| `nn` | depth-first order in the file — the same number as the step folder `steps/<nn>-<id>` in the run record |
| `address` | the step address for editing operations (since 0.5.0, below) |
| `id`, `type`, `when` | the id, the step type (`null` when the file does not determine the type), the condition (`null` without `when`) |
| `fields` | all other step fields as they are in the file, without nested step lists (for `switch` only `value`) |
| `refs` | `steps.<id>.<field>` references from the expressions and templates of this step (without nested steps) |
| `agent` | for `ask` and `task` |
| `call` | for `call`: the name of the called scenario |
| `branches` | for `parallel`: `{branch: [steps]}` |
| `cases`, `default` | for `switch`: `{value: [steps]}` and `[steps]` |

### `GET /projects/<p>/runs/<id>`

The `agencast runs list` fields (`run_id`, `status`, `cost_usd`, `duration_s`,
`callback`) and in addition:

- `steps` — steps in the order of their first event in `events.jsonl`:
  `{"step", "kind", "status", "branch", "started_at", "finished_at",
  "duration_s", "cost_usd"}`; `status` = `running`, `succeeded`,
  `failed`, `cancelled`, or `skipped` (then `reason_code`, `reason`).
  `step` is the path as in `events.jsonl` (for `call` `propose/copy`). Since 0.7.0
  more fields ([below](#step-details-since-070)).
- `files` — relative paths of all files in the run directory (for `files/`).
- since 0.7.0 `tree`, `callees`, `tree_source` — the step tree as it was
  during the run ([below](#run-step-tree-since-070)).

## Editing (since 0.5.0)

The GUI changes files only through these operations; **the file is the truth** (DESIGN
“Wrappers”). Every operation:

1. reads the file and compares the **fingerprint** `etag` from the request body with the fingerprint
   of the file — `etag` = sha256 (hex) of the bytes of the file the client loaded
   (`GET …/scenarios/<s>`, `GET /projects/<p>`, `GET …/files/<path>`);
   a new file has `etag: null`. No match → **409** and nothing is written;
2. edits the file while preserving comments, key order, blank lines
   and quote style (unchanged lines stay verbatim; a rewritten line
   may get different spacing, e.g. `{a: 1}` instead of `{ a: 1 }`);
3. validates a copy of `workflows/` with the change exactly like `agencast validate`
   (without checking models against `GET /models`). The change must not add a
   **new** error to the project — errors that were already in the project do not
   block it (two broken files can be fixed one after the other). The error of an
   untrusted project (“MCP servers (…) are disabled”, see
   [MCP servers are the owner's](#mcp-servers-are-the-owners-since-0180)) names the servers and shows
   only when its scenario has no other error; in a scenario that already had an error it is
   not new — such a scenario can still be given fewer servers or have its other error fixed.
   A new error → **422** and nothing is written;
4. writes atomically (temporary file + rename); the replaced file keeps its
   permission bits (an owner's `chmod 600` on `mcp.yaml` survives an agent rename).

The request body is a JSON object with an `etag` field. Responses:

| Code | Body |
|---|---|
| 200 | `{"etag": "<new fingerprint>" \| null after deletion, "errors": [errors that remain in the project]}` (objects, [below](#errors-as-objects-since-060)) |
| 409 | `{"error", "etag": "<current fingerprint>" \| null}` — the file changed in the meantime; reload it |
| 422 | `{"error", "errors": [...]}` — messages as from `agencast validate` (class `config`) as objects, nothing was written |
| 404 | `{"error"}` — unknown project, file, step address or a path outside the allowed files |
| 401 | missing or mismatched token (the same as for reading) |

A rename additionally returns `name` and `changed`: the new name and the sorted paths
of changed files relative to `workflows/`; `errors` contains the errors that
remain in the project. A rename does not touch `runs/`: older runs still carry the
scenario name that was valid when they started.

### Step address

The path to a step in the scenario document, as a JSON array. It is returned by
`GET …/scenarios/<s>` in the `address` field of every step:

| Address | What it is |
|---|---|
| `["steps", 2]` | the third step of the main list |
| `["steps", 2, "parallel", "a", 0]` | the first step of branch `a` of the `parallel` step |
| `["steps", 4, "switch", "cases", "playful", 1]` | the second step of case `playful` |
| `["steps", 4, "switch", "default", 0]` | the first step of `default` |
| without the last index, e.g. `["steps", 2, "parallel", "a"]` or `["steps"]` | a step list (the start of a branch) |

It nests to any depth the scenario allows. In a URL the address is
the path after `steps/` (each item one segment, `/` in a case name as
`%2F`): `["steps", 2, "parallel", "a", 0]` → `…/steps/2/parallel/a/0`.

### Operations

`<p>` project, `<s>` scenario, `<a>` agent, `<n>` skill. Field changes are a
**merge patch** (RFC 7396): a map is merged, a `null` key deletes, any other
value replaces. Text with `{{ }}` is written in double quotes, multiple
lines as a `|` block; replaced quoted text keeps its style.

| Method and path | Body (besides `etag`) | What it does |
|---|---|---|
| `POST /projects/<p>/scenarios` | `{"name", "description"?}` | a new scenario from the template (`agencast new scenario`); 200 `{"name", "etag"}`, an existing one → 422; `description` since 0.8.0 |
| `POST /projects/<p>/agents` | `{"name", "description"?, "model"?}` | a new agent from the template (`agencast new agent`); 200 `{"name", "etag"}`; since 0.8.0 `description` and `model` (an alias from `config.yaml`, any other → 422) |
| `POST /projects/<p>/scenarios/<s>/rename` | `{"name"}` | renames the scenario, the file and the `call.scenario` references; 200 `{"name", "etag", "changed", "errors"}` |
| `POST /projects/<p>/agents/<a>/rename` | `{"name"}` | renames the agent, the file and the references in `ask`/`task` steps and in the `agents` lists in `mcp.yaml` — the only change the API ever makes to that file, and only this name in those lists; 200 `{"name", "etag", "changed", "errors"}` |
| `PUT /projects/<p>/scenarios/<s>` | `{"fields": {…}}` | header: only `description`, `inputs`, `outputs`, `callable` (any other field → 422) |
| `DELETE /projects/<p>/scenarios/<s>` | — | deletes the scenario; when another one calls it through `call` → 422 |
| `POST /projects/<p>/scenarios/<s>/steps` | `{"after": address, "step": {…}}` | inserts a step (whole, as in the file) after the step `after`; a list address = at its start; without `after` at the start of `steps` |
| `PATCH /projects/<p>/scenarios/<s>/steps/<address>` | `{"fields": {…}}` | step fields (including `id`, `when`, `parallel` branches and `switch` cases) |
| `POST /projects/<p>/scenarios/<s>/steps/<address>/move` | `{"to": address}` | moves the step after the step `to`, or to the start of the list `to`; into its own branch → 422 |
| `DELETE /projects/<p>/scenarios/<s>/steps/<address>` | — | deletes the step |
| `PUT /projects/<p>/scenarios/<s>/steps/<address>` | `{"step": {…}}` | since 0.8.0: replaces the whole step (supports `null`) |
| `POST /projects/<p>/scenarios/<s>/batch` | `{"ops": [...]}` | since 0.8.0: a batch of operations, one validation, one write ([below](#batch-post-scenariossbatch)) |
| `POST /projects/<p>/scenarios/<s>/render` | `{"ops": [...]}`, `etag` optional | since 0.8.0: the result of a batch without writing `{text, tree, errors}` ([below](#preview-post-scenariossrender)) |
| `PUT /projects/<p>/agents/<a>` | `{"frontmatter": {…}, "body": "…"}` | frontmatter as a merge patch, the whole body; a missing one = unchanged; a new agent needs both |
| `DELETE /projects/<p>/agents/<a>` | — | deletes the agent; when a scenario uses it (`ask`/`task`) → 422 |
| `PUT /projects/<p>/skills/<n>` | `{"text"}` | the whole `SKILL.md`; creates a new skill |
| `DELETE /projects/<p>/skills/<n>` | — | deletes `SKILL.md` (and the folder if empty); when an agent uses it → 422 |

**Step headers.** The blank lines and comments directly above a step are its header —
they belong to the step below them (the examples number and describe their steps there).
The step operations treat them alike: deleting a step removes its header and leaves the
header of the next step; moving a step takes its header along (indented like the list it
lands in); a new step is inserted below the step before it and above the header of the
step after it; replacing a step keeps both its header and the next one. What follows the
last step of a list (a blank line and a comment before `outputs:`) stays below the list.
A comment never becomes a part of a `|` or `>` text: one that an operation leaves below such
a text is written at the column of the key that holds the text, left of the text.
| `PUT /projects/<p>/config` | `{"fields": {…}}` | `config.yaml`: only `models`, `limits`, `storage`, `webhook`, `callback` and `openrouter.api_key_env`; since 0.8.0 also `runs_dir` and `openrouter.jev_model` ([why not more](#put-config-since-080)) |
| `GET /projects/<p>/files/<path>` | — | `{"path", "etag", "text", "errors"}` and the parsed content: for `.yaml` `data`, for `.md` `frontmatter` and `body` (the GUI does not parse by itself) |
| `PUT /projects/<p>/files/<path>` | `{"text"}` | the whole text of the file (fallback text editor); a new file with `etag: null` |

- After an operation on steps `output` stays the last step of the main
  list — otherwise 422 (`config`). When the last step leaves a `parallel` branch or a `switch`
  case, the branch/case disappears (the schema does not allow an empty
  list).
- A merge patch cannot write the value `null` (it deletes the key); a step with `null`
  (e.g. `default: { file: null }`) can be inserted whole through `POST …/steps`,
  since 0.8.0 replaced whole through `PUT …/steps/<address>`, or edited as
  text through `files/`.
- **`files/<path>`** (a different family from `…/runs/<id>/files/`) lets through only
  `agents/<name>.md`, `scenarios/<name>.yaml`, `skills/<name>/SKILL.md` and
  `config.yaml` inside the project's `workflows/`; anything else
  (`..`, an absolute path, a symlink pointing out or at a file that is not one of these,
  `.env`, `mcp.yaml`, `commands.yaml`, subfolders) = 404. A write replaces the file and
  follows no link, not at the name of its temporary file either; a file in a linked
  directory (`skills/<name>` → another skill) can be read, a write to it = 404. The same
  holds for every editing route, and for the files the API creates from templates
  (`POST …/scenarios`, `POST …/agents`, `POST /projects/new`): a link waiting at the new
  name — also one whose target does not exist yet — is never written through; the answer is
  404, or 422/409 `already exists`, and nothing is created. **`.env` is never read or
  written.** Up to 0.17 `mcp.yaml` was among the allowed files; since 0.18.0 it is the owner's
  file on disk
  ([below](#mcp-servers-are-the-owners-since-0180)).
- **Secrets:** `config.yaml` contains only variable names
  (`*_env`); the values live in the environment/`.env`. A value instead of a name
  (say an `sk-or-…` key in `api_key_env`) does not pass the schema → 422 and
  the message does not print the value.
- Operations within one `serve` process run one at a time (a lock). A manual edit
  of a file outside `serve` is detected by the fingerprint on the next operation.
- Public API (`agencast.api`): `set_header`, `add_step`, `update_step`,
  `move_step`, `delete_step`, `delete_scenario`, `rename_scenario`, `set_agent`,
  `delete_agent`, `rename_agent`, `set_skill`, `delete_skill`, `set_config`, `read_file`,
  `write_file`, since 0.6.0 `validate_text`, since 0.8.0 `replace_step`,
  `batch`, `render`, `file_etag`; the exceptions `Conflict` (`.etag`),
  `NotFound`, `ConfigErrors`, since 0.8.0 `OpError` (a subclass of
  `ConfigErrors`, `.op` = the index of the batch operation). The Python API returns errors as texts (like
  `agencast validate`); only the HTTP layer turns them into objects.

## GUI additions (since 0.6.0)

Following the GUI design (`docs/ui/gui-design.md` §7, §8). Additive except for the shape of
`errors` — the GUI is the only client of those fields.

### Errors as objects (since 0.6.0)

Everywhere the API returns an `errors` array (`GET /projects/<p>` — project,
scenarios, agents, skills —, `GET …/scenarios/<s>`, `GET …/files/<path>`,
200 and 422 responses of editing operations, `POST …/validate`), an item is
an object:

```json
{"message": "demo.yaml: step \"result\", output.text: step 'missing' does not exist (available: write)\n  {{ steps.missing.text }}\n           ^",
 "file": "scenarios/demo.yaml", "step": "result", "field": "output.text"}
```

| Field | What it is |
|---|---|
| `message` | the message exactly as from `agencast validate` (the CLI prints it unchanged) |
| `file` | relative path within `workflows/` (`scenarios/ig-post.yaml`, `agents/copy.md`, `skills/voice/SKILL.md`, `config.yaml`, `mcp.yaml`) |
| `step` | the id of the step the error concerns |
| `field` | the field (a dotted path, e.g. `ask.prompt`, `inputs.topic.default`, `openrouter`) |
| `line` | the line number — YAML syntax, a duplicate key and, since 0.10.0, `config.yaml` schema errors by key |

Fields other than `message` are absent when the message does not state them (e.g. an error in the request
body `fields: must be a JSON object`). The shape change compared to 0.4.0/0.5.0
(previously texts): `message` = the former text. `details` (a rejected `POST`,
a `config.yaml` error on read) stay texts.

### `POST /projects/<p>/validate` (since 0.6.0)

Validation without writing, the same mechanism as step 3 of the editing operations
(a copy of `workflows/` + `validate` without checking models).

| Body | What it validates |
|---|---|
| empty or `{}` | the project as it is on disk |
| `{"path": "scenarios/ig-post.yaml", "text": "…"}` | the project with this file replaced by `text` (a new file works too); `path` only from the allowed `files/` files |

The response **200** `{"errors": [...]}` = **all** errors of the project (including those
that were already there; objects as above). For `path: "scenarios/<name>.yaml"`
the scenario text additionally returns `tree` in the same shape as
`GET …/scenarios/<s>`; nothing is written. A file outside the allowed ones → 404,
`text` not a text → 422. The fingerprint is not checked, nothing is written.

### Runs for the GUI (since 0.6.0)

`GET /projects/<p>/runs` and `GET /projects/<p>/runs/<id>` additionally have
(source `events.jsonl`):

| Field | What it is |
|---|---|
| `scenario` | the scenario name from `run_started` |
| `started_at`, `finished_at` | `ts` from `run_started` and `run_finished`; `finished_at: null` for a running (or interrupted) run |
| `current_step` | for a run without `run_finished`: the `step` of the last `step_started` without a `step_finished`; otherwise `null` |
| `steps_total` | the number of scenario steps including those nested in branches (without steps of called scenarios) from `run_started.steps_total`; `null` for runs before 0.6.0 |

`status` stays as in `agencast runs list` (`succeeded`, `failed (<class> in <step>)`,
`running`, `interrupted`, `dry-run`; since 0.7.0 `running` and `interrupted` are told apart);
dry runs and runs without `events.jsonl` have the new
fields `null` (since 0.7.0 for a dry run `scenario` and `started_at` come from `run_id`).
The `status` text is for humans; clients should read the machine field `state` (below).

```json
{"run_id": "20260926-120000-demo-ab12", "status": "running", "state": "running", "cost_usd": null,
 "duration_s": null, "callback": "", "scenario": "demo", "started_at": "2026-09-26T12:00:00.004Z",
 "finished_at": null, "current_step": "result", "steps_total": 2, "fake": false, "current_nn": 2, "steps_done": 1}
```

### Starting from the GUI (since 0.6.0)

`POST /projects/<p>/runs` additionally accepts, compared to `POST /runs`:

- `callback_url` is **optional** — without it no callback is sent;
  the record has `run_started.callback_url: null` and no `callback_sent`
  ([run-record.md](run-record.md)). When present, the rules of webhook.md apply.
- `"dry_run": true` → the run is not started, only a folder with `plan.md`
  and `inputs.json` is created (like `agencast run --dry-run`); the response is **200**
  `{"run_id": "…", "dry_run": true}`. Inputs and the scenario are checked
  in the same way (422). With `callback_url` or `request_key` → 422.

The `POST /runs` contract ([webhook.md](webhook.md)) does not change: `callback_url`
is required, the `dry_run` field is unknown (422).

### Uploads (since 0.18.0)

Inputs of type `file` and `files` (scenario.md [Type `file`](scenario.md#type-file))
cannot be JSON values — a string is never a path. Over HTTP a file is uploaded
first:

- `POST /projects/<p>/uploads` (in single-project mode `POST /uploads`), the
  same `Authorization` token, the body = the raw bytes of one image (no
  multipart, `Content-Type` and file name are ignored; the format comes from the
  file header). Checked like a CLI path: PNG, JPEG, WebP, GIF or AVIF, at most
  10 MB → **201** `{"upload_id": "up_<32 hex>", "format": "jpeg", "width":
  4032, "height": 3024, "bytes": 2101234}`; otherwise **422** `{"error"}`
  (**401** without the token, checked before the body is read).
- The run request then carries `{"upload_id": "up_…"}` in place of the file —
  `"inputs": {"photo": {"upload_id": "up_…"}, "refs": [{"upload_id": "up_…"},
  {"upload_id": "up_…"}]}` — for `POST …/runs` and `dry_run` alike. An unknown
  or expired id is a 422 (`upload … not found`). The id may be used again
  (a dry run, then the real run; two scenarios).
- The server keeps uploads in `<runs_dir>/_uploads/`; the run copies the file
  into its own `inputs/` (run-record.md). An upload not used for 24 h (uploaded
  or named in a run request) that no queued run refers to is deleted on the
  next upload.

### GUI and CORS (since 0.6.0)

- `serve` serves static files from the package's `agencast/ui/` folder
  (`framework/src/agencast/ui/`, the GUI built from `ui/` with `npm run
  build`): `GET /` → `index.html`, `GET /assets/…` files. **No
  token.** A path without an extension that is not a file returns `index.html`
  (the GUI uses hash routing); an unknown file with an extension → 404. A path
  outside the GUI folder → 404.
- When the GUI is not built, `GET /` returns **404** `{"error"}` with instructions
  (`ui/` → `npm install` and `npm run build`).
- `agencast serve --cors <origin>` (developing the GUI from `vite dev`, e.g.
  `http://localhost:5173`): every response has
  `Access-Control-Allow-Origin: <origin>` and `OPTIONS` (preflight) returns
  204 with `Access-Control-Allow-Methods` and `Access-Control-Allow-Headers:
  Authorization, Content-Type`. Without the switch there are no CORS headers
  and `OPTIONS` → 404 (source: MDN, *Cross-Origin Resource Sharing (CORS)*,
  https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).

## Additions from GUI findings (since 0.7.0)

Following `docs/ui/api-findings.md` (what the GUI missed while building the read-only version).
All additive; the `POST /runs` contract, `GET /runs/<id>` and the callback are
unchanged.

### Run state: `state`

A run holds an `flock` lock on `<run>/run.lock` for the whole life of its process
([run-record.md](run-record.md)); the lock is released even when the process crashes. The run list
and the run detail both have the machine field `state`:

| `state` | When | `status` (text as in `runs list`) |
|---|---|---|
| `queued` | a request in the `serve` queue, the run folder does not exist yet; since 0.8.0 also a folder from a queue entry whose lock nobody holds and which has no `run_finished` | `queued` |
| `running` | a live process holds the `run.lock` lock | `running` |
| `interrupted` | no lock held, without `run_finished`, or a `run_finished` restored after a `serve` restart (since 0.10.0) | `interrupted` or, after recovery, `failed (internal in <step>)` |
| `succeeded`, `failed` | `run_finished.status` | `succeeded`, `failed (<class> in <step>)` |
| `cancelled` | reserved — a v1 run does not end this way | — |
| `dry_run` | only `plan.md` (`--dry-run`, `dry_run: true`); since 0.8.0 additionally without `run.lock` — a live run has it before `plan.md` | `dry-run` |

Note: a run started by a framework older than 0.7.0 that is still running is
`interrupted` (it holds no lock).

### Run list

`GET /projects/<p>/runs?scenario=<s>&limit=<n>&before=<run_id>`:
`scenario` filters by the name in `run_id`; `limit` = at most `n` items
(a positive integer, otherwise 422; without it all). Results are ordered by the folder
name descending. `before` is an exclusive cursor by folder name; it must have the
shape of a `run_id`, otherwise 422. With `limit` the API returns `next_before` only when
older results exist; the value is the `run_id` of the last item of the page.
The limit is applied before reading the records. New item fields:

| Field | What it is |
|---|---|
| `state` | the machine state (above) |
| `fake` | `run_started.fake`; `null` without `events.jsonl` |
| `queue_position` | only for `queued`: the position as in `GET /runs/<id>` (waiting + running ahead of me, including me) |
| `scenario` | for `queued` from the queue, for a dry run from `run_id` |
| `started_at` | for a dry run the time from `run_id` (`YYYY-MM-DDTHH:MM:SS.000Z`) |
| `current_nn` | only for `running`: the `nn` of the currently running step of the main scenario (for a step called through `call` the number of the `call` step); `null` for records without `nn` |
| `steps_done` | only for `running`: the number of finished or skipped steps — counted like `steps_total` (without steps of called scenarios) |

`last_run` (`GET /projects` for an available project, `GET /projects/<p>`
for a scenario) = the first item of the list (`limit=1`) narrowed to
`{"run_id", "state", "started_at", "finished_at", "cost_usd"}`, `null` without runs —
it can also be a queued run or a dry run.

### Step details (since 0.7.0)

The `steps` items in `GET …/runs/<id>` additionally have:

| Field | What it is |
|---|---|
| `nn` | the step number in its scenario (for `call` a nested step has the number in the called scenario) — from `step_started`/`step_skipped.nn`, for runs before 0.7.0 from the file path |
| `dir` | the step folder in the run folder (`steps/02-tone/steps/01-check`); `null` for a skipped step and for a step without files in a run before 0.7.0 |
| `error` | `{class, message}` of the step's last error after which it was not retried; otherwise `null`. An error of a nested step (branch, `call`) is on that step, not on the parent |
| `continued` | `true` = failed with `on_error: continue` |
| `default_used` | `true` = the `default` was used as the output (a skipped step or `continued`) |
| `calls` | model and Jev calls: `[{attempt, alias, model, input_tokens, output_tokens, cost_usd, finish_reason, structured_output, duration_s}]` (for Jev `alias`, `finish_reason` and `structured_output` are `null`) |
| `turns`, `tool_calls` | only for `task`: the number of turns and of tools called |
| `answers` | only for `jev`: the answers of the last call |

### `GET /projects/<p>/runs/<id>/steps/<path>` (since 0.7.0)

`<path>` = `step` (for `call` `propose/copy` → `…/steps/propose/copy`).
The response = the `steps` item (above) and in addition:

- `events` — all events of the step from `events.jsonl` (`step` = path)
  in write order, unchanged;
- `output` — the contents of the step's `output.json`, `null` when there is none;
- `files` — the files of the step folder (relative to the run folder, for
  `…/files/`), without the folders of nested `call` steps.

An unknown step or run → 404.

### Run step tree (since 0.7.0)

At start the run stores a copy of the scenario being run and of all scenarios called
through `call` in `<run>/scenario/<name>.yaml`
([run-record.md](run-record.md)). `GET …/runs/<id>` returns:

| Field | What it is |
|---|---|
| `tree` | the step tree of the scenario being run, the same shape as `steps` in `GET …/scenarios/<s>` |
| `callees` | `{name: tree}` of the called scenarios from the snapshot; `{}` without a snapshot |
| `tree_source` | `snapshot` = from the snapshot; `current` = a run without a snapshot (before 0.7.0, a dry run, a run that did not start) — the tree comes from the current scenario file, which may have changed since the run (a nonexistent file → `[]`) |

### `config.yaml` and `mcp.yaml` errors

- `GET …/files/config.yaml` returns in `errors` all
  errors of the file (syntax, schema, variables), not only syntax; `line` where
  the loader knows it (YAML syntax, a duplicate key). Up to 0.17 the same held for
  `…/files/mcp.yaml`; since 0.18.0 that file is not served and its errors are the
  project-level `errors` of `GET /projects/<p>` (`file: "mcp.yaml"`, with `line` and `field`).
- The 422 from `GET /projects/<p>` carries `errors` (objects) next to `details` (texts).
- `…/runs`, `…/runs/<id>…` and `spend` need only `runs_dir` from `config.yaml`;
  when even that cannot be read, the default `./runs` applies.

### `GET /projects`

`{"projects": [...], "registry": "/home/…/.config/agencast/projects.yaml",
 "projects_root": "/home/…/workspace", "writable": true}`
— `registry` = the path to the registry file (even when it does not exist, also in
single-project mode). `projects_root` = the configured default path, otherwise
`~/workspace`. `writable` is `true` only in registry mode, when the process can
write the registry atomically; in single-project mode it is `false`. An unavailable
project has `reason` (`missing <root>/workflows/config.yaml`). Since 0.10.0
every project item additionally contains `counts: {scenarios, agents}`
(the number of files in the project folders) and `spend_today_usd` from the daily ledger
in UTC. The counts and the spend are loaded without validating the project.

## Batch, preview and additions from GUI findings, part 2 (since 0.8.0)

Following `docs/ui/api-findings.md` items 10–20. All additive; the existing
endpoints and their responses do not change.

### Batch: `POST …/scenarios/<s>/batch`

```json
{"etag": "9f2c…", "ops": [
  {"op": "rename_step", "address": ["steps", 0], "new_id": "propose"},
  {"op": "add_step", "after": ["steps", 0], "step": {"id": "new_step", "ask": {}}},
  {"op": "update_step", "address": ["steps", 1], "fields": {"ask": {"agent": "copy", "prompt": "…"}}}]}
```

All operations run one after another on **one** in-memory copy of the document;
the address of each operation applies to the state **after** the preceding ones (after deleting
`["steps", 1]` the former `["steps", 2]` is at `["steps", 1]`). Then one
validation of the result (the “must not add a new error” rule, as for a single
operation) and one atomic write — or nothing.

| Operation | Fields (besides `op`) | Like |
|---|---|---|
| `set_header` | `fields` | `PUT …/scenarios/<s>` |
| `add_step` | `step`, `after`? (without = the start of `steps`) | `POST …/steps` |
| `update_step` | `address`, `fields` | `PATCH …/steps/<address>` |
| `replace_step` | `address`, `step` | `PUT …/steps/<address>` (the whole step, supports `null`) |
| `move_step` | `address`, `to` | `POST …/steps/<address>/move` |
| `delete_step` | `address` | `DELETE …/steps/<address>` |
| `rename_step` | `address`, `new_id`, `rename_refs`? (default `true`) | a new `id`; with `rename_refs` it rewrites `steps.<old>.` → `steps.<new>.` in all expressions and templates of the scenario's steps — the whole `when` field, `switch.value` and `set` values, elsewhere only inside `{{ }}`. Comments and text outside `{{ }}` stay |
| `add_branch` | `address` (a `parallel`/`switch` step), `name`, `steps`? (default `[]`) | a new `parallel` branch or a new `switch` case (`cases`); an existing name → an operation error. An empty branch is filled by another `add_step` with `after` = the branch address |

| Code | Body |
|---|---|
| 200 | `{"etag", "errors"}` as for a single operation |
| 409 | the fingerprint does not match (nothing was written) |
| 422 operation | `{"error", "op": <index from 0>, "errors": [...]}` — the operation could not be performed (an unknown `op`, a missing/unknown field, an address that does not exist at that moment, a branch that already exists, …); messages start with `ops[<index>] <op>: ` |
| 422 result | `{"error", "errors": [...]}` without `op` — the operations passed, but the result added an error to the project |
| 404 | unknown project or scenario |

**An incomplete new step and an empty branch** (finding 13): validation does not change —
an empty `ask` or a branch without steps are still an error. A batch handles them
by inserting the step and filling in the fields (or adding the branch and populating it) in one batch;
`render` shows the work-in-progress state without writing.

### Preview: `POST …/scenarios/<s>/render`

The body `{"etag"?, "ops": [...]}` (operations as for `batch`, empty `ops` =
the file as it is). **Nothing is written.** `etag` is optional; when it is present
and does not match → 409.

```json
{"text": "version: 1\n…", "tree": [{"nn": 1, "address": ["steps", 0], "id": "propose", …}],
 "errors": [{"message": "…", "file": "scenarios/ig-post.yaml", "step": "new_step", "field": "ask"}]}
```

- `text` = the resulting YAML with comments preserved (the same as
  `batch` would write);
- `tree` = the step tree of the result, the shape of `steps` from `GET …/scenarios/<s>`
  (the addresses apply to the result);
- `errors` = **all** errors of the project with this text (like
  `POST …/validate`), including new ones — a work-in-progress state may be invalid, 200.

An operation error → 422 with `op` as for `batch`. This is how the GUI validates the Form mode
continuously and converts Form ↔ YAML even with unsaved changes.

Since 0.10.0 `render` also accepts `{"text": "…"}` instead of `ops` and returns
`{"tree": [...], "errors": [...]}` for the scenario being edited; the text is
not written. `text` and `ops` in one body → 422. `POST …/validate` adds the same tree
shape for a scenario text.

### The whole step: `PUT …/scenarios/<s>/steps/<address>`

The body `{"etag", "step": {…}}` — the step is replaced whole (comments inside the
step disappear; its header above it and the header of the next step stay), `null` is written as `null` (`default: { file: null }`).
Responses as for the other operations.

### Lightweight file change detection

- `HEAD /projects/<p>/files/<path>` → 200 without a body with the header
  `ETag: "<fingerprint>"` (the fingerprint in quotes per RFC 9110 §8.8.3, the value
  = `etag` from `GET …/files/<path>`); an unknown file or a path outside the
  allowed ones → 404, without a token 401. With `--cors` responses carry
  `Access-Control-Expose-Headers: ETag` (otherwise the browser does not let
  the script see it) and the preflight allows `HEAD` (sources: RFC 9110 §8.8.3,
  https://www.rfc-editor.org/rfc/rfc9110#section-8.8.3; MDN
  *Access-Control-Expose-Headers*,
  https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Expose-Headers;
  verified 2026-09-26).
- `GET /projects/<p>/files/<path>?etag_only=1` → `{"etag"}`.

The file is not read by the loader or validated — only the sha256 of its bytes. There is no
push of changes (SSE).

### `errors` in `GET …/files/<path>`

For a scenario, agent and skill = the `validate` errors of that file, **the same**
as `errors` of the item in `GET /projects/<p>` (previously only loader
errors). When the file cannot be read, the loader errors remain (with
`line`). With an invalid `config.yaml` (the project cannot be validated) the
`errors` are those of `config.yaml`. `config.yaml` unchanged
(since 0.7.0 all errors of the file).

### State of a fresh run

From the `202` on `POST /projects/<p>/runs` to the end of the run, both
`GET …/runs/<id>` and the list return only `queued` → `running` → the result:
a `serve` queue entry (`<runs>/_queue/<run_id>.json`, removed only after the
callback) overrides `interrupted` and `dry_run` with `queued` (with
`queue_position`) until the run holds the lock (`running`) or finishes.
`dry_run` = a folder with `plan.md` without `events.jsonl` **and without `run.lock`**
(a dry run has no lock, a live run creates it before `plan.md` —
[run-record.md](run-record.md)); the record format does not change. A live run
that crashed between `plan.md` and the first event is `interrupted`. The queue
entry also stays after a `serve` crash — until the restart (when the run is reported as
interrupted) such a run is `queued`.

### `POST …/scenarios` and `POST …/agents`

An optional `description` (text, written in quotes), for an agent
`model` = an alias from `config.yaml` (any other → 422, the default is the first alias).
Without them the template is as before (`TODO`).

### Alias usage: `links.scenario_model` and `models_used`

`links.scenario_model` = sorted [scenario, alias] pairs from the `image.model`
of steps (also in branches). `models_used` = `{alias: [files that use it]}` —
`agents/<a>.md` (the `model` field) and `scenarios/<s>.yaml`
(an `image` step), paths as in `files/` and in `errors[].file`. The keys = all
aliases from `config.yaml` (`[]` = unused, can be deleted) plus aliases that are
referenced but not in the config (that is also a `validate` error).

```json
"models_used": {"smart": ["agents/copywriter.md"], "gemini-image": ["scenarios/ig-post.yaml"], "fast": []}
```

### `PUT …/config` (since 0.8.0)

Allowed fields: `models`, `limits`, `storage`, `webhook`, `callback`,
`runs_dir`, `openrouter.api_key_env` and `openrouter.jev_model`. Still
forbidden (422):

- `version` — the format version, changed only together with a new format (DESIGN §5.6);
- `openrouter.base_url` — where the API key goes; redirecting it from the GUI would
  send the key elsewhere (config.md allows it only for conformance tests).
  It is changed in YAML mode (`PUT …/files/config.yaml`), deliberately.

`runs_dir` applies to new runs and to reading runs immediately; a running `serve` however has
its `_queue/` queue in the folder from the project start — after changing `runs_dir`
restart `serve`, otherwise the GUI will not see waiting runs from the old folder.

## Additions from GUI findings (since 0.10.0)

- A restored running record keeps the original `run_started`; it adds
  `run_finished.status: failed` with an `internal` error, the last started
  step and the message `run interrupted by server restart`. The API `state` stays
  `interrupted`; a step without `step_finished` has `status: interrupted`.
- `config.yaml` schema errors carry `line` by the YAML key in the response
  of `GET …/files/config.yaml` and `GET /projects/<p>`.
- `GET /projects` returns in each item `counts: {scenarios, agents}` and
  `spend_today_usd`; the counts are file listings and the spend is the daily ledger,
  without full validation.
- `GET …/runs` accepts `before=<run_id>` and returns `next_before` when there is
  another page; `last_run` adds `started_at`.
- Errors of a batch operation carry `step` (the address before the operation, or the id
  of the inserted step for `add_step`) and `field` when known.
- For `POST /projects/<p>/runs`, `callback.secret_env` is required only with
  `callback_url`. `webhook.token_env` is read only in single-project
  mode; registry mode verifies the server token.

The `POST /runs` contract, the callback and the v1 formats do not change.

## MCP servers are the owner's (since 0.18.0)

`workflows/mcp.yaml` decides which programs the framework starts on the host and which
remote servers get a token from its environment. The API token is not the owner
(DESIGN §5.2, [config.md](config.md#mcpyaml--registry-of-mcp-servers)):

- **No route creates, replaces, deletes or returns `mcp.yaml`.** `GET`, `HEAD` and
  `PUT …/files/mcp.yaml` and `POST …/validate` with `path: "mcp.yaml"` → **404**
  (`mcp.yaml: only the project owner reads and edits this file, on disk — not through the
  API`). The GUI shows the servers from `mcp_servers` in `GET /projects/<p>` (no `command`,
  `args`, `url`, `env`, `bearer_token_env`) and the file's errors from the project-level
  `errors`, which name an argument by its place (`servers.<name>.args[1]`) and never quote
  it. The one write that remains: `POST …/agents/<a>/rename` replaces the old agent
  name with the new one in the `agents` lists, so that the renamed agent keeps its servers;
  the operation verifies that nothing else in the file changes, otherwise it leaves the file
  alone (and the rename fails validation with 422). A `mcp.yaml` that is a link (the
  owner's file kept elsewhere) is left alone too: the owner renames the agent there. A
  file the rename would rewrite (`mcp.yaml`, a scenario that refers to the agent) that
  changed on disk while the rename was being validated → **409** and nothing is written:
  the owner's edit is never overwritten from the older text; the same request can be sent
  again.
- **A project registered over HTTP is not trusted.** `POST /projects` and
  `POST /projects/new` write `trusted: false` into the registry entry
  ([projects.md](projects.md#trust-projects-registered-through-the-api)) and return it in the
  201 body. `GET /projects` (every item) and `GET /projects/<p>` carry `trusted`
  (read-only). No route sets the flag — not `PUT …/config`, not a `trusted` field in a body
  (an unknown field → 422) — and `DELETE /projects/<p>` followed by `POST /projects` yields
  `trusted: false` again. Only `agencast projects trust <p>` in a terminal clears it.
- **An untrusted project starts no MCP server.** A scenario whose `task` steps would use one
  fails validation with one `config` error, on every path:
  `POST …/runs` (also `dry_run: true`, also with `serve --fake`) → **422** with the message in
  `details`; `GET /projects/<p>` and `GET …/scenarios/<s>` list it in the scenario's `errors`;
  `POST …/validate` and `render` return it too. A run that was queued while the project was
  trusted and starts after it stopped being so (removed and registered again, or removed —
  `serve` in registry mode runs registered projects only) does not start: its record and
  callback carry the `config` error. Scenarios without such a step are unaffected.

  ```json
  {"error": "scenario 'catalog' or its inputs failed validation",
   "details": ["catalog.yaml: MCP servers (filesystem) are disabled — project 'from-gui' (/srv/projects/from-gui) was registered through the API and is not trusted to run them (trusted: false in the project registry). The project owner allows them in a terminal: agencast projects trust from-gui"]}
  ```

- `callback_url` (`POST /runs`, `POST …/runs`) must match `https://…` or
  `http://127.0.0.1[:port]/…` (tests); `http://127.0.0.1:1@example.com/…` — userinfo, the
  host is `example.com` — is a 422 on acceptance, as it already was when the run started.

### Stopping `serve`

On SIGTERM (`systemctl stop`) or Ctrl-C — from the moment the workers start, also while
the server is still starting — the server stops accepting requests and interrupts
the runs in flight the way a signal interrupts `agencast run` (scenario.md, the `task` step):
each run is cancelled once, stops its MCP servers, also those still starting (stdin closed, then SIGTERM and SIGKILL
for the process tree; the server waits up to 15 s for that) and keeps its queue entry
without `run_finished`. Further signals are ignored meanwhile. The next start reports such a
run as before — `run interrupted by server restart`, with the callback
([run-record.md](run-record.md)); requests that had not started — also one that was
waiting for a `max_parallel_runs` slot — stay queued and run then. A run that had already
finished and was only sending its callback keeps its record and its queue entry too
(`callback_failed`); the next start sends that callback — the run's own result — again.
A dry run in flight answers **503** `{"error": "server is stopping"}`.
