# API findings for the GUI (ui/ part 1 read-only version, part 2 editing, part 3 API 0.7.0, part 4 API 0.8.0–0.9.0)

What the GUI lacked, or got in an unsuitable shape, from the `serve` HTTP API while
the read-only version was built (2026-09-26, agencast 0.6.0; GUI design §7). The core
was not changed; each item says how the GUI works around it for now. Roughly in order
of impact.

1. **`GET /projects/<p>/runs` and `…/runs/<id>` — a running run and an interrupted
   run cannot be told apart.** the combined `status` text “running or interrupted” also applies to a run whose
   process ended long ago (a crash, a `serve` restart). The GUI shows it as “running”
   and keeps polling it forever (detail 2 s → 5 s, list 5 s).
   *Needed:* `running` only for a run held by a live worker, otherwise
   `interrupted` (or a flag).
   **Resolved (0.7.0):** done — `state` in both the list and the detail (`running` only with `<run>/run.lock` held by a live process, otherwise `interrupted`); `status` is `running` / `interrupted`.

2. **`GET /projects/<p>/runs/<id>` — steps without details.** The `steps` item
   has no `nn` or step folder, no error message, `continued`,
   `default_used`, calls (alias → model, tokens, `finish_reason`, cascade
   level), tools or Jev answers. The GUI therefore downloads the whole
   `…/files/events.jsonl` (on every poll of a live run) and looks for the step
   folder in `files` with the pattern `steps/\d+-<id>/` (nested for `call`).
   *Needed:* at least `nn`/`dir`, `error {class, message}`,
   `continued`, `default_used` and a summary of calls in `steps`; or
   `GET …/runs/<id>/steps/<path>` with the events of a single step.
   **Resolved (0.7.0):** done — `steps` have `nn`, `dir`, `error {class, message}`, `continued`, `default_used`, `reason`, `calls` (no extra cascade level: `structured_output` is in `calls`), `turns` and `tool_calls` for `task`, `answers` for `jev`; new `GET …/runs/<id>/steps/<path>` (events, `output`, `files`). The error of a nested step (`call`, branch) is on that step, not on its parent.

3. **`GET /projects/<p>` — scenarios without step types.** The `IconChain` on a
   scenario card (§2.2) needs the step types of the main list; the GUI therefore calls
   `GET …/scenarios/<s>` for every scenario (20 requests for the original shared workflows set; today `examples/`
   on every project open). *Needed:* `types` (step types of the main
   list, in file order) in the `scenarios` item.
   **Resolved (0.7.0):** done — `types` in the `scenarios` items.

4. **Broken `config.yaml` → errors only as texts and without a line.**
   `GET /projects/<p>` returns 422 with `details` (texts), `GET
   …/files/config.yaml` returns `errors: []`, so the YAML mode of Config cannot
   mark the faulty line or field. At the same time `…/runs` and `…/spend` return 422 —
   the old runs of such a project cannot be read. *Needed:* `errors` as objects
   (`file`, `field`, `line`) in `files/config.yaml` and in 422 responses too;
   reading runs independent of a valid config (`runs_dir` is enough).
   **Resolved (0.7.0):** done — `files/config.yaml` and `mcp.yaml` (since 0.18.0 `mcp.yaml` is no longer served: its errors are the project-level `errors` of `GET /projects/<p>`) return all errors as objects (`line` only for syntax and duplicate keys; `field` for schema errors); the 422 from `GET /projects/<p>` also has `errors`; `…/runs`, `…/runs/<id>` and `…/spend` work with an invalid config (`runs_dir`, otherwise `./runs`).

