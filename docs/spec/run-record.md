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

- `runs/` je složka z konfigurace serveru, na Modalu Volume (D5).
- **`run_id`** = `RRRRMMDD-HHMMSS-<scénář>-<4 hex znaky>` v UTC
  (**návrh**) — řadí se podle času a je v něm vidět, co běželo.
- **`<nn>`** = pořadí, v jakém běh ke kroku došel, včetně přeskočených
  (v `parallel` podle skutečného startu) — sedí s číslem v `summary.md`.
  Přeskočený krok složku nemá, je jen v `events.jsonl` a v `summary.md`
  s důvodem.
- **`calls/`** — každé volání API zvlášť (opakování i tahy `task`), číslo
  = pořadí volání v kroku. U `task` navíc `calls/NN.tool.json` (argumenty
  a výsledek nástroje).
- **`call`** — složka kroku obsahuje vlastní `steps/` volaného scénáře:
  `steps/03-navrh/steps/01-copy/…`. Události jdou do jednoho
  `events.jsonl` celého běhu, `step` má cestu `navrh/copy`.
- `--dry-run` vytvoří složku jen s `plan.md` (a `inputs.json`).

## Co do záznamu nikdy nepatří

- **base64** (§5.7): data URL obrázku se v `response.json` nahradí textem
  `"<soubor: steps/07-foto/image.png, 1510234 B>"`. Totéž platí pro
  `events.jsonl` a `output.json`.
- **`reasoning_details`** (šifrované, u obrázku ~1,4 MB): v záznamu jen
  `"<vynecháno: reasoning_details, 1412345 B>"`. Framework je drží v paměti
  a posílá zpět v dalším tahu (§5.5), do souboru ne.
- **Tajné klíče a hlavičky** požadavků. `request.json` je jen tělo.
- Z URL callbacku se loguje jen `schéma://host/cesta` bez query.

## `events.jsonl`

Každý řádek je jeden JSON objekt. Společná pole:

| Pole | Co to je | Příklad |
|---|---|---|
| `ts` | čas události, ISO 8601 v UTC s milisekundami | `"2026-09-25T14:03:12.481Z"` |
| `type` | typ události (tabulky níže) | `"step_started"` |
| `step` | cesta ke kroku (`id`, u `call` `navrh/copy`); u událostí běhu chybí | `"copy"` |

Časy trvání jsou v sekundách (`duration_s`), ceny v USD (`cost_usd`).

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

**`step_started`** — krok začal.

| Pole | Co to je |
|---|---|
| `kind` | typ kroku: `ask`, `task`, `jev`, `image`, `parallel`, `switch`, `call`, `set`, `fail`, `output` |
| `branch` | jméno větve `parallel` nebo hodnota `switch`, ve které krok je; jinak chybí |

**`step_skipped`** — krok neproběhl (§5.1 bod 5: vždy s důvodem).

| Pole | Co to je |
|---|---|
| `kind` | typ kroku |
| `reason_code` | `when`, `switch`, `dedupe`, `cancelled` (zrušen, protože selhala jiná větev `parallel`) |
| `reason` | věta pro člověka, např. `when: steps.kontrola.on_brand < 0.7 → false` |
| `default_used` | `true`, pokud se jako výstup použil `default` |

**`step_finished`** — krok skončil.

| Pole | Co to je |
|---|---|
| `kind` | typ kroku |
| `status` | `succeeded` nebo `failed` |
| `continued` | `true`, když selhal s `on_error: continue` (→ varování) |
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
| `duration_s`, `usage` | trvání, normalizovaná spotřeba |
| `request_file`, `response_file` | cesty do `calls/` |

**`tool_call`** — `task` zavolal nástroj.

