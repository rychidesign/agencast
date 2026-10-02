# Brief for the AgenCast GUI redesign (pen.dev)

## What the application is

AgenCast is a web interface for building and running LLM agent workflows. In it the user manages projects, and within a project scenarios (a sequence of steps), agents, skills and config, starts runs and reads their results (steps, files, cost). The interface is technical and dense: lots of identifiers, paths, expressions and YAML, so a monospace font is used a lot. Primarily desktop, but it must also be operable by touch on a tablet. The interface language is English (with an optional Czech translation). Today it is dark; the dark variant is mandatory, a light one is a bonus.

## What I need from you

A component library in pen.dev, where each component has the states and variants from the list below, plus a simple overall frame of screens. The layout and the visual language are up to you. Name the components and variants after the names in this list, so I can map them to code.

The implementation is React + Tailwind, Lucide icons. If you use Lucide icons I'll carry them over 1:1; another set is possible, but then I need SVGs.

## Foundations

### Typography

- A proportional family for texts and a mono family for identifiers, paths, expressions, YAML, JSON and numbers (tabular figures).
- The sizes I need to distinguish: eyebrow (a small uppercase label, e.g. “STEP 3”, “HEADER”, “START RUN”), page/card heading, section title, body, field label, field help, meta text on cards (counts, time, file).

### Colours

- Three surface levels: page background, card/panel, nested element (field, chip, code block).
- Three text levels: primary, secondary, muted.
- Semantic states, each with an icon and a colour (see States): success, error, warning, running, neutral/waiting.
- Two reserved colours outside the states: one for “variable” (the variable-insert button, variable items), one for “step type” (type icons). They must not be confused with the state colours.
- Dimming for: unavailable, skipped, not reached, cut, disabled.

### Icons

A 16 px set, uniform stroke. I need:

- Step types (10): ask (a question to an agent), task (agent with tools), jev (cheap decision), image (image), parallel (branches in parallel), switch (one of several options), call (another scenario), set (computation without an LLM), fail (stop with an error), output (scenario output) + “unknown type”.
- States (10): success, error, skipped, running, queued, warning, cancelled, interrupted, dry run (plan only), no run.
- Actions: add, delete, copy, copied, reload, back (navigation), undo, run, close, ⋯ menu, expand/collapse, variable {}, code/YAML, key (token), scenario header, flow arrow between steps, open in another context ↗, project availability (dot).

## Components

### 1. Buttons

Variants: primary, secondary, dangerous (delete, overwrite, remove), icon (icon only), a “+ add …” pill (small, next to a section label), the round (+) on the flow connector.
States of each: default, hover, focus (keyboard), disabled, busy with text (“Saving…”, “Starting…”). With and without an icon. A touch size (44 px) as a variant.

### 2. Form field (wrapper)

Label, an asterisk for a required field, an optional action next to the label (e.g. a “+ add” pill), help, error (mono, may be multi-line, contains a ^ pointer to the place of the error).
States: default, hover, focus, disabled, invalid, with help, with an error, required.

### 3. Input types

- Single-line text; a mono variant (identifier, path, file name).
- Textarea; a mono variant (agent instructions, JSON, YAML).
- Number (max_turns, budget, limits).
- Select (agent, model/alias, API chat/images, quality, storage type, scenario filter, status filter, input type).
- Checkbox standalone and in a list (MCP servers and their tools; disabled with the note “not allowed by the owner”).
- A radio with two lines (name + explanation): “Dry run: plan only, no model calls; starts the MCP servers to list their tools” / “Live run: calls models and costs money”.
- Password (server token).
- A chip with removal (agent skills) + a select “add skill”.
- Inline editing of a key (name of an input, output, question, model alias): states valid, invalid format, “already exists”; confirmed by leaving the field.

### 4. Expression / template field (CodeInput)

A mono field, single- and multi-line, with an “Insert variable” button ({} icon) in the variable colour. Button states: default, hover, open, disabled (“No variables available” in the tooltip).

- Autocomplete while typing: a list of mono items, an active item.
- The variables menu after clicking {}: groups “Inputs” and “Step <id>”, mono items, active/hover.

### 5. States (StatusIcon, StatusBadge, StatusChip)