5. **`GET /projects/<p>/runs` — data for the list row is missing (§2.6).**
   Missing are `fake` (the design shows “fake run”; the GUI can only get it in the detail
   from `run_started`), `queue_position` for waiting runs (the GUI uses the order
   in the list) and the number of the running step (the design shows “step 4/8”; the GUI shows
   “step photo_prompt (of 8)”). A dry run has `scenario` and `started_at` set to `null`
   (the GUI takes them from `run_id`). *Needed:* `fake`, `queue_position`,
   `current_nn` or the number of finished steps, and `scenario` for a dry run.
   **Resolved (0.7.0):** done — `fake`, `queue_position` (for `queued`), `current_nn` and `steps_done` (for `running`), and for a dry run `scenario` and `started_at` derived from `run_id`.

6. **The run list has no filter and no pagination.** The project card and the scenario
   card (status chip of the last run) download the whole `…/runs`; this will grow with the
   number of runs. *Needed:* `?scenario=&limit=`, or `last_run`
   (state + time) directly in the `scenarios` item and in `GET /projects`.
   **Resolved (0.7.0):** done — `GET …/runs?scenario=&limit=` and `last_run {run_id, state, finished_at, cost_usd}` in `scenarios` and in `GET /projects` (it can also be a waiting run or a dry run).

7. **`GET /projects` — the reason for unavailability and the registry path are missing.**
   The card of an unavailable project shows the reason; the GUI gets it only with another
   `GET /projects/<p>` and reads the 404 text. The heading “Registry
   ~/.config/agencast/projects.yaml” (§2.1) cannot be shown by the GUI.
   *Needed:* `reason` for `available: false` and `registry` (the path)
   in the response.
   **Resolved (0.7.0):** done — `reason` for `available: false`, `registry` in the response.

8. **`links.scenario_agent` without the step id.** An agent in §2.7 has “Used by:
   ig-post (copy)”; the GUI only knows scenario names. *Needed:* a
   `[scenario, step, agent]` triple (or a separate field).
   **Resolved (0.7.0):** done additively — `links.scenario_step_agent` as a `[scenario, step, agent]` triple; `scenario_agent` unchanged (GUI part 1 reads it).

9. **The run detail draws the tree from the current scenario file.** The API does not return
   the step tree that was valid during the run (`scenario_version` is just the format
   number), so after a scenario edit the detail of an old run may show cards that did not
   exist then (as “not reached”) and omit steps that have disappeared.
   *Needed:* the step tree in `run_started` (or the `etag` fingerprint of the scenario
   the run started with).

   **Resolved (0.7.0):** done — a snapshot `<run>/scenario/<name>.yaml` (of the started scenario and of those called via `call`); `GET …/runs/<id>` returns `tree` (the shape of `steps` from `…/scenarios/<s>`), `callees` and `tree_source` (`snapshot`, `current` for older runs). Instead of a tree in `run_started`, a copy of the file — same parser, no new format.

## Part 2 (editing version)

What was missing while the editor was built (2026-09-26, agencast 0.6.0), verified against
`agencast serve --fake`. The core was not changed; each item says how the GUI works around it.

10. **Renaming a step that someone reads cannot be saved.** Every operation
    is validated separately and must not add a new error: `PATCH …/steps/<a>`
    with a new `id` breaks the readers' references (422), and fixing the references first
    points to a nonexistent id (422). The same goes for deleting a read step
    while its readers still reference it. *GUI:* the form does not allow renaming a read step
    and offers YAML mode; deleting warns that saving
    only succeeds with the readers updated. *Needed:* `PATCH` with `rename_refs:
    true` (rewrites `steps.<old>.` in all steps), or a batch of operations
    validated as a whole (`POST …/scenarios/<s>/batch`).
    **Resolved (0.8.0):** `POST …/scenarios/<s>/batch` with the `rename_step` operation (`rename_refs`, default `true`); deleting a read step + updating its readers in a single batch. `PATCH` with `rename_refs` does not exist — the batch covers it.

