# ui — AgenCast GUI

A thin shell over the `agencast serve` HTTP API (`docs/spec/api.md`), design in `docs/ui/gui-design.md`.
React 18 + Vite + TypeScript + Tailwind; it parses and validates nothing itself.

- **Editing (part 2, API 0.10.0):** the file is the source of truth, no autosave. Form mode holds the
  draft step tree (`src/edit.ts`, `src/scenarioDraft.ts`), validates it continuously via
  `POST …/render` and on Save / Ctrl+S sends it in a single `POST …/batch` with an `etag` fingerprint
  (all or nothing); YAML/Markdown mode holds the text (`src/textfile.ts`) and validates it via
  `POST …/validate`; YAML → Form converts unsaved text via `POST …/render {text}`. Draft state is kept in `localStorage` (`agencast.draft.*`), and changes on disk
  are watched by `HEAD …/files/<path>` every 5 s and on window focus (conflict → `ConflictBar`).
  What the API lacks: `docs/ui/api-findings.md`.

- **Projects (part 5, API 0.10.0):** cards take counts and today's spend from `GET /projects`, with
  no extra requests for the detail or the spend of each card. “Add project” creates a new one (`POST /projects/new`) or adds an
  existing one (`POST /projects`), the card menu removes it from the registry (`DELETE /projects/<p>`); without
  `writable` there is only a command for the CLI.

- **Runs (part 3, API 0.10.0):** status only from `state` (only `queued`/`running` are polled, `interrupted`
  has its own label), run cards from the `tree`/`callees` snapshot, step data from `steps`, the step panel
  from `GET …/runs/<id>/steps/<path>` (events.jsonl is not downloaded). Scenario and project cards take
  `types`, counts and `last_run` from the overview; the run list paginates via `?scenario=&limit=&before=`. What the API lacks:
  `docs/ui/api-findings.md`, part 3.

- **Development:** in the `ui/` folder run `npm install`, then in a second terminal
  from the repository root `uv run --project framework agencast serve --port 8787 --cors http://localhost:5173`
  (set `AGENCAST_TOKEN` for registry mode) and in the `ui/` folder run `npm run dev`
  (the GUI calls `http://127.0.0.1:8787`; put a different address in `VITE_AGENCAST_URL`).
- **Build:** `npm run build` writes to `framework/src/agencast/ui/` (in `.gitignore`), `serve` serves it at `/`.
- **Token:** the GUI asks for it (`AGENCAST_TOKEN` in registry mode, otherwise `webhook.token_env`) and keeps
  it only in the browser's `localStorage`; on a 401 it asks again.
- **Checks:** `npm test`, `npm run typecheck`.
- **Languages:** the GUI is English by default. Strings are in `src/locales/en.json` (the source of truth) and
  `src/locales/cs.json` (Czech translation), with ICU plurals; every string goes through `t()` and is added to both
  files (`i18n.test.ts` checks that the keys match).

## E2E (Playwright)

- `npm run e2e` builds the GUI and runs `e2e/*.spec.ts` in headless Chromium; `npm run e2e:report` opens the HTML report.
- Prerequisite: `uv sync --project ../framework` (the `framework/.venv/bin/agencast` binary, otherwise `AGENCAST_BIN`)
  and the Playwright 1.62 browser (`npx playwright install chromium`).
- Each worker runs its own `agencast serve --fake` (port from `E2E_PORT`, default 18700) with `AGENCAST_CONFIG_DIR`
  in tmp; each test creates a project via `POST /projects/new` (`e2e/fixtures.ts`). Network only on localhost.
- The tests cover journeys C1–C18 and states N1–N6 from `docs/ui/user-journeys.md`.

Example projects for manual testing are in `../examples/showcase/` and
`../examples/tutorial/`; add them to the GUI with `agencast projects add <path>`.
