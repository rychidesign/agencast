# ui — GUI AgenCast

Tenká obálka nad HTTP API `agencast serve` (`docs/spec/api.md`), návrh `docs/ui/navrh-gui.md`.
React 18 + Vite + TypeScript + Tailwind; nic neparsuje ani nevaliduje samo.

- **Editace (část 2, API 0.10.0):** soubor je pravda, žádný autosave. Form režim drží
  rozpracovaný strom kroků (`src/edit.ts`, `src/scenarioDraft.ts`), průběžně ho validuje přes
  `POST …/render` a při Uložit / Ctrl+S ho pošle jednou dávkou `POST …/batch` s otiskem `etag`
  (vše, nebo nic); YAML/Markdown režim drží text (`src/textfile.ts`) a validuje ho přes
  `POST …/validate`; YAML → Form převádí neuložený text přes `POST …/render {text}`. Rozpracovaný stav je v `localStorage` (`agencast.draft.*`), změnu na disku
  hlídá `HEAD …/files/<cesta>` každých 5 s a při fokusu okna (konflikt → `ConflictBar`).
  Co API chybí: `docs/ui/nalezy-api.md`.

- **Projekty (část 5, API 0.10.0):** karty berou počty a dnešní útratu z `GET /projects`, bez
  dalších dotazů na detail ani útratu každé karty. „Přidat projekt“ založí nový (`POST /projects/new`) nebo přidá
  existující (`POST /projects`), menu karty odebere z registru (`DELETE /projects/<p>`); bez
  `writable` jen příkaz pro CLI.

- **Běhy (část 3, API 0.10.0):** stav jen z `state` (dotazuje se jen `queued`/`running`, `interrupted`
  má vlastní štítek), karty běhu ze snímku `tree`/`callees`, údaje kroků ze `steps`, panel kroku
  z `GET …/runs/<id>/steps/<cesta>` (events.jsonl se nestahuje). Karty scénářů a projektů berou
  `types`, počty a `last_run` z přehledu; seznam běhů stránkuje přes `?scenario=&limit=&before=`. Co API chybí:
  `docs/ui/nalezy-api.md`, část 3.

- **Vývoj:** `npm install`, pak `agencast serve --cors http://localhost:5173` a `npm run dev`
  (GUI volá `http://127.0.0.1:8787`, jinou adresu dej do `VITE_AGENCAST_URL`).
- **Build:** `npm run build` zapíše do `framework/src/agencast/ui/` (v `.gitignore`), `serve` ho podává na `/`.
- **Token:** GUI se ho zeptá (`AGENCAST_TOKEN` v režimu registru, jinak `webhook.token_env`) a drží
  ho jen v `localStorage` prohlížeče; při 401 se zeptá znovu.
- **Kontroly:** `npm test`, `npm run typecheck`. Řetězce jsou v `src/locales/cs.json` (ICU plurály).

## E2E (Playwright)

- `npm run e2e` sestaví GUI a spustí `e2e/*.spec.ts` v headless Chromiu; `npm run e2e:report` otevře HTML report.
- Předpoklad: `uv sync --project ../framework` (binárka `framework/.venv/bin/agencast`, jinak `AGENCAST_BIN`)
  a prohlížeč Playwrightu 1.62 (`npx playwright install chromium`).
- Každý worker pouští vlastní `agencast serve --fake` (port od `E2E_PORT`, výchozí 18700) s `AGENCAST_CONFIG_DIR`
  v tmp; každý test si založí projekt přes `POST /projects/new` (`e2e/fixtures.ts`). Síť jen na localhost.
- Testy pokrývají cesty C1–C18 a stavy N1–N6 z `docs/ui/uzivatelske-cesty.md`.
