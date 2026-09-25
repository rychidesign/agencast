# Konfigurace — specifikace v1

Tři soubory, které mění **jen vlastník** (DESIGN §4). Rozhodují, co je
v systému vůbec povolené; agenti a scénáře se na ně jen odkazují.

| Soubor | Co obsahuje | Ukázka |
|---|---|---|
| `workflows/config.yaml` | OpenRouter, aliasy modelů, úložiště výstupů, limity běhu, webhook a callback | `workflows/config.example.yaml` |
| `workflows/mcp.yaml` | registr MCP serverů | `workflows/mcp.example.yaml` |
| `workflows/commands.yaml` | pojmenované příkazy pro budoucí krok `run` | `workflows/commands.example.yaml` |

Strojová podoba: [`schema/config.schema.json`](schema/config.schema.json),
[`schema/mcp.schema.json`](schema/mcp.schema.json).

Značení: **návrh** = DESIGN.md to neřeší, navržené výchozí chování.

## Tajné klíče: vždy jen jméno proměnné prostředí (§5.2)

Žádný soubor nikdy neobsahuje hodnotu klíče. Kde je potřeba tajemství,
pole končí na `_env` a obsahuje **jméno** proměnné prostředí:

```yaml
api_key_env: OPENROUTER_API_KEY     # správně: jméno proměnné
```

Hodnota `_env` polí musí vypadat jako jméno proměnné (`VELKA_PISMENA_A_CISLA`).
Když tam někdo omylem vloží samotný klíč (`sk-or-…`), `validate` ho
odmítne — a klíč v chybové hlášce **nevypíše**.

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
  rychly:       { id: google/gemini-3.5-flash-lite }
  gemini-image: { id: google/gemini-3.1-flash-image }

storage:
  type: r2
  r2:
    bucket: thtd-posts
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
| `base_url` | ne | Adresa API. Mění se jen pro konformační testy s falešným poskytovatelem (§5.6). | `https://openrouter.ai/api/v1` | `base_url: http://127.0.0.1:8765/api/v1` |
| `jev_model` | ne | Model pro kroky `jev`. Jev není v `GET /models` (§5.5), proto zvlášť, ne jako alias. Skutečnou datovanou verzi z odpovědi zapisuje záznam běhu. | `jev-1.13` (**návrh**) | `jev_model: jev-1.13` |

### `models` — aliasy (§5.5)

Mapa `alias: { id, max_tokens }`. Agenti a scénáře znají jen alias;
výměna modelu = změna jednoho řádku zde.

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `<alias>` | — | Jméno aliasu: malá písmena, číslice, pomlčka. | Agent/krok s neznámým aliasem → chyba `config`. | `chytry` |
| `<alias>.id` | ano | Konkrétní model OpenRouteru. `validate` ho ověří proti `GET /api/v1/models` (pozor: `claude-haiku-4.5`, ne `-4-5`). | Chyba `config`. | `id: anthropic/claude-haiku-4.5` |
| `<alias>.max_tokens` | ne | Strop délky odpovědi. Potřeba hlavně u reasoning modelů, které jinak vyčerpají limit na přemýšlení (`finish_reason: length`, viz scenario.md §6). | Výchozí poskytovatele. | `max_tokens: 4000` |

Ke každému aliasu patří konformační scénář (§5.5), který se spustí při
změně `id` — to je věc frameworku (Fáze 2), ne tohoto souboru.

### `storage` — kam se nahrají soubory z `output` (§5.7)

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `type` | ano | `local` nebo `r2`. | Chyba `config`. | `type: r2` |
| `local.path` | u `local` | Složka, kam se soubory zkopírují. | Chyba `config`. | `path: ./outputs` |
| `local.public_base_url` | ne | Adresa, na které server tu složku vystavuje. | Callback nese `file://` cestu — pro Instagram nepoužitelné. | |
| `r2.bucket` | u `r2` | Jméno bucketu (není tajné). | Chyba `config`. | `bucket: thtd-posts` |
| `r2.account_id_env`, `r2.access_key_id_env`, `r2.secret_access_key_env` | u `r2` | Proměnné s údaji S3 tokenu Cloudflare R2. | Chyba `config`. | |
| `r2.public_base_url` | u `r2` | Veřejná adresa bucketu (vlastní doména nebo `r2.dev`). Instagram potřebuje stálou veřejnou URL. | Chyba `config`. | `https://files.example.com` |

Klíč souboru v úložišti: `<run_id>/<jméno výstupu>.<přípona>` (**návrh**),
URL = `public_base_url` + `/` + klíč. Tam se nahraje i `report.html`
záznamu běhu (D2).

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

Agent smí použít jen server, který je tady (a má ho v `mcp`). Dva druhy
spojení podle specifikace MCP (stdio, Streamable HTTP;
<https://modelcontextprotocol.io/specification/latest/basic/transports>,
staženo 2026-09-25):

```yaml
version: 1
servers:
  filesystem:
    description: Čtení a zápis souborů ve složce běhu
    command: npx
    args: ["@modelcontextprotocol/server-filesystem", "/runs"]

  instagram:
    description: Publikace na Instagram (vzdálený server)
    url: https://mcp.example.com/instagram
    bearer_token_env: IG_MCP_TOKEN
```

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `version` | ano | Verze formátu. | Chyba `config`. | `version: 1` |
| `servers.<name>` | — | Jméno serveru, na které odkazují agenti. Malá písmena, číslice, pomlčka. | — | `instagram` |
| `description` | ano | K čemu server je (pro člověka a `--dry-run`). | Chyba `config`. | |
| `command` | buď `command`, nebo `url` | Program místního serveru (stdio). Spouští se bez shellu. Na Modalu musí být balíček předinstalovaný v image (D5: 0,7 s vs. 3,8 s). | — | `command: npx` |
| `args` | ne | Argumenty programu, seznam textů. | Žádné. | |
| `env` | ne | Proměnné pro proces serveru: `JMENO_PRO_SERVER: JMENO_NA_HOSTITELI`. Hodnota se vezme z prostředí frameworku. Server nedostane nic jiného než tyto proměnné a `PATH` (**návrh**). | Server nedostane žádné tajemství. | `env: { GITHUB_TOKEN: GH_TOKEN }` |
| `url` | buď `command`, nebo `url` | Adresa vzdáleného serveru (Streamable HTTP), jen `https://`. | — | |
| `bearer_token_env` | ne | Proměnná s tokenem; pošle se jako `Authorization: Bearer …`. Jen u `url`. | Bez autorizace. | `bearer_token_env: IG_MCP_TOKEN` |

Pevné (netajné) nastavení serveru patří do `args`, ne do `env`.

---

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