The ten states from the Icons part. Three forms: the icon alone, icon + text, a chip (a pill with an icon and text).
Texts: “succeeded”, “failed”, “skipped”, “running” (the icon pulses), “queued”, “warning”, “cancelled”, “interrupted”, “plan only (dry run)”, “no runs”.
The chip of the last run also carries the time: “✓ 12 min ago”, “✗ yesterday 2:02 PM”, “◌ running”. An error chip with a count: “3 errors” (may be clickable).

### 6. Feedback and empty states

- Skeleton: row, pill, card.
- Empty state: text + an optional CLI line with a command (“This project has no scenarios yet.”, “No runs.”, “Pick a file on the left.”).
- Error text with an icon; a list of validation errors (items with an icon, mono text, the item clickable as a link to the file/step).
- CLI line: a mono command + a copy button, the state “Copied”.
- Bars: “The agencast server is not responding, retrying…” (permanent); the conflict bar “The file changed on disk.” / “The unsaved changes in this browser belong to an older version of the file.” with three actions (Show diff, Reload from disk and discard my changes, Keep mine); a status row after a rename (“Updated: a.yaml, b.yaml”); the config error block (text + list + an “Open Config” link).
- Save state (SaveNote): “Saving…”, “Unsaved”, “Saved ✓ 2:02 PM”, “Reloaded from disk (2:02 PM)”, a save error (text from the API) + an optional error-count chip.
- The live indicator in the run list: “2 running · 1 queued”.
- The daily spend progress bar (“today 1.20 / 5.00 USD”) and the 0–1 probability bar for Jev answers.

### 7. ⋯ menu, tabs, toggle, accordion

- ⋯ menu: the trigger (icon), the open list, an item default/hover/focus, a dangerous item (Delete, Remove from registry).
- Tabs (links): active, inactive, hover; a variant with a count “Calls (3)”.
- A segmented toggle with two options (Form | YAML, Form | Markdown, Create new | Add existing): active, inactive, disabled with a tooltip (“Fix the YAML: line 12”).
- Accordion row: title + value summary + arrow; closed, open, hover. Used for Condition (value “always” or an expression), Reliability (“default” or a list of filled-in fields), Step details.
- A collapsible file tree (folder open/closed, file, selected file).

### 8. Modals

One frame: title, body, actions (primary / secondary / dangerous) + Cancel or Close; a busy state. Content variants:

- New scenario / agent / skill: name (mono, format and collision check), description, model (select).
- New project: a toggle Create new / Add existing, name, path; a variant without write access with only a CLI command.
- Rename (scenario, agent, step): name; for a step a list of the steps in which references will be rewritten.
- Delete (step, scenario, agent, skill, project from the registry): the reason text; a variant “the step is read by other steps” with a list; a variant “this also deletes N steps inside”; a variant of a refusal from the API with the reason.
- Change the step type (what stays, what is discarded).
- Unsaved changes when switching mode: Save and switch / Discard and switch.
- Overwrite the version on disk (a dangerous action).
- Diff against disk: a mono block with rows − and + in colour, “The texts are identical.”
- Scenario validation: loading, a list of errors, or a chip “no errors”.

### 9. Project card (ProjectCard)

Content: an availability indicator (dot + “available”/“unavailable”), name, path (mono), number of scenarios and agents, spend today, the chip of the last run (all states from part 5 including “no runs”), the ⋯ menu (Open, Copy path, Remove from registry).
States: default, hover, focus, unavailable (dimmed, the reason text instead of the counts), skeleton. A special “Add project” card (default, hover).

### 10. Scenario card (ScenarioCard)

Content: a chain of step type icons in order (at most 5, then a “+N” chip), name or description, a meta row (number of steps · agents · inputs · outputs · “callable”), the file name (mono), the time of the last run or “no runs”, the chip of the last run OR a validation error chip (“2 errors”), the ⋯ menu (Open, Runs of this scenario, Copy run command, Validate).
States: default, hover, focus, with validation errors, without runs, with the last run in each state, callable. A special “New scenario” card and the empty state of the list.

### 11. Agent / skill list item

Name (mono), an optional error indicator (“✗ 2 errors”). States: active, inactive, hover. The “New agent” / “New skill” button and the empty state.

### 12. Run row (RunRow) and filter

