# GUI redesign after design V3 — implementation plan

Design source: `docs/ui/design/agencast-design.pen` (a local pen.dev working file, not tracked in git; frames named `V3 · …`).
Reference for workers (not in git, generated from the `.pen` via `pen interactive`):
`docs/ui/design/ref/png/*.png` (frames 1:1) and `docs/ui/design/ref/html/*.html` (`html-tailwind` export,
useful for exact colours, gaps and sizes; the classes use fixed pixels, don't copy them into the code).
The brief the design was made from: `docs/ui/redesign-pen-brief.md`.

The design is a **preview**, not a pixel template. Its screens are overcrowded and some things repeat.
Goal: the new layout with a left sidebar, new base elements and cards, and a **visual simplification**
following the rules in §2. Where the design and the rules in §2 disagree, §2 wins.

What does not change: routes (`#/…`), the API, the file format, error texts from the API, keyboard shortcuts, the
saving behaviour (etag, conflict, validation before writing), accessibility (status = icon + text, `aria-*`,
focus). The v1 spec is frozen.

---

## 1. Tokens (contract for everyone)

Tailwind 4, defined in `ui/src/index.css` in the `@theme` block. The names are binding, the other tasks
use them as classes (`bg-canvas`, `text-fg-muted`, `ring-line`, `font-mono`, …).

| token | value | use |
|---|---|---|
| `--color-canvas` | `#0B1220` | page background |
| `--color-sidebar` | `#0B1524` | sidebar background |
| `--color-surface` | `#172436` | card, panel, menu, modal |
| `--color-surface-hover` | `#1D2D42` | card / item hover |
| `--color-surface-active` | `#1B2A3D` | selected card and active item |
| `--color-control` | `#31455F` | secondary and icon button |
| `--color-control-hover` | `#3B5170` | secondary button hover |
| `--color-track` | `#25374A` | progress bar track |
| `--color-nested` | `#0D192A` | field, chip, code block, nested element |
| `--color-line` | `#BDD9F026` | hairline, field ring |
| `--color-fg` | `#EDF5FF` | primary text |
| `--color-fg-secondary` | `#B5C6DB` | labels, captions |
| `--color-fg-muted` | `#8497B0` | meta, help (wave C: from `#8194AD`, see contrast below) |
| `--color-accent` | `#D2E4FA` | primary button, focus ring, active element |
| `--color-ink` | `#132236` | text on the accent |
| `--color-success` | `#6ED5AB` | success |
| `--color-error` | `#FF8F9D` | error, dangerous action |
| `--color-warning` | `#EBC477` | warning, conflict, interrupted, cancelled |
| `--color-running` | `#73BAFF` | running |
| `--color-neutral` | `#A5B2C5` | waiting, skipped, dry run, no runs |
| `--color-variable` | `#D6A2FF` | variable (the `{}` button, variable menu items) |
| `--color-type` | `#8BDCDF` | step type icon |
| `--font-sans` | `"Inter Variable", Inter, system-ui, sans-serif` | text |
| `--font-mono` | `"JetBrains Mono Variable", ui-monospace, monospace` | ids, paths, expressions, YAML, numbers |
| `--radius-control` | `8px` | fields and small nested elements |
| `--radius-button` | `10px` | buttons |
| `--radius-card` | `12px` | cards, menus |
| `--radius-panel` | `16px` | panel, modal |

Sizes by V3 fidelity: button 40 px (icon button in the header 48 px), field 44 px, tab 40 px,
H1 32 px, panel title 20 px, field label 13 px, meta mono 12 px, eyebrow 11 px. Fonts are bundled
(`@fontsource-variable/inter`, `@fontsource-variable/jetbrains-mono`), no CDN — the GUI runs
only on Tailscale and must work offline.

The `zinc-*` colours are gradually disappearing from the code; new code does not use them. Since wave C there are no `zinc-*` or
hard-coded colours in `ui/src` (exceptions: the white background of the `report.html` iframe and colours in test fixtures);
the select arrow is drawn with a gradient from `var(--color-fg-muted)`, not an SVG with a colour.

Contrast (WCAG 2.1, wave C, 2026-09-28): `fg-muted` `#8497B0` has 6.3:1 on `canvas`, 5.24:1 on `surface`,
5.91:1 on `nested` and 4.67:1 on `surface-hover`. The original `#8194AD` had only 4.50:1 (4.496) on `surface-hover`,
hence the 3-point brightness shift. `fg-secondary` ≥ 8.0:1, `error` ≥ 6.4:1, `warning` ≥ 8.4:1, `success` ≥ 7.8:1,
`running` ≥ 6.8:1, `neutral` ≥ 6.5:1 on all surfaces; `ink` on `accent` 12.4:1.

---

## 2. Simplification rules (apply above the design)

- **G1 One header per page.** H1 + an optional one-line description + actions on the right: at most two
  visible buttons (primary + one secondary) and a ⋯ menu with the rest. Inside cards and forms
  the name is not repeated (no “Agent · writer” below the header “writer”, no
  `agents/writer.yaml`).
- **G2 One Save.** Only in the page header. No bottom row “Cancel / Save changes”.
- **G3 One mode toggle** (Form | YAML, Form | Markdown) in the second row of the header, next to the save
  status (SaveNote). Not again inside the form.
- **G4 Secondary actions go into ⋯:** Rename, Delete, Undo (with the Ctrl+Z hint), Validate,
  Copy run command, Copy path, Remove from registry, Runs of this scenario,
  Open in YAML. Dangerous items (Delete, Remove) in red and last.
- **G5 The project context lives in the sidebar:** logo, the “← Projects” link, the project name, navigation
  Scenarios · Agents · Runs · Skills · Config, at the bottom “Spent today 1.20 / 5.00 USD” with a bar.
  Page headers do not repeat the project name or the path. Run limits (“run 2.00 USD · 300 s”) are not
  shown in the header (they are in Config and in the Run panel). The project path is only on the card in
  Projects and as the first row in Config.
- **G6 Status only when it says something.** The card of an available project has no “available” label; an unavailable one has a
  label + reason. The “server available” row is not shown; during an outage
  “The agencast server is not responding (…), retrying…” appears at the bottom of the sidebar (replaces today's ServerBar, the same `role="alert"`).
- **G7 Time once.** The chip of the last run also carries the time (“✓ 12 min ago”); the second time on the scenario
  card is dropped. On the scenario card the title = name, the subtitle = description; the `.yaml` suffix is gone.
  Meta row: “N steps · agents”; “callable” as a small label; the counts of inputs/outputs are gone.
- **G8 Adding is a button in the header** (“+ Add project”, “+ New scenario”, “+ New agent”).
  The dashed card is shown only as an empty state (a list without items).
- **G9 The run list** without a run_id column (it is in the detail) and without a spend row (it is in the sidebar).
  The filters, the live indicator “2 running · 1 queued” and “Load more” stay.
- **G10 Run detail:** title = the scenario (a link), next to it a small mono run_id; a status badge; duration · cost;
  inputs on one line; tabs; “follow run” only while the run is alive; the message “Run finished: …” only
  for the screen reader (`sr-only`, `aria-live`); the hint for an interrupted run stays visible.
- **G11 Help once and simply.** One help line below the field, 12 px muted. No framed
  “info boxes” for what the help says. No technical labels on sections (`skills[]`, `mcp[]`,
  `system_prompt`, `providers`) — whoever wants the YAML keys switches to YAML.
- **G12 Form sections** = a heading + fields. No badges, counts or “Used by” buttons; the text
  “used by 2 agents” stays as an ordinary meta sentence.
- **G13 Keep** keyboard shortcuts, `data-testid`, accessible names and roles; change tests deliberately,
  not because of an accidental text change.
- **G14 Responsiveness.** From 1024 px the sidebar is fixed at 232 px. Below 1024 px the sidebar collapses into a top
  bar (logo, project name, navigation horizontally, ⋯). Touch targets 44 px (`pointer-coarse`).
- **G15 Density.** Content max. width 1200 px; card padding 20, radius 12; panel radius 16;
  no `backdrop-blur` (performance on a tablet), surfaces in solid colours.

---

## 3. Waves and file ownership

Each task has its own worktree from `main`. **Nobody edits another task's files.** When a change is
needed elsewhere, the task describes it in its report and wave C resolves it.

Shared files, rules for the parallel wave B:
- `ui/src/locales/cs.json`: new keys **only at the end of the object**, don't reorder; delete the unused keys
  of your own task.
- `framework/CHANGELOG.md`: bullets under the heading `## 0.16.0 (unreleased)` (created by wave A), with an area
  prefix (“Shell:”, “Elements:”, “Cards:”, “Panels:”). Nobody changes the version in `pyproject`/`__init__`.
- `docs/ui/gui-design.md`, `docs/ui/user-journeys.md`: only the paragraphs of your own area.
- E2E: new tests in a new file `ui/e2e/redesign-<area>.spec.ts`; in the existing specs
  only the necessary assertion changes.

### Wave A — tokens (1 task, Codex Luna max)

`ui/src/index.css` (`@theme`, base: `body` = canvas/fg, focus ring accent), fonts via
`@fontsource-variable`, `ui/package.json`. Don't restyle anything else. Create `## 0.16.0 (unreleased)`
in the changelog. Tests must pass unchanged.

### Wave B — 4 parallel tasks

| task | model | owned files |
|---|---|---|
| **B1 Shell and sidebar** | Claude Opus 5.5 high | `ui/src/App.tsx` (incl. TokenScreen, ServerBar → sidebar), new `ui/src/components/Shell.tsx` (+ `Sidebar.tsx`, `PageHeader.tsx`), `ui/src/pages/Project.tsx`, `ui/src/pages/Projects.tsx` (incl. ProjectCard, dialogs), `ui/src/pages/Scenario.tsx` (header, column + panel layout), `ui/src/pages/Run.tsx` (header, layout), `ui/src/pages/Runs.tsx` (filters, RunRow), `ui/src/router.ts`, `ui/e2e/projects.spec.ts`, docs §1–§2 layout |
| **B2 Base elements** | Codex Sol xhigh | `ui/src/components/ui.tsx`, `form.tsx`, `YamlEditor.tsx`, `CodeView.tsx`, `Markdown.tsx`, their vitest tests, docs §3 inventory |
| **B3 Cards and flow** | Codex Sol xhigh | `ui/src/components/StepCards.tsx`, `TypeIcon.tsx`, `TypePicker.tsx`, `RunBadge.tsx`, `ui/src/pages/Scenarios.tsx` (ScenarioCard, list), `ui/src/steps.ts`, `ui/src/run.ts`, their tests, docs §2.2–§2.4, §5 |
| **B4 Panels and forms** | Claude Opus 5.5 high | `ui/src/components/StepPanel.tsx`, `RunPanel.tsx`, `RunStepPanel.tsx`, `RunFiles.tsx`, `ui/src/pages/Agents.tsx` (list, EditorBar, forms), `ui/src/pages/Config.tsx`, their tests, docs §2.5, §8, journeys for agents/config |

B2 keeps a **stable exported API** (`btn`, `StatusChip`, `Menu`, `Toggle`, `Modal`, `FormField`,
`CodeInput`, …), so the other files keep working without changes. It may add (e.g. `MenuItem.danger`),
not remove. The other tasks only use the primitives; a missing new element they write
locally and mention it in the report.

B1 creates `PageHeader` (title, description, actions, menu) and uses it on its pages. Agents
and Config move to it in wave C.

### Wave C — integration (1 task, Claude Opus 5.5 high)

After merging B1–B4: unify the headers (Agents, Config onto `PageHeader`), remove the remaining `zinc-*`,
go through all screens against §2, responsiveness 768/1024/1440, fine-tune contrasts, finish
`docs/ui/user-journeys.md`, version 0.16.0 (`pyproject`, `__init__`, `uv.lock`), changelog,
`npm run build`. After that the coordinator restarts the service.

---

## 4. Done means

- `npm run typecheck`, `npx vitest run`, `npm run e2e` pass in the task's worktree
  (E2E starts its own `agencast serve --fake`; no live API).
- `uv run pytest -q` unchanged (UI tasks don't change the framework).
- No new dependencies except the fonts (wave A). No CDN, no `backdrop-blur`.
- A report in `/tmp/agencast-<task>-report.md`: what changed, decisions beyond the brief, what was left to
  another task, test results, model and effort (from the agent's status line).
- A commit on its own branch, no merge into `main`, no push.
