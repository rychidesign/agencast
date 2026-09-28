# AgenCast framework

Verze 0.17.0, Python 3.12 + uv. Formáty podle `docs/spec/` (v1), návrh
v `docs/DESIGN.md`. Balík i příkaz se jmenují `agencast` (do 0.2.5
`maw`); jméno příkazu je v `pyproject.toml` (`[project.scripts]`).

Balíček obsahuje i skilly, dokumentaci a příklady: [návod](../docs/getting-started.md).

## Použití

Příkazy spouštějte z kořene klonu repozitáře.

```
uv run --project framework agencast --project examples/showcase validate ig-post
uv run --project framework agencast --project examples/showcase run ig-post -i tema="nová káva" --dry-run
uv run --project framework agencast --project examples/showcase run ig-post -i tema="nová káva" --fake examples/showcase/fake/ig-post.yaml
uv run --project framework agencast --project examples/showcase run ig-post -i tema="nová káva"
uv run --project framework agencast --project examples/showcase run ukazka-task -i knihy="Čapek: R.U.R. (1920)" --fake examples/showcase/fake/ukazka-task.yaml
uv run --project framework agencast --project examples/showcase runs list
uv run --project framework agencast --project examples/showcase runs show <run_id>
uv run --project framework agencast --project examples/showcase serve --host 127.0.0.1 --port 8080 [--workers 2] [--cors http://localhost:5173]
uv run --project framework agencast --project examples/showcase migrate examples/showcase/workflows/scenarios/ig-post.yaml
uv run --project framework agencast new project ~/muj-projekt [--example showcase|tutorial]
uv run --project framework agencast new agent recenzent | new scenario kontrola [--project <cesta>]
uv run --project framework agencast skills list | path | install [--to all] [--prefix DIR] [--copy] [--force]
uv run --project framework agencast docs [show spec/scenario.md]
uv run --project framework agencast projects list | add <cesta> [--name N] | rm <jméno>
```

- Scénář jde zadat jménem (`ig-post`) nebo cestou k `.yaml`. Kořen
  projektu = první složka s `workflows/` od aktuální složky nahoru, nebo
  `--project <cesta>` u kteréhokoli příkazu — všechno funguje z libovolné
  složky.

- Konfigurace `workflows/config.yaml` (vzor `config.example.yaml`) a
  registr MCP serverů `workflows/mcp.yaml` (vzor `mcp.example.yaml`; oba
  mění jen vlastník). Klíče jen z prostředí nebo z `.env` v kořeni
  projektu.
- Krok `task` spouští MCP servery z `mcp.yaml` jednou za běh (stdio přes
  `npx` potřebuje Node; na Modalu balíček předinstalovat). stderr serverů
  je v záznamu běhu v `mcp/<server>.stderr.log`.
- `--fake` nahrazuje volání modelů bez ceny za model a bez klíče OpenRouteru;
  volitelný YAML obsahuje skriptované odpovědi (popis v `src/agencast/fake.py`).
  MCP servery z `mcp.yaml` v kroku `task` jsou skutečné i s `--fake`; ukázkový
  `filesystem` přes `npx` potřebuje Node.js a při prvním spuštění stáhne balíček.
  Callback se odesílá doopravdy a potřebuje podpisové tajemství. Zaručeně offline
  jsou jen scénáře bez `task` (i ve volaných scénářích) a bez `--callback-url`, např. `ig-post`.
- `--callback-url https://…` pošle po běhu výsledek podepsaný HMAC
  (`callback.secret_env`).
- Záznamy běhů jsou v `runs/` (v `.gitignore`), soubory z `output`
  v `outputs/` (`storage.type: local`).
- Každý běh má `report.html` (jeden soubor, CSS uvnitř, bez externích
  zdrojů, prompty a odpovědi v `<details>`); kopie jde do úložiště a jeho
  URL je v callbacku jako `report_url` (`storage.type: local` → `file://`).
- `new project <cesta>` založí `workflows/` (config, agent `pisatel`,
  scénář `ukazka` — projdou `validate --offline` i `--fake`),
  `.env.example` a `.gitignore`; `new agent|scenario <jméno>` přidá
  minimální soubor do projektu. Nic nepřepisuje (docs/spec/projects.md).
