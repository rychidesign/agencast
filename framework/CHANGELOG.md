# Framework changelog

Semver per DESIGN §5.9 item 5: a fix = patch, an addition = minor, a new
format version = major. Format changes are in `docs/spec/CHANGELOG.md`.

Up to 0.2.5 the package and the command were called `maw`; older entries here keep that name.

## Unreleased (0.19.0, MCP server)

- `agencast mcp` — AgenCast as an MCP server (spec/mcp-server.md): 17 tools to list projects and scenarios, read
  workflow files and the bundled guide, validate drafts, plan (`dry_run`), run (`fake_run` free, `run_scenario`
  live — two tools so that a client's permission for the free one never covers the paid one), wait for and read
  runs (`run_status`, `wait_run` at most 50 s, `list_runs`, `get_run_file` with small images inline) and, with
  `--allow edit`, write scenarios, agents and skills (`etag`-guarded, refused when they add a validation error).
  The owner fixes the level at start (`--allow read|run|edit`, default `run`), `--fake [SCRIPT]` makes a server
  that cannot spend money, `--input-dir DIR` allows image inputs from a directory (read once into a private
  copy; `list_projects` also returns `server.host` and `server.user`, the scp target a caller on another machine
  copies images to — the recipe is in the `agencast-run` skill). Registry mode serves every registered project;
  `--project` one. The server never touches `config.yaml`,
  `mcp.yaml`, `commands.yaml`, `.env` or the registry, loads from a project's `.env` only the variables the
  project names (never the current directory's `.env`), and masks every result, error and log line with the
  secrets of the addressed project.
- Run card (MCP Apps, `io.modelcontextprotocol/ui`): in a client that renders MCP Apps (Claude Desktop), `fake_run`,
  `run_scenario` and `run_status` also show a card in the chat that follows the run by itself — state, steps,
  current step, elapsed time, cost, warnings, error, outputs with inline images — by calling `run_status` and
  `get_run_file` through the host; one bundled HTML file (`agencast/mcp_app/run-card.html`, resource
  `ui://agencast/run-card.html`) in the AgenCast GUI design — a segmented animated progress bar, step type icons,
  motion only under `prefers-reduced-motion: no-preference` — no external URL, no `&` before a letter (hosts that
  embed through an HTML attribute decode legacy entities), no change to any tool result (spec/mcp-server.md
  “Run card”). Open WebUI shows it through the community MCP App Bridge tool.
- Transports: stdio (the client starts the server) and `--http` — streamable HTTP at `http://HOST:PORT/mcp`
  (`--host`, default 127.0.0.1; `--port`, default 8765; `--allow-host` for the names clients use, e.g. behind
  `tailscale serve`), stateless, POST only, with a required bearer token from `AGENCAST_MCP_TOKEN` (at least 32
  characters, removed from the environment at start) and Host/Origin checks. Setup for Claude Code, Claude Desktop
  (also over ssh), Open WebUI and a systemd user service (`KillMode=process`): README “Use from an MCP client”.
- Runs started through MCP outlive the client and the server: each executes in a detached worker,
  `agencast run <scenario> --mcp-job <run_id>` (a hidden option; the job on stdin, never on a command line; a
  session of its own; the server's environment as at start plus only its own project's named variables). At most
  4 unfinished runs and dry runs started through MCP per project, shared by every MCP server, as lock files
  `<runs>/_mcp-slots/<n>.lock` that hold the run id — so every server, also one started after a restart, reports
  a run `queued` before its directory exists. A stop or restart of the server stops no run (under systemd only
  with `KillMode=process`); SIGTERM / SIGINT end the server killed by the signal, a clean stop for systemd.
- Fix: `agencast serve` refuses a scenario that is a link out of the project's own `workflows/scenarios/` (it
  loaded the other tree's `config.yaml`, `.env` and `mcp.yaml` under the addressed project's trust): the request
  is answered like an unknown scenario (422), a queued one fails with `config`.
- Fix: a run takes `run.lock` right after creating its directory, before input images are copied — a run with
  input images no longer reads `interrupted` (in `agencast runs list`, the API and the GUI) while they are copied,
  as run-record.md already said.
- Fix: a run's `scenario/<name>.yaml` snapshot is the text the run loaded, not the file as it is when the run
  starts (an edit while a run waited for a slot ended up in its record).
- The YAML reader of workflow files refuses a document whose aliases expand to more than 100,000 values
  (`cannot read YAML — aliases expand to too many values`), for every reader: `validate`, `run`, `serve`, the GUI.
- Fix: an unquoted `{{ … }}` value inside a block mapping (`v: {{ x }}`, a mapping as a key) is the usual
  `cannot read YAML … must be quoted` error with the file and line (`found unhashable key`), not a `TypeError`
  traceback that broke `validate` and every project listing.
- Fix: an agent, skill or called scenario that is a link out of the project's own `workflows/` (a called
  scenario: out of its `scenarios/`) does not exist for `validate` and a run — as a linked top-level scenario
  (`validate.own_file`); the copy a draft is validated in leaves such links out.
- `agencast docs show` and the MCP server's `get_guide` share one reader (`resources.read_doc`, `docs_index`) that
  serves, and suggests on a miss, only what the wheel bundles (`getting-started.md`, `spec/`, `tutorials/`) — in a
  clone too, whose other `docs/` files `docs show` read before; a link loop (a file input, a file of the files API)
  or a name too long for the file system is a missing file instead of an exception; a run file path with a NUL byte
  or a name too long answers 404 in `serve`. The files API serves no file of a `workflows/` that is a link to
  another directory (404).
- API additions (api.py): `project_env(root)` (load a project's named variables from its `.env`, return the values
  to mask), `scenario_file(root, name)` (the real path of a scenario that lies in the project, otherwise
  `NotFound`), `added_errors`, `runs_dir`, `run_output_files`; `load(…, dotenv=False)`; `record.Mask` (masking
  without a run directory, `(NAME, value)` pairs); `task.SlotStore.held_ids()`; `loader.load_dotenv(path, only)`
  returns what it read.

## 0.18.0 — 2026-10-02 (images as inputs, MCP hardening)

- Images as inputs and as a variable (0.18.0, scenario.md Type `file`): input types `file` and `files` take a path
  from the CLI (`-i photo=a.jpg`, `-i 'refs=["a.png","b.webp"]'`) or from Python (`Path`), are copied into
  `runs/<id>/inputs/` and carry `width`, `height` and `format` readable with a dot; `images:` on `ask`/`task` sends
  them to the model (`Image 1 (inputs/photo.png, W×H)` labels — the path `{{ inputs.photo }}` renders, so a prompt
  can name an image; the `image` step puts the same labels in a legend at the top of the prompt; `<file: …>` in the record); a `files` output uploads every file;
  PNG, JPEG (EXIF orientation), WebP, GIF and AVIF headers are read without Pillow; `validate` checks
  `input_modalities` of the agent's model.
- `POST /projects/<p>/uploads` (single project: `POST /uploads`): raw image bytes → `{"upload_id"}`, which a run
  request (also `dry_run`) passes as a `file`/`files` input; stored in `<runs_dir>/_uploads/`, an upload not
  used for 24 h expires. The token is checked before the body is read; the body limit is 10 MB.
- GUI: `file`/`files` inputs in the run form are a file picker (PNG, JPEG, WebP, GIF, AVIF; uploaded on pick,
  previews with size and format, removable); the step panel has an `images` field for ask, task and image steps;
  run files show GIF and AVIF; files served from a run carry `X-Content-Type-Options: nosniff`.
