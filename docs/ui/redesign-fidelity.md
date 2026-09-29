# V3 design fidelity — differences between the deployed GUI (0.16.0) and the `.pen`, and what should change

The coordinator compared screenshots of the deployed GUI (1440 px) with the frames of the design
`docs/ui/design/agencast-design.pen` (a local pen.dev working file, not tracked in git; exports in `docs/ui/design/ref/png/`, exact component values
in `docs/ui/design/ref/component-specs.md`, HTML with Tailwind classes in `ref/html/`).
The structure (sidebar, cards, column of steps, panel) matches, but **the scale, shapes and density do not**:
the GUI is a class smaller, flatter and darker than the design. This document is the binding brief for wave E.

**Wave F (2026-09-28):** the values below were reconciled with the `.pen` (HTML export and 1440 px PNG frames). Where the
first estimate differed, the value says “measured from the .pen”; the coordinator decided: the `.pen` wins, above it only §11 and
`redesign-plan.md` §2.

The simplification rules from `redesign-plan.md` §2 still apply (one header, one Save, ⋯ menu,
no duplicates, no “available” / `skills[]` labels etc.). Where the design shows something that §2 removes,
§2 stays. Everything else should look **like the design**, including the sizes in px.

## 0. Tokens — add to `ui/src/index.css` (owned by E2, the others use them)

| token | value | use in the design |
|---|---|---|
| `--color-control` | `#31455F` | fill of the secondary button and the icon button (`V3 / Button / secondary`, `V3 / IconButton`) |
| `--color-control-hover` | `#3B5170` | secondary button hover |
| `--color-surface-active` | `#253B50` (measured from the .pen; the estimate was `#1B2A3D`) | active sidebar and list item, selected step card |
| `--color-group` | `#132032` (between the `surface` card and the `nested` field) | a box grouping fields; the fields themselves stay `nested` |
| `--color-track` | `#25374A` | progress bar track |
| `--radius-button` | `10px` | buttons |
| `--radius-tile` | `14px` (measured from the .pen) | project card, scenario card, list item, step container, run filters, modal |
| `--color-danger` / `-hover` | `#492937` / `#5A3142` (measured from the .pen) | fill of the dangerous button |
| gradient `bg-app` | `linear-gradient(-112.6deg, #1A2833 11%, #0C1A26 48%, #132430 89%)` (measured from the .pen) | app background and sticky headers |

## 1. Scale and typography (everywhere)

- **Page H1 28/42 px regular** (measured from the .pen; the estimate was 32 semibold), below it a 14/21 `fg-secondary` description (gap 12). The meta row (registry path) mono 12 is a separate row below the header; the run_id in the run detail mono 13 is 8 px below the title. The header block has 32 px top padding and a 24 px gap below it.
- The scenario editor title **mono 27/41 regular**, the run detail title **mono 26/39 regular** (measured from the .pen). Panel title 18/26 semibold; the panel eyebrow 10 px mono uppercase `letter-spacing 0.08em` `fg-muted` (measured from the .pen).
- Section heading in a form 16 px semibold `fg`; field label 13 px **medium** `fg-secondary` (not bold); help 12 px `fg-muted`.
- Meta data (counts, times, costs, ids) is **mono 12 px** `fg-muted` (the design uses JetBrains Mono for all numbers and technical text). Today the meta is in Inter 13 px.
- Page content: padding 32 px, max. width 1176 px (1440 − 232 − 2×16), card grid gap 20 px.

## 2. Buttons and controls (`ui.tsx`, `form.tsx`)

