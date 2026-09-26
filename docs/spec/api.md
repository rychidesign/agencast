# Čtecí API `agencast serve` — rodina `/projects/...` (od frameworku 0.4.0)

Pro GUI (DESIGN „Obálky“) a kohokoli, kdo chce číst projekty a běhy přes
HTTP. Doplňuje [webhook.md](webhook.md) — `POST /runs`, `GET /runs/<id>`
a callbacky se nemění. Projekty: [projects.md](projects.md).

## Režimy serveru

| Spuštění | Režim | Token (`Authorization: Bearer …`) | `/runs` |
|---|---|---|---|
| `agencast serve` v projektu (složka s `workflows/` od cwd nahoru) nebo `--project <cesta>` | jeden projekt (jako do 0.3.x; Modal) | hodnota `webhook.token_env` projektu | ano, beze změny |
| `agencast serve` mimo projekt | registr | proměnná **`AGENCAST_TOKEN`** (povinná při startu, jinak `config`) | ne — 404, běh přes `POST /projects/<p>/runs` |

- V jednoprojektovém režimu je v `/projects` právě ten projekt; jméno má
  z registru, jinak výchozí (jméno složky, [projects.md](projects.md)).
- **Tajemství v režimu registru:** `serve` bere všechna tajemství
  z prostředí svého procesu (a z `.env` v aktuální složce); `.env`
  jednotlivých projektů se v registru nečtou. Jména proměnných
  (`openrouter.api_key_env`, `callback.secret_env`) se dál berou
  z `config.yaml` projektu, hodnoty z prostředí serveru.
- Registr se čte při každém požadavku. Každý projekt má vlastní frontu
  (`<runs>/_queue/`) a `--workers N` pracovních vláken; fronty dostupných
  projektů se obnoví při startu, projekt přidaný později při prvním `POST`.
- Čtení i zápis používají stejný token. Chybějící/nesedící token → 401.

## Endpointy

Odpovědi jsou JSON (kromě `files/`). Chyby `{"error": "…"}`, u 422 navíc
`"details": [...]`.

| Metoda a cesta | Odpověď |
|---|---|
| `GET /projects` | `{"projects": [{"name", "root", "available"}]}` |
| `GET /projects/<p>` | popis projektu (níže) |
| `GET /projects/<p>/scenarios/<s>` | scénář se stromem kroků (níže) |
| `GET /projects/<p>/runs` | `{"runs": [...]}` — položky jako `agencast runs list`: čekající `{"run_id", "status": "queued"}`, pak `{"run_id", "status", "cost_usd", "duration_s", "callback"}`, nejnovější první |
| `GET /projects/<p>/runs/<id>` | stav běhu + kroky + soubory (níže); čekající ve frontě `{"run_id", "status": "queued"}` |
| `GET /projects/<p>/runs/<id>/files/<cesta>` | obsah souboru ze složky běhu (`summary.md`, `report.html`, `events.jsonl`, `steps/…`), `Content-Type` podle přípony |
| `GET /projects/<p>/spend?day=RRRR-MM-DD` | denní kniha útraty ostrých běhů: `{"day", "total_usd", "runs": [{"run_id", "cost_usd", "finished_at"}]}`; bez `day` dnešek (UTC); jiný tvar `day` → 422 |
| `POST /projects/<p>/runs` | totéž co `POST /runs` ([webhook.md](webhook.md)) v projektu `<p>` — stejné tělo, odpovědi 202/200/401/422 i callback |

- **404** s JSON chybou: neznámý projekt, nedostupný projekt
  (`available: false`), neznámý scénář, běh, soubor nebo adresa. Cesta
  souboru mimo složku běhu (`..`, absolutní cesta, symlink ven) = 404.
- **422**: `config.yaml` projektu neprošel kontrolou (`details` = chyby);
  u `POST` i chybějící proměnná prostředí projektu.
- `spend` čte jen knihu ostrých běhů (`_ledger/`); falešné běhy
  (`--fake`) mají vlastní `_ledger-fake/` a v `spend` nejsou.