11. **A series of operations is not atomic.** Saving from the form = several
    operations in a row; when the nth gets 422/409, the previous ones are already
    on disk. *GUI:* after a failure it reloads the file, adopts the steps on disk
    (uid ← id) and leaves the rest in progress with the message “N
    operations from the save are on disk”. *Needed:* a batch (see 10) written only
    when all of it succeeds.
    **Resolved (0.8.0):** the batch writes everything or nothing; an operation error = 422 with `op` (index), a result error = 422 without `op`.

12. **A work-in-progress state can be neither validated nor converted between modes.**
    `POST …/validate` takes only text; the form holds a tree and does not
    build YAML, so there is no continuous validation in Form mode (a deviation
    from design §4.4) and Form ↔ YAML with unsaved changes must first be
    saved or discarded. *Needed:* `validate` with operations (`{path,
    ops: [...]}`) returning the resulting text/tree, or
    `POST …/scenarios/<s>/render` (operations → text without writing).
    **Resolved (0.8.0):** `POST …/scenarios/<s>/render` `{etag?, ops}` → `{text, tree, errors}` without writing (all errors, 200 even with errors).

13. **A new step cannot be saved incomplete.** An empty `ask` (without an agent
    and a prompt) is a new error → 422; a new `parallel`/`switch` needs
    steps in its branches, and a new branch of an existing container can only be added
    with its first step (`PATCH` with `{parallel: {<branch>: [step]}}`).
    *GUI:* holds a new step locally and sends it in a single `POST …/steps` only
    once the fields are filled in; it reports a branch without a new step before sending.
    **Resolved (0.8.0):** validation unchanged; insert and complete the step (or add a branch with the `add_branch` operation and fill it) in one batch, the work-in-progress state goes through `render`.

14. **Merge patch cannot express a `null` value** (api.md says so) — `default:
    {file: null}` works only in YAML mode. *GUI:* the form rejects such a change
    with a pointer to YAML. *Needed:* `PUT …/steps/<a>` with the whole
    step (replacement), or JSON Patch.
    **Resolved (0.8.0):** `PUT …/steps/<address>` `{step}` and the batch operation `replace_step` — the whole step, handles `null`.

15. **A freshly started run is `dry-run` for a moment.** Right after `202` on
    `POST /projects/<p>/runs`, `GET …/runs/<id>` returns `status:
    "dry-run"` (the folder has `plan.md`, not yet `events.jsonl`); the GUI would
    stop reading. *GUI:* after starting a live run (a temporary URL flag) it keeps reading the detail
    for another 15 s. *Needed:* `queued`/`running` from the first moment
    (for example from the record in the queue), `dry-run` only for a real plan.
    **Resolved (0.8.0):** a record in the `_queue/` queue → `queued` (with `queue_position`) until the run holds the lock (`running`) or finishes; `dry_run` only without `run.lock` (a dry run never had one) — the record format is unchanged.

16. **Changes on disk are found only by polling.** The GUI detects a conflict (§4.6) with a
    `GET` of the whole scenario/file every 5 s and on window focus. *Needed:*
    a light `HEAD`/`GET …/files/<path>?etag_only=1`, or SSE with file
    changes.
    **Resolved (0.8.0):** `HEAD /projects/<p>/files/<path>` (the `ETag` header, exposed with `--cors`) and `GET …?etag_only=1` → `{etag}`. No SSE.

17. **`GET …/files/<path>` reports only loader errors.** Its `errors` are not
    `validate` errors, so YAML mode calls `POST …/validate` with the text from
    disk right after loading. *Needed:* the same `errors` in `files/`
    as in `GET /projects/<p>` for the given file.
    **Resolved (0.8.0):** `errors` in `GET …/files/<path>` = the `validate` errors of the file, the same as for the item in `GET /projects/<p>`.

18. **`POST …/agents` and `POST …/scenarios` take only a name.** The description of a new
    scenario can only be set by a second operation (`PUT` of the header), a new agent
    gets the template description `TODO`. *Needed:* an optional `description` (and for
    an agent `model`) in the body.
    **Resolved (0.8.0):** optional `description`, and for an agent `model` (an alias from the config, anything else → 422).