Columns: status (icon + text), run_id (mono), scenario, when (“5 min ago”, “today 2:02 PM”) or for a running one “running · step 3/7 propose” or “queued (#2)”, duration, cost USD, a note (error reason, “plan only (dry run)”, “interrupted”, “fake run”, callback).
Row states: running (live), queued, succeeded, failed, interrupted, cancelled, dry run; hover. Filters (scenario select, status select), the “Load more” button, an empty state with a CLI command.

### 13. Step card (StepCard) in the editor

Content: the sequence number, the type row (type icon + type name + id mono), the step value, optionally the condition “when <expression>” (mono), an error indicator and error text, card controls (⋯ menu: Move up/down, Cut, Insert step above/below, Delete; a separate trash button).
States: default, hover, selected, focus, with an error, an empty value (“fill in the panel”, muted), with a condition, cut (waiting to be pasted elsewhere), controls hidden/shown (hover, focus; on touch permanently muted).
Value variants by type (examples): ask/task “writer: “Write an introduction…””; jev ““Is the text finished?” · choice; +2 questions”; image “gpt-image · 1:1 · medium · “Product photo…””; call “→ image · 2 inputs”; set/output “title, intro”; fail the message text; parallel “a ∥ b”; switch “by steps.jev.choice: yes, no, otherwise”.

### 14. Step card in a run

The same component; instead of the sequence number a status icon, instead of the condition the duration and cost (mono).
States: running (pulses, elapsed time), succeeded, failed, cancelled, skipped (dimmed, the reason in the value), interrupted, not reached (dimmed), the warning “Warning: the step failed and the run continued (on_error: continue).” as a row at the card.

### 15. Scenario header card (HeaderCard)

An icon instead of the number, the label “HEADER”, the value “2 inputs: prompt, aspect_ratio · 1 output: image” or “no inputs · no outputs”. States: default, hover, selected.

### 16. Step containers (parallel, switch, call)

- The main container card (distinguishable from an ordinary card), a collapse/expand button; the collapsed state shows “N steps”.
- Branch: a label (branch name / “= value” / “otherwise (default)”), inside a list of cards or empty; the text “otherwise: nothing”; the button “+ branch” / “+ case”. Parallel has branches side by side, switch has cases one after another.
- Call: a card with a link “<target> open ↗”; in a run as a container with the steps of the called scenario.
- All also in the run states (see 14).

### 17. Flow connector and adding a step

An arrow between cards; in the editor it turns into a (+) on hover/focus; with a cut step the (+) is shown permanently and highlighted; at the end of the list a permanent (+) + an “+ output” pill.
The type picker (TypePicker): a list of items “keyword (mono) + description” in three groups separated by a line, an active item, a filter row (“filter: as”), “No type matches.”, the item “Paste ‘x’ here”.
Type descriptions: ask “single agent call”, task “agent with tools”, jev “cheap Jev decision”, image “generate an image”, parallel “branches in parallel”, switch “one of several options”, call “run another scenario”, fail “stop the run with an error”, set “compute values without an LLM”.

### 18. Panel (PanelShell) and its contents

Frame: eyebrow, title, a close button, optional actions. Contents:

- Step panel in the editor: the Step type select, the id field (with the format rule), the Condition accordion, fields by type (Agent select; Prompt template; Output schema JSON; Questions as rows: key + question + type + criteria + remove, “+ Add question”; State; Model; Aspect ratio / Quality / Resolution “fixed, or {{ inputs.x }}”; Scenario + Inputs for call, a chip “not callable” with an explanation; Values for set; Message for fail; Max turns; MCP servers checkboxes; Tools), the Reliability accordion (timeout, budget_usd, retry, on_error, default, dedupe_key), the Step details accordion (chips “Reads from” / “Output read by” as links to steps, “nothing”, the link “Open in YAML”), the list of step errors.
- Header panel: description, the toggle “Other scenarios may call this scenario with a call step” with an explanation, Inputs and Outputs as rows (inline name, type select, description, default value, remove; “+ Add input” / “+ Add output”).
- Run panel (“START RUN”): inputs by type (text, number, checkbox, JSON, disabled “a file can only be passed by a call step”), the radio Dry run / Live run, a table of limits (per run, of which images, run timeout, spent today / limit), warnings (“You have unsaved changes — the run will use the version on disk.”, “The scenario has an input of type file…”), an API error, the button “Start dry run” / “Start live run” / “Starting…”.
- Step panel in a run: a status row (badge + duration + cost + “3 turns · 2 tool calls”), skip / warning / error text, tabs by type (Prompt, Response, Output, Calls (n), Tools, Image, Files), contents: a code block (mono, JSON/Markdown), Jev answers (key, value, a 0–1 bar), a call item (attempt · turn · alias → model; provider · finish_reason · HTTP; duration · tokens · cost; an error item with “↻” on retry), a tool item (turn · server.tool; duration; a link to the file; variants “not allowed” / “invalid arguments” / “tool returned an error”), an image, a list of files, the empty state “Nothing to show.”

### 19. Text editors

- YAML editor: line numbers, a highlighted range of the selected step, an error line, read-only with the hint “File x — read-only.”, the hint “You are editing … directly. Changes are written only when you click Save.”
- Agent/skill Markdown editor (a mono textarea) and a Markdown preview.
- A read-only code block (step output, run files), a run image, the report in a frame.

### 20. Agent, skill and config forms

- Agent: description, model (an alias select + the help “An alias from config.yaml, never a concrete model id.”), skills (chips + add), MCP (a server checkbox and tool checkboxes under it; notes “(not allowed by the owner)”, “the server doesn't restrict tools”), limits (max_turns conditionally required with the text “Required: the agent has an MCP server.”, budget_usd, timeout), Instructions (a large textarea), the “Used by” list (links to scenarios). Skill: Markdown + “used by”.
- Config: the Models section (alias rows: alias inline, model id, API select chat/images, quality select only for images, structured_output, max_tokens, delete alias disabled with the reason “The alias is used by writer — it can't be deleted.”, a note “used by 2 agents”; “+ alias”), Jev model, Storage (type select + fields; *_env fields with the indicator “set on the server” / “missing on the server” / “the server doesn't know this variable yet”), Limits, Variables, MCP servers read-only (description, transport, agents, scenarios, tools; one note “MCP servers are set up by the project owner in workflows/mcp.yaml on the server. This page only shows them.”, “This project has no MCP servers.”, and for a project added through the GUI a warning with the command `agencast projects trust <name>` — a command line with Copy, no button that changes trust), the state “config.yaml failed validation — fix it in YAML”.

## Overall frame (screens)

A simple frame into which the components are assembled is enough; the detailed layout is up to you.

1. Server token: a card with a password field, help, the error “The server token doesn't match — the server returned 401.”, Save.
2. Projects: heading, subtitle, registry path (mono), reload, a grid of project cards.
3. Project: back navigation, name, path (mono), spend today + the daily limit progress, run limits, a chip “N errors” with a drop-down list of errors, reload; tabs Scenarios · Agents · Config · Skills · Runs; the tab content (a grid of cards / list + detail / form / runs table).
4. Scenario editor: back (“project / Scenarios”), the call path breadcrumbs, name (mono), description, the Form | YAML toggle, save state, Rename, Delete, Undo, Run, Save; the conflict bar; a column of step cards with connectors; a panel (step / header / run); YAML mode.
5. Run detail: back (“project / Runs”), scenario (mono, link) + run_id, a status badge (for a failure “error: <reason>”), a “fake run” chip, duration · cost, an inputs row (“prompt = “…””), tabs Steps · Summary · Report · Files, the “follow run” checkbox, the hint for an interrupted run, the status row “Run finished: succeeded”; content: a column of step cards in the run + panel, or “The run is waiting in the queue.”, or a dry run with a plan, a Markdown summary, a report, a file tree + viewer.
6. The page “There's nothing at this address.” with a link to Projects.

## Rules that must remain

- Status is always icon + text, never colour alone.
- Identifiers, paths, expressions, YAML, JSON and numbers in mono.
- The step card in the editor and in a run is a single component; they differ only in the content of the number slot and the right part.
- The variable colour and the step type colour must not collide with the state colours.
- Touch targets 44 px on touch devices.
- Everything in English, take the texts from this list.

## Output

One .pen file with a component library (variants = states) and a frame of screens. For each component the name from this list.