### `GET /projects/<p>`

```json
{
  "name": "thtd", "root": "~/thtd",
  "models": {"chytry": "anthropic/claude-haiku-4.5"},
  "limits": {"run_budget_usd": 1.0, "run_timeout": "1h", "max_call_depth": 3},
  "scenarios": [{"name": "ig-post", "description": "…", "inputs": {…}, "outputs": {…},
                 "callable": false, "steps_count": 8, "errors": []}],
  "agents": [{"name": "copywriter", "description": "…", "model": "chytry",
              "model_id": "anthropic/claude-haiku-4.5", "skills": ["thtd-hlas"], "mcp": [], "tools": {},
              "errors": []}],
  "skills": [{"name": "thtd-hlas", "description": "…", "errors": []}],
  "mcp_servers": [{"name": "filesystem", "type": "stdio", "agents": ["knihovnik"],
                   "tools": ["read_text_file"], "scenarios": null}],
  "links": {"scenario_agent": [["ig-post", "copywriter"]], "scenario_scenario": [["ukazka-call", "kontrola-tonu"]],
            "agent_skill": [["copywriter", "thtd-hlas"]], "agent_server": [["knihovnik", "filesystem"]]},
  "errors": []
}
```

- Čte se loaderem a `validate` (bez kontroly modelů proti `GET /models`).
  `errors` = hlášky `validate` daného souboru; rozbitý soubor se přesto
  zobrazí, co z něj jde přečíst. `errors` projektu = chyby `mcp.yaml`.
- `steps_count` = všechny kroky včetně vnořených ve větvích.
- MCP servery bez tajemství: jen jméno, `type` (`stdio`/`http`) a povolení
  z `mcp.yaml` (`agents`, `tools`, `scenarios`) — žádné `command`, `args`,
  `url`, `env` ani `bearer_token_env`.
- `links` = seřazené dvojice [odkud, kam]: krok `ask`/`task` → agent,
  krok `call` → scénář, agent → skill, agent → MCP server.

### `GET /projects/<p>/scenarios/<s>`

Hlavička jako v `scenarios` výše a `steps` — strom kroků pro karty:

```json
{"nn": 3, "id": "stop", "type": "fail", "when": "steps.kontrola.on_brand < 0.7",
 "fields": {"fail": "Text neodpovídá značce (on_brand = {{ steps.kontrola.on_brand }})"},
 "refs": ["steps.kontrola.on_brand"]}
```

| Pole | Co to je |
|---|---|
| `nn` | pořadí v souboru hloubkově — stejné číslo jako složka kroku `steps/<nn>-<id>` v záznamu běhu |
| `id`, `type`, `when` | id, typ kroku (`null`, když soubor typ neurčuje), podmínka (`null` bez `when`) |
| `fields` | všechna ostatní pole kroku tak, jak jsou v souboru, bez vnořených seznamů kroků (u `switch` jen `value`) |
| `refs` | odkazy `steps.<id>.<pole>` z výrazů a šablon tohoto kroku (bez vnořených kroků) |
| `agent` | u `ask` a `task` |
| `call` | u `call`: jméno volaného scénáře |
| `branches` | u `parallel`: `{větev: [kroky]}` |
| `cases`, `default` | u `switch`: `{hodnota: [kroky]}` a `[kroky]` |

### `GET /projects/<p>/runs/<id>`

Pole `agencast runs list` (`run_id`, `status`, `cost_usd`, `duration_s`,
`callback`) a navíc:

- `steps` — kroky v pořadí první události z `events.jsonl`:
  `{"step", "kind", "status", "branch", "started_at", "finished_at",
  "duration_s", "cost_usd"}`; `status` = `running`, `succeeded`,
  `failed`, `cancelled`, nebo `skipped` (pak `reason_code`, `reason`).
  `step` je cesta jako v `events.jsonl` (u `call` `navrh/copy`).
- `files` — relativní cesty všech souborů ve složce běhu (pro `files/`).