- `image` step with reference images (`images:`, Images API `input_references`; aliases with `api: images` only,
  `validate` checks `input_references` in `GET /images/models`): edit one photo or compose from several.
  `aspect_ratio: auto` / no ratio with references = the first reference's ratio snapped to a supported value
  (catalog kept on `Project`, also for called scenarios; offline a built-in list; a model whose catalog lists no
  aspect_ratio gets none), a mismatch is then a warning. The showcase and tutorial configs gain the alias
  `gemini-image-api`.
- English is the primary language for messages, the CLI and documentation. The GUI defaults to English, with an optional Czech translation.
- Example projects, their files and identifiers now use English names. New projects create the `writer` agent and `demo` scenario, with `write`/`result` steps and the `topic` input.
- Model aliases are now `smart`/`fast` (and `cheap` where used).
- Run `status` text is now English; clients should read the machine-readable `state` field. The restart message is now `run interrupted by server restart`; runs interrupted by a restart under agencast ≤ 0.17 show as `failed` instead of `interrupted`.
- Numbers use a decimal point, dates use ISO `YYYY-MM-DD`, and times use `HH:MM`.
- Old Czech GUI URLs no longer resolve.
- `workflows/mcp.yaml` is the project owner's file (0.18.0, api.md “MCP servers are the owner's”): the HTTP API no
  longer returns or writes it — `GET`, `HEAD` and `PUT …/files/mcp.yaml` and `POST …/validate` with `path: mcp.yaml`
  answer 404. **Changed for existing users: the GUI can no longer edit `mcp.yaml`; edit it on disk.** Until now a
  holder of the API token could write the file, and a run — a dry run was enough — started the `command` in it.
  `GET /projects/<p>` still lists the servers (without `command`, `args`, `url`, `env`, `bearer_token_env`), now with
  `description`, `transport` and `env_missing` (names of the server's unset variables), and carries the file's errors
  in the project-level `errors`. The one write left is an agent rename: it changes only the agent's name in the
  `agents` lists, keeps the file's permission bits, answers 409 when the file changed on disk meanwhile and leaves a
  `mcp.yaml` that is a symlink alone.
- Trust (projects.md “Trust”): a project added or created over HTTP (`POST /projects`, `POST /projects/new`, the GUI)
  is written to the registry with `trusted: false` and uses no MCP server, local or remote — `validate`, `run`,
  `--dry-run`, `--fake` and the same requests over HTTP end with one `config` error — until its owner runs the new
  `agencast projects trust <name>` in a terminal (it shows the project root and every server's command line or remote
  host and asks; outside a terminal it needs `--yes`). **Changed for existing users: projects added or created
  through the API need `agencast projects trust` before their scenarios can use MCP servers.** Entries already in the
  registry and everything registered from a terminal stay trusted; scenarios without MCP servers are unaffected.
  `agencast projects list` marks untrusted entries; the API carries `trusted` (read-only) in `GET /projects`,
  `GET /projects/<p>` and the 201 bodies, and no route sets it.
- **Changed: `agencast run --dry-run` no longer adds the project to the registry**; a real run still does, right
  after validation.
- `agencast run` (also `--dry-run`) handles SIGINT and SIGTERM: the first signal cancels the run once and stops its
  MCP servers with the full kill escalation — also one still in its handshake — further signals are ignored
  meanwhile, and the command exits with 130 / 143 and two stderr lines instead of a traceback: one at the signal
  (`SIGTERM: stopping the run and its MCP servers…`), one when it has stopped. The record is that of
  an interrupted run; skipped steps say `cancelled — the run was interrupted (SIGTERM)`; a signal during the callback
  retries leaves a finished run with `callback_failed`.
- `agencast serve` stopped by SIGTERM or Ctrl-C interrupts its runs in flight the same way (their MCP servers used
  to be orphaned): the queue entries stay, the next start reports each run with its callback, and sends again the
  callback of a run that had finished and was cut short while sending it. Waiting requests stay queued; a dry run in
  flight answers 503.
- MCP server start: a failure names its cause — the HTTP status for both remote transports (401/403 with a hint to
  check `bearer_token_env`), the last stderr lines of a local server, a stdout line that is not JSON-RPC instead of a
  handshake timeout. Network errors (also a connection reset or closed without an answer) and HTTP 408, 429 and 5xx
  are `transient` and retried according to the step's `retry` (2 s, 4 s, 8 s… or the server's `Retry-After`),
  everything else is `config`; every failed attempt has an `error` event and its own `mcp_server` `failed` event, and
  is not cached for the run. The SSE handshake limit is `timeouts.handshake` (was + 5 s). A server still starting
  when the run ends (interrupt, step or run `timeout`) is stopped at once and recorded as `stopped`; one that dropped
  the connection during a tool call is recorded as `failed`. A remote server's session is ended within 5 s as a
  whole, and a failed start reaches the step before that request, not after it.
- A tool call that did not return (timeout, dropped connection, cancelled step) is in the record: `tool_call` event
  and `calls/NN.tool.json` with the arguments, `is_error: true`, `result: null` and the new field `error`. A tool
  answer that is no tool result, or an image that is not base64, fails the step as `config` instead of `internal`.
- `task`: once the step has called an MCP tool, the retry after a `schema` error only allows the answer
  (`tool_choice`, tool definitions kept); tool calls in such a retry are not executed and count as another `schema`
  error.
- `parallel`: a cancellation that arrives while a failed branch is still cancelling the others is no longer lost — a
  signal (the run used to go on to `run_finished`), or a failed branch of an outer `parallel` (a branch used to go on
  past a `call` step with `on_error: continue`).
- Secrets in the run record: `mcp/<server>.stderr.log` is written with secret values masked when the server stops
  (never raw in the run directory; a later start in the same run appends; a killed run has no log). Masking replaces
  longer values first (a connection URL before its user name), the JSON-escaped forms of a value once or twice —
  also as PHP (`\/`), Go (`\u0026`, `\u003c`, `\u003e`, `\u2028`, `\u2029`) and .NET's System.Text.Json (uppercase
  hex, also for `"`, `&`, `'`, `+`, `<`, `>` and `` ` ``: `\u002B`, `\u0022`, `\u00E9`) write them — and the
  HTML-escaped ones, a JSON number whose digits hold a value, and the bytes of a saved file (a tool's image block;
  `image_saved.bytes` and the `<file: …, N B>` note give the size of the file as it is stored, after masking);
  JSON files, `events.jsonl` and the callback are masked per string, so they stay valid JSON. Error messages quote a remote server's URL without
  userinfo and query and the MCP library's errors without the server's input values; the SDK's log no longer prints
  tracebacks that quote server output. `agencast projects trust` and `projects list` show control characters escaped.
- `mcp.yaml` and `config.yaml` validation: schema errors name the field and the line, and one broken server entry
  no longer makes `validate` report every server as “not in mcp.yaml”; a value pasted where a variable name belongs
  (`*_env`, `env`) is never printed; braces in `args` are named by place (`servers.<name>.args[1]`), not quoted.
  Plain `http://` in a server `url` and in `openrouter.base_url` is accepted only for `127.0.0.1`/`localhost` with an
  optional port — `http://127.0.0.1:1@example.com/` (userinfo) is rejected, also as a `callback_url` (422 when the
  run is accepted). **Changed for existing files: a plain `http://` URL that goes on after the host with anything
  but a numeric port and `/` — the userinfo form above, `http://localhost:abc`, `http://localhost:8080?x=1` — was
  valid until now and fails validation (`value does not match pattern …`);** `http://localhost` without a `/` is
  accepted now. An unreadable or non-UTF-8 `mcp.yaml`, `config.yaml` or `--fake` script and a missing `--fake`
  file are `config` errors (exit code 2), not tracebacks.
