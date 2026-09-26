# Webhook — spuštění běhu (specifikace v1)

Běh spouští n8n (nebo kdokoli s tokenem) požadavkem na webhook. Odpověď
přijde hned; výsledek později na `callback_url` (D2). Podoba callbacku:
[run-record.md](run-record.md#callback).

Značení: **návrh** = DESIGN.md to neřeší, navržené výchozí chování.

Čtení projektů a běhů přes HTTP (`GET /projects/...`) a spuštění běhu
v konkrétním projektu (`POST /projects/<p>/runs`, jinak totéž co
`POST /runs`) popisuje [api.md](api.md) (od frameworku 0.4.0); spuštění
z GUI bez `callback_url` a s `dry_run` jen tam ([api.md „Spuštění
z GUI“](api.md#spuštění-z-gui-od-060), od 0.6.0). Tahle smlouva se tím
nemění.

## Požadavek

```http
POST /runs
Authorization: Bearer <token>
Content-Type: application/json

{
  "scenario": "ig-post",
  "inputs": { "tema": "nová káva" },
  "callback_url": "https://n8n.example.com/webhook-waiting/4711",
  "request_key": "n8n-4711"
}
```

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| hlavička `Authorization` | ano | `Bearer <token>`, token je hodnota proměnné z `webhook.token_env` v `config.yaml` (Modal endpointy jsou jinak veřejné, D5). | 401 | |
| `scenario` | ano | Jméno scénáře z `workflows/scenarios/`. | 422 | `"ig-post"` |
| `inputs` | ne | Vstupy podle `inputs` scénáře. Typ `file` z webhooku není dovolen. | `{}` — scénář dostane své `default`. | `{"tema": "nová káva"}` |
| `callback_url` | ano | Kam poslat výsledek. Jen `https://`. Typicky resume URL čekajícího workflow v n8n. | 422 | |
| `request_key` | ne | Idempotenční klíč (§5.2): opakovaný požadavek se stejným klíčem nespustí druhý běh. | Každý požadavek = nový běh. | `"n8n-4711"` |

## Odpovědi

| Status | Kdy | Tělo | `run_id` / callback |
|---|---|---|---|
| **202** | požadavek přijat, běh je ve frontě | `{"run_id": "…", "queue_position": 2}` | ano / ano |
| **200** | `request_key` už byl použit | `{"run_id": "<původní>", "queue_position": null}` | původní běh / callback původního běhu, nový nevznikne |
| **401** | chybí nebo nesedí token | `{"error": "…"}` | ne / ne |
| **422** | neznámý scénář, vstupy nesedí na `inputs`, `callback_url` není `https`, nebo scénář neprošel `validate` | `{"error": "…", "details": [...]}` | ne / ne |

- **Synchronně** (401, 422) se odmítá všechno, co jde poznat bez spuštění:
  token, tvar těla, vstupy, `validate` scénáře. Pak **nevzniká `run_id`
  ani callback** — chybu dostane volající hned v odpovědi.
- **`queue_position`** počítá framework (Modal ho spolehlivě nedává, D5);
  smí být `null`, když ho nezná. Je to informace, ne slib.
- **Souběžné běhy** (od frameworku 0.3.0): `agencast serve --workers N`
  (výchozí 1) pouští N běhů najednou nad jednou frontou. `queue_position`
  pak počítá čekající i běžící požadavky včetně tohoto — hodnota ≤ N
  znamená, že běh už běží nebo začne, jakmile se uvolní worker. **Pořadí
  dokončení (a tedy callbacků) není zaručené**; s `--workers 1` jdou běhy
  jeden po druhém v pořadí přijetí. S `limits.max_parallel_runs`
  ([config.md](config.md#limits--pojistky-celého-běhu), od 0.3.1) čeká
  vyzvednutý běh ještě na volný slot, který sdílí i CLI a cron.
- **Od přidělení `run_id` se callback posílá vždy** — i když `validate`
  selže až po vyzvednutí z fronty (např. změnil se mezitím soubor), pak
  s třídou `config`; nedočkaný slot `max_parallel_runs` → `timeout`,
  vyčerpaný `daily_budget_usd` → `budget` (od 0.3.1).
- V `POST /projects/<p>/runs` může být `callback_url` vynechána; v tom
  případě se `callback.secret_env` ani podpis nevyžadují. Smlouva
  `POST /runs` zůstává beze změny a `callback_url` nadále vyžaduje.
- Záznam `request_key` platí po dobu uchování složek běhů (**návrh**).
- Časový limit v n8n musí počítat i s čekáním ve frontě (D2).
