# AgenCast GUI design

Status: design document from 2026-09-26; the GUI is implemented in `ui/`.
The current behaviour is described in the [GUI README](../../ui/README.md). The design follows
the DESIGN decision “Wrappers”: a standalone wrapper over the `serve` HTTP API that
can be embedded in a host application as a tab. Visual model: a workflow
editor with a vertical column of steps, a right-hand panel with a form, a
Form / YAML toggle and a dark theme.

The decisions on the questions in §8 are at the end of the document.

Sources: DESIGN.md (Wrappers, §5), specs scenario/agent/config/skill/api/projects/run-record, ig-post.yaml, SKILL.md of agencast-create.

## 1. Information architecture

```
Projects  (#/)                                   list from the registry, sidebar with the logo only
└ Project (#/p/lumen)                             sidebar: ← Projects, name, navigation, spend
   ├ Scenarios (default)   list → Scenario editor (#/p/lumen/scenarios/ig-post?step=tone_check)
   ├ Agents                list on the left + form (#/p/lumen/agents/copywriter)
   ├ Config                one form: config.yaml + read-only MCP servers (the owner's mcp.yaml)
   ├ Skills                list on the left + text (#/p/lumen/skills/lumen-voice)
   └ Runs                  list → Run detail (#/p/lumen/runs/<run_id>?step=propose/copy)
```

- Depth of at most 2 below a project. The scenario editor and the run detail are full screens with the same column of cards; on the right a **panel** (440 / 520 px on desktop) with the step.
- **Modals only for decisions:** delete with impact, file conflict, step type change. The type picker at + is a popover, not a modal.
- The selected step is in the URL (`?step=`), so a link can be sent. Hash routing because of the iframe in Skynet Soul; the iframe sends a `postMessage` with the current path for deep links from the dashboard.
- Read-only version (per DESIGN) = the same screens without +, without Save, panel read-only. The editor is a superset, nothing is redrawn.

### 1.1 Layout (shell, redesign V3 0.16.0)

```
┌ sidebar 232 px ───┐┌ main area (canvas, content max. 1176 px, padding 32) ────────────────────┐
│ ◈ agencast        ││ ← Scenarios                                                              │
│ ← Projects        ││ ig-post  ✗ 2 errors                              [▷ Run] [Save]  ⋯       │
│ ───────────────── ││ Draft IG post for approval                                               │
│ lumen              ││ [Form | <> YAML]   Unsaved                                               │
│ ▣ Scenarios       ││                                                                          │
│   Agents          ││   … page content (cards, panel, table)                                   │
│   Runs            ││                                                                          │
│   Skills          ││                                                                          │
│   Config          ││                                                                          │
│                   ││                                                                          │
│ Spent today       ││                                                                          │
│ 1.20 / 5.00 USD   ││                                                                          │
│ ▬▬▬───────        ││                                                                          │
│ Language [English]││                                                                          │
└───────────────────┘└──────────────────────────────────────────────────────────────────────────┘
```
- `Shell` (`ui/src/components/Shell.tsx`): sidebar `bg-sidebar` with a hairline on the right, the main area with the shared
  background gradient (`bg-app`, measured from the .pen), content max. 1176 px with 32 px padding (fidelity §1). The token screen has no shell.
- **Sidebar dimensions** (fidelity §3, `V3 / ProjectSidebar`): width 232, padding 28 20, gap 22. The logo
  `Layers2` 25 px `text-type` + “agencast” 22 px semibold (`letter-spacing -0.7`). “← Projects” is a 44 px
  row (icon 16, text 14 medium `fg-secondary`), below it a 1 px `line` divider, the project name 14 semibold
  and 44 px navigation items, radius 8, gap 6, padding 0 14, icon 16 `fg-muted`, text 14 medium
  `fg-secondary`; active `bg-surface-active` (`#253B50`, measured from the .pen) `text-fg` with icon `fg`. Spend: label 12 `fg-muted`, amount
  mono 12 medium, a 3 px bar on a `bg-track` track.
- **Sidebar** carries the project context (G5): the logo (a link to Projects), “← Projects”, the project name, navigation
  Scenarios · Agents · Runs · Skills · Config (`nav` “Project sections”, the active item `aria-current="page"`;
  the scenario editor belongs under Scenarios, the run detail under Runs) and at the bottom “Spent today 1.20 / 5.00 USD” with a bar
  (green, red once the daily limit is exceeded; without a limit only the amount), then the language switch (§1.2). On the Projects page only the logo and the language switch, on a nonexistent address the logo, “← Projects” and the language switch.
  There is no “server available” row (G6); during an outage “The agencast server is not responding (…), retrying…”
  appears at the bottom (`role="alert"`, `data-testid="server-bar"`). GET/HEAD has a 20 s timeout and after a network error one
  silent retry after 1.5 s; only the second error shows the bar. On `online` or when the page becomes visible again, the data and
  the conflict check are refreshed immediately; while the page is hidden the conflict check is paused.
- **Below 1024 px** the top bar has the logo and the project name. The project navigation opens from a 56 px FAB
  at the bottom right into a menu above the button; it has “← Projects”, 48 px items, the spend and the language switch. The FAB is on every page (also the project list and 404) because the menu holds the language switch.
- **Content responsiveness** (verified at 768 / 1024 / 1440 px): the scenario editor has the panel as a drawer on the right
  only from 1280 px (sidebar 232 + column + panel 440); a narrower screen shows a bottom sheet with 16 px top corners,
  a shadow and a max height of `100dvh - 48px` (on a tablet at most 720 px wide), always with a close cross and Esc. Agents and Skills have
  the list next to the editor from 1100 px; a narrower screen shows only cards and opens the editor in a bottom sheet. The runs table scrolls horizontally (min. 46rem), the row
  of a model alias in Config wraps. Popovers are in a portal in `body`, fit into the viewport with a 12 px margin
  and open downwards or upwards depending on the space, even from inside a transformed card or sheet.
- **Page header** (`PageHeader`, `ui/src/components/PageHeader.tsx`, G1–G4, fidelity §1): an optional back link,
  from 768 px only a ← arrow before the title (36 px ghost), narrower a “← Scenarios” row (12 px) above it; breadcrumbs
  (`trail`) stay in the row above the title; H1 28/42 regular (measured from the .pen) + `meta` (error chip, run status), below it a
  one-line description 14 `fg-secondary` and `detail` 8 px under the title (mono 13 `fg-muted`: run_id); on the right
  at most a primary + one secondary button (36 px, 44 on touch) and a ⋯ “More actions” menu with the rest (dangerous
  items last) as an icon button `bg-control` 36 × 36; a standalone icon button in the header is
  `headerIconBtn` (36 × 36). 24 px below the header; a second row for the mode toggle and the save
  status or tabs. In the editor and the run detail the header is sticky and reports its height
  in `--page-header-h` (for the card offset when jumping to a step).