- Dry run: `plan.md` marks allowed tools a server does not offer (`(NOT OFFERED by the server)`, `allowed but NOT
  OFFERED: …`) and lists a server that does not start with the reason (`missing environment variable X (MCP server s
  in mcp.yaml)`). The help of `--dry-run` says that MCP servers are started to list their tools, the help of `--fake`
  that only the model is faked — MCP servers and callbacks stay real.
- `callback_failed` in `GET /runs/<run_id>` and the callback note in `agencast runs` follow the callback events:
  only a delivered attempt clears it, also one sent after a `serve` restart.
- Editing API: the blank lines and comments directly above a step are its header — deleting a step removes it and
  keeps the next step's, moving carries it along (re-indented), a new step goes above the next step's header,
  replacing keeps both; what follows a block or a step list stays in place when a key or a step is added or removed
  at its end; a comment never becomes a part of a `|` or `>` text. Writes keep the permission bits of the replaced
  file and follow no symlink — not at the name of the temporary file, not through a linked directory, and not when
  `POST …/scenarios`, `POST …/agents` or `POST /projects/new` create a file from a template; `files/` follows a link
  only to a file it serves under its own name. In an untrusted project a scenario that already has an error can
  still be given fewer MCP servers or have its other error fixed.
- A scenario, agent or skill file that cannot be read — a link that leads nowhere, a directory under that name, no
  permission — no longer fails `GET /projects/<p>` and every edit of the project (500, also before this release):
  the entry is listed with its read error and `etag: ""`.
