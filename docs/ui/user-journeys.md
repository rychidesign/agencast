# User journeys for Playwright E2E — AgenCast GUI

Design brief from 2026-09-26 and a coverage map of the E2E tests in `ui/e2e/`. The markers
**[done]**, **[worked around]** and **[not done]** capture the state at the time the
scenarios were written; the current coverage is shown by the tests and the current description in `ui/README.md`.

Sources: `docs/ui/gui-design.md`, `docs/spec/api.md`, `docs/spec/projects.md`,
the ui-1/2/3 reports, `docs/ui/api-findings.md` and the implementation in `ui/src/`.

## Common initial state (fixture)

```bash
export AGENCAST_CONFIG_DIR=$TMP/cfg AGENCAST_TOKEN=test-token
agencast new project $TMP/demo          # registry “demo”: agents/writer.md, scenarios/demo.yaml (write → result, input topic default “coffee”)
agencast serve --fake $TMP/fake.yaml --port 8787   # outside a project = registry mode; GUI = the built ui/ (npm run build) at http://127.0.0.1:8787/
```
- `fake.yaml` = a map `step id: [response…]` (fake.py): `write: [{text: "Two sentences."}]`, for a live run `slowly: [{text: "…", sleep: 4}]` (step `slowly` in the fixture `slow.yaml`), for tool calls `probe` (C21). One script per `serve` process → steps with different behaviour must have different ids.
- Playwright `storageState`: `localStorage["agencast.token"]="test-token"` (except C1). Files are verified through `fs` + a YAML parser; the GUI writes only through the API and parses nothing itself.
- Hash paths: `#/` · `#/p/demo` (= scenarios) · `#/p/demo/{agents|config|skills|runs}[/item]` · `#/p/demo/scenarios/<s>?step=<id|_header>&mode=yaml&from=…` · `#/p/demo/runs/<run_id>?tab=…&step=…`.
- Stable hooks that already exist: a step card `button[data-step-card="<id>"]` with `aria-label="Step n: <type> <id>[ — status][ — cut]"` and `aria-pressed`; the header `[data-step-card=""]`; the panel `role=complementary` (an aside with `aria-labelledby=step-panel-title` / `run-panel-title`); the toggle `radiogroup "View"` with `radio "Form"` / `"YAML"` / `"Markdown"`; the ⋯ menu `button "Actions for <name>"` → `menuitem`; the TypePicker `listbox "New step type"` → `option` (text `ask single agent call`); YAML `textbox "scenarios/<s>.yaml"`; the column `section "Scenario steps"`; the tabs `nav "Project sections"` / `nav "Run sections"` with `aria-current=page`.
- Status markers: **[done]** · **[worked around]** = write the test as an expected failure with a note · **[not done]** = the same, the target is only being built.

## Proposed `data-testid`s (where text is not enough)

| testid | where and why |
|---|---|
| `save-status` | the text of the save status in the editor/agent header (changes over time, “Saved ✓ 2:05 PM”) |
| `run-state`, `run-cost`, `run-duration` | the status badge and the mono time/cost in the run header (today without a label) |
| `step-cost-<id>`, `step-duration-<id>` | the right side of a card in a run |
| `add-after-<id>` (or `aria-label="Insert step after <id>"`) | all (+) between cards have the same “Insert step here”, the test currently indexes them |
| `branch-<name>`, `case-<value>`, `case-default` | the branch/case sections have `aria-label` = the raw name |
| `yaml-line-<n>` | a faulty line in the YAML editor is only a class today |
| `conflict-bar`, `server-bar` | both are `role=alert` and collide with field errors |
| `project-card-<name>`, `scenario-card-<name>`, `run-row-<run_id>` | cards and rows (today only a link by name) |
| the step panel in a run: rename the `tablist` to `"Step sections"` | today `"Run sections"`, like the page tabs |

## Journeys (by importance for a beginner)

### C1 First launch: token **[done]**
Goal: get to the projects without a terminal. State: empty localStorage.
1. Open `/` → `h1 "Server token"`, `textbox "Token"` (type=password), the help “In registry mode, the server's AGENCAST_TOKEN variable…”, `button "Save"` disabled; no fetch to `/projects`.
2. Type `wrong`, Enter → `role=alert "The server token doesn't match — the server returned 401."`, the form stays, the token is not in the URL.
3. Type `test-token`, Enter → `h1 "Projects"`, the description “Registry …/cfg/projects.yaml”, the `demo` card **without** the “available” label (G6), with “1 scenario · 1 agent”, “today 0.00 USD”, “no runs”.
Playwright: `localStorage.agencast.token === "test-token"`; `Authorization: Bearer` in the request (route intercept).