- Headers by page:
  - **Project:** title = the section (“Scenarios”, “Agents”, …), `meta` = an “N errors” chip with a drop-down list
    (links to the file and step). ⋯ always starts with “Reload”. Without the project path, limits and spend. The config
    error block (422) stays below the header. The header is assembled by `ProjectPage` (type `SectionHeader`) and each section
    adds its actions, ⋯ items and second row to it; until the data has loaded the page draws it itself:
    - Scenarios: “+ New scenario” (primary).
    - Agents / Skills: “+ New agent” / “+ New skill” (secondary) and Save (primary, Ctrl+S); ⋯ has
      the accessible name “Actions for <name>” and carries Rename (agent only) and Delete (red, last).
      Second row: Form | Markdown (agent only) + save status. An empty section has only the primary “+ New …”.
    - Config: description = the project path (mono, the only place besides the project card, G5), Save; second row
      Form | YAML + save status.
    - Runs: title, `meta` = a chip “2 running · 1 queued” (mono 12 `running`, only when something is alive) and ⋯.
  - **Scenario editor:** “← Scenarios” (+ breadcrumbs across `call`), title = the scenario name in mono, description = `description`,
    actions Run (primary, Play) and Save (secondary, Save, Ctrl+S); ⋯ 40 × 40: Undo (shortcut Ctrl+Z on the right), Copy run command, Runs of this
    scenario, Rename, Delete. Second row: Form | YAML + save status with an error chip.
  - **Run detail:** see 2.5.
  - **Nonexistent address** (design V3 / 14): centred `MapPinX` icon, “404” mono 64 `fg-muted`, title
    “There's nothing at this address.”, the sentence “Go back to the project overview and continue from there.” and a primary
    “← Projects”.
  - **Server token** (design V3 / 01): a 420 px card, radius 16, padding 32; logo, title 28, help,
    a 36 px field (44 on touch) with a lock and a Show token / Hide token toggle, the error as a `text-error` chip, a primary
    “✓ Save” and below it the server address mono 12; the language switch is also here (§1.2).

### 1.2 Language (English by default, optional Czech)

The GUI is **English by default**; a Czech translation is optional. All strings live in
`ui/src/locales/en.json` (the source of truth for every label) and `ui/src/locales/cs.json` (Czech translation);
the ICU-style messages (`{name}`, `{n, plural, one {…} other {…}}`) are formatted by the small formatter in `ui/src/i18n.ts`.

- **Switcher:** a “Language” select (options “English” / “Čeština”) in the sidebar footer, in the mobile navigation menu (opened by the FAB) and on the token screen. Changing it saves the choice in `localStorage` (`agencast.lang`) and reloads the page.
- **Choice order:** the saved choice, else the browser language (`cs` → Czech, `en` → English; the first supported entry of `navigator.languages`), else English. A key missing from `cs.json` falls back to English.
- **Numbers, costs and times** follow the chosen locale (`0.0812` vs `0,0812`; a 12-hour clock in English vs a 24-hour clock in Czech). `<html lang>` follows the locale.
- **Keys:** `en.json` and `cs.json` must keep **identical keys** (and the same placeholders per key). This is checked by `ui/src/test/i18n.test.ts`; add every new string to both files.
- Routes, query keys and URL values are English regardless of the locale (`#/p/<project>/scenarios`, `?step=`, `?mode=yaml`, `_header`); localStorage keys and `data-testid` values are not translated either.

## 2. Screens

### 2.1 Project list (cards)

```
Projects                                                                          [⟳] [+ Add project]
Manage projects, scenarios and agent runs in one place.
~/.config/agencast/projects.yaml
┌──────────────────────────────┐  ┌──────────────────────────────┐  ┌─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
│ lumen                      ⋯ │  │ demo                     ⋯ │    old-project                ⋯  
│ ~/lumen                      │  │ ~/demo                     │    /mnt/disk/old                 
│                              │  │                              │    ⊘ unavailable                 
│ [3 scenarios] [4 agents]     │  │ [1 scenario] [1 agent]       │    missing …/workflows/config.yaml  
│ ──────────────────────────   │  │ ──────────────────────────   │                                  
│ ✓ 12 min ago  today 0.42 USD │  │ no runs       today 0.00 USD │                                  
└──────────────────────────────┘  └──────────────────────────────┘  └─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
```
Header (fidelity §4, measured from the .pen): title, description “Manage projects, scenarios and agent runs in one place.”,
below the header the registry path (mono 12; the full “Registry …” in `title`), an icon “Reload” 44 × 44 `bg-control` and
“+ Add project” (without write access to the registry it opens a dialog with the CLI command). Card: `bg-surface`, radius 14,
padding 22, gaps 20, min height 260, grid gap 20; top row with ⋯ without a fill (an unavailable project has a
chip there), name 20 semibold, path mono 12 `fg-muted`, count chips (`bg-nested` r6, mono 11 `fg-secondary`), below the line the chip of the last run and today's spend mono 12 (“today 1.20 USD”,
two decimal places, small amounts below 0.01 four — `formatSpend`). An available project has no label (G6); an unavailable one has the label “unavailable”,
the reason and a dashed border without a fill (no transparency: the text would have a contrast below 4.5:1). The whole card is a link. ⋯: Open, Copy path, Remove from registry
(last, dangerous). The dashed “Add project” card only for an empty list (G8).

### 2.2 Project overview (scenario cards)

```
Scenarios                                                           [+ New scenario]  ⋯
┌───────────────────────────────────┐  ┌───────────────────────────────────┐
│ ▭ ⚖ ⊗ ▭ ⚖ +3                     ⋯ │  │ ⚙ ▣                              ⋯ │
│                                   │  │                                   │
│ ig-post                           │  │ ig-publish                        │
│ Draft IG post for approval        │  │ Publishing an approved post       │
│ 8 steps · 2 agents                │  │ 3 steps · 1 agent · callable      │
│                                   │  │                                   │
│ (✓ 12 min ago)               Open ↗ │  │ (✗ 2 errors)                 Open ↗ │
└───────────────────────────────────┘  └───────────────────────────────────┘
```
- Title = the scenario name (18/26 semibold); `description` is a 14 px `fg-secondary` subtitle, at most 2 lines, in full in `title`. Card (fidelity §5, measured from the .pen): solid `surface`, hover `surface-hover`, radius 14, padding 24, height 292, grid gap 20.
- The icon chain = the step types in file order as **plain 18 px `text-type` icons, gap 10, without circles and arrows**, at most 5, then “+N” mono 12 `fg-muted`; `parallel`/`switch` once with their own icon, the inside is not spelled out. On the right the ⋯ menu.
- Meta row mono 11 `fg-secondary` “N steps · N agents” (a count, not names) and an optional chip “callable” (`nested`, text `type`). Bottom row: on the left the chip of the last run (as on the project card), validation errors take precedence (“✗ 2 errors”); on the right “Open ↗” 14 medium `fg` — only a visual prompt, the whole card (the title) is the link. The counts of inputs and outputs, the `.yaml` name and a second time are not shown.
- ⋯: Open, Runs of this scenario, Copy run command, Validate; later Duplicate, Delete.
- The “+ New scenario” button is in the section header (G8); the dashed card opens the same dialog only in an empty list.
- “Validation errors” in the header = the sum of `errors` of all files; a click opens a list with links to the file and step.

