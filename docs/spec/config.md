# Konfigurace — specifikace v1

Tři soubory, které mění **jen vlastník** (DESIGN §4). Rozhodují, co je
v systému vůbec povolené; agenti a scénáře se na ně jen odkazují.

| Soubor | Co obsahuje | Ukázka |
|---|---|---|
| `workflows/config.yaml` | OpenRouter, aliasy modelů, úložiště výstupů, limity běhu, webhook a callback | `examples/showcase/workflows/config.example.yaml` |
| `workflows/mcp.yaml` | registr MCP serverů | `examples/showcase/workflows/mcp.example.yaml` |
| `workflows/commands.yaml` | pojmenované příkazy pro budoucí krok `run` | `examples/showcase/workflows/commands.example.yaml` |

Strojová podoba: [`schema/config.schema.json`](schema/config.schema.json),
[`schema/mcp.schema.json`](schema/mcp.schema.json).

Soubory se čtou jako **YAML 1.2 core** (booleany jen `true`/`false`,
duplicitní klíč = chyba `config` s číslem řádku; viz
[scenario.md](scenario.md)).

Značení: **návrh** = DESIGN.md to neřeší, navržené výchozí chování.

## Tajné klíče: vždy jen jméno proměnné prostředí (§5.2)

Žádný soubor nikdy neobsahuje hodnotu klíče. Kde je potřeba tajemství,
pole končí na `_env` a obsahuje **jméno** proměnné prostředí:

```yaml
api_key_env: OPENROUTER_API_KEY     # správně: jméno proměnné
```

Hodnota `_env` polí musí vypadat jako jméno proměnné (`VELKA_PISMENA_A_CISLA`).
Když tam někdo omylem vloží samotný klíč (`sk-or-…`), `validate` ho
odmítne — a klíč v chybové hlášce **nevypíše**. Dvě různá `_env` pole se
stejnou hodnotou (např. token webhooku = klíč OpenRouteru) jsou chyba
`config` — jinak by n8n dostalo klíč k OpenRouteru.