### C2 Creating a project from the GUI **[done]**
Goal: a new project without a terminal. State: the registry has only `demo`.
1. `#/` → click “Add project” (a button in the header; the dashed card only for an empty list) → a dialog (`role=dialog`) “New project”: `textbox "Name"` (a slug; the typed name is corrected while typing — `Café Crème` → `cafe-creme`; error ““demo” already exists.”), `textbox "Path"`, `button "Create"`.
2. `my-web` + `$TMP/my-web`, Create → `#/p/my-web`, `h1 "Scenarios"`, the name “my-web” and `nav "Project sections"` in the sidebar (the project path is not on the page, G5), the scenario card `demo` with the subtitle “Write a short text on a given topic” and the meta “2 steps · writer” (without the number of inputs/outputs and without “demo.yaml”, G7).
3. Disk: `my-web/workflows/config.yaml`, `agents/writer.md`, `scenarios/demo.yaml`, `.env.example`, `.gitignore`; `cfg/projects.yaml` has `name: my-web, root: …, trusted: false` (registered over HTTP = no MCP servers until `agencast projects trust`, C21).
4. Back to `#/` → two cards. A name/path collision → an API error in the dialog (`role=alert`), nothing was created.

### C3 New agent **[done; the dialog has no description or model although API 0.8.0 supports them — the template writes `description: TODO`]**
Goal: an agent with its own instructions. State: `demo`.
1. `#/p/demo/agents` → one section header: `h1 "Agents"`, `button "New agent"` (secondary), `button "Save"` and the ⋯ `button "Actions for writer"`. On the left `nav "Agents"` with a 200 px list (48 px items, icon, active ring), on the right `h2 "writer"` above the editor card (`bg-surface`, radius 16, padding 24). The first row of the card is `radiogroup "View"` and the save status; inside the card there is no other title or Save.
2. New agent → the dialog “New agent”, `textbox "Name"` (autofocus); `Wrîter` is corrected while typing to `writer` → ““writer” already exists.”; `proofreader` → Create.
3. → `#/p/demo/agents/proofreader`, `h2 "proofreader"`, a card with `radiogroup "View"` (Form | Markdown) and the `save-status` testid “Saved ✓”; the field `textbox "description"` (contains `TODO`), `combobox "model"` = `smart`, skills and MCP servers as lists of checkboxes in `bg-nested`, limits in three columns, `textbox "Instructions (system prompt)"` (at least 12 rows, the footer “Supports Markdown”), “Used by: –”. Disk: `agents/proofreader.md` with the frontmatter `model: smart`, `budget_usd: 0.02`.
4. Description “Checks spelling”, instructions “Fix only mistakes.” → “Unsaved” → Ctrl+S → “Saved ✓ HH:MM”; disk: `description:` changed, the body replaced, the other lines unchanged.
5. Switch `radio "Markdown"` → `textbox "agents/proofreader.md"` with the whole file including `---`; the hint “You are editing workflows/agents/proofreader.md directly. Changes are written only when you click Save.”
6. `button "Actions for proofreader"` → `menuitem "Delete"` (red, last; before it “Reload” and “Rename”) → the dialog “Delete agent “proofreader”?” → Delete → back to `#/p/demo/agents`, only `writer` in the list, the file gone. Variant: delete `writer` → in the dialog a `role=alert` “agent 'writer' cannot be deleted — used by: demo”, the file stayed.

Skill: `#/p/demo/skills` → “New skill” creates `skills/research/SKILL.md`; the 200 px list has 48 px items and a book icon. On the right is `h2 "research"` above the card, in it the Markdown editor and “Used by”. In the agent tick `research` in the list of skills → Save → the link is written to `agents/writer.md`; after returning to the skill the link “writer ↗” leads back to the agent. Test `fidelity-agents-config.spec.ts`.

### C4 New scenario with two steps and `output` **[done; saving = several operations in a row, not a batch → finding 11 worked around]**
Goal: your own scenario “write and check”. State: `demo` with `writer`.
1. `#/p/demo` → click `button "New scenario"` (primary in the section header) → a dialog: `textbox "Name"` (help “Also used as the file name.”), `textbox "description"`; `article` + “Writes and rates an article” → Create.
2. → `#/p/demo/scenarios/article?step=_header`; the header `h1 "article"` + the description; a `complementary` panel with the eyebrow “HEADER”, `textbox "description"` = the entered text, the section “Inputs” (row `topic`, `checkbox "required"` unchecked, `textbox "Default value of topic"` = `coffee`) and “Outputs” (`text`). Cards: `[data-step-card=""]` “1 input: topic · 1 output: text”, “Step 1: ask write” (value `writer: “Write two sentences about…”`), “Step 2: output result” (“text”). Disk: `scenarios/article.yaml` with `description: Writes and rates an article`.
3. Click the second `button "Insert step here"` (between write and result; proposed `add-after-write`) → `listbox "New step type"`; type `j` → `option "jev cheap Jev decision"` remains; Enter → a new card “Step 2: jev jev_1” named “2. jev_1”, the panel “STEP 2”, `combobox "Step type"` = jev, `aria-live` “Added step jev_1.”, URL `?step=jev_1`, `save-status` “Unsaved”.
4. `combobox "State"` → `{{ steps.` → the autocomplete `listbox` offers only `steps.write.text` (Enter completes it); click `button "Add question"` (a text button in `type` with a + icon) → row `q_1`: `textbox "Name"`, `combobox "Question type for q_1"`, `combobox "Question"`; rename to `ok`, the question “Is the text in English and without mistakes?”.
5. The card “Step 3: output result” → panel, `combobox "text"` = `{{ steps.write.text }}`; collapsed rows “Condition always”, “Step details result” (`aria-expanded`).
6. `button "Save"` → “Saved ✓”, `POST …/scenarios/article/batch` 200. Disk: id order `[write, jev_1, result]`, the block `jev: {state, questions: {ok: {type: noul, instructions: …}}}`, the template comments preserved. The `article` card in the overview: title `article`, subtitle “Writes and rates an article”, meta “3 steps · writer”, without the `.yaml` name; the icon chain `aria-label "Step types: ask, jev, output"`.