19. **Use of a model alias in `image` steps.** `links` has only agent →
    alias via `agents[].model`; an alias used only in `image.model` cannot be marked by the GUI
    as “in use” (deleting it is then rejected only by validation, 422).
    *Needed:* `links.scenario_model` (or `models_used`).
    **Resolved (0.8.0):** `links.scenario_model` (scenario–alias pairs from `image.model`) and `models_used` (`{alias: [agents/…md, scenarios/…yaml]}`, all aliases).

20. **`openrouter.jev_model` and `runs_dir` cannot be changed via `PUT …/config`**
    (only `openrouter.api_key_env` and five sections are allowed); the GUI shows them
    read-only and points to YAML mode. If this is intentional, one sentence
    in api.md is enough.
    **Resolved (0.8.0):** `runs_dir` and `openrouter.jev_model` are now allowed too; `version` and `openrouter.base_url` remain forbidden (api.md “`PUT …/config`” — the format, where the key goes).


## Part 3 (GUI on API 0.7.0)

The GUI moved to `state`, `steps` with details, `GET …/steps/<path>`, `tree`/`callees`,
`types`/`last_run`, `?scenario=&limit=`, `scenario_step_agent`, `reason`/`registry` (items 1–9).
Verified 2026-09-26 against `agencast serve --fake` (framework 0.7.0 from the branch). The core was not changed.

21. **A `serve` restart turns an interrupted run into `failed`.** A run that was running under `serve`
    at the moment of a crash gets, after `serve` starts, an appended `run_started` + `error internal`
    (“run interrupted — server stopped during the run…”) + `run_finished failed`. `state:
    interrupted` is therefore visible only between the crash and the restart (and for a CLI run
    that nobody finishes). In addition: `status` is `failed (internal in None)` (step `null` → “None”),
    `started_at` is the recovery time (the second `run_started`) and `duration_s` is `0.0`. *GUI:* shows what
    it receives (`error: internal in None`). *Needed:* `status` without “in None”, `started_at` from the first
    `run_started`; consider whether a recovered run should stay `interrupted` (or carry a flag).
    **Resolved (0.10.0):** recovery keeps the original `run_started` and appends an `internal` error with the last
    started step and the message “run interrupted by server restart”; `run_finished.status` is `failed`,
    but the API `state` stays `interrupted` and `started_at` stays the original.
22. **A step without an end has `status: running` in a finished run.** The `steps` item of a step that
    had `step_started` and then the run crashed stays `running` even with `state` `interrupted`/`failed`.
    *GUI:* when the run is not `queued`/`running`, it shows such a step as “interrupted” (no pulsing).
    *Needed:* `status: interrupted` (or `null`) instead of `running` for a run that is not alive.
    **Resolved (0.10.0):** a step without `step_finished` has `status: interrupted` when no live worker holds it.
23. **`config.yaml` schema errors without a line.** For schema errors `files/config.yaml` returns only
    `field` (`limits.run_budget_usd`); `line` only for syntax and duplicate keys (as api.md
    says). The YAML mode of Config therefore does not mark the line for them, it only prints the message. *Needed:*
    `line` for schema errors too (the loader knows the node position).
    **Resolved (0.10.0):** `config.yaml` schema errors contain `line` according to the key in the YAML, in `files/config.yaml`
    and in the 422 from `GET /projects/<p>`.
24. **`GET /projects` without counts.** The project card shows “20 scenarios · 8 agents” and today's
    spend, so it still calls `GET /projects/<p>` for every available project (the whole project for
    two numbers) and `…/spend`. *Needed:* `counts {scenarios, agents}` and `spend_today_usd`
    in the `GET /projects` item.
    **Resolved (0.10.0):** available and unavailable items return counts based on the file listing and `spend_today_usd`
    from the daily ledger without validating the project.