- GUI: MCP servers in Config are read-only cards (description, transport, “not restricted by the owner”, variables
  missing on the server, the file's errors); the `mcp.yaml` text block in YAML mode is gone. An untrusted project
  shows the `agencast projects trust <name>` command in Config and in the run form of a scenario that uses an MCP
  server. Agent editor: a server whose tools the owner does not restrict has a field for tool names, and ticking a
  server no longer writes an empty `tools.<server>` list. Step panel (`task`): servers and tools are one checkbox
  tree built from the agent's permissions (the raw JSON `tools` field is gone; the YAML is unchanged). Run viewer,
  Tools tab: a call that did not return shows its error, and each server called links to its stderr log. The dry-run
  texts say that MCP servers are started; the step number on a selected card is readable again.
- Docs: agent.md names `agencast run <scenario> --dry-run` (there is no `validate --dry-run`); scenario.md warns
  that tool calls scripted in a `--fake` run are real.

## 0.17.0 — 2026-09-28

- The distribution includes the license text and the README as the package's long description; a test checks that the licenses match.
- The spec check covers both projects in `examples/`; CI checks Python, the GUI, E2E and the installed wheel.
- The guides clarify `--fake`, MCP/callbacks, the supported environment and the GUI port; run logs are in the archive.
- English quick start, community guidelines without commitments and the current state of the spec v1 decisions.

- The package includes the skills, the Czech guide, the specification, the tutorials and both examples.
- `skills list|path|install` exposes and installs the skills; `docs [show <path>]` prints the documentation.
- `new project --example showcase|tutorial` creates a ready-made project with fixtures in `fake/`.
- Fixtures are part of the examples; a relative `--fake` also looks in the project root.

## 0.16.4 — 2026-09-28 (preparing the public release)

- `serve` reads the default address and port from `AGENCAST_HOST` and `AGENCAST_PORT`; an invalid port ends with a `config` error.
- The package metadata drops the old repository name and points to the public AgenCast repository.
- The framework README describes the environment variables, deployment via systemd and safely restricting access to the GUI.

## 0.16.3 — 2026-09-28 (GUI fixes in the editor)

- The desktop panel scrolls with the page without its own scroll and starts at the selected card; the mobile sheet stays.
- Menus show shortcuts on the right and destructive items in red.
- Floating menus and the type picker stay within the viewport, also inside cards and sheets.
- Short connection drops are retried silently; after wake-up, data and conflicts are checked immediately.
- Step connectors have free space around the + button, input and alias boxes have a lighter background, fields stay dark and checkboxes and radios have a legible custom look.
- Scrollbars of sheets and long lists are hidden; code blocks have a thin scrollbar on hover or focus.
- The selection ring of the selected HEADER is fully visible under the sticky page header.
- The duplicate trash can next to the step card is gone; deleting stays in the ⋯ menu, the panel and the Delete key.

## 0.16.2 — 2026-09-28 (menus, sheets and mobile navigation)

- Context menus and popovers without a border, with a lighter fill and a soft purple shadow.
- Fix for the clipped editor header menu on a phone: menus stay within the viewport.
- Panels up to 1279 px and modals on a phone as bottom sheets with rounded top corners, a shadow and a visible page edge.
- Mobile and tablet navigation in a menu above the floating FAB button instead of the top ☰ and drawer.

## 0.16.1 — 2026-09-28 (GUI faithful to the V3 design)

GUI only; API, CLI, file formats, routes and keyboard shortcuts unchanged. Dimensions are measured from the `.pen`
(HTML/PNG exports); where they differed from the first estimate in `docs/ui/redesign-fidelity.md`, the `.pen` rules.

- Fidelity: shared app background gradient; page H1 28 px regular, editor title mono 27, run detail title
  mono 26; buttons and icon buttons 44 px (radius 10), fields 44 px (radius 6), danger button
  in a solid color; active surface `surface-active` `#253B50` (sidebar, selected card, list item).
- Fidelity: sidebar 232 px (brand 25/22 px, “← Projects” with a divider, items 44 px), spend at the bottom with a bar.
- Fidelity: Projects — registry path under the header, icon “Reload”, project card r14 p22 with gaps
  20, ⋯ without a fill in the top row (an unavailable project has a chip there), count chips mono 11, spend “today 1.20 USD”.
- Fidelity: Scenarios — card r14 p24 h 292, type icons 18 px without circles and arrows, name 18, meta mono 11,
  run chip and “Open ↗”.
- Fidelity: Runs — filters in an r14 card with an outline (search, status, scenario at 210 px each), header mono 10, rows
  72 px r8, chip “N running · M queued”; costs always with four decimal places (“0.0000 USD”).
- Fidelity: editor — Form | YAML switch as 44 px segments, SaveNote as a status chip, header card as a
  rectangle r14 with a 21 px title, step cards p16 (type mono 11, title 15, detail mono 12, a 40 circle in the
  type color), selection by surface only, connector 44 px with (+) 44 px, containers r14 with a header 15 / mono 10, r8 branches
  side by side; column up to 676 px, panel 440, gap 28.
- Fidelity: panels — header with a line (icon, eyebrow mono 10, title 18, close 44), body p20, accordion with an
  arrow on the left; run panel with r8 p14 mode cards, limits 12 px; run step panel 520 px.
- Fidelity: run detail — inputs as an r8 p14 card, tabs 13 px, step cards with “12.4 s · 0.0210 USD” on the third
  line and the status on the right; queue with order and a 380 px empty state; dry run with the plan in a card; Files with a
  300 px tree and a Markdown preview (Preview | Code).
- Fidelity: one `CodeBlock` for outputs, prompts, responses, files and blocks in Markdown (header 18/13 with a chip,
  27 px rows, Copy with an outline); YAML editor with 27 px rows; conflict bar with a left stripe and “Reload
  from disk” as a danger action; modal with a header (title 22, close) and a footer Cancel + action.
- Fidelity: Agents and Skills — 240 px list (items r14 p16, icon 22), editor in an r16 card with 18 px fields,
  “Description” and “Model” labels, skills and MCP as rows with 18 px checkboxes, a Markdown preview for a skill.
- Fidelity: Config in an r16 card, sections in two columns, aliases as nested r10 cards.
- Fixed: line numbers in the YAML editor drifted from the text lines (`text-xs` overrode the line height);
  the pulsing text of the “running” chip fell below the 4.5:1 contrast (only the icon pulses); a skeleton inside a card was
  invisible; the run filter selects stretched across the whole width.
- Fields: at rest without a border, only the `nested` fill (design `V3 / TextInput`); focus ring 2 `accent` without an offset,
  invalid ring 2 `error`. A field with variables is a single box with `{}` inside (no fill); a multiline template
  and JSON have a toolbar (label, “template” / “JSON”, `{}`), an editor p16 and a footer with a status (“Valid JSON”,
  “Unclosed variable”) and the hint “Ctrl + Space for the menu” (the shortcut opens the variables menu).
- Mobile: up to 1023 px a 56 px bar (brand, project, ☰) with a full-height navigation drawer (Esc, click outside,
  48 px items, spend at the bottom) instead of overflowing tabs; header H1 24, only primary actions + ⋯, the title is
  never clipped; content p16 (tablet p24), cards in one column without a fixed height.
- Mobile: the step, header, run and run step panel is a full-screen sheet up to 1279 px (`role="dialog"`,
  focus trap, Esc, focus returns to the card after closing), never over the column or the header; step card 80 px without a
  number, connector 32 px with a 44 px (+) touch target.
- Mobile: runs as two-line cards without column headers; run detail tabs with horizontal scrolling;
  the agent and skill list below 1100 px as horizontal chips; Config and the agent editor with smaller card padding.
- Fixed: the daily spend everywhere with two decimals (“today 0.00 USD”, sidebar and run panel), run and step costs with
  four; Esc in the ⋯ menu closes only the menu, not the panel below it.
- Accessibility: “+ Add …” in panels has an icon and an accessible name without the “+” (“Add question”).

## 0.16.0 — 2026-09-28 (GUI per the V3 design: sidebar, unified headers, tokens)

GUI only; API, CLI, file formats, routes and keyboard shortcuts unchanged.

- QA (wave D): muted cards (not reached, skipped, unavailable project) have a dashed outline
  instead of transparency (contrast ≥ 4.5:1, axe without serious findings); the card's ⋯ menu lies above other
  cards and the header menu above the panel; the scenario card has the status at the bottom and a 3-line description; the editor's
  conflict bar is in the sticky header; a nonexistent project, scenario and run without extra controls;
  the dialog keeps focus even after a rejected delete; Tab closes ⋯; a server outage is reported by SaveNote in Czech;
  dark native selects (`color-scheme: dark`), a hand cursor on clickable elements, visible focus
  on (+); “Reload” on Projects in ⋯; duplicate project errors only once.
- Tokens: V3 colors, fonts and radii in `ui/src/index.css`; Inter Variable and
  JetBrains Mono are bundled locally (no CDN). No `zinc-*` classes or hard-coded
  colors remain in `ui/src` (exception: the white background of the report iframe).
  `fg-muted` is `#8497B0` so that it has a contrast ≥ 4.5:1 even on `surface-hover`.
- Shell: left sidebar (brand, “← Projects”, project name, navigation
  Scenarios · Agents · Runs · Skills · Config, today's spend with a bar at the bottom);
  below 1024 px a top bar. A server outage is reported at the bottom of the sidebar.
- Headers: every page has one header (`PageHeader`): title, description,
  at most two buttons and a ⋯ menu with the other actions (dangerous ones in red and
  last); the Form | YAML / Markdown switch and the save state are in its
  second row. Project sections carry “+ New scenario”, “+ New agent”,
  “+ New skill” and Save in it; “Reload” is in ⋯. Config has the project path
  as its description. A nonexistent address has the same header.
- Projects and project: the project card without the “available” label, adding a project
  is a button in the header (a dashed card only for an empty list); the project
  header shows no path, limits or spend.
- Cards: steps, connectors, the type menu and scenario cards in V3 tokens; the scenario
  card shows the name, description, “N steps · agents” and a single time in the last
  run chip.
- Panels: the step, header, run and run step panels in V3 tokens
  (eyebrow “STEP n · type”, step type as the first field, run mode as a card).
  In the scenario editor the panel sits next to the card column from 1280 px, a narrower screen
  shows it as a sheet at the bottom with a close cross.
- Runs: a list without the run_id column and without the spend row, the status is not
  repeated in the note; run detail with “← Runs”, inputs on one line and “Run finished”
  for the screen reader only.
- Forms: the agent and skill editor and Config have a single Save; sections without
  cards and technical labels; a model alias has the meta “used by …” /
  “not used” and wraps on a narrow screen. Elements (buttons, fields,
  menus, modals, editors) in V3 tokens.

## 0.15.1 — 2026-09-27 (the registry tolerates an unavailable root; validate without writing to the registry)

- `GET /projects` no longer crashes (500) when a registered root has no
  `workflows/`; the entry is just `available: false` with a reason, as when
  `config.yaml` is missing. The GUI offers to remove it.
- `agencast validate` no longer adds the project to the registry, only a successful
  `run` does. Validation from project copies (tests, workers' worktrees) thus
  leaves no foreign entries in the registry.

## 0.15.0 — 2026-09-27 (renaming a scenario and an agent)

- The public API, the HTTP API, the CLI and the GUI can rename a scenario or an agent and
  rewrite their references. Runs keep the name valid at the time they started.

## 0.14.0 — 2026-09-27 (image parameters as templates)

- `image`: templates for aspect ratio, quality and resolution, checking the substituted
  values and default inputs; the step's quality overrides the alias.
- The GUI offers variables for all three parameters; the chat API records ignored
  parameters as a warning. Callable example `image.yaml`.

## 0.12.0 — 2026-09-27 (the image step via the OpenRouter Images API)

- Model aliases choose `chat` (default) or the dedicated Images API; support for
  quality, model validation and `--fake` for the new endpoints.

## 0.11.0 — 2026-09-27 (variables menu in the editor)

- GUI: expression and template fields gained a menu of available variables that
  inserts them at the cursor position; the existing suggestions while typing stay.

## 0.10.3 — 2026-09-26 (model alias from the GUI)

- GUI: a model alias in Config can be renamed even with a hyphen (`gpt-image`,
  like an agent name). The field accepted only expression names without a hyphen, so the
  rename silently reverted to `model-1` when leaving the field. An invalid name
  now has the rule in the field's hint and below the alias list.
- Editing: a new map next to maps in the inline `{ … }` style (aliases in
  `config.yaml`) is written in the same style, not as a block; the file thus
  looks uniform after an edit from the GUI.

## 0.10.2 — 2026-09-26 (fixes for concurrency and leaving the editor)

- Editing re-checks the file's SHA-256 after validation and right before writing; a change
  during validation returns 409 and is preserved.
- Writes to the project registry lock reading, modifying and writing via
  `projects.yaml.lock`, so concurrent additions do not lose an entry.
- An unsaved editor confirms leaving even on a hash change or the Back button;
  declining restores the original hash.

## 0.10.1 — 2026-09-26 (cleanup per the ponytail audit, no behavior change)

Patch: cleanup per the ponytail audit, no behavior change; the v1 formats, the run
record and the HTTP contracts do not change. Audit: `docs/audit-ponytail-2026-09-26.md`.

- Duplicated helper functions in one place: `validate.require_config`
  (config or `ConfigErrors`, formerly 4 copies in api, cli, projects, server),
  `projects.text_tree` (step tree from text, formerly 3 copies in edit and
  projects), `record._events` also when restoring the queue in `server`,
  `mcp_client._leaves` also in `engine`, `projects.NAME` also in `server`.
- `api` re-exports the registry functions from `projects` instead of wrappers that only
  passed arguments (`projects`, `new_project`, `projects_root`,
  `normalize_project_root`, `registry_writable`, `remove_project`).
- Expressions compute arithmetic and `< <= > >=` via `operator`; `validate`
  calls the step checks with a single `getattr`; shorter `schema_errors`.
- Tests: shared `registry_server`, `serve`, `TOKEN` and `SECRET`
  in `conftest.py` (no cross imports and `noqa`), the unused
  `fake_for` deleted.

## 0.10.0 — 2026-09-26 (API additions per GUI findings 21–28)

Minor: additive HTTP API only and a run recovery fix; the v1 formats, the
`POST /runs` contract and the callback do not change. ISSUES 48.

- A `serve` restart keeps the original `run_started`, adds an `internal` error
  with the last started step and the API returns `state: interrupted`; an unfinished
  step has `status: interrupted`.
- `config.yaml` schema errors return the YAML line. `GET /projects` returns
  the scenario/agent counts and today's spend; the run list supports `before` and
  `next_before`, `last_run` adds `started_at`.
- `render` accepts scenario text; `validate` adds the tree of a text
  scenario. Batch errors contain `step` and the available `field`.
- The callback secret is required only when sending a callback; the project token
  is read only in single-project mode.

## 0.9.0 — 2026-09-26 (projects from the GUI)

Minor: additive API for creating, registering and removing a project; the v1
formats do not change. ISSUES 47.

- **Projects over HTTP:** `POST /projects/new` creates a project from the same
  templates as `api.new_project`, `POST /projects` registers an existing
  project with `workflows/config.yaml`, `DELETE /projects/<p>` removes only the
  registry entry. A write in single-project mode returns 405.
- **Projects root:** optional `projects_root` in the registry (default
  `~/workspace`); `GET /projects` returns `projects_root` and `writable`.
- `agencast projects add|rm` and `new project` keep using the public
  functions of `agencast.api`, just like the new HTTP writes.

## 0.8.0 — 2026-09-26 (API per GUI findings, part 2)

Minor: new endpoints and fields, v1 formats and the run record unchanged.
Assignment `docs/ui/api-findings.md` items 10–20, ISSUES 46.

- **Batch:** `POST …/scenarios/<s>/batch` `{etag, ops}` — the operations
  `set_header`, `add_step`, `update_step`, `replace_step`, `move_step`,
  `delete_step`, `rename_step` (with `rename_refs`), `add_branch` one after another
  over a single copy, one validation, one write; an operation error = 422
  with `op` (`api.batch`, `api.OpError`).
- **Preview:** `POST …/scenarios/<s>/render` → `{text, tree, errors}` without
  writing (`api.render`).
- **Whole step:** `PUT …/steps/<address>` (`api.replace_step`), accepts `null`.
- **State of a fresh run:** a folder from a `serve` queue record without a lock is
  `queued`, not `interrupted`/`dry_run`; `dry_run` only without `run.lock`.
- **Files:** `HEAD …/files/<path>` (`ETag` header),
  `?etag_only=1` (`api.file_etag`); `errors` in `GET …/files/<path>` =
  the file's `validate` errors as in `GET /projects/<p>`.
- **New files:** `description` in `POST …/scenarios` and `…/agents`,
  for an agent `model` (`api.new_scenario(…, description)`,
  `api.new_agent(…, description, model)`).
- **Project:** `links.scenario_model`, `models_used`.
- **Config:** `PUT …/config` allows `runs_dir` and `openrouter.jev_model`.
- CORS: preflight allows `HEAD`, responses carry `Access-Control-Expose-Headers: ETag`.

## 0.7.0 — 2026-09-26 (API per GUI findings)

Minor: new fields and an endpoint, v1 formats unchanged, new files and
fields in the run record (additive). Assignment `docs/ui/api-findings.md`, ISSUES 45.

- **Running × interrupted:** a run holds a `flock` on `<run>/run.lock`
  (`task.hold_run_lock`, `task.run_locked`); `runs list` and the API have a
  machine-readable `state` (`queued|running|interrupted|succeeded|failed|
  cancelled|dry_run`) and the text `running` / `interrupted` instead of “running or
  interrupted” (also in the CLI `runs list`).
- **Step details:** `steps` in `GET …/runs/<id>` have `nn`, `dir`,
  `error`, `continued`, `default_used`, `calls`, for `task` `turns`
  and `tool_calls`, for `jev` `answers`; a new `GET …/runs/<id>/steps/<path>`
  (events, `output`, step files). `step_started` carries `nn` and `dir`,
  `step_skipped` `nn`, `step_finished` with `continued` `default_used`.
- **Scenario snapshot:** `<run>/scenario/<name>.yaml` (the started one and those called
  via `call`); the run detail returns `tree`, `callees`, `tree_source`.
- **Run list:** `fake`, `queue_position`, `current_nn`, `steps_done`,
  for a dry run `scenario` and `started_at` from `run_id`; `?scenario=&limit=`
  (`api.runs_list(root, scenario, limit)`); `api.last_run` and `last_run`
  in `scenarios` and in `GET /projects`.
- **Project:** `types` in `scenarios`, `links.scenario_step_agent`
  (triples), in `GET /projects` `reason` for an unavailable one and `registry`.
- **Broken config:** `files/config.yaml` and `mcp.yaml` also report schema
  and variable errors; the 422 from `GET /projects/<p>` also has `errors`
  objects; reading runs and `spend` need only `runs_dir` (otherwise
  `./runs`).
- **Fix:** a duplicate key in `.md` frontmatter — “first on line
  N” now points to the line in the file (the shift by the `---` line was missing).

## 0.6.0 — 2026-09-26 (API additions for the GUI)

Minor: new endpoints and fields, v1 formats unchanged (R8), two new fields in
the run record. **The only shape change:** `errors` in the HTTP API are objects
(the GUI is the only client). ISSUES 44.

- **Errors as objects** `{message, file?, step?, field?, line?}` in all
  `errors` of the HTTP API (`GET /projects/<p>`, `…/scenarios/<s>`, `…/files/`,
  responses of editing operations, `validate`); `message` = the former text.
  CLI and Python API unchanged (`projects.error_fields`).
- **`POST /projects/<p>/validate`** without writing: an empty body = the project on
  disk, `{path, text}` = with one file replaced (`edit.validate_text`,
  re-exported in `agencast.api`; the same copy of `workflows/` as editing).
- **`env`** in `GET /projects/<p>`: `{NAME: true|false}` for all
  variables from `config.yaml` (`*_env`) and `mcp.yaml` (`env`,
  `bearer_token_env`); never the value.
- **Runs for the GUI:** `runs list` / `GET …/runs[/<id>]` have `scenario`,
  `started_at`, `finished_at`, `current_step`, `steps_total`;
  `run_started` carries `steps_total` and `callback_url` (without the query, `null`
  = no callback). `run_status` tolerates a multi-line last line.
- **Starting from the GUI:** in `POST /projects/<p>/runs`, `callback_url` is
  optional and `dry_run: true` immediately returns `{run_id, dry_run: true}` (only
  `plan.md` and `inputs.json`). `POST /runs` unchanged.
- **GUI in `serve`:** static files from `agencast/ui/` (`GET /`,
  `/assets/…`, no token, a path without an extension → `index.html`; without a
  built GUI 404 with instructions). `--cors <origin>` for `vite dev`.
  `pyproject.toml`: `[tool.hatch.build.targets.wheel] artifacts` for
  `agencast/ui/**` (the folder is in `.gitignore`).

## 0.5.0 — 2026-09-26 (editing operations for the GUI)

Minor: new operations and endpoints, v1 formats unchanged (R8). ISSUES 43.

- **Editing operations in the core** (`agencast/edit.py`, re-exported in
  `agencast.api`): `set_header`, `add_step`, `update_step`, `move_step`,
  `delete_step`, `delete_scenario`, `set_agent`, `delete_agent`,
  `set_skill`, `delete_skill`, `set_config`, `read_file`, `write_file`.
  Each verifies the fingerprint (sha256 of the content → `Conflict`), validates a copy of
  `workflows/` with the change (a new error → `ConfigErrors`, nothing is written)
  and writes atomically. Deleting a used agent/skill/called scenario
  is refused.
- **YAML round-trip** via `ruamel.yaml` (new dependency, DESIGN D4):
  comments, key order, blank lines and quotes are preserved, unchanged
  lines verbatim. Every scenario and agent from `workflows/` passes a no-op edit
  byte for byte unchanged (test).
- **Step address** `["steps", 2, "parallel", "a", 0]` in the `address` field of
  the `GET …/scenarios/<s>` response; `etag` for scenarios, agents and skills.
- **HTTP in `serve`** (docs/spec/api.md “Editing”): `PUT/DELETE
  …/scenarios/<s>`, `POST …/scenarios/<s>/steps`, `PATCH/DELETE
  …/steps/<address>`, `POST …/steps/<address>/move`, `PUT/DELETE
  …/agents/<a>`, `PUT …/config`, `PUT/DELETE …/skills/<n>`, `GET/PUT
  …/files/<path>`, `POST …/scenarios` and `…/agents` (= `new`). 409 on a
  fingerprint mismatch, 422 with `errors`, 404 outside the allowed files; the same token
  as reading.

## 0.4.0 — 2026-09-26 (agencast new, project registry, read API of serve)

Minor: new commands and endpoints, v1 formats unchanged (R8).

- **`agencast new project <path> [--name N]`** — a project skeleton:
  `workflows/config.yaml` (OpenRouter, aliases `smart`/`fast`/
  `gemini-image`, `storage.type: local`), agent `writer`, scenario `demo`
  (they pass `validate --offline` and `--fake`), `.env.example`, `.gitignore`.
  **`new agent|scenario <name>`** adds a minimal file. It never overwrites anything.
  API `new_project`, `new_agent`, `new_scenario` (return the created paths).
- **Project registry** `~/.config/agencast/projects.yaml`
  (`AGENCAST_CONFIG_DIR`): `agencast projects list|add|rm`; filled by
  `new project` and a successful `validate`/`run` (a message once on stderr).
  API `projects()` (with `available`), `add_project`, `remove_project`.
- **`serve` outside a project = registry mode** with the token `AGENCAST_TOKEN`,
  secrets from the server's environment; in a project or with `--project` unchanged.
- **Read API** (docs/spec/api.md): `GET /projects`, `/projects/<p>`
  (scenarios, agents, skills, MCP servers without secrets, aliases, limits,
  links), `/scenarios/<s>` (step tree for cards with `refs`), `/runs`,
  `/runs/<id>` (steps with status, cost and time), `/runs/<id>/files/<path>`
  (only inside the run folder), `/spend?day=`; `POST /projects/<p>/runs`.
  API `describe_project`, `describe_scenario`, `run_detail`, `run_file`,
  `spend`; `Ledger.rows`.

## 0.3.1 — 2026-09-26 (cap on concurrent runs, daily spend limit)

Patch: two optional keys, behavior unchanged without them (R8).
Format: spec v1, a backward-compatible addition (ISSUES 40).

- **`limits.max_parallel_runs: N`** — at most N runs at once over one
  `runs/`, across processes (CLI, n8n, cron, `serve --workers`): a `flock` on
  `<runs>/_slots/<n>.lock`, the slot is taken before the run folder and always
  released. Full → stderr “waiting for a free slot (max_parallel_runs=N)”,
  polling every 0.5 s for at most `run_timeout`, then `timeout`. The wait is
  in the record as a `run_waiting` event (`waited_s`). Fake runs take part in
  the slots.
- **`limits.daily_budget_usd: X`** — a daily spend ledger
  `<runs>/_ledger/<YYYY-MM-DD>.jsonl` (UTC, a line `{run_id, cost_usd,
  finished_at}` for every finished run; `--fake` goes to `_ledger-fake/`).
  Today's total ≥ X → a new run ends with `budget` before the first
  call. Checked only at start; the ledger is always written, since 0.3.1.
- A run that did not start because of a slot or the daily limit has a record like a run
  not started by a webhook (`run_scenario(error=…)`): `run_finished` with `error`,
  `callback.json`, `summary.md`, without `plan.md`/`inputs.json`.
- `SlotStore` and `Ledger` in `task.py` next to `DedupeStore` (a place for Modal).
- `agencast run`: an error without a step is printed as `<class>: <message>` (formerly
  “… in step None: …”).

## 0.3.0 — 2026-09-26 (AgenCast, concurrent runs, API for the shells)

Minor: a rename and new features, all backward compatible. Format: spec
v1 unchanged (only `--workers` added in webhook.md).

- **Rename:** the framework is called AgenCast — package `agencast`
  (formerly `maw`), command `agencast` (formerly `maw`), exception `AgencastError`
  (formerly `MawError`). No format (run record, callback, webhook
  headers, fake scripts) contained the name, so old records and scripts
  stay valid unchanged. Alias from the tutorial:
  `alias agencast="uv run --project framework agencast"`.
- **`agencast serve --workers N`** (default 1): N worker threads over
  one queue; queue recovery and `request_key` under a lock, the completion
  order with N > 1 is not guaranteed (ISSUES 39).
- **`run_id` collisions** (ISSUES 35): a new suffix, at most 5×, then `internal`;
  on receipt the webhook skips an id with an existing queue record.
- **The `/models` cache** is written atomically (temporary file + `os.replace`),
  a corrupted cache = no cache.
- **`DedupeStore`** (`task.py`): `dedupe_key` behind a `get` / `claim` /
  `finish` interface, locally the `<runs>/_dedupe/` and `_dedupe-fake/` files unchanged;
  `Run.dedupe` is the place where Modal plugs in its own storage.
- **`agencast.api`**: `load`, `run`, `dry_run`, `runs_list`, `run_status`
  (+ `find_root`) — thin functions over validate, engine and record; `cli.py`
  and `server.py` call through them (DESIGN “Shells”).

## 0.2.5 — 2026-09-25 (time in the Total row)

Format: spec v1, only a clarification (ISSUES 38):

- **The Total row** in `summary.md` and `report.html` has the time of the
  whole run in the Time column (`duration_s` from `run_finished`, the same number as
  in the header), not the sum of the steps — `parallel` branches run concurrently and nested
  steps are already in the time of the parent `parallel`/`switch`/`call`.

## 0.2.4 — 2026-09-25 (full cost, Total row)

Format: spec v1, only a clarification (ISSUES 38):

- **Cost without rounding:** a call's cost goes into `events.jsonl`,
  `calls/*.json`, `step_finished`, `run_finished` and `callback.json`
  exactly as OpenRouter returned it. Totals (step, run, images,
  `budget_exceeded_usd`) are rounded to 10 decimal places (formerly 8,
  so the callback showed 4.48e-06 instead of 4.482e-06).
- **Display:** `summary.md`, `report.html`, the final line of `maw run`,
  `maw runs list/show` and the budget messages show the cost in decimal
  (`0.000004482`, formerly `0.0000`), to at least 4 places; a step without a model
  call has a cost of `0`. Budget messages now use a decimal comma.
- **A Total row** at the end of the step table in `summary.md` and `report.html`
  (also for a failed run): the run cost, for images “of which images …”.

## 0.2.3 — 2026-09-25 (subfolders are ignored)

Format: spec v1, only a backward-compatible relaxation (ISSUES 37):

- **Subfolders in `workflows/agents/` and `workflows/scenarios/`** (e.g.
  `archive/`) no longer stop validate or a run with a `config` error — they are silently
  ignored. Agents, `call` targets, the webhook and `maw runs`/`serve` still read
  only files directly in the folder.
- When an agent or a `call` target does not exist but a file of the same name lies
  in a subfolder, the message adds “(file is in subfolder agents/archive/,
  subfolders are not read)”.
- A clearer message when a scenario is started from outside
  `workflows/scenarios/` (e.g. from `archive/`).

## 0.2.2 — 2026-09-25 (fixes from tutorials 6 and 7)

Format: spec v1, only backward-compatible additions. Fixes from
`docs/tutorials/BUGS.md` (section maw 0.2.1):

- **Dedupe and `--fake` (BUGS 8, high):** a fake run writes dedupe to
  `<runs>/_dedupe-fake/` (the same structure), a live one to `<runs>/_dedupe/`;
  they are never read across. Previously a live run after a `--fake` trial
  skipped the step and returned an invented output. `run_started` has a new
  field `fake` (run-record.md), `summary.md` and `report.html` mark
  a fake run. The fix does not recognize and does not delete the records in `_dedupe/` from fake runs of 0.2.1
  — after `--fake` trials, find them (`grep -l <scenario>
  runs/_dedupe/*.json`) and delete manually only those you know belong to
  the trials.
- **`task` with `schema` always via `tool_wrapper` (BUGS 7, ISSUES 36):**
  structured output in a `task` step is enforced with the tool
  `_submit_output` regardless of `models.<alias>.structured_output`;
  `response_format` is not sent in turns (Haiku ended the loop with it
  without calling tools). The cascade continues to `prompt`. The alias setting applies
  only to `ask`. The level is in `model_call.structured_output`, in the step
  note and in `plan.md` (“cascade from tool_wrapper”). The fake provider
  at the `tool_wrapper` level respects `text` from the script (the model did not call
  `_submit_output`).
- An agent with `mcp` without `tools`: the message names the servers, shows the shape
  `tools: { server: [tool, …] }` and advises `maw run … --dry-run` (BUGS 9).
- `POST /runs`: the 422 returns the body's errors (unknown field, …) together with the errors of the
  scenario and inputs, not only on the second attempt (BUGS 9).
- Tutorials: part 5 `report_url` (since 0.2.0 the address of `report.html`, not
  `null`), part 6 a note on `schema` in `task`, part 7 `_dedupe-fake/`.

## 0.2.1 — 2026-09-25 (fixes from the tutorials)

Format: spec v1 unchanged. Bug fixes from `docs/tutorials/BUGS.md`:

- The warning “provider returned no cost” only for a successful response without
  `usage.cost`; an error response (HTTP 429, 400, `error` in the body) costs
  nothing and gives no warning (BUGS 1).
- `{{ }}` in an expression (`set`, `when`, `switch.value`): only the message “template
  is not allowed here”, now with a caret; the second message about the AST node `Set`
  is gone (BUGS 2).
- A concrete model id in an agent (`model: anthropic/claude-haiku-4.5`):
  the message “model '…' is not an alias in config.yaml (aliases: …)” instead of a regex
  from the schema; the schema unchanged (BUGS 3).
- YAML syntax error: a sentence with advice (a value with `{`, `[`, `: ` or
  ` #` into quotes, scenario.md §5 “YAML pitfalls”) and the line, the original
  parser message as the second line. A duplicate key unchanged (BUGS 4).
- Pluralization of counts: `validate` “(1 step / 2 steps / 9 steps)”, `serve`
  “queued 2 runs”, the note of a `call` step in `summary.md` (BUGS 5).
- Tests: the test config takes the aliases from the real
  `workflows/config.yaml` (keys, limits and storage stay test ones),
  the fake `GET /models` knows their ids — a new owner alias does not break the
  golden tests (BUGS 6).
- Read timeout of the provider's HTTP calls (ISSUES 34): for every call
  min(remaining step time, 120 s chat/image/`task` turn, 30 s Jev);
  expiry = `transient`, retried per `retry`. `model_call`
  and `jev_call` have a new field `timeout_s` (run-record.md, backward
  compatible). Previously a stuck connection waited until the step timeout.
- The unstable test `test_webhook.py::test_202_and_signed_callback`
  (under load 1 failure in 8 runs): the test read `events.jsonl` as soon as the
  receiver got the callback, but the framework writes `callback_sent` only after the
  receiver's response. Webhook tests now wait for the end of the run (deletion of the
  queue record) and keep the queue order with a barrier instead of `sleep` —
  the same applied to the restart in `test_request_key_is_idempotent_across_restart`.
  The `live` marker (network, a real npx server) is registered in pyproject,
  an ordinary `uv run pytest` skips it; no test needs it yet —
  the whole suite passed even without a network. Tests: +9 (369 in total).

## 0.2.0 — 2026-09-25 (Phase 3)

Format: spec v1 unchanged.

### 3b — call, webhook server, report.html, CLI

- The `call` step (scenario.md call, DESIGN §5.3): a nested scenario in the same
  run — the same `events.jsonl`, budget and time limit, steps have a path
  `propose/copy`, the record in `steps/<nn>-<id>/steps/…` (+ the call's `inputs.json`).
  `validate`: `callable: true`, inputs (required, none extra,
  types; `file` only from a file), only the declared `outputs` are read, cycles
  and `limits.max_call_depth`; errors of the called scenario with its file name.
  At run time: an input type that could not be verified in advance → `expression`; an error
  inside = an error of the `call` step (`step` is a path); `on_error: continue`
  of the `call` step covers it, including its own `budget_usd`/`timeout`.
  Files from the called scenario are not uploaded.
- Webhook server `maw serve --host --port [--fake]` (webhook.md):
  `POST /runs` (Bearer token, 401/422 synchronously without `run_id`, 202,
  200 for a repeated `request_key`), `GET /runs/<run_id>`, a queue with one
  run at a time, a persistent queue and `request_key` in `<runs>/_queue/`,
  a callback always from the moment `run_id` is assigned (even if `validate` fails only after
  being taken from the queue → `config`; a run interrupted after a restart → `internal`).
  Stdlib `http.server.ThreadingHTTPServer` — no new dependency.
- `report.html` for every run: a single file without external resources,
  header, error, warnings, inputs, a table of steps (also nested), prompts
  and responses in `<details>` (truncated to 4000 characters), outputs; masking of
  secret values, no base64. It is uploaded to storage, `report_url`
  in the callback (formerly `null`, ISSUES 5).
- CLI: a scenario by name or path; the project root by `workflows/` from
  cwd upwards or `--project` (on all commands; replaces `runs
  --workflows`); `runs list` also shows queued requests; `maw migrate
  <file>` (skeleton: v1 → “nothing to convert”, an unknown version → `config`).
  Own messages in Czech; the messages of `argparse` itself (usage, a missing
  argument) stay in English.
- `callback_url` may also be `http://127.0.0.1` (tests, a local receiver) —
  ISSUES 14.
- Tests: +44 (call, webhook with a local callback receiver, report, CLI);
  golden scenarios `tone-check` (`callable: true`) and `demo-call`.

### 3a — the task step, MCP servers, skills, dedupe_key

- **The `task` step** (`task.py`): a model ↔ tools loop via the OpenRouter
  chat; tools only from the effective set step ⊆ agent ⊆ `mcp.yaml`;
  `max_turns` (a repeat after `transient`/`schema` is not counted; exhaustion =
  `budget`), `budget_usd`, `timeout`; `isError` and argument validation errors
  go to the model as a tool result; images from tools as a
  file `steps/<nn>-<id>/tool-<NN>-<k>.png` + a following user message;
  `reasoning_details` back; output cascade (`native_schema` →
  `tool_wrapper` with `_submit_output`, which never goes to the server →
  `prompt`); events `tool_call`, `calls/NN.tool.json`.
- **MCP client** (`mcp_client.py`) over the official SDK `mcp==2.2.*`: stdio,
  Streamable HTTP, SSE; `mode="legacy"`; handshake and call timeouts +
  an outer safeguard; unwrapping `ExceptionGroup` into the classes `timeout` /
  `config` / `transient`; server stderr to `mcp/<server>.stderr.log`
  (masked); a server starts at the first `task` in a run, is shared by the `parallel`
  branches and is terminated at the end of the run (test: 0 leftover processes);
  events `mcp_server`.
- **Tool schema normalization:** `server__tool` (`[a-zA-Z0-9_-]`, max
  64), inlining `$ref`, `allOf`/`oneOf`, `const` → `enum`, a non-string
  `enum` into `description`; arguments are validated against the original schema
  (`invalid_args`). A name collision after normalization = `config`.
- **`mcp.yaml`:** loading and validation against `mcp.schema.json`, only
  `{run_dir}`; owner permissions in `validate` (`agents`, `scenarios`,
  `tools` of a server; a step must not widen a server, a tool or `max_turns`);
  server variables are masked and must not be the same as `*_env` from
  `config.yaml`; a missing variable = `config` before the run.
- **Skills:** for `task` a `## Skills` section with a list `- name: description`
  and the tool `load_skill` (`enum` of names, an error with a list, a turn, server
  `_skills`); for `ask` unchanged, the whole body.
- **`dedupe_key`:** atomic files `<runs>/_dedupe/<sha256>.json`;
  `started` before the first MCP tool call, `succeeded` with the output;
  the next run skips the step (`step_skipped`, `dedupe`), `started` without
  `succeeded` = `config` “check manually and delete <file>”.
- `validate`: an agent's alias in `task` must have `tools` in `GET /models`.
- Fake provider: `tool_calls` in a script. Tests (+30, of which 2 after
  merging with 3b: `--dry-run` with server tools, `task` with `dedupe_key`
  inside `call`): a fake MCP server
  `tests/fake_mcp_server.py`, `test_task.py`, the golden scenario
  `workflows/scenarios/demo-task.yaml` (agent `librarian`, skill
  `catalog`, a new `workflows/mcp.yaml`).

Dependencies: only `mcp==2.2.*` was added (locked in `uv.lock`).

- `--dry-run`: `plan.md` for a `task` step shows the agent, the resulting set of
  tools, skills, `max_turns` and `dedupe_key`; servers the run may
  start are started in a temporary folder for `tools/list` and the plan lists
  what they offer (or why they did not start) — scenario.md §7.

Not in 0.2.0: repeating the MCP handshake (ISSUES 26), the read timeout of the provider's HTTP
calls (ISSUES 34, open).

## 0.1.0 — 2026-09-25 (Phase 2: the core)

Format: spec v1 (`version: 1` of a scenario, agent, config).

- CLI `maw`: `validate`, `run` (`-i`, `--dry-run`, `--fake [SCRIPT]`,
  `--callback-url`, `--request-key`), `runs list|show`.
- Loader: YAML 1.2 core (only `true`/`false`, `4:5` and `yes` are text,
  a duplicate key = `config` with a line), frontmatter, `.env` with CRLF.
  JSON Schemas are read from `docs/spec/schema/` (the single source of truth);
  steps are each verified against the schema of their type → Czech messages
  without printing the values of `*_env`.
- Validate (scenario.md §7): version, schema, name = file, subfolders,
  unique `id`, references only upwards and not into another `parallel` branch, a step
  that may not run, without `default`, a complete `default`, agent / skill /
  alias exists, step limits ⊆ agent, templates only in allowed fields,
  expressions (syntax, forbidden constructs, types known in advance), `output`
  last and matching `outputs`, unreachable steps after `fail`, `cases`
  ⊆ `criteria`, aliases against `GET /models` (24 h cache, image output,
  structured_outputs/tools).
- Expressions and templates (§5, D1c): a custom evaluator over `ast`, dot = key,
  strict types, `and/or/not` only bool, `round` half away from zero, limits
  2000 characters / depth 100 / result 100 000, messages in Czech with a caret.
- Engine: step order, `when`, `parallel` (TaskGroup, cancelling the other
  branches → `cancelled`), `switch` with `default`, `set`, `fail`, `output`;
  `retry` (2 s, 4 s, 8 s or `Retry-After`), `timeout` (step, parallel,
  run), `budget_usd` (step, agent, parallel, run, images), `on_error:
  continue`; error classes §6; HTTP 200 is not success.
- Providers: OpenRouter chat (cascade `native_schema` → `tool_wrapper`
  → `prompt`, feedback to the model, `reasoning_details` back), Jev
  (`/systemone`), image (chat completions with `modalities`, base64 →
  file, `aspect_ratio` check ±2 %), `usage` normalization. The fake
  provider = `httpx.MockTransport` (the same code path as the live one).
- Run record (run-record.md): a folder, `events.jsonl`, `steps/<nn>-<id>/`,
  `summary.md`, `plan.md`, `callback.json`, masking of secret values,
  without base64 and `reasoning_details`; callback POST (https, HMAC-SHA256,
  3 attempts).
- Conformance suite `uv run pytest` (expressions from spike (c), loader, validate,
  engine, golden scenarios from `workflows/` and examples from `docs/spec/`).

Dependencies: `pyyaml`, `jsonschema`, `httpx`; development `pytest`. Compared to the
D4 default set **without** `pydantic` (the formats are JSON Schemas from the spec, verified
by `jsonschema` directly — a second description in pydantic would be a duplicate) and
**without** `typer` (stdlib `argparse` is enough). `hatchling` is only a build
backend for installing the `maw` command (not used at run time). `mcp` and `modal`
will come with the `task` step and deployment.

Not in 0.1.0 (places in the code prepared): `task` (MCP, skills via
`load_skill`, `dedupe_key`), `call`, the webhook server, Modal, `report.html`,
R2 storage — `validate` rejects them with a clear `config` error.