### C5 Validation with an error and fixing it — in the panel and in YAML **[done; Form validates via `render`, YAML → Form converts unsaved text via `render {text}`]**
Goal: understand what is wrong and fix it without a terminal. State: `demo/demo`.
1. The `demo` editor, the card `write` → `combobox "Prompt"` → `Topic: {{ steps.missing.text }}` → Save.
2. → within 500 ms `save-status` “Unsaved · 1 error”, the chip `button "1 error"` (a click jumps to the step), below the `write` card and below the field the text `step 'missing' does not exist (available: …)`, the field `aria-invalid=true`; disk unchanged (etag).
3. Fix to `Topic: {{ inputs.topic }}` → Save → “Saved ✓”, errors gone; disk has the new prompt on one line (quoted because of `{{ }}`).
4. `radio "YAML"` → `textbox "scenarios/demo.yaml"`, the hint with the file name, Save disabled. Break the indentation of the line `- id: write` → within ≤ 1 s a list of errors “line N · …” (a click = the cursor on the line), a mark at the line (`yaml-line-N`), Save disabled; a click on Form opens the dialog “Unsaved changes”.
5. Restore the indentation, change `agent: writer` to `agent: nobody` → error “write · agent 'nobody' does not exist…”, Form is now allowed, Save is still disabled (per §4.5). Fix it → no errors, Save enabled → `PUT files/…` → “Saved ✓”; going back to Form selects the step under the cursor (`?step=write`).
6. Valid YAML with unsaved changes → Form takes over the tree via `POST …/render {text}` without a dialog and without writing. The dialog “Unsaved changes” stays for YAML with a syntax error.