- Registr projektů `~/.config/agencast/projects.yaml` (`AGENCAST_CONFIG_DIR`)
  plní `new project`, `projects add` a úspěšný `run` (`validate` od 0.15.1
  registr nemění); GUI může
  zapisovat v režimu registru. `projects_root` určuje výchozí složku pro
  nové projekty (výchozí `~/workspace`).
- `migrate`: ve v1 není co převádět; neznámá verze = chyba `config`.
- Návratový kód: 0 úspěch, 1 běh skončil chybou, 2 chyba `config`
  (validate, vstupy, prostředí).

## Webhook server (`agencast serve`)

Smlouva: `docs/spec/webhook.md`. Stdlib `ThreadingHTTPServer`, žádný
webový framework.

```
POST /runs            Authorization: Bearer $WEBHOOK_TOKEN
{"scenario": "ig-post", "inputs": {"tema": "…"}, "callback_url": "https://…", "request_key": "n8n-4711"}
→ 202 {"run_id": "…", "queue_position": 1}   běh je ve frontě, výsledek přijde na callback_url
→ 200 {"run_id": "<původní>", "queue_position": null}   request_key už byl použit
→ 401 / 422 {"error": "…", "details": [...]}   nic nevzniká, callback nepřijde
GET /runs/<run_id>    stav: queued (+ queue_position) / running / tělo callbacku + callback_failed
GET /projects, /projects/<p>[/scenarios/<s>|/runs[/<id>[/files/<cesta>]]|/spend?day=]   čtecí API (docs/spec/api.md)
POST /projects/<p>/runs   jako POST /runs v projektu <p>; callback_url volitelná, "dry_run": true → jen plán
POST /projects/<p>/validate   validace bez zápisu ({path, text} nebo prázdné tělo), chyby jako objekty
POST /projects/new       založí projekt ze šablony a zapíše jej do registru
POST /projects           zapíše existující projekt s workflows/config.yaml
DELETE /projects/<p>     odebere projekt jen z registru, soubory zůstanou
GET /, /assets/…      GUI (framework/src/agencast/ui/, bez tokenu)
```

- **GUI** (od 0.6.0): `serve` podává sestavené GUI z
  `framework/src/agencast/ui/` (výstup `npm run build` ve složce `ui/`
  repozitáře; git ho ignoruje, do wheelu jde přes `artifacts`). `GET /`
  a `/assets/…` jsou bez tokenu, token chrání jen `/projects…` a `/runs…`;
  cesta bez přípony vrátí `index.html` (hash routing). Bez sestaveného
  GUI vrátí `GET /` 404 s návodem. Při vývoji GUI z `vite dev` (jiný
  origin) pusť `serve --port 8787 --cors http://localhost:5173` — bez přepínače
  žádné CORS hlavičky.

- V projektu nebo s `--project` jeden projekt (token `webhook.token_env`);
  **mimo projekt režim registru**: všechny projekty z registru, token
  serveru `AGENCAST_TOKEN`, tajemství z prostředí serveru a `.env` v cwd,
  `/runs` jen přes `/projects/<p>/runs`.

- `--host` a `--port` přepisují `AGENCAST_HOST` a `AGENCAST_PORT`; výchozí
  hodnoty jsou `127.0.0.1` a `8080`. `AGENCAST_PORT` musí být celé číslo 1–65535.
  Tyto proměnné se čtou z prostředí procesu při parsování argumentů;
  `.env` v cwd se načítá až potom, proto z něj bind adresu ani port nenastavíš.
- Pro režim registru může `~/.config/agencast/serve.env` obsahovat
  `AGENCAST_TOKEN`, `AGENCAST_HOST` a `AGENCAST_PORT`:

  ```dotenv
  AGENCAST_TOKEN=<tajný-token>
  AGENCAST_HOST=127.0.0.1
  AGENCAST_PORT=8080
  ```

  Pro přístup z jiných zařízení nastav `AGENCAST_HOST` na privátní adresu
  rozhraní Tailscale. Služba systemd uživatele:

  ```ini
  [Unit]
  Description=AgenCast server
  [Service]
  ExecStart=%h/.local/bin/agencast serve
  EnvironmentFile=%h/.config/agencast/serve.env
  Restart=on-failure
  [Install]
  WantedBy=default.target
  ```