| Pole | Co to je |
|---|---|
| `turn` | tah, ve kterém model nástroj zavolal |
| `server`, `tool` | MCP server a nástroj |
| `allowed` | `false`, když nástroj nebyl povolen (nespustil se, model dostal chybu) |
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
| `class` | třída chyby (scenario.md §6): `transient`, `schema`, `content`, `budget`, `timeout`, `config`, `fail`, `internal` |
| `message` | přesná hláška (u API včetně `error.message` poskytovatele) |
| `attempt` | pokus, ve kterém chyba nastala |
| `will_retry` | `true`, když následuje další pokus |
| `http_status` | status, pokud jde o HTTP |

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

**`callback_sent`** — pokus o doručení callbacku (poslední řádek souboru).

| Pole | Co to je |
|---|---|
| `url` | adresa bez query |
| `attempt` | pokus 1–3 (**návrh**: 3 pokusy, prodleva 5 s a 30 s) |
| `http_status` | odpověď n8n, `null` při chybě sítě |
| `error` | hláška, pokud doručení selhalo |

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
Běh `20260925-140311-ig-post-a1b2` · 25. 9. 2026 14:03:11 UTC · 17,5 s · 0,0693 USD (z toho obrázky 0,0672 USD)

## Vstupy
- tema: nová káva

## Kroky
| # | Krok | Typ | Stav | Čas | Cena | Poznámka |
|---|---|---|---|---|---|---|
| 1 | copy | ask | ✓ | 3,7 s | 0,0015 | chytry → anthropic/claude-haiku-4.5 |
| 2 | kontrola | jev | ✓ | 0,3 s | 0,0000 | on_brand = 0,91 |
| 3 | stop | fail | přeskočeno | | | when: steps.kontrola.on_brand < 0.7 → false |
| 4 | foto_prompt | ask | ✓ | 1,8 s | 0,0006 | rychly → google/gemini-3.5-flash-lite |
| 5 | kontrola_obrazku | jev | ✓ | 0,3 s | 0,0000 | skutecna_osoba = 0,02, cizi_znacka = 0,01 |
| 6 | stop_obrazek | fail | přeskočeno | | | when: … → false |
| 7 | foto | image | ✓ | 10,6 s | 0,0672 | image.png, 1408×768 |
| 8 | out | output | ✓ | | | |

## Varování
žádná

## Výstup
- caption: „…"
- hashtags: #kava, #thtd
- image: https://files.example.com/20260925-140311-ig-post-a1b2/image.png
```

Při chybě je nadpis `— chyba`, hned pod ním blok **Chyba** s třídou,
krokem a přesnou hláškou, a v tabulce kroků je vidět, kde běh skončil.

`report.html` má stejný obsah plus rozbalitelné prompty a odpovědi
(bez base64). Podobu HTML určí Fáze 2.

## Callback

Posílá se **vždy** po skončení běhu — při úspěchu i chybě (D2, §5.1
bod 2). `POST` na URL z požadavku, tělo JSON:

```json
{
  "run_id": "20260925-140311-ig-post-a1b2",
  "scenario": "ig-post",
  "request_key": "n8n-4711",
  "status": "succeeded",
  "outputs": {
    "caption": "…",
    "hashtags": ["#kava", "#thtd"],
    "image": "https://files.example.com/20260925-140311-ig-post-a1b2/image.png"
  },
  "error": null,
  "warnings": [],
  "cost_usd": 0.0693,
  "duration_s": 17.5,
  "report_url": "https://files.example.com/20260925-140311-ig-post-a1b2/report.html",
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
  "report_url": "https://files.example.com/20260925-141502-ig-post-9f3c/report.html",
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
| `sent_at` | čas odeslání — n8n může odmítnout staré zprávy |

Podpis (§5.2, **návrh** podoby): hlavička
`X-Signature: sha256=<hex>`, kde `<hex>` = HMAC-SHA256 nad přesnými bajty
těla s tajemstvím z `callback.secret_env`. Hlavička `X-Run-Id` nese
`run_id`. n8n podpis ověří, než zprávě uvěří.