- Primary: height **44 px** (measured from the .pen: all buttons on the screens are 44; the library component 40), padding 0 18, radius **10**, `bg-accent text-ink` 14 px semibold, icon 16 px. Secondary: the same with `bg-control text-fg`. Dangerous: fill `#492937` (`bg-danger`) with `text-error` (measured from the .pen). Ghost (text only) only in menus.
- Icon button: **44 × 44** also in the header (measured from the .pen), radius 10, `bg-control`, icon 18–20 px `fg`. The ⋯ on cards (project, scenario, step) is **without a fill** (click area 44, icon 18), the `control` surface only on hover and when open (measured from the .pen).
- Field: height **44 px**, radius **6** (measured from the .pen), `bg-nested`, **without a border at rest** (the stroke in the `.pen` is transparent; wave G), text 14 px, placeholder `fg-muted`; focus ring 2 `accent` without an offset, invalid ring 2 `error`; mono variant 13 px. Textarea padding 12. A select has a `fg-muted` chevron on the right. The `{}` button in a field with variables is inside the box, without a fill, 44 × 44, `text-variable`. Multi-line template and JSON (`V3 / CodeInput`): a `nested` r8 box, a toolbar (label 13 + “template”/“JSON” mono 11 `text-type` + `{}`) with a line, editor p16, a footer with the status and “Ctrl + Space for the menu”.
- Segmented toggle (Form | YAML): wrapper `bg-nested` radius 9 padding 4 gap 4, **segment 44 px radius 7**, 13 px (measured from the .pen), active `bg-accent text-ink`, inactive `fg-muted`.
- Run detail tabs: height 47, padding 12 18, gap 28, text 13 medium (measured from the .pen), active `fg` with a 2 px `accent` underline, inactive `fg-secondary`. Tabs in the step panel 13 regular, gap 24.
- Status chip: a `bg-nested` pill, padding 7 10, gap 8, icon 14 px, **text mono 12 medium in the status colour** (measured from the .pen). Only the “running” icon pulses (pulsing text would lack contrast).
- ⋯ menu: `bg-menu` radius 12, padding 8, gap 4, without a border with a `shadow-pop` shadow; items 40 px, radius 7, padding 10 12, 14 px; dangerous in red.
- Accordion (Condition / Reliability / Step details): row 52 px (padding 16), **arrow 16 on the left**, title 14 medium, value mono 11 `fg-muted` on the right (measured from the .pen).
- Code block (“CodeViewer”): `bg-surface` radius **16**, header padding 14 18 with a line (icon 18 + name mono 13 + a radius 6 chip with an outline, mono 11), `nested` body padding 18 0 with 27 px rows (number mono 12 `fg-muted` width 26, gap 14), footer padding 14 with a caption mono 11 on the left and an outlined “Copy” on the right (measured from the .pen). A single `CodeBlock` component in `ui.tsx` for Output/Prompt/Response, files and blocks in Markdown; the YAML editor has the same header and 27 px row.
- Modal (“ModalShell”): radius 14, header padding 24 with a line (title 22 semibold + close 44), content padding 24 gap 18, footer padding 18 24 with a line, buttons on the right **Cancel, then the action** (measured from the .pen).
- Empty state: `bg-surface` radius 12 padding 28 gap 14, icon 28, title 18 semibold, description 13 (measured from the .pen).

## 3. Sidebar (`Shell.tsx`)

- Width 232, padding 28 20, `bg-sidebar`, right hairline. Active item `#253B50` (measured from the .pen). Logo: a `Layers2` icon 25 px in `text-type` + “agencast” 22 px semibold `letter-spacing -0.7`. Gap below the logo 22.
- “← Projects” as a 44 px row (icon 16 + text 14 medium `fg-secondary`), then a 1 px `line` divider, then the project name (14 semibold) and navigation: items **44 px**, radius 8, gap 6, padding 0 14, icon 16 `fg-muted`, text 14 medium `fg-secondary`; active `bg-surface-active text-fg` and icon `fg`.
- At the bottom: “Spent today” 12 `fg-muted`, the amount mono 12 medium `fg` (`1.20 / 5.00 USD`), progress 3 px, track `track`, fill `success` (over the limit `error`). Keep the server outage message.

## 4. Projects (`Projects.tsx`)

- Header: H1 “Projects” 28, description “Manage projects, scenarios and agent runs in one place.” 14 `fg-secondary`, below the header the registry path mono 12. On the right an icon button Reload 44 × 44 `bg-control` and a primary “+ Add project” 44 px.
- Project card: `bg-surface`, radius **14**, padding **22**, gaps 20, min height 260 (measured from the .pen). Content: a top row with ⋯ without a fill on the right (without the “available” label, §2 G6; an unavailable one has an “unavailable” chip in this row and the reason at the bottom), name **20/29 semibold**, path mono 12 `fg-muted`, **count chips** (radius 6, padding 5 9, mono 11 `fg-secondary`), a 1 px `line` divider with a 14 offset, bottom row: the status chip of the last run + spend mono 12 (“today 1.20 USD”).

## 5. Scenario overview (`Scenarios.tsx`, `TypeIcon.tsx`)