- Start potřebuje proměnné `webhook.token_env`, `callback.secret_env`
  a (bez `--fake`) klíč OpenRouteru; jinak skončí chybou `config`.
- Běhy jdou jeden po druhém (jedno pracovní vlákno); `--workers N` pustí
  N běhů najednou, pořadí dokončení pak není zaručené. Fronta a
  `request_key` jsou soubory v `<runs>/_queue/` — po restartu serveru se
  čekající požadavky zpracují; běh přerušený uprostřed se neopakuje,
  pošle se callback `internal` (ověř ručně).
- Volitelné `limits.max_parallel_runs` a `limits.daily_budget_usd`
  v `config.yaml` (od 0.3.1) platí pro všechny běhy nad jedním `runs/` —
  `serve`, ruční CLI i cron sdílí jeden strop (docs/spec/config.md).
- Callback: `https://` (výjimka `http://127.0.0.1` pro testy), podpis
  `X-Signature: sha256=<HMAC>`, 3 pokusy, pak `callback_failed`.
- Server je HTTP bez TLS a GUI nemá tokenovou ochranu. Nikdy ho
  nevystavuj veřejně; binduj jen na localhost nebo privátní síť, například
  Tailscale. Nasazení na Modal je Fáze 3c.

## Testy

```
cd framework && uv run pytest
```

Konformační sada (DESIGN §5.6, §5.9): výrazy (58 případů ze spiku (c)
upravených podle spec + pravidla spec), loader, validate, engine (třídy
chyb, retry, kaskáda, parallel, switch, rozpočet, timeout, callback,
maskování), krok `task` s falešným MCP serverem `tests/fake_mcp_server.py`
(oprávnění, normalizace schémat, smyčka, skilly, `dedupe_key`, zbylé
procesy) a zlaté scénáře — každý soubor v `examples/*/workflows/` a každá ukázka
v `docs/spec/`. Nový scénář v `examples/*/workflows/scenarios/` se testuje sám;
skriptované odpovědi pro něj patří do `../examples/<projekt>/fake/<jméno>.yaml`.

## Struktura (vrstvy DESIGN D3)

| Soubor | Vrstva |
|---|---|
| `loader.py` | čtení souborů: YAML 1.2 core, frontmatter, `.env`, JSON Schema ze spec |
| `validate.py` | statické kontroly (scenario.md §7), vstupy |
| `expressions.py` | výrazy a šablony (scenario.md §5) |
| `engine.py` | běh: kroky, retry, timeout, rozpočet, callback |
| `providers.py` | OpenRouter chat / Jev / obrázek, třídy chyb, kaskáda |
| `fake.py` | falešný poskytovatel (`httpx.MockTransport`) |
| `record.py` | záznam běhu, summary.md, plan.md, report.html |
| `server.py` | webhook server, fronta, request_key, API `/projects/...` (čtení, editace, validate), GUI a `--cors` |
| `mcp_client.py` | `mcp.yaml`, MCP servery běhu (SDK `mcp` 2.2), normalizace schémat nástrojů |
| `task.py` | krok `task` (smyčka model ↔ nástroje, `load_skill`), `dedupe_key` |
| `projects.py` | registr projektů, šablony pro `agencast new`, popis projektu a scénáře pro GUI |
| `api.py` | veřejné API pro obálky (CLI, `serve`, později Modal a MCP): `load`, `run`, `dry_run`, `runs_list`, `run_status`, `new_*` |
| `cli.py` | příkaz `agencast` |

Zatím ne: Modal a úložiště R2 (Fáze 3c). Nejasnosti spec: `docs/spec/ISSUES.md`.

Historické protokoly jsou v [archivu ostrých běhů](../docs/archive/ostre-behy-2026-09.md).