Hodnoty všech proměnných z `_env` polí a z `env` v `mcp.yaml` framework
před zápisem každého souboru záznamu i callbacku nahradí textem
`<tajné: JMENO>` (MCP nástroj je může vrátit ve výsledku — DESIGN §5.2,
[run-record.md](run-record.md#co-do-záznamu-nikdy-nepatří)).

Proměnné přicházejí z prostředí procesu: na serveru z `.env` (je
v `.gitignore`), na Modalu z `modal.Secret.from_name` (D5). Načítání
`.env` toleruje konce řádků CRLF (DESIGN §7 bod 8). Chybějící proměnná
→ chyba `config` před během, s jménem proměnné (ne hodnotou).

---

## `config.yaml`

```yaml
version: 1

openrouter:
  api_key_env: OPENROUTER_API_KEY
  jev_model: jev-1.13

models:
  chytry:       { id: anthropic/claude-haiku-4.5 }
  rychly:       { id: google/gemini-3.5-flash-lite, structured_output: tool_wrapper }
  gemini-image: { id: google/gemini-3.1-flash-image }

runs_dir: ./runs

storage:
  type: r2
  r2:
    bucket: lumen-posts
    account_id_env: R2_ACCOUNT_ID
    access_key_id_env: R2_ACCESS_KEY_ID
    secret_access_key_env: R2_SECRET_ACCESS_KEY
    public_base_url: https://files.example.com

limits:
  run_budget_usd: 1.00
  run_image_budget_usd: 0.30
  run_timeout: 1h
  max_call_depth: 3

webhook:
  token_env: WEBHOOK_TOKEN

callback:
  secret_env: CALLBACK_SECRET
```

### `openrouter`

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `api_key_env` | ano | Proměnná s API klíčem OpenRouteru (R4). | Chyba `config`. | `api_key_env: OPENROUTER_API_KEY` |
| `base_url` | ne | Adresa API. Mění se jen pro konformační testy s falešným poskytovatelem (§5.6). Povoleno jen `https://openrouter.ai/…` nebo `http://127.0.0.1` / `http://localhost` — jinam by odešel klíč. | `https://openrouter.ai/api/v1` | `base_url: http://127.0.0.1:8765/api/v1` |
| `jev_model` | ne | Model pro kroky `jev`. Jev není v `GET /models` (§5.5), proto zvlášť, ne jako alias. Skutečnou datovanou verzi z odpovědi zapisuje záznam běhu. | `jev-1.13` (**návrh**) | `jev_model: jev-1.13` |

### `models` — aliasy (§5.5)

Mapa `alias: { id, api, quality, max_tokens, structured_output }`. Agenti a scénáře znají jen alias;
výměna modelu = změna jednoho řádku zde.

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `<alias>` | — | Jméno aliasu: malá písmena, číslice, pomlčka. | Agent/krok s neznámým aliasem → chyba `config`. | `chytry` |
| `<alias>.id` | ano | Konkrétní model OpenRouteru. `validate` ho ověří proti `GET /api/v1/models` pro `chat` nebo `/api/v1/images/models` pro `images` (pozor: `claude-haiku-4.5`, ne `-4-5`). | Chyba `config`. | `id: anthropic/claude-haiku-4.5` |
| `<alias>.api` | ne | API pro krok `image`: `chat` používá chat completions a `images` dedikované Images API. | `chat` (dosavadní chování). | `api: images` |
| `<alias>.quality` | jen při `api: images` | Kvalita požadavku Images API. | Výchozí modelu. | `quality: low` |
| `<alias>.structured_output` | ne | Na které úrovni kaskády strukturovaného výstupu (§5.5) začít: `native_schema`, `tool_wrapper`, `prompt`. Nastavuje se podle konformačního scénáře aliasu (spike (a): Gemini flash-lite s nástroji potřebuje `tool_wrapper`). Viz [scenario.md](scenario.md#kaskáda-strukturovaného-výstupu-55). | `native_schema` | `structured_output: tool_wrapper` |
| `<alias>.max_tokens` | ne | Strop délky odpovědi. Potřeba hlavně u reasoning modelů, které jinak vyčerpají limit na přemýšlení (`finish_reason: length`, viz scenario.md §6). | Výchozí poskytovatele. | `max_tokens: 4000` |

Ke každému aliasu patří konformační scénář (§5.5), který se spustí při
změně `id` — to je věc frameworku (Fáze 2), ne tohoto souboru.

### `runs_dir` — kde jsou složky běhů

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `runs_dir` | ne | Složka se záznamy běhů ([run-record.md](run-record.md)), `_dedupe/`, `_slots/`, `_ledger/` a cache `_models.json`. Na Modalu cesta k Volume. | `./runs` | `runs_dir: /runs` |

### `storage` — kam se nahrají soubory z `output` (§5.7)

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `type` | ano | `local` nebo `r2`. | Chyba `config`. | `type: r2` |
| `local.path` | u `local` | Složka, kam se soubory zkopírují. | Chyba `config`. | `path: ./outputs` |
| `local.public_base_url` | ne | Adresa, na které server tu složku vystavuje. | Callback nese `file://` cestu — pro Instagram nepoužitelné. | |
| `r2.bucket` | u `r2` | Jméno bucketu (není tajné). | Chyba `config`. | `bucket: lumen-posts` |
| `r2.account_id_env`, `r2.access_key_id_env`, `r2.secret_access_key_env` | u `r2` | Proměnné s údaji S3 tokenu Cloudflare R2. | Chyba `config`. | |
| `r2.public_base_url` | u `r2` | Veřejná adresa bucketu (vlastní doména nebo `r2.dev`). Instagram potřebuje stálou veřejnou URL. | Chyba `config`. | `https://files.example.com` |

Klíč souboru v úložišti: `<run_id>-<32 hex náhodných znaků>/<jméno
výstupu>.<přípona>` — pro **všechny** soubory včetně `report.html` (D2).
URL = `public_base_url` + `/` + klíč. Bucket je veřejný (Instagram
potřebuje veřejnou URL) a `run_id` jde uhodnout, proto náhodná část:
vzniká při startu běhu a je **jen** v callbacku a v záznamu běhu
(DESIGN §5.2).

Fakta k R2 pocházejí ze spiku (b), který R2 neimplementoval (chyběly
klíče); před implementací ověřit v dokumentaci Cloudflare R2
(<https://developers.cloudflare.com/r2/>).

### `limits` — pojistky celého běhu

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `run_budget_usd` | ano | Nejvýš tolik USD za celý běh včetně `call` a obrázků. Překročení → `budget`. | Chyba `config` — běh bez stropu útraty neexistuje. | `run_budget_usd: 1.00` |
| `run_image_budget_usd` | ne | Zvláštní strop pro kroky `image` (o dva řády dražší než text, §5.7). Počítá se zároveň do `run_budget_usd`. | Obrázky hlídá jen `run_budget_usd`. | `run_image_budget_usd: 0.30` |
| `run_timeout` | ano | Nejdelší doba běhu (bez čekání ve frontě). `s`/`m`/`h`. Na Modalu nejvýš 24h (D5). | Chyba `config`. | `run_timeout: 1h` |
| `max_call_depth` | ne | Nejvyšší hloubka vnoření `call` (§5.3). | `3` (**návrh**) | `max_call_depth: 3` |
| `max_parallel_runs` | ne | Nejvýš tolik běhů naráz nad jedním `runs_dir` — sdílí ho CLI spuštěné ručně, n8n, cron i `agencast serve --workers` (od frameworku 0.3.1). Celé číslo ≥ 1. Další běh čeká na volný slot (na stderr `čekám na volný slot (max_parallel_runs=N)`), nejdéle `run_timeout`; pak chyba `timeout` a běh nezačne. Čekání není součást `run_timeout` běhu. Falešné běhy (`--fake`) se slotů účastní. | Bez stropu — chování jako do 0.3.0. | `max_parallel_runs: 2` |
| `daily_budget_usd` | ne | Denní strop útraty v USD (den = UTC) přes všechny běhy nad jedním `runs_dir` (od frameworku 0.3.1). Když součet denní knihy útraty ([run-record.md](run-record.md#složka-běhu)) dosáhne limitu, nový běh nezačne — chyba `budget` ještě před prvním voláním. Kontroluje se **jen na startu**: běh, který začal pod limitem, doběhne a limit může překročit nejvýš o svůj `run_budget_usd` (souběžné běhy každý o svůj). Falešné běhy mají vlastní knihu. | Bez denního stropu — chování jako do 0.3.0. | `daily_budget_usd: 5.00` |

Ukázka obou volitelných klíčů (od frameworku 0.3.1):

```yaml
limits:
  run_budget_usd: 1.00
  run_timeout: 1h
  max_parallel_runs: 2      # víc běhů naráz se nespustí, další čekají (nejdéle run_timeout)
  daily_budget_usd: 5.00    # útrata dnešního dne (UTC) ≥ 5 USD → nový běh nezačne (budget)
```

Denní kniha útraty vzniká od frameworku 0.3.1 — běhy starších verzí se do
`daily_budget_usd` nezapočítávají. Zapisuje se vždy, i bez
`daily_budget_usd`, takže limit zapnutý během dne počítá i dosavadní dnešní
běhy.

Pojistka mimo framework: limit útraty přímo na klíči OpenRouteru a
časový limit v n8n (§5.1 bod 7).

### `webhook` a `callback`

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `webhook.token_env` | ano | Proměnná s tokenem, který musí nést každý příchozí požadavek na spuštění běhu (Modal endpointy jsou jinak veřejné, D5). | Chyba `config`. | `token_env: WEBHOOK_TOKEN` |
| `callback.secret_env` | ano | Proměnná s tajemstvím pro podpis callbacku HMAC (§5.2); n8n podpis ověří. | Chyba `config`. | `secret_env: CALLBACK_SECRET` |

Adresu callbacku posílá n8n s každým požadavkem na spuštění (typicky
resume URL čekajícího workflow), proto v `config.yaml` není. Podoba těla
a podpisu callbacku: [run-record.md](run-record.md#callback).

---

## `mcp.yaml` — registr MCP serverů

Agent smí použít jen server, který je tady, a jen když ho tu vlastník
povolil. **Oprávnění drží vlastník** (DESIGN §5.2): agenti i scénáře jsou
soubory, které píší i ostatní, proto omezení „kdo smí co" v nich být
nemůže. Druhy spojení podle specifikace MCP (stdio, Streamable HTTP, SSE;
<https://modelcontextprotocol.io/specification/latest/basic/transports>,
staženo 2026-09-25; DESIGN §5.8):

```yaml
version: 1
servers:
  filesystem:
    description: Čtení a zápis v pracovní složce aktuálního běhu
    command: npx
    args: ["@modelcontextprotocol/server-filesystem", "{run_dir}/work"]
    agents: [publisher]

  instagram:
    description: Publikace na Instagram (vzdálený server)
    url: https://mcp.example.com/instagram
    bearer_token_env: IG_MCP_TOKEN
    agents: [publisher]
    scenarios: [ig-publish]
    tools: [create_media, publish_media]
    timeouts: { handshake: 10s, call: 120s }
```

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `version` | ano | Verze formátu. | Chyba `config`. | `version: 1` |
| `servers.<name>` | — | Jméno serveru, na které odkazují agenti. Malá písmena, číslice, pomlčka. | — | `instagram` |
| `description` | ano | K čemu server je (pro člověka a `--dry-run`). | Chyba `config`. | |
| `agents` | ano | Kteří agenti smí server použít. Agent se serverem, který ho tu nemá, je chyba `config`. | Chyba `config`. | `agents: [publisher]` |
| `scenarios` | ne | Které scénáře smí spustit (`task`) agenta s tímto serverem. Scénář mimo seznam → chyba `config`. Brání tomu, aby libovolný scénář použil publikačního agenta a obešel schválení v n8n. | Kterýkoli scénář. | `scenarios: [ig-publish]` |
| `tools` | ne | Horní seznam nástrojů, které vlastník povoluje. Agent smí mít v `tools` jen nástroje z tohoto seznamu, jinak chyba `config`. | Jen seznam v agentovi. | `tools: [publish_media]` |
| `command` | buď `command`, nebo `url` | Program místního serveru (stdio). Spouští se bez shellu, **jednou za běh** (při prvním `task`, který ho potřebuje). Na Modalu musí být balíček předinstalovaný v image (D5: 0,7 s vs. 3,8 s). | — | `command: npx` |
| `args` | ne | Argumenty programu, seznam textů. Jediná povolená náhrada je `{run_dir}` = absolutní cesta ke složce aktuálního běhu (server tak nevidí cizí běhy ani `_dedupe`). Jiné `{…}` jsou chyba `config`. Kořen, který server dostane, je druhá vrstva oprávnění (§5.8). | Žádné. | `["…", "{run_dir}/work"]` |
| `env` | ne | Proměnné pro proces serveru: `JMENO_PRO_SERVER: JMENO_NA_HOSTITELI`. Hodnota se vezme z prostředí frameworku. Server dostane jen `HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, `USER` (výchozí sada `mcp` SDK, DESIGN §5.8) a proměnné z `env` — nic jiného. Jména `PATH`, `HOME`, `LD_PRELOAD`, `LD_LIBRARY_PATH`, `NODE_OPTIONS`, `PYTHONPATH` v `env` nejsou dovolená. | Server nedostane žádné tajemství. | `env: { GITHUB_TOKEN: GH_TOKEN }` |
| `url` | buď `command`, nebo `url` | Adresa vzdáleného serveru: `https://…`, nebo `http://127.0.0.1` / `http://localhost` (sidecar ve stejném kontejneru). | — | |
| `transport` | ne | Jen u `url`: `streamable-http` nebo `sse`. | `streamable-http` | `transport: sse` |
| `bearer_token_env` | ne | Proměnná s tokenem; pošle se jako `Authorization: Bearer …`. Jen u `url`. | Bez autorizace. | `bearer_token_env: IG_MCP_TOKEN` |
| `timeouts.handshake` | ne | Nejdelší doba spuštění a handshaku serveru. Překročení → `transient` (síť) nebo `config`. | `10s` | `handshake: 20s` |
| `timeouts.call` | ne | Nejdelší doba jednoho volání nástroje. Překročení → krok selže, třída `timeout` (nástroj mohl proběhnout). | `60s` | `call: 120s` |

Timeouty jsou vždy výslovné — bez nich `mcp` SDK čeká neomezeně (DESIGN
§5.8). `stderr` každého serveru jde do záznamu běhu
(`mcp/<server>.stderr.log`). Pevné (netajné) nastavení serveru patří do
`args`, ne do `env`.

## `commands.yaml` — příkazy pro budoucí krok `run`

Krok `run` je **plánovaný** (D1d), ve v1 se neimplementuje. Tady je jen
struktura, aby bylo jasné, jak bude vypadat povolení (§5.2: jen
pojmenované příkazy, bez shellu, s prázdným prostředím, s validovanými
argumenty). JSON Schema vznikne spolu s krokem `run`.

```yaml
version: 1
commands:
  zmensi-obrazek:
    description: Zmenší obrázek na šířku pro Instagram
    program: /usr/bin/convert
    args: ["{{ params.vstup }}", "-resize", "{{ params.sirka }}x", "{{ params.vystup }}"]
    params:
      vstup:  { type: file }
      sirka:  { type: integer, min: 320, max: 1440 }
      vystup: { type: string, pattern: "^[a-z0-9_-]+\\.jpg$" }
    timeout: 60s
```

| Pole | Co dělá |
|---|---|
| `commands.<name>` | Jméno, kterým krok `run` příkaz zavolá. |
| `description` | K čemu příkaz je. |
| `program` | Absolutní cesta k programu; spouští se přímo, **nikdy přes shell**. |
| `args` | Pevné argumenty; `{{ params.x }}` je vždy **jeden** celý argument (mezery ani uvozovky v hodnotě nic nerozdělí). |
| `params` | Popis a omezení každého parametru; hodnota, která neprojde, příkaz nespustí. |
| `timeout` | Nejdelší doba běhu příkazu. |

Program běží s prázdným prostředím (ani `PATH`), v pracovní složce kroku.