- The toolbar above the grid is in `PageHeader` (already is): “+ New scenario” primary 40 px.
- Scenario card: `bg-surface`, radius **14**, padding 24, height **292**, gap 18 (measured from the .pen). At the top a 32 px row: **the chain of type icons as plain 18 px icons in `text-type`, gap 10, without circles and without arrows** (max. 5, then “+N” mono 12), on the right ⋯ without a fill. Name **18/26 semibold** (the scenario name), description 14 `fg-secondary` (2 lines, ellipsis), meta **mono 11 `fg-secondary`**: “7 steps · 3 agents” + a “callable” chip. Bottom row: the status chip of the last run (or an error chip) on the left, on the right “Open ↗” 13 `fg` (measured from the .pen).
- Today the chain of icons with arrows wraps onto two rows and pushes the status chip; that disappears.

## 6. Scenario editor (`Scenario.tsx`, `StepCards.tsx`, `TypePicker.tsx`)

- Header: “← Scenarios” (12 `fg-secondary`), title **mono 27/41 regular**, description 13/20 `fg-secondary` (measured from the .pen); on the right **“Run” primary** (Play icon) and **“Save” secondary** (Save icon; disabled = 50 % opacity), then ⋯ 44 × 44 `bg-control`. Second row: the segmented toggle + SaveNote as a status chip (“Saved ✓ 2:02 PM” `success`, “Unsaved” `warning`).
- Column of steps up to **676**, panel **440**, gap **28** (measured from the .pen: 1144 − 440 − 28). Connector: height **44**, arrow 16 px `fg-muted`; the (+) circle **44 px** `bg-surface`, `control` on hover.
- **Step card** (a pill, radius 999, `bg-surface`, height **96**, padding **16**, gap **14**; measured from the .pen): on the left the sequence number mono 11 `fg-muted` (editor only), then a **40 px circle with a `type/7` fill and a 16 px type icon `text-type`**, then the texts (gap 4): the type row **mono 11 `text-type` lowercase** “ask · propose”, title **15/22 semibold** `fg`, third row **mono 12 `fg-secondary`** (for `ask`/`task` the agent + a prompt excerpt, for `image` model · aspect ratio, the condition “when …”); on the right ⋯ without a fill. In a run the third row shows “12.4 s · 0.0210 USD” and on the right an 11 px status.
- Selected card: only the `bg-surface-active` fill (without a border, measured from the .pen). Hover `bg-surface-hover`.
- Header card: a **rectangle** `bg-surface` radius 14 padding 22 gap 16, an `AlignJustify` icon 24 px `text-type`, the title “HEADER” 21 semibold, below it the inputs row by row (`nested` r8 p 8 12 gap 6, a `Variable` icon 16 `variable`, name mono 13 `fg`, on the right “REQUIRED” mono 11 `fg-muted` and the type mono 11 `type`, the input description in a tooltip; without inputs “no inputs”) and below them the outputs mono 13 `fg-secondary`; the selected one additionally has an inner 1 px `accent` ring, so the sticky page header does not cover it.
- Containers (parallel/switch/call): a `bg-surface` wrapper radius **14** padding 16; header = a 20 icon without a circle, title 15/22, mono 10 `fg-muted` “3 · parallel · variants”, a collapse arrow 16 on the right; branches `bg-nested` radius **8** padding 12 with a label mono 11 `text-variable`, parallel branches side by side; cards in a branch padding 10, circle 30, title 13 (measured from the .pen).
- Buttons below the column: “+ Add step” and “+ output” secondary 44 px side by side, centred.
- TypePicker: `bg-surface` radius 12, items 40 px: keyword mono 13 `fg` + description 13 `fg-muted` (for the active one `fg-secondary` because of contrast on `surface-active`).

## 7. Panel (`StepPanel.tsx`, `RunPanel.tsx`, `RunStepPanel.tsx`)

- `bg-surface` radius 16; **header** padding 20 with a line at the bottom: panel icon 16, eyebrow mono 10 `fg-muted` uppercase, title 18/26 semibold, close ghost 44; **body** padding 20, field gap 18 (measured from the .pen). Width 440 (the step panel in a run **520**).
- On desktop the panel is in the page flow, its top edge at the selected card (the header and run panels at the start of the column), without a height limit and its own scroll. The page grows with the panel. Sheets up to 1279 px and long menus have a hidden scrollbar; code blocks on desktop have a thin scrollbar on hover or focus.
- Fields per §2 (height 44, labels 13 medium). The “Step type” select shows “ask · single agent call” (mono key + description). Inputs and outputs in the header panel are `group` r8 p14 cards with `nested` fields, “+ Add …” is a secondary button.
- Run panel: eyebrow “START RUN”, gaps 20; the label “RUN MODE” 11 px uppercase; mode cards `bg-nested` radius 8 padding 14 (a row with a 20 px radio 44 px, description 12), the selected one ring 1 `accent`; “Run limits” as 32 px rows with separators (label 12 `fg-secondary`, value mono 12 `fg`); a `warning/10` warning r8 p12 text 12; on the right “Cancel” + “Start dry run” (measured from the .pen).
- Step panel in a run: status row = status chip + mono 11 “12.4 s · 0.0210 USD”; tabs 13 px; content = a code block (see §2) and a file row `bg-nested` r8 p12 height 52 (path mono 12 + ↗).