### C6 Starting a run with an input form (dry run, live, in-progress) **[done; after 202 the GUI also reads the `dry_run` state for 15 s (the URL-flag hack, finding 15 — no longer needed since 0.8.0 and gone from the GUI)]**
Goal: start a scenario and see that it is running. State: `demo` + the fixture `slow.yaml` (step `slowly` with `sleep: 4`).
1. The `demo` editor → `button "Run"` → a panel with the eyebrow “START RUN”, `textbox "topic"` prefilled with `coffee`, the help “string · What to write about”, `group "Run mode"` with two cards (a radio inside, a click anywhere on the card selects, the selected one has a ring), `radio "Dry run"` checked (help “Plan only (plan.md): no model calls; starts the MCP servers to list their tools.”), on the right `button "Cancel"` (closes the panel like ✕ and Esc) and `button "Start dry run"`; limits only for a live run (PN2).
2. Clear topic, `checkbox "required"` is on in the fixture (a scenario variant without a default) → submit → below the field “Required input.”, no POST.
3. `topic` = “new coffee”, Start dry run → `POST /projects/demo/runs {dry_run: true}` 200 → `#/p/demo/runs/<run_id>`, `run-state` “plan only (dry run)”, the text “This is only a plan (dry run) — no step ran and no model was called; MCP servers the scenario uses were started only to list their tools.”, the rendered `plan.md`. Disk: `demo/runs/<run_id>/plan.md`, `inputs.json` (`{"topic":"new coffee"}`), no `events.jsonl`.
4. Start again, `radio "Live run"` → `dl "Run limits"`: “per run 1.00 USD”, “run timeout 1h”, “spent today 0 / 5.00 USD” (spend ignores fake runs); with an unsaved change also a warning with an icon “You have unsaved changes — the run will use the version on disk.” → `button "Start live run"` → 202 → `#/p/demo/runs/<run_id>`.
5. On `slow`: the header “running”, the chip “fake run”, the card `[data-step-card="slowly"]` `aria-label` “… — running” (pulse), the time ticks, `aria-live` “step slowly running”, `checkbox "follow run"`; after ≈ 4 s `role=status` “Run finished: succeeded”, the card “— succeeded”, the checkbox disappears, polling ends (no further GET within 6 s).
6. The `Runs` tab: a `run-row` with an icon + sr “running”, “step 1/2 · slowly” (the status is not repeated in the row), “fake run”, on the right “1 running · 0 queued”; two starts at once → the second “queued (#2)”. Disk: `runs/<run_id>/{run.lock, events.jsonl, scenario/slow.yaml, steps/01-slowly/…, summary.md, report.html}`.

### C7 Reading the result and the cost **[done]**
Goal: understand what the run produced and what it cost. State: a finished `demo` run (C6).
1. Detail: above the title “← Runs”, `h1` = the link `demo` + a small mono `run_id`, `run-state` “succeeded”, `run-duration` `\d+\.\d s`, `run-cost` `/^(0|\d+\.\d{4,}) USD$/` (a decimal point, USD after the number), the row “Inputs topic = “new coffee””, `nav "Run sections"` = Steps · Summary · Report · Files.
2. Cards: “Step 1: ask write — succeeded” with the value `smart → anthropic/claude-haiku-4.5` and on the right time + cost; “Step 2: output result — succeeded” with the value. A click on `write` → the panel “STEP 1 · write”, `tablist` with `tab "Prompt"`, “Response”, “Output”, “Calls”, “Files”; Calls: “attempt 1”, `alias → model`, “N + M tokens”; Output = JSON `{"text": "Two sentences."}`; `GET …/runs/<id>/steps/write`.
3. `tab "Summary"` → Markdown with the section “Total”; `tab "Report"` → `iframe[sandbox]` (title “Run report”); `tab "Files"` → `nav "Files"` with a tree, a click on `summary.md` → text, `?file=`.
4. Back to `#/p/demo`: the `demo` card has the chip of the last run (a success icon + “just now”) as the only time on the card (G7); the sidebar “Spent today” `spend-today` “0.00 USD” (+ “/ limit” if there is a daily limit; the fake ledger is separate — so it is always 0 in the test; a target with a live run is untestable).
5. The run list (without a run_id column and without spend, G9; status = icon + text, run_id in the row's `title`): filter `combobox "Scenario filter"` = demo → only its rows (`?scenario=demo&limit=50`), `combobox "Status filter"` = succeeded; duration/cost columns mono; “Load more” only at 50+.

### C8 A failed run (fail) **[done]**
Goal: recognise where and why the run ended. State: the fixture `failing.yaml`: `write → stop (fail: "Stopped on purpose") → result`.
1. Start a live run → the header `run-state` “error: fail in stop” (an `error` icon + text; the API `status` string is `failed (fail in stop)`), the Summary has the heading “— failed” and an **Error** block.
2. Cards: `write` “— succeeded”, `stop` “— failed” with the value = the message, `result` “— not reached” (a dashed outline, the `aria-label` ends with “— not reached”). The `stop` panel: the message with the class `fail`.
3. A skipped step (a variant with `when: false` and `default`) → the card “skipped: when … → false” + “default used”; `on_error: continue` → the row “Warning: the step failed and the run continued (on_error: continue).”
4. Run list: the note “fail in stop · fake run”; the scenario card chip “failed”. Disk: `events.jsonl` has `run_finished status: failed`, `summary.md` contains “Stopped on purpose”.

### C9 File conflict (a change on disk during editing) **[done]**
Goal: lose neither your own nor someone else's change. State: the `demo` editor, the card `write` selected.
1. Change the Prompt (Unsaved). The test via `fs.appendFile` adds the comment `# by hand` to `demo.yaml`.
2. Within 5 s (or after `window.dispatchEvent(new Event("focus"))`) → `conflict-bar` “The file changed on disk.” with the buttons “Show diff”, “Reload from disk and discard my changes” (dangerous, red) and “Keep mine” below the text; Save disabled.
3. “Show diff” → the dialog “Diff against disk”, the note “− is the version you started from, + is the file on disk now.”, the line `+ # by hand` in green → Close.
4. “Keep mine” → the bar disappears, Save → the dialog “Overwrite the version on disk?” → “Overwrite the version on disk” → `PATCH` with the current etag → “Saved ✓”; disk has both `# by hand` and the new prompt.
5. A variant without local changes: an edit on disk → a silent reload, `save-status` “Reloaded from disk (HH:MM)”, the card shows the new text. A variant after a page reload with a draft in progress for the old version → the bar “The unsaved changes in this browser belong to an older version of the file.”

### C10 Moving and deleting a step with reference protection **[done; deleting a read step + updating the readers currently goes as two operations, the 0.8.0 batch is not used → 422 if the second operation is late]**
Goal: rearrange a scenario and not break references. State: `article` from C4 (`write, jev_1, result`).
1. Focus the card `jev_1` (click), `Alt+↑` → `aria-label` “Step 1: jev jev_1”, `write` is “Step 2”; the ⋯ menu “More actions” in the header → `menuitem "Undo"` (shortcut Ctrl+Z on the right, or Ctrl+Z on the keyboard) reverts; the menu `"Actions for jev_1"` has `menuitem`s “Move up” (Alt+↑ on the right), “Move down” (Alt+↓), “Cut” (Ctrl+X), “Insert step above”, “Insert step below”, a red “Delete” (Del). On a touch device the shortcuts are hidden.
2. `Ctrl+X` on `jev_1` → `aria-live` “Step jev_1 cut — paste it with the + button in its new place.”, the card at 50 % with “— cut”, all (+) permanently visible; click + above `write` → the first `option` “Paste “jev_1” here” → Enter → “Step jev_1 pasted.”, order `[jev_1, write, result]`; validation at the card `jev_1` reports `steps.write` further down (after Save a 422 “step 'write' comes later — expressions can only reference preceding steps”) → Ctrl+Z.
3. Delete on `write` (read by `jev_1` and `result`) → the dialog “Delete step “write”?” with the text “Step “write” is read by jev_1, result. Saving only succeeds if you update their references or delete them too — everything is written at once, or nothing.” → “Delete anyway” → `aria-live` “Step write deleted. Undo: Ctrl+Z.”; Save → 422 with a message at `result`, disk unchanged. Target (batch): updating the readers + the deletion in one batch, everything is written or nothing.
4. Delete on `jev_1` (nobody reads it) → gone immediately, without a dialog; the same deletion is triggered by ⋯ → “Delete” or the trash in the panel header. Save → `DELETE …/steps/1` → disk has `[write, result]`. Deleting a container with steps → the dialog “This also deletes N steps inside.” The `output` card has no Move/Cut/Insert below; there is no separate trash next to cards.

### C11 `parallel` and `switch` **[done — a new branch must start with a new step (finding 13); renaming/deleting branches only in YAML]**
Goal: “side by side = at the same time, one below another = one of the options”. State: `article`.
1. + after `write` → `option "parallel branches in parallel"` → a card (a rounded rectangle) “Step 2: parallel parallel_1”, the panel “Branches: . Add steps to them with the + button in the card.”; `button "+ branch"` → a dialog “branch” `textbox "Name"` (`^[a-z0-9_]+$`) → `short` → `section "short"` with `h4 short` and `button "Add step at the end"`; the same for `long`. Save without a step in a branch → `save-status` “New branch in step parallel_1 must start with a new step.” (locally, without a POST).
2. In each branch + → `ask` → agent `writer`, prompt → Save → one `POST …/steps` with the whole step `{id, parallel: {short: [...], long: [...]}}`; disk matches; the card has the meta “short ∥ long · 2 branches, run in parallel”; the TypePicker inside a branch does not offer `output`.
3. `button "Collapse parallel_1"` (`aria-expanded`) → the inside disappears, the text “2 steps”; “Expand parallel_1” brings it back.
4. + → `switch` → the panel `combobox "Value"` = `steps.jev_1.ok`, the section `"otherwise (default)"` is always visible; `button "+ case"` → a dialog “case” (`pattern [^/]`) → `= true`; add steps; Save → disk `switch: {value, cases: {"true": [...]}, default: [...]}`; without `default` → the text ““otherwise” is required” in the panel and a 422 from the API.
5. In a run (fixture `branches.yaml` + fake): the unselected case is dimmed with a reason, cards in branches with a status; `call` expands in the card (`section "<target>"`).

### C12 Renaming a step with reference rewriting (batch) **[worked around — the GUI does not let you rename a read step and offers YAML; the API 0.8.0 `batch rename_step` exists]**
Goal: rename `write` to `article_text` and break nothing. State: `demo` (`result` reads `steps.write.text`).
1. The card `write` → the panel → `button "Step details"` (`aria-expanded=true`) → `textbox "id"`, chips “Reads from: nothing”, “Output read by: result” (a click on the chip selects `result`), the link “Open in YAML” (`?mode=yaml&step=write`).
2. Today: overwrite the id, Tab → below the field “Step is read by result — renaming would break their references and the API will not save it one operation at a time.” + the link “Rename with references in YAML mode”; the id does not change.
3. Target: Tab → the card “Step 1: ask article_text”, the card `result` without an error, `?step=article_text`; Save → `POST …/scenarios/demo/batch` with `rename_step` (`rename_refs: true`) → disk: `- id: article_text` and in `result` `{{ steps.article_text.text }}`, comments preserved; `aria-live` “Saved ✓”. The id is corrected while typing (`Résult` → `result`, `1` → empty); an empty or existing `result` → “Lowercase letters, digits and _; starts with a letter.” / ““result” already exists.” and no change.

### C13 Adding an existing project **[done]**
State: the folder `$TMP/foreign` created by `agencast new project` **without** the registry (a different `AGENCAST_CONFIG_DIR` at creation), then removed from the registry.
1. `#/` → “Add project” → a dialog with the toggle “Create new” / “Add existing” (or a second button) → `textbox "Path"` = `$TMP/foreign`, the name prefilled `foreign` → Create/Add.
2. → the card `foreign` with counts; `cfg/projects.yaml` has a second entry (with `trusted: false`); on disk `foreign/` is unchanged (no new files). A path without `workflows/config.yaml` → an error in the dialog `role=alert` (the API text), nothing written. The same path a second time → a collision error with the `--name` hint.

### C14 Removing a project from the registry **[done]**
1. `#/` → `button "Actions for foreign"` → `menuitem "Remove from registry"` → the dialog “Remove “foreign” from the registry?” with a sentence that the files stay → confirm.
2. → the card disappears without a reload, the registry without the entry, `$TMP/foreign/workflows/` untouched; a direct `#/p/foreign` → `role=alert` with the 404 text + the link “Projects”. Removing an unavailable project works the same (an “unavailable” card has the menu).

### C15 Keyboard journey without a mouse **[done; ⋯ is reachable via Tab]**
Goal: the whole of C4 by keys only. State: `demo`.
1. `#/` Tab → the link `demo` (Enter) → `h1 "Scenarios"` → Tab through `nav "Project sections"` in the sidebar → “New scenario” Enter → a dialog (focus in “Name”, Tab cycles inside, Esc closes) → name, Enter = Create.
2. In the editor: Tab to `[data-step-card=""]`, `↓` → `write` (`document.activeElement` = the card), Enter → the panel (`?step=write`), focus in the panel; Esc → the panel gone, focus back on the card `write`.
3. Tab from the card → `"Actions for write"` → (+) `"Insert step here"` (focus makes it visible); Enter on + → the `listbox` has focus, typing filters (`aria-live` “filter: j”), Enter selects, Esc returns focus to +. Deleting is in ⋯ or on the Delete key.
4. `Delete` on a card = deletion with a dialog (focus on the first button), `Alt+↓` move, `Ctrl+X` cut, `Ctrl+Z` undo, `Ctrl+S` save (not inside a textarea for Ctrl+Z); the ⋯ menu: Enter opens, `↓` cycles the `menuitem`s, Esc returns focus to the button.
5. Check: every focused element has a visible ring (`focus-visible`), the Tab order = the document order, `aria-live` texts are present in the DOM (Playwright `getByRole("status")` / `[aria-live]`).

### C16 Mobile width 375 px (panel as a sheet) **[done — the panel is a sheet at the bottom over the column below 1280 px; agents and skills below 1100 px as cards with the editor in a bottom sheet; the runs table scrolls horizontally; test `mobile.spec.ts`]**
Viewport 375×667 (iPhone SE emulation, `pointer: coarse`).
1. `#/p/demo/scenarios/demo` → cards in one column, `document.documentElement.scrollWidth <= 375`; the editor header wraps (Form/YAML, status, Save visible without horizontal scrolling).
2. Click a card → `complementary` has a `boundingBox` at the bottom edge (`y + height ≈ 667 - 16`), height ≤ 70 % (≤ 467 px), covers the cards (a sheet), a shadow; Esc / `button "Close"` hides it.
3. `pointer: coarse`: deleting a step is in ⋯ and in the panel; button targets ≥ 44 px (measure `+` 28 px → **fails**, record as a finding, not a test failure).
4. `#/p/demo/agents` and `#/p/demo/runs` → no width overflow: `nav "Agents"` above the editor's `h2`, the runs table in a scroll container (`region "Runs"`).
5. Starting from mobile: the panel “START RUN” as a sheet, `textbox "topic"` font ≥ 16 px (otherwise iOS zooms), the button “Start dry run” at full width.
6. Tablet (768 and 1024 px, manual check of wave C): below 1024 px a top bar instead of the sidebar; the scenario editor has the panel as a sheet over the column (from 1024 px offset from the sidebar) with a close cross, next to the column only from 1280 px; the alias row in Config wraps without overflow.

### C17 Model alias in Config **[done — tuned 2026-09-26, 0.10.3]**

1. Config → the radius 16 card has as its first row the project path (mono 13), the Form | YAML toggle and the save status; Connection | Jev model are side by side. “+ Add alias” adds a nested card `model-1`; the Alias field takes the name as for an agent (lowercase letters, digits, hyphen — `gpt-image`), an invalid one is reverted when leaving the field and the rule is in the field's `title` and below the list.
2. Model id, Save → `PUT …/config` (merge patch); the new alias is written into `config.yaml` in the same line style `{ id: … }` as the others, renaming deletes the old key first.
3. Below each alias card is the meta “used by writer” or “unused”; a used alias has “Delete alias” inactive with the reason in `title`. Storage | Webhook and callback and Limits | Variables are in column pairs; variables are 40 px rows with a coloured status and an MCP server has a nested card with a “Read-only” chip.
4. After loading, the alias is in the agent's model menu. Test: `editor.spec.ts` “C17”, `fidelity-agents-config.spec.ts`; the Config header has `h1 "Config"`, a single Save and a ⋯ with “Reload”. The project path and the only Form | YAML toggle are in the card.

### C18 Inserting a variable from the menu

1. `demo` → step `write` → Prompt; click in the middle of the text → “Insert variable” → `inputs.topic`. The variable is inserted at the cursor as `{{ inputs.topic }}` and both focus and cursor stay in the field.
2. Save → “Saved ✓”; `project.read("scenarios/demo.yaml")` contains the inserted template.
3. By keys: Tab from the field to the button → Enter → arrow down → Enter; the same result. Test: `editor.spec.ts` “C18”.

### C19 Renaming a scenario and an agent

1. In the scenario editor open the ⋯ menu “More actions” → “Rename”; in the Agents section the ⋯ menu in the header
   (`button "Actions for <agent>"`) → “Rename”. The dialog prefills
   the current slug and rejects an invalid or taken name; with an unsaved draft
   it first offers to save or discard it.
2. The confirmation sends `POST …/scenarios/<old>/rename` or
   `POST …/agents/<old>/rename` with `{etag, name}`. A scenario also rewrites
   `call.scenario`; an agent rewrites references in `ask`/`task` and the `agents`
   lists in `mcp.yaml` (the only change the API makes to that file). Comments stay.
3. On success the draft of the old path disappears, the list refreshes and the editor moves to
   the new name. When several files changed, their paths are shown.
   `runs/` does not change; older runs still show the original name.
   E2E: `editor.spec.ts` “C19” verifies renaming `demo` → `intro`,
   the link from another scenario via `call`, the file contents and the new URL.

### C20 Shell: sidebar, headers and the bar below 1024 px (redesign V3, 0.16.0)

1. `#/` → the sidebar with only the logo (`link "agencast"`) and the language switch, without “Spent today” and without “server available”;
   “Add project” is the only button (in the header) until the list is empty.
2. The `demo` card → `nav "Project sections"` = Scenarios · Agents · Runs · Skills · Config, the active one
   `aria-current="page"` (exactly one); at the bottom “Spent today” and `spend-today` “0.00 USD” (with a limit
   “0.00 / 5.00 USD” and a bar). Click Runs → `#/p/demo/runs`, `h1 "Runs"`. The scenario editor highlights
   Scenarios, the run detail Runs. “← Projects” leads back.
3. The `demo` editor: `h1 "demo"`, the buttons “Run” and “Save” (disabled without changes), no visible
   “Rename”; `button "More actions"` → `menuitem` Undo (Ctrl+Z on the right) · Copy run command ·
   Runs of this scenario · Rename · Delete; “Runs of this scenario” → `#/p/demo/runs?scenario=demo`
   with a preselected filter.
4. Viewport 900 px: the bar at the top contains the logo and the project; the 56 px FAB “Navigation” at the bottom right opens
   a menu with projects, 48 px items, today's spend and the language switch. Esc, a click outside and selecting an item close it; `scrollWidth ≤ 900`.
5. Every project section has a single header (`h1` = the section name) and in ⋯ “More actions” first
   “Reload” (formerly an icon). Scenarios: “+ New scenario”; Agents / Skills: “+ New agent” / “+ New
   skill” + Save + ⋯ “Actions for <name>”; Config: the project path as the description + Save. There is neither a second Save nor a
   second mode toggle on the page (G1–G3).
   E2E: `redesign-shell.spec.ts` R1–R3, `redesign-panels.spec.ts` PN3–PN4, `redesign-integration.spec.ts` IC1–IC2, `projects.spec.ts` N2
   (Reload via ⋯), vitest `editor.test.tsx` (a single `h1 "Agents"`).

### C21 MCP servers are the owner's (0.18.0)

State: a project created by `POST /projects/new` (`trusted: false` in the registry, like every project of the fixture);
on disk the owner's `workflows/mcp.yaml` with the framework's fake stdio server `fs` (`framework/tests/fake_mcp_server.py`,
`timeouts: { call: 6s }`), the agent `tester` and the scenario `tools` with one `task` step `probe`.
1. Config → the section “MCP servers”: once the sentence “MCP servers are set up by the project owner in
   workflows/mcp.yaml on the server. This page only shows them.”, the card `fs` (description, `stdio`, `tester`,
   a “Read-only” chip) and `untrusted-notice` with `agencast projects trust <name>`; its only button is “Copy command”.
   `radio "YAML"` → one `textbox "config.yaml"` and the same card below it. No request contains `mcp.yaml`
   (`GET …/files/mcp.yaml` is a 404).
2. Agents → `tester`: tick `fs`, “Tools of fs” = `red_pixel, slow`, Save → “The change failed validation …”, the
   message “… MCP servers (fs) are disabled — … agencast projects trust <name>”; the file on disk is unchanged.
   The owner then writes `mcp: [fs]` into the agent by hand.
3. The `tools` editor → Run: `untrusted-notice` with the command in the panel; “Start dry run” → `role=alert`
   “scenario 'tools' or its inputs failed validation” with the same message, the address does not change. The
   `demo` scenario (no MCP) has no notice.
4. `agencast projects trust <name>` in a terminal → after loading again neither Config nor the Run panel shows the notice.
5. A live run of `tools` (fake: `fs.red_pixel`, then `fs.slow` for 60 s): the step panel → Tools shows `fs.red_pixel`
   and “Server log (stderr): mcp/fs.stderr.log”; the link → Files with “The stderr log of a local MCP server is written
   when the server stops …” and no 404 request. After 6 s the call times out, the run fails, the server stops and the
   same page shows the log (“fake-mcp: root …”). Tools: the row `fs.slow` in `bg-error/10` with “tool fs.slow did not
   respond within 6 s (may have run)”.
   E2E: `mcp.spec.ts` “C21”; vitest `mcp.test.tsx` (read-only section, notice, Tools, pending log).

## Negative and edge states

- **N1 Server not responding** — State: `page.route("**/projects*", r => r.abort())` or a stopped `serve`. Expectation: `server-bar` `role=alert` at the bottom of the sidebar (in the top bar below 1024 px) “The agencast server is not responding (127.0.0.1:8787), retrying…”, the content stays (the last data), no extra error message; after the route is restored the bar disappears on its own within 5 s. In an editor with a change in progress “Unsaved” stays and the draft in `localStorage` (`agencast.draft.*`). **[done]**
- **N2 Wrong token** — see C1 step 2; in addition: a valid token → the server restarted with a different `AGENCAST_TOKEN` → the first 401 brings back the token screen with an alert, the token in localStorage is overwritten only by a new entry. **[done]**
- **N3 Unavailable project** — State: the registry contains `stale` with a `root` without `workflows/config.yaml`. `#/` → an “unavailable” card (a dashed frame without a fill) with the reason “missing …/workflows/config.yaml” from `reason`, the menu only Open/Copy path, no detail GET; `#/p/stale` → `role=alert` with the API 404 text. An unknown name `#/p/absent` → the same; `#/x` → in the shell with the logo the header `h1 "There's nothing at this address."` + the link “Projects” (the look of a secondary button). **[done]**
- **N4 Broken config** — State: in `demo/workflows/config.yaml` a duplicate key `runs_dir` (or `limits.run_budget_usd: "x"`). `#/p/demo` → `role=alert` “The project's config.yaml failed validation: …” + a list + the link “Open Config”; the Config tab goes straight into YAML (Form disabled with “config.yaml failed validation — fix it in YAML”), the error “line 20 · …” with a mark for syntax; a schema error with text only (finding 23, **[worked around]**); the Runs tab works; a fix in YAML + Save → the alert disappears, Scenarios load. **[done]**
- **N5 Interrupted run** — (a) the CLI `agencast --project $TMP/demo run slow --fake $TMP/fake.yaml` and `kill -9` in the middle of `sleep` → the detail “interrupted” (a `warning` icon), the sentence “The run ended without an end record (the process crashed or was killed); the GUI no longer polls it.”, the card `slowly` “— interrupted” (does not pulse), no further GET within 6 s; the list: the status column “interrupted”, the note only “fake run” (the status is not repeated in the note). (b) A run started from `serve`, `serve` killed and started again → the API appends it as `failed (internal in None)`, the GUI shows “error: internal in None” (findings 21/22, **[worked around]** — report the expected text as a known defect). **[done]**
- **N6 Leaving with unsaved changes** — a `beforeunload` dialog on reload (Playwright `page.on("dialog")`), after accepting, the draft is still in localStorage and after returning “Unsaved” + text (C5 var.). Navigation via a hash link (back to Scenarios) **does not ask** — design §4.4 wants it; **[worked around]**.

## What a test will not capture
- The Buzz look: the surface ladder, the selected card's ring, the pulse, hover states, `prefers-reduced-motion` — only screenshots (a screenshot diff) with a tolerance, not asserts.
- Performance (LCP, bundle size 96 kB gz, 20 cards × N+1 for projects — finding 24) and behaviour with hundreds of runs (the cursor, finding 25).
- Real models, costs and `spend` (the fake ledger is separate → “today 0 USD” always), callbacks, R2 storage, real MCP servers (C21 uses the framework's fake stdio server).
- The iframe in a host dashboard (`postMessage` with the path), CORS with `vite dev`, real screen readers (only the ARIA structure), the system clipboard (“Copy” only with `clipboard-read` permissions).
- Time captions (“3 min ago”, “yesterday 2:03 PM”) and the `title` with UTC — test with a regex, not by value.

## The designer's questions and the coordinator's decisions (2026-09-26)

1. *Tests against the built GUI from `serve`, or against `vite dev` + `--cors`?* — **Against the built GUI from `serve`** (one address, the same path as in production). `npm run e2e` builds `ui/` first.
2. *One `serve --fake` for the whole test run, or per worker?* — **One `serve` per Playwright worker** with its own port and its own `AGENCAST_CONFIG_DIR`; every test creates its own project (named after the test), so writes do not cross. Variants of the fake provider's behaviour via different step ids in one script.
3. *The new project form: name + path, or a derived path?* — **Name + path, the path prefilled from `projects_root` (`<projects_root>/<name>`) and editable.** The toggle “Create new” / “Add existing” in one dialog.
4. *Renaming with references: silently, or ask?* — **Ask once: “Rewrite references in N steps?”** with a list of steps; confirming sends the `rename_step` batch with `rename_refs: true`. Without readers, without a dialog.

## Dialogs (0.16.2)
A dialog has a header with a title and a “Close” cross (an info dialog without actions has only “Close” at the bottom) and a footer
“Cancel”, then the actions. Focus after opening is on the first action (or on the field with `data-autofocus`), Tab cycles inside
(from the last action to the cross), Esc and a click outside close it. On a phone the dialog is a bottom sheet with round top corners,
a shadow and a visible strip of the page above it. Test: `redesign-elements.spec.ts` P3, `fidelity.spec.ts`.
