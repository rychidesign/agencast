# Záznam běhu — specifikace v1

Každý běh má vlastní složku (D2). Z ní musí být vidět, co se stalo, bez
znalosti vnitřku frameworku (R2): `summary.md` čte člověk, `events.jsonl`
stroj (a budoucí GUI), `report.html` je jeden samostatný soubor
v úložišti s odkazem v callbacku.

Značení: **návrh** = DESIGN.md to neřeší, navržené výchozí chování.

## Složka běhu

```
runs/20260925-140311-ig-post-a1b2/
  plan.md              plán z validate: pořadí kroků, nástroje, limity
  inputs.json          vstupy běhu (po doplnění default)
  events.jsonl         strojový log — jedna událost na řádek
  summary.md           souhrn pro člověka
  report.html          totéž jako jeden HTML soubor (nahraje se do úložiště)
  callback.json        přesně to, co odešlo v callbacku
  run.lock             zámek živého běhu (od frameworku 0.7.0), prázdný
  scenario/            snímek scénářů při startu (od frameworku 0.7.0)
    ig-post.yaml
  mcp/                 stderr MCP serverů: <server>.stderr.log
  steps/
    01-copy/
      prompt.md        system prompt + zpráva, přesně jak je dostal model
      calls/01.request.json
      calls/01.response.json
      output.json      výstup kroku (steps.copy)
    02-kontrola/
      calls/01.request.json
      calls/01.response.json
      output.json
    04-foto_prompt/ …  (03-stop byl přeskočen → nemá složku)
    05-kontrola_obrazku/ …
    07-foto/
      prompt.md
      calls/01.request.json
      calls/01.response.json
      image.png
      output.json      { "file": "steps/07-foto/image.png" }
    08-out/
      output.json
```