## 8. Runs (`Runs.tsx`, `format.ts`) and the run detail (`Run.tsx`)

- Header “Runs” H1 32 + next to it a chip “2 running · 1 queued” (mono 12 `running`).
- **Filter bar** as a `bg-surface` card radius **14** padding 12, `line` outline, gap 10, selects 210 px (measured from the .pen): a search field (magnifier icon, placeholder “Search scenario or run ID…”, filters client-side by scenario name and run_id), a select “All statuses”, a select “All scenarios”. (Do not implement the period filter from the design.)
- **Column headers** mono **10** uppercase `fg-muted` (measured from the .pen): SCENARIO / RUN_ID, STATUS, WHEN, DURATION, COST.
- **A run row as a card**: `bg-surface` radius **8**, height **72** (padding 16 20), gap 8 (measured from the .pen); on the left a 20 px status icon in a circle, then the scenario name 15 semibold `fg` and below it the run_id mono 12 `fg-muted`; the status column = text in the status colour 14 (“running” in blue, “succeeded” in green, “error: timeout” in pink, “plan only (dry run)” neutral); WHEN mono 12 (“step 3/7 · propose”, “queued (#2)”, “12 min ago”, “today 2:02 PM”); DURATION mono 12 (“32.4 s”, “00:42” for running ones); COST mono 12 “0.0812 USD”; on the right a 16 px chevron. Hover `bg-surface-hover`, the whole row a link.
- `formatCost`: **always four decimal places** and the unit where the design shows USD (“0.0000 USD”, “0.0812 USD”), never “0” or “0.000013128”. On the project card “today 1.20 USD” (two places for amounts ≥ 0.01, otherwise four).
- “Load more” secondary 40 px with a chevron-down icon.
- Run detail: title **mono 26/39** + a ↗ icon (a link to the scenario), 8 px below it the run_id mono 13 `fg-muted`; on the right a status chip, mono 13 “32.4 s · 0.0812 USD” and a secondary button “Open scenario”. Inputs as a `bg-nested` card radius 8 padding 14: the label “INPUTS” 10 px + values mono 12 `fg-secondary` (measured from the .pen). Queue: a row “queued (#2)” mono 12 `neutral` and a 380 px empty state with a clock icon; dry run: a status row 12 `neutral` and the plan in a `surface` r12 p24 card with the eyebrow “RUN PLAN”. Files: a 300 px tree (`surface` r10 p12, mono 12 items with an icon), a `surface` r12 p24 viewer, for Markdown a Preview | Code toggle. Underlined tabs + a “follow run” checkbox on the right. Step cards in a run as in the editor (a circle with a status icon, on the right mono “12.4 s · 0.0210 USD” and a status text 12 `fg-muted`).

## 9. Agents and skills (`Agents.tsx`)

- Left list width **240**: items as `bg-surface` cards radius **14** padding **16** gap 14, mono 14 semibold, a type icon (Bot/BookOpen) **22 `text-type`**, the active one only `bg-surface-active`, errors as a second row mono 11 `error` + icon (measured from the .pen); “+ New agent” secondary 40 px above the list (or in the header, §2 G8).
- The editor on the right **in a card** `bg-surface` radius 16 padding 24 (today the form is “naked” on the background). No duplicate name inside (§2 G1); the first row of the card = the segmented toggle Form | Markdown + SaveNote on the left, the Save in the page header remains the only one.
- Fields 18 px apart, section headings 16 semibold with a 10 offset above (measured from the .pen): labels “description”, “model” 13 px; **skills as a list of checkboxes** in a `bg-nested` card radius 10 padding 14 (rows 40 px, checkbox 18, name 13, on the right mono 11 “SKILL.md”; measured from the .pen) — not chips + a select; MCP servers in the same style (the server checkbox, indented tools below it, the note “not allowed by the owner” as `fg-muted`); Limits in **three columns**; Instructions = a mono 13 textarea min. 12 rows in a `bg-nested` radius 12 box with the footer “Supports Markdown” 12 `fg-muted`; Used by = `bg-nested` 44 px rows with a link and a ↗ icon.

## 10. Config (`Config.tsx`)

- The whole form **in a card** `bg-surface` radius 16 padding 24; the first row the project path mono 13 `fg-muted`; the Form | YAML toggle + SaveNote; Save only in the header.
- Sections in **two columns** (gap 24): Connection (api_key_env + status) | Jev model (read-only, mono, a note); Models across the full width: each alias as a **`bg-group` card** (radius 12, padding 16) with `bg-nested` fields Alias / Model id / max_tokens / API + quality and below it the meta “used by writer” mono 12 + on the right “Delete alias” (dangerous, disabled with a reason); “+ Add alias” secondary on the right above the list; Storage | Webhook and callback (`*_env` statuses as rows with an icon); Limits (two columns of fields) | Variables (`bg-nested` 40 px rows: name mono + status on the right in colour); MCP servers as a `bg-nested` card: name 15 semibold, rows Transport / Allowed agents / Tools (mono 12), a “Read-only” chip.

## 11. What stays different from the design (deliberately)

Added in wave F (deliberate simplifications and decisions from earlier waves, which the `.pen` does not override): the step panel has
title = the step id in mono (the design shows a human name), without an “id” field (renaming is in ⋯) and without the footer
“Saved / Done” (G2); the run panel is 440 wide like the others (design 480) and shows limits only for a live run
(PN2); step cards in a run have no ⋯ (no action); deleting a step is in the editor's ⋯, the panel and on Delete (§2.3 gui-design); the message “Run
finished: …” only for the screen reader (G10); breadcrumbs only “← Scenarios” / “← Runs” (G5); YAML in two colours per
gui-design §4.5; the step highlight in YAML only as a flash; a skill is edited as Markdown (without the fields Name / Description
/ File and a formatting bar; the API stores SKILL.md only as a whole), below the editor a preview; the queue state neutral
(tokens §1: `neutral` = waiting); tabs in the run panel have the active one underlined (not only by colour).


Without the “available” and `skills[]`/`mcp[]` labels; without repeated names in form cards; without a second Save and a second toggle; without an extra time column; without an “Add project” card in a non-empty list; without a period filter in runs; Rename / Delete / Undo in the ⋯ menu; step types only ask, task, jev, image, parallel, switch, call, set, fail, output.

## 12. Mobile and tablet (wave G; the design has no mobile)

- Up to 1023 px a 56 px bar (`bg-sidebar`, hairline): the logo and the project (truncate). The navigation is in a menu above the 56 px FAB
  at the bottom right (“← Projects”, 48 px items, the spend and the language switch at the bottom; Esc, a click outside, focus back on the FAB). Content p16, from 768 px p24.
- Up to 767 px the header H1 24, description 13, only the primary action + ⋯ (secondary actions go into ⋯, `PageHeader compact`),
  the title wraps (`overflow-wrap:anywhere`); below 1024 px the header is not sticky.
- Up to 1279 px the panel (step, header, run, step in a run) is a bottom sheet with round top corners and a shadow,
  max height `100dvh - 48px` (`role="dialog"`, focus trap, Esc, after closing focus goes back to the card). Up to 767 px a step card of 80 px without a number (circle 36), a 32 px connector with a (+)
  of 32 px and a 44 touch area, the column across the full width (deleting only in ⋯ or the panel), TypePicker as a sheet at the bottom edge.
- The ⋯ menu has destructive items `text-error`; keyboard shortcuts are muted on the right and hidden on touch devices.
- Runs up to 767 px without a header: a two-row card (status + name + status text; run_id, when, duration · cost),
  a chevron on the right. Run detail tabs scroll horizontally. Agents/Skills below 1100 px as cards, the editor in a bottom sheet.
- Wave H per the user: menus have a shadow instead of a border, panels and mobile modals are bottom sheets,
  mobile and tablet navigation uses a FAB instead of a top menu.
- Wave I: the ⋯ menus, the variables menu, the autocomplete and the type picker are rendered through a portal into `body`, so `fixed`
  coordinates belong to the viewport even in transformed cards and sheets. The connector between cards is 48 px, the (+) 40 px,
  that is 4 px of free space above and below, also in branches.
- Wave K: boxes grouping fields have `group` `#132032`, fields stay `nested` `#0D192A`, and the scrollbars of sheets and menus are hidden.
- Wave I: checkboxes/radios are rendered uniformly on all surfaces (empty `control`, selected `accent` with a dark mark). API reads retry once after 1.5 s
  and after the connection is restored or the page becomes visible again they refresh the data and the conflict check immediately.
