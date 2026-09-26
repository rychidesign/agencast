# ui — GUI AgenCast

Tenká obálka nad HTTP API `agencast serve` (`docs/spec/api.md`), návrh `docs/ui/navrh-gui.md`.
React 18 + Vite + TypeScript + Tailwind; nic neparsuje ani nevaliduje samo.

- **Editace (část 2):** soubor je pravda, žádný autosave. Form režim drží rozpracovaný strom kroků
  (`src/edit.ts`, `src/scenarioDraft.ts`) a při Uložit / Ctrl+S ho převede na editační operace API
  v pořadí, každou s otiskem `etag`; YAML/Markdown režim drží text (`src/textfile.ts`) a validuje ho
  průběžně přes `POST …/validate`. Rozpracovaný stav je v `localStorage` (`agencast.draft.*`),
  změnu na disku hlídá dotaz každých 5 s a při fokusu okna (konflikt → `ConflictBar`).
  Co API pro editaci chybí: `docs/ui/nalezy-api.md`, část 2.

- **Běhy (část 3, API 0.7.0):** stav jen z `state` (dotazuje se jen `queued`/`running`, `interrupted`
  má vlastní štítek), karty běhu ze snímku `tree`/`callees`, údaje kroků ze `steps`, panel kroku
  z `GET …/runs/<id>/steps/<cesta>` (events.jsonl se nestahuje). Karty scénářů a projektů berou
  `types` a `last_run` z přehledu (žádné N+1), seznam běhů `?scenario=&limit=`. Co API chybí:
  `docs/ui/nalezy-api.md`, část 3.

- **Vývoj:** `npm install`, pak `agencast serve --cors http://localhost:5173` a `npm run dev`
  (GUI volá `http://127.0.0.1:8787`, jinou adresu dej do `VITE_AGENCAST_URL`).
- **Build:** `npm run build` zapíše do `framework/src/agencast/ui/` (v `.gitignore`), `serve` ho podává na `/`.
- **Token:** GUI se ho zeptá (`AGENCAST_TOKEN` v režimu registru, jinak `webhook.token_env`) a drží
  ho jen v `localStorage` prohlížeče; při 401 se zeptá znovu.
- **Kontroly:** `npm test`, `npm run typecheck`. Řetězce jsou v `src/locales/cs.json` (ICU plurály).