25. **Pagination with `limit` only.** “Load more” downloads the whole longer list again (`limit`
    +50); `last_run` has no `started_at`, so the GUI takes the time of a waiting/interrupted run and of a dry run
    from `run_id`. *Needed (once there are many runs):* a cursor `?before=<run_id>`; `started_at`
    in `last_run`.
    **Resolved (0.10.0):** `before` paginates by folder name and `next_before` is returned when there are more runs;
    `last_run.started_at` is additive.


## Part 4 (projects from the GUI, 0.8.0 batches, Playwright E2E)

The GUI moved to `POST /projects/new`, `POST /projects`, `DELETE /projects/<p>`, `projects_root`/`writable`
(0.9.0), the `…/batch` batch, the `…/render` preview, `HEAD …/files/<path>`, `description`/`model` in `POST`
(0.8.0) — the GUI no longer works around items 10–18. Verified 2026-09-26 with E2E tests (`ui/e2e/`, Playwright against
`agencast serve --fake` from the branch, framework 0.9.0). The core was not changed. Findings 21 and 22 also hold in 0.9.0;
N5b caught the recovery error back then, fixed in 0.10.0.

26. **`render` takes only operations, not text.** Form → YAML with unsaved changes works (`render` returns
    `text`), but not the other way round: the GUI neither builds nor parses YAML, and no endpoint returns a tree
    from a work-in-progress text (`validate` returns only `errors`). *GUI:* YAML → Form with unsaved text still
    asks “Save and switch” / “Discard and switch”. *Needed:* `POST …/scenarios/<s>/render`
    (or `validate`) with `{text}` instead of `ops`, returning `tree` and `errors` without writing.
    **Resolved (0.10.0):** `render` accepts `{text}` and returns `{tree, errors}`; for scenario text `validate`
    returns `tree` in addition to `errors`, without writing.
27. **A batch operation error has no step.** A 422 with `op` carries in `errors` only a `message`
    (`ops[0] update_step: …`), without `step`/`field`. *GUI:* keeps, for every operation, the id of the step it
    came from and shows the error on its card. *Needed:* `step` (the step id according to `address` before the operation)
    in the operation error, and for `add_step` the id of the inserted step.
    **Resolved (0.10.0):** batch operation errors return `step` according to the address before the operation (for `add_step` according to the inserted
    step) and `field` if the error determines one.
28. **A live (even fake) run in the registry wants `CALLBACK_SECRET` even though no callback is sent.**
    `POST /projects/<p>/runs` without `callback_url` returns, for a project from the template, 422 “missing environment
    variable CALLBACK_SECRET (callback signature)” until the `serve` environment has the variable (verified
    with `--fake`; E2E therefore sets `CALLBACK_SECRET` and `WEBHOOK_TOKEN` to placeholder values). A project
    created from the GUI thus cannot be run even though it does not need a callback. *GUI:* shows the 422 with `details`
    in the run panel. *Needed:* check `callback.secret_env` only together with `callback_url` (and
    `webhook.token_env` only where the token is actually read).
    **Resolved (0.10.0):** `callback.secret_env` is required only for a callback; `webhook.token_env` only in single-project
    mode. A project from the template can be run with `--fake` without `CALLBACK_SECRET`.

## Part 5 (GUI on API 0.10.0)

The GUI uses the new fields and endpoints; it works around nothing in the API.

29. **`render`/`validate` with `{text}` does not return the scenario header.** When switching YAML → Form
    with unsaved text, the GUI gets `tree` and `errors`, but not `description`, `inputs`, `outputs`
    and `callable`. *GUI:* takes the header from the version on disk and says so with a sentence in the header card:
    “Header taken from the version on disk — header changes made in YAML appear after saving.” *Needed:*
    `header {description, inputs, outputs, callable}` in the `render`/`validate` response with text,
    so that the GUI parses nothing (coordinator's decision 2026-09-26).