### 2.3 Scenario editor (cards + panel)

```
← Scenarios
ig-post                                                          [▷ Run] [Save]  ⋯
Draft IG post for approval
[Form | <> YAML]   Unsaved · ✗ 1 error

      ( ≡  HEADER                                                                )
      (    1 input: topic · 3 outputs: caption, hashtags, image                  )
                                     ↓
      ( 1  ASK · copy                                                            )
      (    copywriter: “Write an IG post about: {{ inputs.topic }}”              )
                                     ↓
    ╭─( 2  JEV · tone_check                                                     )─╮   (🗑)
    ╰─(    “Does the text match the Lumen brand tone…?” · noul                  )─╯
                                     ↓
      ( 3  FAIL · stop                                       when on_brand < 0.7 )
      (    “The text does not match the brand (on_brand = …)”                    )
                                     ↓
      ( 4  ASK · photo_prompt                                                    )
      (    photographer: “Suggest a photo for the text…”                         )
        ✗ agent 'photographr' does not exist (agents/photographr.md)
                                     ↓  …
      ( 7  IMAGE · photo                                                         )
      (    gemini-image · 4:5 · “{{ steps.photo_prompt.photo_description }}”     )
                                     ↓
      ( 8  OUTPUT · out                                                          )
      (    caption, hashtags, image                                              )
                                    (+)
```
Pill (fidelity §6): `surface`, height 72, padding 16, gap 14; hover `surface-hover`, selection only by the `surface-active` fill (no border). On the left a 40 px circle with a `type/7` fill and a 16 px type icon `type`. Texts (gap 2): the row `type · complement` mono 11 `type` in lowercase (+ with a condition only the mark “◇ conditional”, the expression in its tooltip, + an optional error dot), then **the name `n. id`** 15/22 semibold `fg` (not mono; the sequence number `fg-muted` — `fg-secondary` on the selected card, for contrast — is part of the name). The prompt, messages and the condition expression are not on the card — they are in the panel. On the right ⋯ without a fill inside the pill. In a run the circle holds a status icon, below the name the run value (model, answers, error, skip reason) 13/19 on up to 2 lines, the last row “12.4 s · 0.0210 USD” and on the right an 11 px status. Container heads have the same rows. A new step gets the id `<type>_<n>`. Complement by type (`steps.ts` `stepDetail`):

| Type | Complement |
|---|---|
| ask, task | agent |
| jev | type · “+1 question” |
| image | alias · aspect ratio · quality · resolution |
| call | scenario · N inputs |
| parallel | N branches, run in parallel |
| set, fail, switch, output | — |

**Connector:** a 16 px `fg-muted` arrow ↓, height 44, which on hover or focus turns into a 44 px (+) circle `surface` (hover `control`); a cut step keeps the (+) visible with `ring-accent`. Below the main column are the secondary 44 px buttons “+ Add step” and “+ output” side by side, centred; at the end of the branches a (+) stays permanently visible. TypePicker: `surface` r12, 40 px items, keyword mono 13 `fg` + description 13 `fg-muted`, active `surface-active`. Column up to 676 px, panel 440 px, gap 28 (measured from the .pen). The header card is a rectangle r14 p22 with a 24 icon, the title “HEADER” 21 px, below it the inputs row by row (icon `{}` `variable` — the same as the insert-variable button in fields, name, “required” and type, like Start in Dify) and a row of outputs mono 13; the selected one has an `accent` ring. The ⋯ menu has “Insert step above / below”. Container cards (`parallel`, `switch`, `call`) have a wrapper and a main card with the `card` radius. In a run the status icon replaces the type icon; the running icon pulses only when motion is allowed, skipped and not-reached steps have 40 % opacity.

**Deleting a step:** ⋯ on the card → a red “Delete” with the Del shortcut on the right, the trash in the header of the open panel, or the Delete key on a focused card. There is no separate trash next to the card; the delete protection from §4.3 applies unchanged. The header card is not deleted. Other shortcuts in the menu are on the right as a muted hint (hidden on touch; ⌘/⌥ on Mac).

**Panel** (V3: `bg-surface`, padding 20; from 1280 px a drawer on the right edge over the full window height, over the header strip too, with a large blurred shadow to the left (`--shadow-drawer`); it reports its width in `--drawer-w` and the Shell narrows the page by it, so the column and the header actions stay beside it; not modal (the cards stay clickable), its body scrolls, a narrower screen = a sheet at the bottom over the column with a close cross, see §1.1):