- `runs/` je `runs_dir` z `config.yaml` (výchozí `./runs`), na Modalu
  Volume (D5). Vedle složek běhů jsou jen `_dedupe/` (samostatné soubory
  klíčů, [scenario.md](scenario.md#dedupe_key--jednou-a-dost)), cache
  `_models.json` a od frameworku 0.3.1:
  - `_slots/<n>.lock`, n = 1..`max_parallel_runs` — zámky `flock`
    ([config.md](config.md#limits--pojistky-celého-běhu)). Běh drží jeden
    slot od chvíle před vytvořením své složky do konce (i při chybě); zámek
    uvolní i pád procesu. Soubory zůstávají, obsah nemají. Jen s
    `max_parallel_runs`.
  - `_ledger/<RRRR-MM-DD>.jsonl` — denní kniha útraty (den = UTC podle
    konce běhu), jeden řádek na dokončený běh, jen se připisuje:
    `{"run_id": "…", "cost_usd": 0.0123, "finished_at": "2026-09-26T08:15:02.120Z"}`
    (`cost_usd` = `usage.cost_usd` z `run_finished`, včetně obrázků).
    Píše se vždy; čte ji `daily_budget_usd`. Falešné běhy (`--fake`) píšou
    do `_ledger-fake/` (jako `_dedupe-fake/`). Běhy před 0.3.1 v knize
    nejsou.
- **`run_id`** = `RRRRMMDD-HHMMSS-<scénář>-<4 hex znaky>` v UTC
  (**návrh**) — řadí se podle času a je v něm vidět, co běželo. Jde
  uhodnout, proto má klíč v úložišti navíc 32 náhodných hex znaků (viz
  [Callback](#callback)).
- **`<nn>`** = pořadí kroku **v souboru scénáře** (hloubkově, včetně kroků
  ve větvích), pevné pro scénář — stejný scénář má při každém běhu stejná
  čísla a dva běhy jdou porovnat. Skutečné pořadí startu je vidět z `ts`
  v `events.jsonl`. Sedí s číslem v `summary.md`. Přeskočený krok složku
  nemá, je jen v `events.jsonl` a v `summary.md` s důvodem.
- **`calls/`** — každé volání API zvlášť (opakování i tahy `task`), číslo
  = pořadí volání v kroku. U `task` navíc `calls/NN.tool.json` (argumenty
  a výsledek nástroje) a obrázky z nástrojů `tool-<NN>-<k>.png` ve složce
  kroku.
- **`call`** — složka kroku obsahuje vlastní `steps/` volaného scénáře:
  `steps/03-navrh/steps/01-copy/…`. Události jdou do jednoho
  `events.jsonl` celého běhu, `step` má cestu `navrh/copy`.
- `--dry-run` vytvoří složku jen s `plan.md` (a `inputs.json`).
- **`run.lock`** (od frameworku 0.7.0) — proces běhu drží na souboru
  `flock` (výhradní) od vytvoření složky do konce běhu (i při chybě);
  zámek uvolní i pád procesu, soubor zůstává prázdný. Čtenář (`runs
  list`, `serve`) zkusí sdílený zámek bez čekání: nejde = běh žije
  (`state: running`), jde a chybí `run_finished` = běh přerušen
  (`interrupted`, [api.md](api.md)). Na Modalu obálka dosadí vlastní
  mechanismus (jako sloty `max_parallel_runs`). Dry-run zámek nemá —
  od frameworku 0.8.0 se podle toho pozná: `plan.md` bez `events.jsonl`
  a bez `run.lock` = dry-run; ostrý běh vytvoří `run.lock` před
  `plan.md`, takže ostrý běh, který spadl před první událostí, je
  přerušený, ne dry-run.
- **`scenario/<jméno>.yaml`** (od frameworku 0.7.0) — při startu běhu
  (po `plan.md`) kopie spouštěného scénáře a všech scénářů volaných přes
  `call` (i vnořeně), bajt po bajtu až na maskování tajných hodnot. Detail
  běhu z nich kreslí strom kroků, jak platil při běhu. Běh, který nezačal
  (bez `plan.md`), a dry-run snímek nemají.

## Co do záznamu nikdy nepatří

- **base64** (§5.7): data URL obrázku se nahradí textem
  `"<soubor: steps/07-foto/image.png, 1510234 B>"`. Platí pro **všechny**
  soubory záznamu: `calls/NN.request.json` (obrázek z nástroje v user
  zprávě dalšího tahu), `calls/NN.response.json`, `calls/NN.tool.json`,
  `events.jsonl`, `output.json`.
- **`reasoning_details`** (šifrované, u obrázku ~1,4 MB): v záznamu jen
  `"<vynecháno: reasoning_details, 1412345 B>"` — i v `request.json`
  dalšího tahu, kde se posílají zpět (§5.5). Framework je drží v paměti.
- **Tajné klíče a hlavičky** požadavků. `request.json` je jen tělo.
- **Tajné hodnoty kdekoli:** před zápisem každého souboru záznamu i
  callbacku framework nahradí každý výskyt hodnoty kterékoli proměnné
  z polí `*_env` (config.yaml, mcp.yaml) a z `env` v `mcp.yaml` (hodnoty
  od 8 znaků) textem `<tajné: JMENO>` a zapíše varování. Nástroj MCP totiž
  může klíč vrátit ve výsledku (spike (d): `get-env`; DESIGN §5.2).
- Z URL callbacku se loguje jen `schéma://host/cesta` bez query.

## `events.jsonl`

Každý řádek je jeden JSON objekt. Společná pole:

| Pole | Co to je | Příklad |
|---|---|---|
| `ts` | čas události, ISO 8601 v UTC s milisekundami | `"2026-09-25T14:03:12.481Z"` |
| `type` | typ události (tabulky níže) | `"step_started"` |
| `step` | cesta ke kroku (`id`, u `call` `navrh/copy`); u událostí běhu chybí | `"copy"` |

Časy trvání jsou v sekundách (`duration_s`), ceny v USD (`cost_usd`).
Cena volání je přesně hodnota, kterou vrátil poskytovatel (`usage.cost`),
bez zaokrouhlení. Součty (krok, běh, obrázky, `budget_exceeded_usd`) se
zaokrouhlují jen na 10 desetinných míst kvůli šumu floatů
(0.30000000000000004 → 0.3). V `summary.md`, `report.html` a výpisech
`agencast` je cena desetinně s čárkou (nikdy exponent), aspoň na 4 místa, víc
jen když je potřeba ukázat všechny číslice (`0,000004482`); skutečná nula
je `0` (od frameworku 0.2.4, ISSUES 38).

### Normalizované `usage` (§5.5)

Všude, kde je spotřeba, má jeden tvar:

```json
"usage": { "input_tokens": 674, "output_tokens": 86, "cost_usd": 0.0000283 }
```

| Zdroj | `input_tokens` ← | `output_tokens` ← | `cost_usd` ← |
|---|---|---|---|
| chat completions (`ask`, `task`, `image`) | `prompt_tokens` | `completion_tokens` | `cost` |
| Jev (`/systemone`) | `input_tokens` | `output_tokens` | `cost` |

Když poskytovatel cenu nevrátí, je `cost_usd: null` a vznikne varování
(rozpočet pak nejde hlídat přesně) — nikdy se nedopočítává odhadem.

### Typy událostí

**`run_started`** — běh začal.

| Pole | Co to je |
|---|---|
| `run_id` | id běhu |
| `scenario`, `scenario_version` | jméno a `version` scénáře |
| `request_key` | idempotenční klíč z webhooku (§5.2), jinak `null` |
| `inputs` | vstupy po doplnění `default` |
| `models` | mapa alias → id, jak platila při startu (reprodukovatelnost) |
| `limits` | `run_budget_usd`, `run_image_budget_usd`, `run_timeout` |
| `framework_version` | verze frameworku |
| `storage_prefix` | `<run_id>-<32 hex>` — prefix souborů v úložišti |
| `fake` | `true` = falešný poskytovatel (`--fake`), odpovědi modelů jsou vymyšlené (od frameworku 0.2.2) |
| `steps_total` | počet kroků scénáře včetně vnořených ve větvích `parallel`/`switch`, bez kroků volaných scénářů; `null` u běhu, který nezačal (od frameworku 0.6.0) |
| `callback_url` | kam odejde callback, bez query (jako `callback_sent.url`); `null` = běh bez callbacku (CLI, GUI bez `callback_url`) (od frameworku 0.6.0) |

**`run_waiting`** — běh čekal na volný slot `max_parallel_runs` (od
frameworku 0.3.1). Jen když se čekalo; je hned za `run_started`, i když
čekání proběhlo před ním (složka běhu vzniká až po získání slotu).

| Pole | Co to je |
|---|---|
| `waited_s` | jak dlouho běh čekal na slot |
| `max_parallel_runs` | platný strop |

Nedočkaný slot (`timeout`) a vyčerpaný `daily_budget_usd` (`budget`) jsou
běhy, které nezačaly: záznam má jen `run_started`, `error`,
`run_finished` s `error` (`step: null`), `callback.json` a `summary.md`,
bez `plan.md` a `inputs.json` — stejně jako běh, který webhook nespustil
([webhook.md](webhook.md)). Callback odejde normálně, `agencast run` vypíše
na stderr `<třída>: <hláška>` a skončí kódem 1.

**`step_started`** — krok začal.

| Pole | Co to je |
|---|---|
| `kind` | typ kroku: `ask`, `task`, `jev`, `image`, `parallel`, `switch`, `call`, `set`, `fail`, `output` |
| `branch` | jméno větve `parallel` nebo hodnota `switch`, ve které krok je; jinak chybí |
| `nn` | číslo kroku `<nn>` v jeho scénáři (u kroku volaného scénáře číslo ve volaném scénáři) (od frameworku 0.7.0) |
| `dir` | složka kroku ve složce běhu, např. `steps/03-navrh/steps/01-copy` (od frameworku 0.7.0) |

**`step_skipped`** — krok neproběhl (§5.1 bod 5: vždy s důvodem).

| Pole | Co to je |
|---|---|
| `kind` | typ kroku |
| `reason_code` | `when`, `switch`, `dedupe`, `cancelled` (nerozběhnutý krok zrušený, protože selhala jiná větev `parallel`). Kroky uvnitř přeskočeného `parallel`/`switch` dostanou každý stejný důvod. |
| `reason` | věta pro člověka, např. `when: steps.kontrola.on_brand < 0.7 → false` |
| `default_used` | `true`, pokud se jako výstup použil `default` |
| `nn` | číslo kroku jako u `step_started` (od frameworku 0.7.0) |

**`step_finished`** — krok skončil.

| Pole | Co to je |
|---|---|
| `kind` | typ kroku |
| `status` | `succeeded`, `failed`, nebo `cancelled` (rozběhnutý krok zrušený, protože selhala jiná větev `parallel`; `cost_usd` = dosavadní volání) |
| `continued` | `true`, když selhal s `on_error: continue` (→ varování) |
| `default_used` | jen u `continued: true`: `true`, když se jako výstup použil `default` (od frameworku 0.7.0) |
| `duration_s` | trvání |
| `cost_usd` | součet všech volání kroku |
| `output_file` | cesta k `output.json` |

**`model_call`** — jedno volání chat completions (`ask`, tah `task`, `image`).

| Pole | Co to je |
|---|---|
| `attempt` | pokus 1, 2, … (opakování přes `retry`) |
| `turn` | jen u `task`: pořadí tahu |
| `alias`, `model` | alias a id, které se poslalo |
| `response_model`, `provider` | model a poskytovatel podle odpovědi |
| `generation_id` | `id` odpovědi OpenRouteru (dohledání v jeho logu) |
| `http_status` | status odpovědi |
| `finish_reason`, `native_finish_reason` | jak volání skončilo (§5.1 bod 8) |
| `structured_output` | použitá úroveň kaskády (§5.5): `native_schema`, `tool_wrapper`, `prompt`; bez `schema` `null` |
| `budget_exceeded_usd` | o kolik volání překročilo rozpočet (volání se dokončí a platí), jinak chybí |
| `timeout_s` | timeout HTTP volání: min(zbývající čas kroku, 120 s); vypršení = `transient` (od frameworku 0.2.1) |
| `duration_s`, `usage` | trvání, normalizovaná spotřeba |
| `request_file`, `response_file` | cesty do `calls/` |

**`tool_call`** — `task` zavolal nástroj.

| Pole | Co to je |
|---|---|
| `turn` | tah, ve kterém model nástroj zavolal |
| `server`, `tool` | MCP server a nástroj; u skillů `server: "_skills"`, `tool: "load_skill"` |
| `allowed` | `false`, když nástroj nebyl povolen (nespustil se, model dostal chybu) |
| `invalid_args` | `true`, když argumenty neprošly validací proti schématu nástroje (nespustil se, model dostal chybu) |
| `is_error` | nástroj vrátil chybu (předána modelu, krok pokračuje) |
| `duration_s` | trvání |
| `call_file` | `calls/NN.tool.json` s argumenty a výsledkem |

**`jev_call`** — jedno volání Jev.

| Pole | Co to je |
|---|---|
| `attempt` | pokus |
| `model`, `response_model` | poslaný model a datovaná verze z odpovědi (`typesafe/jev-1.13-20260917`) |
| `http_status` | status odpovědi |
| `answers` | hodnoty odpovědí, např. `{"on_brand": 0.91}` |
| `timeout_s` | timeout HTTP volání: min(zbývající čas kroku, 30 s); vypršení = `transient` (od frameworku 0.2.1) |
| `duration_s`, `usage` | trvání, normalizovaná spotřeba |
| `request_file`, `response_file` | cesty do `calls/` |

**`image_saved`** — obrázek uložen do složky běhu.

| Pole | Co to je |
|---|---|
| `path` | cesta relativně ke složce běhu |
| `media_type`, `bytes` | typ a velikost souboru |
| `width`, `height` | rozměry z hlavičky souboru |

**`error`** — chyba (i ta, která se ještě opakuje).

| Pole | Co to je |
|---|---|
| `class` | třída chyby (scenario.md §6): `transient`, `schema`, `content`, `budget`, `timeout`, `config`, `expression`, `fail`, `internal` |
| `message` | přesná hláška (u API včetně `error.message` poskytovatele) |
| `attempt` | pokus, ve kterém chyba nastala |
| `will_retry` | `true`, když následuje další pokus |
| `http_status` | status, pokud jde o HTTP |

**`mcp_server`** — start, konec nebo selhání MCP serveru (DESIGN §5.8).

| Pole | Co to je |
|---|---|
| `server` | jméno z `mcp.yaml` |
| `action` | `started`, `stopped`, `failed` |
| `duration_s` | u `started` doba handshaku |
| `error` | hláška u `failed` |
| `stderr_file` | `mcp/<server>.stderr.log` |

**`file_uploaded`** — soubor z `output` nahrán do úložiště.

| Pole | Co to je |
|---|---|
| `output` | jméno výstupu (`image`), u HTML záznamu `report` |
| `path`, `url` | odkud a kam |

**`run_finished`** — běh skončil.

| Pole | Co to je |
|---|---|
| `status` | `succeeded` nebo `failed` |
| `error` | `{class, step, message}` nebo `null` |
| `warnings` | seznam vět (kroky s `on_error: continue`, chybějící cena, …) |
| `duration_s` | trvání bez čekání ve frontě |
| `usage` | součet celého běhu |
| `image_cost_usd` | z toho obrázky (§5.7 — počítají se zvlášť) |
| `image_duration_s` | součet trvání kroků `image` (jen informace; samostatný časový limit obrázků ve v1 není) |

**`callback_sent`** — jeden pokus o doručení callbacku (každý pokus =
jedna událost).

| Pole | Co to je |
|---|---|
| `url` | adresa bez query |
| `attempt` | pokus 1–3 (**návrh**: 3 pokusy, prodleva 5 s a 30 s) |
| `http_status` | odpověď n8n, `null` při chybě sítě |
| `error` | hláška, pokud doručení selhalo |

**`callback_failed`** — po třetím neúspěšném pokusu (poslední řádek
souboru). Stav běhu se **nemění**, `callback.json` zůstává ve složce běhu.
CLI (`runs`) a `summary.md` ukazují „callback nedoručen". Obnovu řeší
časový limit v n8n (§5.1 bod 7).

| Pole | Co to je |
|---|---|
| `url` | adresa bez query |
| `attempts` | počet pokusů |
| `error` | poslední hláška |

Příklad (zkráceno):

```json
{"ts":"2026-09-25T14:03:11.002Z","type":"run_started","run_id":"20260925-140311-ig-post-a1b2","scenario":"ig-post","scenario_version":1,"request_key":null,"inputs":{"tema":"nová káva"},"models":{"chytry":"anthropic/claude-haiku-4.5"},"limits":{"run_budget_usd":1.0,"run_image_budget_usd":0.3,"run_timeout":"1h"},"framework_version":"0.1.0"}
{"ts":"2026-09-25T14:03:11.010Z","type":"step_started","step":"copy","kind":"ask"}
{"ts":"2026-09-25T14:03:14.720Z","type":"model_call","step":"copy","attempt":1,"alias":"chytry","model":"anthropic/claude-haiku-4.5","response_model":"anthropic/claude-haiku-4.5","provider":"Anthropic","generation_id":"gen-…","http_status":200,"finish_reason":"stop","native_finish_reason":"end_turn","structured_output":"native_schema","duration_s":3.7,"usage":{"input_tokens":812,"output_tokens":214,"cost_usd":0.0015},"request_file":"steps/01-copy/calls/01.request.json","response_file":"steps/01-copy/calls/01.response.json"}
{"ts":"2026-09-25T14:03:14.731Z","type":"step_finished","step":"copy","kind":"ask","status":"succeeded","continued":false,"duration_s":3.72,"cost_usd":0.0015,"output_file":"steps/01-copy/output.json"}
{"ts":"2026-09-25T14:03:15.050Z","type":"step_skipped","step":"stop","kind":"fail","reason_code":"when","reason":"when: steps.kontrola.on_brand < 0.7 → false","default_used":false}
```

## `summary.md`

Pro člověka, česky, vždy stejná stavba (**návrh**):

```markdown
# ig-post — úspěch

Návrh IG příspěvku ke schválení
Běh `20260925-140311-ig-post-a1b2` · 25. 9. 2026 14:03:11 UTC · 17,5 s · 0,06934 USD (z toho obrázky 0,0672 USD)

## Vstupy
- tema: nová káva

## Kroky
| # | Krok | Typ | Stav | Čas | Cena | Poznámka |
|---|---|---|---|---|---|---|
| 1 | copy | ask | ✓ | 3,7 s | 0,0015 | chytry → anthropic/claude-haiku-4.5 |
| 2 | kontrola | jev | ✓ | 0,3 s | 0,00002 | on_brand = 0,91 |
| 3 | stop | fail | přeskočeno | | | when: steps.kontrola.on_brand < 0.7 → false |
| 4 | foto_prompt | ask | ✓ | 1,8 s | 0,0006 | rychly → google/gemini-3.5-flash-lite |
| 5 | kontrola_obrazku | jev | ✓ | 0,3 s | 0,00002 | skutecna_osoba = 0,02, cizi_znacka = 0,01 |
| 6 | stop_obrazek | fail | přeskočeno | | | when: … → false |
| 7 | foto | image | ✓ | 10,6 s | 0,0672 | image.png, 1408×768 |
| 8 | out | output | ✓ | 0,0 s | 0 | |
| | Celkem | | | 17,5 s | 0,06934 | z toho obrázky 0,0672 |

## Varování
žádná

## Výstup
- caption: „…"
- hashtags: #kava, #thtd
- image: https://files.example.com/20260925-140311-ig-post-a1b2-3f9c1e7a0b5d4c2e8a6f1d9b7c3e5a0f/image.png
```

Poslední řádek tabulky **Celkem** má čas a cenu běhu (`duration_s` a
`cost_usd` v `run_finished`, stejná čísla jako v hlavičce a
`callback.json`) a u běhu s obrázky poznámku „z toho obrázky …". Čas
Celkem je čas celého běhu, ne součet kroků: kroky v `parallel` běží
současně a čas i cena `parallel`, `switch` a `call` už obsahují kroky
uvnitř, proto Celkem není prostý součet sloupce. Řádek Celkem má i
neúspěšný běh (dosavadní čas a cena). Od frameworku 0.2.4, čas od 0.2.5.

Při chybě je nadpis `— chyba`, hned pod ním blok **Chyba** s třídou,
krokem a přesnou hláškou, a v tabulce kroků je vidět, kde běh skončil.
Falešný běh (`--fake`) má pod hlavičkou řádek **Falešný běh** (od
frameworku 0.2.2).

`report.html` má stejný obsah plus rozbalitelné prompty a odpovědi
(bez base64). Podobu HTML určí Fáze 2.

## Callback

Posílá se **vždy**, jakmile běh dostal `run_id` — při úspěchu i chybě,
i když `validate` selže až po vyzvednutí z fronty (D2, §5.1 bod 2).
Požadavky odmítnuté hned webhookem (401, 422) `run_id` ani callback
nemají ([webhook.md](webhook.md)). `POST` na `callback_url` z požadavku,
tělo JSON:

```json
{
  "run_id": "20260925-140311-ig-post-a1b2",
  "scenario": "ig-post",
  "request_key": "n8n-4711",
  "status": "succeeded",
  "outputs": {
    "caption": "…",
    "hashtags": ["#kava", "#thtd"],
    "image": "https://files.example.com/20260925-140311-ig-post-a1b2-3f9c1e7a0b5d4c2e8a6f1d9b7c3e5a0f/image.png"
  },
  "error": null,
  "warnings": [],
  "cost_usd": 0.0693,
  "duration_s": 17.5,
  "report_url": "https://files.example.com/20260925-140311-ig-post-a1b2-3f9c1e7a0b5d4c2e8a6f1d9b7c3e5a0f/report.html",
  "sent_at": "2026-09-25T14:03:36.120Z"
}
```

Při chybě:

```json
{
  "run_id": "20260925-141502-ig-post-9f3c",
  "scenario": "ig-post",
  "request_key": "n8n-4712",
  "status": "failed",
  "outputs": null,
  "error": {
    "class": "fail",
    "step": "stop",
    "message": "Text neodpovídá značce (on_brand = 0.42)"
  },
  "warnings": [],
  "cost_usd": 0.0016,
  "duration_s": 4.4,
  "report_url": "https://files.example.com/20260925-141502-ig-post-9f3c-8b2d6f0e4a1c7e9d3b5f2a8c6e0d4b1a/report.html",
  "sent_at": "2026-09-25T14:15:06.530Z"
}
```

| Pole | Co to je |
|---|---|
| `status` | `succeeded` / `failed` |
| `outputs` | hodnoty podle `outputs` scénáře; `file` je nahrazen **URL** v úložišti. Při chybě `null`. |
| `error` | `{class, step, message}` nebo `null`; `step` je cesta (`navrh/copy`) |
| `warnings` | stejné jako v `run_finished` |
| `report_url` | URL `report.html`; když nahrání záznamu selže, `null` a varování |

Adresy souborů mají tvar `<public_base_url>/<run_id>-<32 hex náhodných
znaků>/<jméno>` — pro všechny soubory včetně `report.html` (DESIGN §5.2).
Náhodná část vzniká při startu běhu a je jen v callbacku a v záznamu
(`run_started.storage_prefix`), aby nikdo nenašel neschválené obrázky ani
prompty zkoušením `run_id`.
| `sent_at` | čas odeslání — n8n může odmítnout staré zprávy |

Podpis (§5.2, **návrh** podoby): hlavička
`X-Signature: sha256=<hex>`, kde `<hex>` = HMAC-SHA256 nad přesnými bajty
těla s tajemstvím z `callback.secret_env`. Hlavička `X-Run-Id` nese
`run_id`. n8n podpis ověří, než zprávě uvěří.
