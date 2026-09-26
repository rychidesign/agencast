# ui — GUI AgenCast

Tenká obálka nad HTTP API `agencast serve` (`docs/spec/api.md`), návrh `docs/ui/navrh-gui.md`.
React 18 + Vite + TypeScript + Tailwind; nic neparsuje ani nevaliduje samo.

- **Vývoj:** `npm install`, pak `agencast serve --cors http://localhost:5173` a `npm run dev`
  (GUI volá `http://127.0.0.1:8787`, jinou adresu dej do `VITE_AGENCAST_URL`).
- **Build:** `npm run build` zapíše do `framework/src/agencast/ui/` (v `.gitignore`), `serve` ho podává na `/`.
- **Token:** GUI se ho zeptá (`AGENCAST_TOKEN` v režimu registru, jinak `webhook.token_env`) a drží
  ho jen v `localStorage` prohlížeče; při 401 se zeptá znovu.
- **Kontroly:** `npm test`, `npm run typecheck`. Řetězce jsou v `src/locales/cs.json` (ICU plurály).
