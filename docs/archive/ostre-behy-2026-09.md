# Ostré běhy — září 2026

Toto jsou archivní protokoly z vývoje; zachovávají tehdejší výsledky a kontext.

## Ostrý test webhooku (Fáze 3b, 2026-09-25)

`agencast serve --port 8788` lokálně (proti OpenRouteru, `examples/showcase/workflows/config.yaml`
beze změny), přijímač callbacku na `http://127.0.0.1:8799/cb` (ověřuje
HMAC), `WEBHOOK_TOKEN` a `CALLBACK_SECRET` vygenerované jen pro test.
Jeden `POST /runs` s `ig-post`, téma „ranní espresso na cestu do práce",
`request_key: ostry-test-3b-1`.

| Co | Výsledek |
|---|---|
| odpověď na `POST /runs` | **202** `{"run_id": "20260925-152331-ig-post-3820", "queue_position": 1}` za **0,10 s** |
| callback | dorazil **4,1 s** po POST, `X-Signature` ověřen, `X-Run-Id` sedí |
| běh | `failed`, třída `fail` v kroku `stop`: on_brand = 0,56 (práh 0,7) — záměrné ukončení scénářem, jako ve Fázi 2 |
| kroky | `copy` (Claude Haiku 4.5, 3,6 s, 0,0013 USD) → `kontrola` (Jev 1.13, 0,4 s) → `stop` |
| cena, doba běhu | **0,0013 USD**, 3,96 s |
| `report_url` | `file://…/outputs/20260925-152331-ig-post-3820-<32 hex>/report.html` (4,8 kB, bez base64 a tajných hodnot) |
| `GET /runs/<run_id>` | 200, `status: failed`, `callback_failed: false` |
| opakovaný POST se stejným `request_key` | **200**, původní `run_id`, žádný nový běh |

Útrata Fáze 3b: **0,0013 USD**.

## Ostrý běh (Fáze 2, 2026-09-25)

`agencast --project examples/showcase run ig-post` proti OpenRouteru, aliasy
`chytry` = `anthropic/claude-haiku-4.5`, `rychly` =
`google/gemini-3.5-flash-lite` (`tool_wrapper`), `gemini-image` =
`google/gemini-3.1-flash-image`. `agencast validate` proti `GET /models` prošel.

| Běh | Téma | Výsledek | Čas | Cena |
|---|---|---|---|---|
| `runs/20260925-145904-ig-post-81e5` | ranní káva s přáteli | `fail` v kroku `stop`: on_brand = 0,68 | 6,2 s | 0,0013 USD |
| `runs/20260925-145923-ig-post-d686` | nová káva Lumen | `fail` v kroku `stop`: on_brand = 0,63 | 2,8 s | 0,0013 USD |

Útrata Fáze 2 celkem **0,0026 USD**. Oba běhy doběhly přesně podle
scénáře: `copy` (Claude Haiku přes Amazon Bedrock, `native_schema`,
2,6–5,8 s, 0,0012 USD) → `kontrola` (Jev `typesafe/jev-1.13-20260917`,
0,27–0,41 s, 0,000016 USD) → záměrný `fail` pod prahem 0,7. Záznam
(summary, events, request/response bez klíče) je kompletní.

**Práh 0,7 je pro text od Haiku přísný; scénář se choval správně.** Jev
text copywritera (Claude Haiku 4.5) dvakrát ohodnotil pod prahem (0,68
a 0,63), takže běh skončil záměrným `fail` dřív, než došel k fotce. Obsah
textu a práh jsou ve vrstvě uživatele (agent `copywriter`,
`ig-post.yaml`), ne ve frameworku. Třetí běh `ig-post` jsem podle zadání
(nejvýš 2 pokusy) nespouštěl.

Zbylé kroky ověřil se souhlasem koordinátora **jeden** ostrý běh
dočasného scénáře `live-image` (mimo `workflows/`, nekomitovaný):
`ask` s agentem `photographer` + `image` s `aspect_ratio: "4:5"`.

| Běh | Krok | Výsledek | Čas | Cena |
|---|---|---|---|---|
| `runs/20260925-150206-live-image-7210` (úspěch, celkem 11,0 s, 0,0676 USD) | `foto_prompt` | `google/gemini-3.5-flash-lite` přes `tool_wrapper`: `finish_reason: tool_calls` (nativně `STOP`), `_submit_output` napoprvé platný | 1,5 s | 0,0003 USD |
| | `foto` | `google/gemini-3.1-flash-image`, `image_config.aspect_ratio: "4:5"` → PNG **928×1152** (1,83 MB), poměr 0,806 proti 0,8 = odchylka 0,7 % → **4:5 platí** (kontrola spec D10, tolerance 2 %) | 9,5 s | 0,0672 USD |

Záznam: base64 ani `reasoning_details` v `calls/*.json` nejsou (jen
`<soubor: steps/02-foto/image.png, 1834634 B>`), obrázek je ve složce
kroku a zkopírovaný do `outputs/<run_id>-<32 hex>/image.png`.

**Útrata Fáze 2 celkem 0,0702 USD** (2× `ig-post` 0,0026 + `live-image`
0,0676; `GET /models` zdarma).

## Ostrý běh Fáze 3a (2026-09-25): krok `task` se skutečným MCP serverem

`agencast --project examples/showcase run ukazka-task -i knihy="Karel Čapek:
R.U.R. (1920); Božena Němcová: Babička (1855); Jaroslav Hašek: Osudy
dobrého vojáka Švejka (1921)"`, agent `knihovnik` na aliasu `chytry` =
`anthropic/claude-haiku-4.5` (`native_schema`), MCP server
`@modelcontextprotocol/server-filesystem@2026.8.31` přes `npx -y`,
kořen `runs/<běh>/work`. `agencast validate` proti `GET /models` prošel.

| Běh | Výsledek | Čas | Tahy | Cena |
|---|---|---|---|---|
| `runs/20260925-152451-ukazka-task-9190` | **úspěch**: `katalog.md` se 3 knihami seřazenými podle příjmení (podle skillu), výstup `{soubor, pocet: 3}` | 21,7 s | 4 tahy, 4 nástroje | 0,0104 USD |
| `runs/20260925-152121-ukazka-task-f370` | `timeout` kroku (3m): 2. tah — HTTP požadavek na OpenRouter 160 s bez odpovědi | 180,0 s | 1 tah, 2 nástroje | 0,0019 USD |

Úspěšný běh: start serveru + handshake 0,77 s; tah 1 `list_allowed_directories`
+ `load_skill katalog` (1,7 s), tah 2 `write_file` (4,0 s), tah 3
`read_text_file` (1,7 s), tah 4 finální JSON (13,5 s, poskytovatel
Anthropic; tahy 1–3 Amazon Bedrock). Nástroje 5–7 ms. Po běhu 0 procesů
serveru, `summary.md` a `events.jsonl` kompletní (`mcp_server`
started/stopped, 4× `tool_call`, 4× `model_call` s `turn`).

První běh selhal na zaseknutém volání poskytovatele: framework se zachoval
podle spec (třída `timeout`, server ukončen, záznam úplný), ale zaseknuté
spojení se pozná až limitem kroku — viz `docs/spec/ISSUES.md` bod 34.
Tentýž požadavek (`calls/04.request.json`) zopakovaný ručně prošel za
2,1 s s `response_format` i bez něj (0,0055 USD).

**Útrata Fáze 3a celkem 0,0178 USD** (2 běhy 0,0123 + diagnostika 0,0055).