```
┌ STEP 2 · JEV                                🗑   ✕ ┐
│ tone_check                                        │
│                                                   │
│ Name (id)                                         │
│ [tone_check                                      ]│
│ Step type                                         │
│ [jev                                            ▾]│
│ State                                             │
│ [{{ steps.copy.caption }}                        ]│
│ Questions                         [+ Add question]│
│  [on_brand                                   ]   🗑│
│  [noul ▾]  Question [Does the text match…  ]      │
│ ──────────────────────────────────────────────────│
│ Condition                                always  ›│
│ ──────────────────────────────────────────────────│
│ Reliability                             default  ›│
│ ──────────────────────────────────────────────────│
│ Step details                                     ›│
└───────────────────────────────────────────────────┘
```
- **PanelShell** (redesign V3, measured from the .pen): header padding 20 with a line (panel icon 16, eyebrow mono 10 px uppercase `letter-spacing 0.08em` `fg-muted` “STEP n · TYPE” — also the accessible name of the panel, title 18 semibold = the step id (not mono, like the name on the card), on the right trash and close as a 36 px ghost (44 on touch), also Esc), body padding 20, field gap 18. The step type is the first form field (a select with options such as “ask · single agent call” — a mono key + description), not the title. Fields without framed info boxes, one 12 px help line below the field (G11). Map rows (Jev questions, `set` values, header inputs/outputs) are separated by a hairline, header inputs and outputs as nested `nested` r8 p14 cards: key (`KeyInput`, mono) + remove (`Trash2`), below it the fields; “+ Add …” next to the label as text only in `type` (#8BDCDF), 14 medium, without a fill, `surface-hover` on hover (`btn.add`) (accessible name “Add …”); the same style for “+ Add alias” in Config and “+ case” / “+ branch” in a container card.
- **Scenario header** (`HeaderPanel`, eyebrow “HEADER”, title = the scenario name in mono as in the Run panel): description, Inputs and Outputs as rows (inline name, type, for an input required / default value, description, remove) and a “Callable” toggle with an explanation below it.
- As in Buzz: the type field on top, common things at the bottom in three collapsed rows (value on the right in grey, a hairline between them). A row expands in place (accordion, the chevron rotates) so the panel context stays.
- **Condition:** the collapsed row shows `always` or a shortened expression (`steps.tone_check.on_brand < 0.7`); expanded = `ExprInput` + the help “If it evaluates to false, the step is skipped; any step that reads its output needs a default.” There is no such row for `output`.
- **Reliability:** timeout, budget_usd, retry, on_error, default; only for the types from the table in §3 of the spec.
- **Name (id)** is the first field of the panel (rename with a check of `refs` and an offer to rewrite references); the card shows it as the name of the step.
- **Step details:** “Reads from” and “Output read by” as chips (a click jumps to the card), the “Open in YAML” link (jumps to the step's line).
- A validation error is right below the card and at the field in the panel.

### 2.4 `parallel`, `switch`, `call` cards

```
│ ⑤ variants        parallel · 2 branches, run in parallel              │
│   ┌ short ───────────────┐   ┌ long ────────────────┐                 │
│   │ ⑥ short_text    ask  │   │ ⑦ long_text     ask  │                 │
│   │      +               │   │      +               │                 │
│   └──────────────────────┘   └──────────────────────┘   + branch      │
│      │  +                                                             │
│ ⑧ by_kind       switch · by  steps.tone_check.kind                    │
│   = product                                                           │
│     ⑨ product_text     ask · copywriter                               │
│          +                                                            │
│   = sale                                                              │
│     ⑩ sale_text        ask · copywriter                               │
│          +                                                            │
│   otherwise (default)                                                 │
│     ⑪ unknown_kind     fail                                           │
│          +                                                      + case│
│      │  +                                                             │
│ ⑫ propose         call → ig-text  (open ↗) · 1 input                  │
```
A rule for beginners: **side by side = at the same time, one below another = one of the options.** Container (measured from the .pen): a `surface` wrapper radius 14, padding 16; header = a 20 icon without a circle, title 15, mono 10 “3 · parallel · variants”, a collapse arrow 16 on the right next to ⋯. Branches and cases have `nested` without a border, radius 8, padding 12, a mono 11 `variable` label and their own +; cards inside have padding 10, a 30 circle and a 13 title, without a sequence number. An unexpanded `call` is an ordinary pill with an “open ↗” link below it. An empty `default: []` is shown as “otherwise: nothing”. Collapsing a card hides the inside and shows only the number of steps.

### 2.5 Run viewer on cards (run detail)

```
← Runs
ig-post 20260925-141502-ig-post-9f3c  ✗ error: fail in stop_image  fake run      4.4 s · 0.0016 USD
INPUTS topic = “new coffee” · aspect_ratio = “1:1”
Steps · Summary · Report · Files                                                          ☐ follow run
│ ✓ ① copy            ask · smart → claude-haiku-4.5             3.7 s   0.0015│ ┌ STEP 2 · tone_check · jev ✓ 0.3 s ──┐
│ ✓ ② tone_check      jev · on_brand = 0.91                       0.3 s  0.00002│ │ Response · Prompt · Calls (1) · Files │
│ ○ ③ stop            fail · skipped: when … → false                            │ │ on_brand   0.91  ▮▮▮▮▮▮▮▮▮▯          │
│ ✓ ④ photo_prompt    ask · fast → gemini-3.5-flash-lite        1.8 s   0.0006│ │ state  “The new coffee is here…”     │
│ ✓ ⑤ image_check     jev · real_person = 0.8                     0.3 s  0.00002│ │ model  typesafe/jev-1.13-20260917    │
│ ✗ ⑥ stop_image      fail · The photo description breaks the content rules: …  │ │ 21 + 4 tokens · 0.00002 USD          │
│ · ⑦ photo           image · not reached                                       │ └──────────────────────────────────────┘
│ · ⑧ out             output · not reached                                      │
```
Header (G10, measured from the .pen): title = the scenario in mono 26 with a ↗ icon (a link to the editor), 8 px below it the run_id mono 13 `fg-muted`; on the right the status chip (+ “fake run”), mono 13 “32.4 s · 0.0812 USD” and a secondary “Open scenario”. Inputs as a `bg-nested` r8 p14 card: the label “INPUTS” 10 px + values mono 12 on one line (in full in `title`). Tabs 47 px, 13 medium. A queued run shows “queued (#N)” and an empty state of 380 px; the dry run plan in a card with the eyebrow “RUN PLAN”. Tabs underlined across the full width, “follow run” on the right on the same line. “follow run” only while the run is alive; the message “Run finished: …” only for the screen reader (`role="status"`), the hint of an interrupted run visible. The same cards as in the editor: the circle holds a status icon instead of the number, on the right mono duration · cost with tabular figures. Skipped and not-reached steps are muted to 40 %, the running icon pulses only when motion is allowed. Panel by type: `ask`/`task` Prompt (prompt.md), Response, Output (output.json), Calls (attempts, turns, tokens, `finish_reason`, cascade level), and for `task` also Tools (`tool_call`; denied, invalid arguments and a call that did not return — its `error` text: timed out, the server dropped the connection, cancelled — highlighted; below the calls “Server log (stderr): mcp/<server>.stderr.log” per server called, a link to the Files tab — offered while the run is alive although the file is written only when the server stops, afterwards only when the file exists); `image` preview + prompt; `jev` answers with probabilities; `call` expands right in the card into nested cards (`propose/copy`); `set` values; `output` values + URLs of uploaded files. A skipped step: the reason and “default used”. A warning (`continued: true`) = a `text-warning` triangle + text below the card. Tabs: Summary = the rendered summary.md, Report = report.html in a sandboxed iframe, Files = a tree from `files` with a text/JSON/PNG viewer.

**Step panel in a run** (redesign V3, measured from the .pen; width 520): the same PanelShell (eyebrow “STEP n · type”, title = the step path, not mono). Status row: a status chip + mono 11 “12.4 s · 0.0210 USD” + “3 turns · 2 tool calls”; below it the text of a skip / warning / error. Tabs 44 px, 13 px (`role="tablist"`, active `fg` + `border-accent`, inactive `fg-muted`); “Calls (n)” carries the count. Prompt, Output and Response are a `CodeBlock` (r16, a header with `{}` 18 + the file name mono 13 + a “Read-only” chip, `nested` body with 27 px rows and mono 12 `fg-muted` numbers, a footer “JSON · read-only” + an outlined “Copy”); step files are `nested` r8 52 px rows (icon + path mono 12 + ↗) leading to the Files tab; Jev answers = key mono, value tabular, a 0–1 bar (`bg-nested` / `accent`); calls and tools as `bg-nested` rows with the control radius, errors `bg-error/10` with red text; the image with rounded corners; the list of files as mono links to the Files tab; an empty tab “Nothing to show.” The **Files** tab in the run detail: a tree on the left 300 px in a `surface` r10 p12 card (mono 12 items with a folder/file icon, the selected file `surface-active`), the viewer on the right in a `surface` r12 padding 24 card: the path, for Markdown a Preview | Code toggle (preview = rendered Markdown), otherwise a code block or an image; a path that is not in the run shows “This file is not in the run.”, and for `mcp/<server>.stderr.log` “The stderr log of a local MCP server is written when the server stops, at the end of the run. A remote server has none.” — no request is sent for a missing file, and the viewer appears once the polled `files` contain it; the report unchanged in a sandboxed iframe.

### 2.6 Run list

```
Runs  ∿ 1 running · 2 queued                                                              [⋯]
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ 🔍 Search scenario or run ID…             │ All statuses ▾         │ All scenarios ▾         │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
      SCENARIO / RUN_ID               STATUS                  WHEN                      DURATION  COST
┌ ◌  ig-post                       running                 step 4/8 · photo_prompt   00:07   0.0021 USD  › ┐
│    20260926-091502-ig-post-3c1f
┌ ✗  ig-post                       error: fail in stop     yesterday 2:15 PM         4.4 s   0.0016 USD  › ┐
│    20260925-141502-ig-post-9f3c · fake run · callback not delivered
```
Fidelity §8: a `bg-surface` filter card radius 16 padding 12 — search (client-side by scenario name and
run_id), a status select (client), a scenario select (server `?scenario=`); the period filter from the design does not exist. Column
headers mono 11 uppercase `fg-muted`. A row = a `bg-surface` card radius 12, height 80, gap 8, hover
`bg-surface-hover`, the whole row a link: a 20 px status icon, the scenario name 15 semibold and below it the run_id mono 12
(+ “fake run”, callback); the status as text in the status colour (for an error “error: <reason>”); WHEN, DURATION
(“00:42” since the start for running runs) and COST (“0.0812 USD”, `formatCost` always four places) mono 12; on the right a
chevron. No spend row (it is in the sidebar), G9. The table
scrolls horizontally. A running row refreshes (see 4.8). Empty list: “No runs.” with a CLI line; older pages via the
“Load more” button.

### 2.7 Agent

```
Agents  ✗ 1 error                                       [+ New agent] [Save]  ⋯
 copywriter          │ copywriter
 photographer        │ ┌ card: [Form | <> Markdown]  Saved ✓ ─────────────────────┐
 publisher  ✗ 1 error│ │ description *  [Copywriter for the Lumen IG brand      ] │
                     │ │ model *        [smart — anthropic/claude-haiku-4.5 ▾] │
                     │ │ skills         ☑ lumen-voice                     SKILL.md │
                     │ │                ☐ research                        SKILL.md │
                     │ │ MCP servers    ☑ instagram · ☑ create_media            │
                     │ │                ☐ filesystem (not allowed by the owner) │
                     │ │ Limits    max_turns [6] budget_usd [0.20] timeout [5m] │
                     │ │ Instructions (system prompt) [Markdown textarea, at least 12 rows] │
                     │ │ Used by   [ig-post / copy ↗] [ig-text / write ↗]       │
                     │ └──────────────────────────────────────────────────────────┘
```
One section header (§1.1): “+ New agent”, Save and ⋯ “Actions for copywriter” (Rename, Delete).
The second row Form | Markdown and the save status sit in the editor card (`bg-surface`, radius 16, padding 24).
From 1100 px the agent list is on the left (240 px), items are r14 p16 cards with a 22 `type` icon,
the active one only by the `surface-active` fill, errors as a second row mono 11 (measured from the .pen); the name of the selected agent is
above the card only as a heading (`h2`, mono 24), without the file path and without a second Save.
Below 1100 px there is neither the list nor the editor, only a grid of cards (like Scenarios): icon, name mono, description on 2 lines, model mono 12
“alias — id” from config.yaml, meta mono 11 “N skills · N MCP servers · N scenarios” (skill: “N agents”), an error chip. A card opens the editor in a bottom sheet
(`PanelShell`): title = the name, Save and ⋯ in the sheet header, the page header has only “+ New agent”. Without a selection in the address
nothing opens; closing (cross, Esc, a tap outside) returns to the cards, work in progress is guarded by the leave prompt.
Name = the file name, read-only (renaming = a separate action with a check of references). MCP lists every
server; those where the agent is not in `agents` in mcp.yaml are disabled with a reason. A ticked server shows the owner's
tools as checkboxes (“N tools”); a server without an owner allowlist says “not restricted by the owner” and has a field for
comma-separated tool names instead — an empty `tools.<server>` list is never written. A task step (§2.3) shows the same
tree narrowed: without `mcp`/`tools` in the file everything the agent has is ticked, unticking writes the narrower list,
and names the agent does not have stay visible to be removed (the last ticked tool of a server is locked — “At least one tool
stays; untick the server instead.” — only when the agent allows it: a lone stray name can be unticked, which returns the step to the agent's tools). `max_turns` is conditionally required:
with a server ticked it gets an asterisk and the help below the field says so. Skills are chosen with checkboxes;
the order in the file is preserved when other items are toggled off and on. The instructions have the footer “Supports Markdown”.

### 2.8 Config

```
Config                                                                      [Save]  ⋯
┌ card: ~/lumen · [Form | <> YAML] Saved ✓ ────────────────────────────────┐
│ Connection [OPENROUTER_API_KEY] ✓  │ Jev model [jev-1.13] read-only     │
│ Models                                        [+ Add alias]              │
│ ┌ smart · anthropic/claude-haiku-4.5 · max_tokens · API ───────────┐ │
│ │ used by copywriter                          [Delete alias disabled] │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│ Storage                             │ Webhook and callback            │
│ Limits                              │ Variables (status rows)          │
│ MCP servers: the owner's note, nested cards with a Read-only chip    │
└───────────────────────────────────────────────────────────────────────┘
```
The section header has the only Save; the project path and the only Form | YAML toggle with the status are at the start of the
card (YAML mode shows `config.yaml` as text and below it the same MCP server cards). Pairs of sections form two columns, models
span the full width as nested cards. `_env` fields show only the variable name; the value is never
shown or edited. Below each alias is the meta “used by copywriter” / “unused”; a used alias cannot be deleted.
On a narrow screen the alias row wraps (the ID field keeps the smallest width).

**MCP servers are read-only in both modes** (since 0.18.0): `workflows/mcp.yaml` decides which programs start on the
host, so the API neither returns nor writes it (api.md “MCP servers are the owner's”) and the GUI never asks for
`files/mcp.yaml`. The section says so once above the cards — “MCP servers are set up by the project owner in
workflows/mcp.yaml on the server. This page only shows them.” — and without servers “This project has no MCP servers.”.
A server card comes from `mcp_servers` in `GET /projects/<p>` and shows the description, the transport (`stdio` /
`streamable-http` / `sse`), agents, tools (“not restricted by the owner” without an allowlist), scenarios, and each of
its variables that is missing on the server. Errors of the file (the project-level `errors` with `file: mcp.yaml`) are
listed above the cards; the owner fixes them on disk.

**Untrusted project** (`trusted: false` in `GET /projects/<p>` — every project created or added through the GUI or the
API): when the project has servers, the section shows a `bg-warning/10` notice with an icon, “MCP servers are switched
off in this project: …” and the command `agencast projects trust <name>` as a command line with “Copy command”. The same
notice (“This scenario uses an MCP server …”) is in the Run panel of a scenario whose validation errors name that
command, i.e. one the server will refuse to run (422, also for a dry run). The GUI has no control that changes trust —
no route sets it; the owner runs the command in a terminal on the server. A change that would make a scenario of an
untrusted project use a server (ticking a server on an agent of a `task` step) is refused by the server and the editor
shows its message, which names the command too. A scenario that already has that error can still be edited: unticking
some of its servers or fixing another error in it is saved (api.md “Editing”).

### 2.9 Skill

```
Skills                                                  [+ New skill] [Save]  ⋯
Saved ✓
 lumen-voice        │ lumen-voice
 ig-rules      │ ┌ SKILL.md (Markdown editor with line numbers) ──────────────────┐
                  │ │ ---                                                            │
                  │ │ name: lumen-voice …                                              │
                  │ └────────────────────────────────────────────────────────────────┘
                  │ Used by: copywriter · publisher
```
The same header as Agent, without the mode toggle (a skill is always the whole SKILL.md); ⋯ has only Delete.

## 3. Component inventory

| Component | Content | States |
|---|---|---|
| `StepCard` | a two-row pill: eyebrow `TYPE · id` + the value in bold (table in §2.3); a 36 px number in a circle; on the right `when` / in a run time + cost; the error below the card | default, hover, selected (ring with a gap), with an error, collapsed; in a run a status icon instead of the number, not-reached and skipped muted by a dashed outline without a fill and muted text (not by transparency, because of contrast) |
| `DeleteButton` | a red round 28 px outside the pill | hover / focus-within / permanent on touch |
| `ScenarioCard` | `IconChain` (max 5 + “+N”) and ⋯ on top, the chip of the last run with the time at the bottom right (validation errors take precedence), title = name, subtitle = description, meta “N steps · agents” + the label “callable” | default, hover, with validation errors |
| `ProjectCard` | name + ⋯, path mono, counts, below the line the chip of the last run + today's spend | available without a label; unavailable a dashed border without a fill + label and reason |
| `PageHeader` | H1 + `meta` + description, on the right at most two buttons and ⋯ (`menu`, `menuLabel`), above the title `back`, a second row `children` | sticky (`sticky`, height in `--page-header-h`) in the editor and the run detail |
| `AddCard` | a dashed card with +; scenario → the New scenario dialog (read-only phase: a CLI command with copying); project → a CLI command with copying | |
| `IconChain` | a type icon in a 28 px circle `bg-nested text-type`, an arrow → between them, file order | |
| `HeaderCard` | the scenario inputs row by row (name, required, type) and the outputs | like a card, not deletable, always first |
| `Connector` + `AddButton` | an arrow ↓ as a glyph between pills (a 44 px connector), on hover/focus it turns into a 44 px (+) circle; a permanent (+) only at the end of each list | default, focus, “paste the cut step” |
| `BranchColumn` / `CaseSection` | a `parallel` branch side by side / a `switch` case one below another, each with its own list and + | active, skipped in a run (muted with a reason) |
| `TypePicker` | a plain list at +, on a phone at the bottom edge; `bg-menu` without a border with a shadow, radius 12, padding 8, 40 px row; `role="listbox"` | `output` is not offered; after Cut also “Paste … here” |
| `StepPanel` | a floating rounded panel (16 px, 16 px from the edges), the eyebrow “STEP n” + the type as a select, trash and ×; the type field on top; at the bottom three collapsed rows Condition / Reliability / Step details as an accordion (`h-12 text-[15px]`, value `text-fg-muted`, `divide-y divide-line`, `aria-expanded`) | read, edit, with errors; in a run the tabs Prompt/Response/Output/Calls/Files |
| `Toggle` (`FormYamlToggle`) | a segmented toggle `bg-nested` r9 with 4 px padding; segment 44 px r7, 13 px, active `bg-accent text-ink`, inactive `text-fg-muted`; `role="radiogroup"`; for agents and skills the second segment is Markdown | a YAML syntax error = returning to Form disabled with the reason in `title` and `aria-description` |
| `YamlEditor`, `CodeBlock`, `Markdown` | a header with a name and a chip, `bg-nested` body mono 13 px, line numbers mono 12 px, highlight `surface-active`, a footer with a hint/position or Copy; Markdown uses `CodeBlock` | without errors, with a syntax error (Form disabled), with semantic errors |
| `Button` (`btn`) | height 44 px, radius 10 px, padding 18 px (measured from the .pen); `primary`: `bg-accent text-ink`; `secondary`: `bg-control text-fg`; `icon`: 44 px `bg-control`; `iconGhost`: 44 px without a fill (⋯ on cards); `danger`: `bg-danger text-error`; `ghost`: text only; `copyBtn`: an outlined Copy in a code block | default, hover, focus, disabled |
| `StatusIcon`, `StatusBadge`, `StatusChip` | always an icon + text (for the icon, text for the screen reader); chip `bg-nested`, padding 7×10 px, text mono 12 medium in the status colour; for “running” only the icon pulses | `succeeded` → `success`; `failed` → `error`; `warning`, `cancelled`, `interrupted` → `warning`; `running` → `running` (pulse only `motion-safe`); `queued`, `skipped`, `dry-run`, `none` → `neutral` |
| `Menu` | a ⋯ button (`btn.icon`) and a `bg-menu` list without a border with a `shadow-pop` shadow, radius 12, padding 8, gap 4; item 40 px, radius 7, hover `surface-active`; `MenuItem.danger` = `text-error`, `MenuItem.disabled` = reason in `title`, `aria-disabled` | at least 12 px from the viewport edge; arrows to move, Esc closes and returns focus |
| `TabLinks`, `Collapsible` | tabs 47 px, 13 medium, padding 0 18, gap 28, a 2 px `accent` underline; accordion row 52 px with an arrow on the left, title 14 medium, value mono 11 px `fg-muted` | active tab `aria-current`, accordion `aria-expanded` |
| `FormField`, `CodeInput`, `JsonInput`, `ValueInput` | label `fg-secondary` 13 px medium, help `fg-muted` 12 px, error mono `error`; field 44 px `bg-nested ring-line` radius 6 with an `accent` focus; variables `variable` | invalid `ring-error`; both the autocomplete and the variables menu keyboard-operable; in the run form `file`/`files` = a file picker (uploaded at once, previews with size and format, remove buttons, “Uploading…”, failures as `role=alert`) |
| `Modal` | backdrop `canvas/70`, panel `bg-surface` radius 14 and a shadow: header p24 with a line (title 22 + close 44; an info dialog without a cross), content p24 gap 18, footer p 18 24 with a line, on the right Cancel and then the action; on a phone a bottom sheet with top corners and a max height of `100dvh - 48px`; focus on the first action | Esc closes, Tab stays in the dialog, a dangerous action uses `btn.danger` |
| `CostChip`, `DurationChip` | `0.0015 USD` (decimal separator per locale, ≥ 4 places, zero = `0`, `USD` after the number with a fixed space), `17.5 s` / `1 min 12 s`; mono | for images “of which images …” in the header |
| `ExprInput`, `TemplateInput` | a mono field; an autocomplete for `inputs.` and `steps.<id>.<field>` only for steps above and in the same branch; a variables menu via a button next to the field | an error with a message and a caret `^` from the server |
| `ValidationError` | text below the field + a red dot at the card + the count in the header “Unsaved · 2 errors” (a click = jump to the first) | |
| `ConflictBar` | in the scenario editor the last row of the sticky header (the panel next to the column is placed below it), for an agent and Config a sticky bar above the form | see 4.6 |
| `EmptyState` | `bg-surface` radius 12, padding 28, gap 14, icon 28, title 18 semibold, an optional description 13 and a `CliLine` with a command; `tall` = 380 px (queue) | project without scenarios, without runs, a queued run, an unavailable project |
| `Skeleton`, `Loading` | pulsing `bg-surface` blocks; no spinners outside buttons | loading lists and cards |
| `ServerBar` → sidebar | “The agencast server is not responding (localhost:8787), retrying…” at the bottom of the sidebar (`role="alert"`); 401 = the Server token screen; 422 config = a block below the project header with a link to Config | |

## 4. Interactions

1. **Inserting a step:** a click on + (or Enter on a focused +) opens the `TypePicker` — a plain list to the right of + as in Buzz (flipped to the left when there is no room), without icons and group headings, the groups are separated by two hairlines only; the type keyword in mono (exactly what will be in the YAML) and 2–4 words of description in grey on the same row, so a beginner can tell `jev` from `ask`. Arrows, Enter, Esc, typing filters (`j` jumps to jev). After “Cut” there is an extra item at the top “Paste “tone_check” here”. The selection inserts a card with the id `<type>_<n>` and opens the panel. `output` is not in the list: it goes only at the end of the main list, and it is added by the offer at the end when missing; there is no + below it. `output` is not offered in a branch.

```
   (+)  ┌──────────────────────────────────────────┐
        │ Paste “tone_check” here                  │   only after Cut
        │ ──────────────────────────────────────── │
        │ ask       single agent call              │   highlighted
        │ task      agent with tools               │
        │ jev       cheap Jev decision             │
        │ image     generate an image              │
        │ ──────────────────────────────────────── │
        │ parallel  branches in parallel           │
        │ switch    one of several options         │
        │ call      run another scenario           │
        │ fail      stop the run with an error     │
        │ ──────────────────────────────────────── │
        │ set       compute values without an LLM  │
        └──────────────────────────────────────────┘
```
2. **Moving:** the ⋯ menu on a card “Move up/down” (keys Alt+↑/↓) within a list. Between lists (into a branch, out of it): “Cut” (Ctrl+X), after which every + offers “Paste “tone_check” here”. No drag & drop. A reference to a step further down after a move is caught by validation at the card.
3. **Deleting:** ⋯ → Delete or the Delete key. When a step is read by another step (`refs`) or has nested steps: a modal “Delete step “tone_check”?” — “Step “tone_check” is read by stop and out. …” / “This also deletes 3 steps inside.” with the button “Delete anyway”. Otherwise immediately, with “Undo” in the header (Ctrl+Z, until saved).
4. **Saving:** explicitly with the button or Ctrl+S, no autosave (the file is the truth, a work-in-progress state must not go to disk). While editing, validation through the server with a 500 ms delay, errors at cards and fields. Save sends the whole text with the version fingerprint; 422 = the file was not written, header “Unsaved · N errors”, jump to the first; deprecation warnings still allow saving. Leaving with unsaved changes asks. The work-in-progress text is kept in `localStorage` (key file + fingerprint) in case the page is reloaded. Form mode validates the work-in-progress tree continuously through `POST …/render` (operations → text and errors without writing, API 0.8.0), YAML mode through `POST …/validate` with the text; Save in Form sends a single batch `POST …/batch` (all or nothing).
5. **Form / YAML:** a single source = the raw text of the file; edits from the form are targeted patches to the text, so that comments and order survive (ig-post.yaml has numbered comments). YAML mode replaces the column of cards and the panel with a single block across the full width and height, as in Buzz:

```
← Scenarios
ig-post                                                          [▷ Run] [Save]  ⋯
[Form | <> YAML]   Unsaved · ✗ 1 error
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│  1  version: 1                                                                             │
│  2  name: ig-post                                                                          │
│  …                                                                                         │
│ 52    - id: photo_prompt                                                                    │
│ 53      ask:                                                                               │
│▌54        agent: photographr                                                               │
│ 55        prompt: |                                                                        │
│  …                                                                                         │
└────────────────────────────────────────────────────────────────────────────────────────────┘
You are editing workflows/scenarios/ig-post.yaml directly. Changes are written only when you click Save.
✗ line 54 · step photo_prompt · agent 'photographr' does not exist (agents/photographr.md)
```
   - A deviation from Buzz: a narrow grey column with line numbers, because both the `validate` messages and the YAML loader errors (duplicate key) refer to a line. Syntax highlighting: keys light, comments muted, variables in the `variable` colour and operators in the `success` colour. Every YAML in the GUI is coloured the same way: the editor, the diff on conflict, `.yaml` files in a run, ```` ```yaml ```` blocks in Markdown and the expression and template fields in the step panel; for `.md` (agent, skill) only the frontmatter.
   - The hint below the block names the file (a reminder that “the file is the truth”), not a generic sentence.
   - **Errors:** while typing (500 ms) `POST validate`; the faulty line has an `error/10` background and a vertical `error` mark on the left, below the block a list of errors (line · step · message), a click jumps to the line. A YAML syntax error is shown immediately with the line and blocks returning to Form (the toggle is muted, tooltip “Fix the YAML: line 12”); semantic errors (unknown agent) do not block returning, they are shown on the cards. Save is disabled while there is any error.
   - Switching Form → YAML puts the cursor on the `- id:` line of the selected step and briefly highlights its lines; the header card leads to the start of the file. YAML → Form: selects again the step the cursor was in.
   - The same for Config (`config.yaml` only — `mcp.yaml` is the owner's file and is not available through the API, §2.8), for agents and skills the second segment is `<> Markdown` and the block shows the whole file including the frontmatter.
6. **File conflict:** the GUI keeps a fingerprint; a check on window focus and every 5 s. A change on disk without local edits = a silent reload + a short message “Reloaded from disk (2:05 PM)”. With local edits a sticky bar: “The file changed on disk.” [Show diff] [Reload from disk and discard my changes] [Keep mine]; Save then requires the confirmation “Overwrite the version on disk”. Never automatic merging.
7. **`call`:** the card shows the target scenario and the number of inputs; “open” loads the target scenario in the same editor with the breadcrumbs `ig-post › propose › ig-text`, back returns to the card. A target without `callable: true` = an error at the card with a link to the target scenario's header. In a run `call` expands right in the card into nested cards with a status.
8. **Live run:** while the run is `queued`/`running`, the GUI reads `GET /runs/<id>` every 2 s (every 5 s after 2 min). The running card pulses, the elapsed time ticks locally between polls, the cost in the header grows. “follow run” scrolls the view to the active card. At the end a bar “Run finished: succeeded/failed” and the Summary is loaded. The run list refreshes every 5 s while something is running. SSE later without a screen change.
9. **Changing the step type** in the panel: keeps the id and `when`, discards the other fields; a modal only when filled-in fields would be lost.

## 5. Visual principles (Tailwind) — after the Buzz screenshot

**Tokens (V3).** The binding names and values of colours, fonts and radii are in the [redesign plan, §1](redesign-plan.md#1-tokens-contract-for-everyone). Rules G7, G8 and G15 apply above the reference exports.

- **Surface ladder:** page `bg-app` (a gradient from the .pen over `canvas`), card and panel `bg-surface`, hover `bg-surface-hover`, fields, chips and branches `bg-nested` with an optional `ring-line`. The selected card has `ring-2 ring-accent` without an offset. No transparent surfaces and no `backdrop-blur`.
- Boxes grouping fields have the `group` surface (`#132032`, between the card and the field), the fields themselves stay `nested` (`#0D192A`). Checkboxes and radios have an empty `control` surface, selected `accent` and a dark tick or dot.
- **Colour:** primary text `fg`, labels `fg-secondary`, meta `fg-muted`, type icons `type`; the run status has an icon and text with the colours `success`, `error`, `running`, `warning` and `neutral`. Pulse only `motion-safe`.
- **Shapes:** the step pill `rounded-full` with a 40 px circle, container/scenario card `rounded-tile`, panel `rounded-panel`, controls `rounded-control`; the small (+) a 28 px circle with `ring-line`.
- **Text in the pill:** type 11 px uppercase, id mono 13 px `fg-secondary`, value 14 px semibold `fg`, meta 13 px `fg-muted`. Mono also for expressions, `run_id`, costs and YAML.
- **Spacing:** an 8 px scale; pill `px-5 py-3`, the number in a circle 12 px from the text, the arrow between pills in a 40 px gap, panel `p-5` with a 20 px inner section gap, panel margin from the edges 16 px.
- **Widths:** column of cards up to 676 px, panel 440 px (in a run 520), gap 28 (measured from the .pen); the panel layout is governed by §2.3 and responsiveness by G14. The concrete element dimensions are in [redesign-fidelity.md](redesign-fidelity.md).
- **Type icons** (lucide, 16 px, stroke 1.5, always with the text name of the type): ask `message-square`, task `bot`, jev `scale`, image `image`, parallel `columns-2`, switch `split`, call `corner-down-right`, set `equal`, fail `octagon-x`, output `package-check`.
- **Don't:** borders around pills and sections (only a ring for the selected one), shadows, nested boxes beyond two levels, lines instead of arrows between steps, more than two labels on a card, status by colour alone, a tooltip as the only carrier of information, 12 px text for content, overlay spinners.

- **Card grid:** `grid gap-5`, card min 340 px, `bg-surface rounded-tile` (14 px), project p 22, scenario p 24; the dashed card only in an empty list.
- **Type icons on scenario cards:** plain 18 px `text-type` icons with a gap of 10, without circles and arrows, then optionally “+N”.
- **Trash:** `bg-error/15 text-error hover:bg-error/25`.
- **Status chip on a scenario card:** icon + 12 px text, `bg-nested rounded-full px-2`; only the icon is coloured.

## 6. Accessibility and keyboard

- Cards are buttons in a list: ↑/↓ move focus, Enter/space opens the panel, Esc closes and returns focus to the card, Delete deletes (with protection), Alt+↑/↓ moves, Ctrl+S saves, Ctrl+Z undoes.
- + is a real button in the tab order, visible even without hover. The panel is an `aside` with `aria-labelledby`; form fields have the label above the field, `aria-describedby` for both the help and the error.
- Focus `:focus-visible` = `ring-2 ring-accent ring-offset-2 ring-offset-canvas` globally in `index.css`; contrast of readable text ≥ 4.5:1 (token measurements in the redesign plan §1); status is always icon + text (for a lone dot `sr-only`); a live run announces changes via `aria-live="polite"` (“step photo running”).
- `<html lang>` follows the chosen locale (§1.2), all strings are in `locales/en.json` and `locales/cs.json` (keys like `run.tab.summary`, `rstatus.skipped`), ICU plurals (`{n, plural, one {# step} other {# steps}}`; Czech adds `few`/`many`), numbers via `Intl.NumberFormat(locale)`, times local with UTC in the tooltip.

## 7. What the GUI needs from the API in addition (changes what can be built)

1. `GET` of the raw file text with a fingerprint and `PUT` with a fingerprint (conflict = 409), for scenarios, agents, skills, config. *(0.5.0: `files` with `etag` = sha256, 409 on mismatch.)*
2. `POST …/validate` without writing, errors as `{file, step, field, line, message}`.
3. `GET /projects/<p>/config` without secrets (+ optionally a “variable is set” flag), the agent and skill body.
4. In the run list `scenario`, `started_at` and for a running run `current_step`; today this can only be derived from `run_id`.

## 8. Questions for the user and decisions

1. *A read-only first version, or the editor right away?* — **The editor right away**; the run viewer is its read-only mode (decided 2026-09-26, the user wants the editing variant).
2. *Preserve comments and order in YAML?* — **Yes**, a round trip on the server (agencast 0.5.0, ruamel.yaml), the GUI sends operations, not text.
3. *The accent from Skynet Soul, or grey like Buzz?* — **Grey like Buzz**; colour only for run statuses and errors and **the only accent spot is the type icon squares on scenario cards** (like the blue squares in the Buzz list), the colour taken from the Skynet Soul dashboard. Background and font also from Soul. (The designer's recommendation after the screenshots, accepted by the coordinator; the user can change it.)
4. *Show whether an environment variable is set (only ✓/✗)?* — **Yes**, never the value. Requires item 7.3.
5. *Starting a run from the GUI with an input form?* — **Yes**, `POST /projects/<p>/runs` with an optional callback URL. Requires an API change. The “Run” panel (redesign V3): eyebrow “START RUN”, title = the scenario; inputs by type; “Run mode” (label 11 px uppercase) as two selectable `nested` r8 p14 cards with a 20 px radio inside (Dry run — plan only, no model calls; starts the MCP servers to list their tools / Live run — calls models and costs money; the selected one has `ring-1 ring-accent`); “Run limits” (per run, of which images, run timeout, spent today / limit) as 32 px rows with separators (label 12 `fg-secondary` on the left, value mono 12 on the right) only for a live run; a warning in `bg-warning/10` with an icon for unsaved changes, and in the same style the notice of an untrusted project with the command `agencast projects trust <name>` when the scenario uses an MCP server (§2.8); Start is disabled while an image upload is in flight; the API error; on the right a secondary “Cancel” (closes the panel like ✕ and Esc) and a primary “▷ Start dry run” / “Start live run” / “Starting…” (fidelity §7, 0.16.1; on a narrow screen stacked across the full width).

Items 7.2–7.4 and 8.5 go into the follow-up task “API additions for the GUI” after 0.5.0.

The variables menu is inspired by Webflow: the button next to an expression and a template opens the available values and the selection inserts the variable at the cursor position. Purple marks a variable, blue stays for the step types on the cards.
