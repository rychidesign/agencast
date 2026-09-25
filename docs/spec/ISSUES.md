# Nejasnosti ve spec v1 zjištěné při implementaci (Fáze 2)

Spec v1 je zmražená; nic z toho ji nemění. U každé položky je výklad,
podle kterého se framework 0.1.0 chová. Nic z toho neblokovalo práci,
rozhoduje koordinátor nebo uživatel.

1. **`tool_wrapper` a `finish_reason`** (scenario.md ask, §6): spec chce
   `tool_calls`. Framework přijme i `stop`, když odpověď obsahuje volání
   `_submit_output` (s vynuceným `tool_choice` to někteří poskytovatelé
   hlásí jako `stop`). Jiný `finish_reason` → `transient`. Naživo Gemini
   3.5 Flash-Lite vrátil `tool_calls` (nativně `STOP`).
2. **Které proměnné prostředí jsou povinné před během** (config.md „Chybějící
   proměnná → config"): framework kontroluje jen ty, které běh opravdu
   použije: `OPENROUTER_API_KEY` (ne s `--fake`), `callback.secret_env` jen
   s `--callback-url`. `webhook.token_env` až s webhook serverem, R2 klíče
   až s R2.
3. **Relativní `runs_dir` a `storage.local.path`** — spec neříká, vůči
   čemu. Framework je bere vůči kořeni projektu (složka nad `workflows/`),
   protože do `workflows/` framework nikdy nezapisuje.
4. **`aspect_ratio` u chat completions** (scenario.md image): framework
   posílá `image_config: {aspect_ratio}` (pole `ChatRequest.image_config`,
   <https://openrouter.ai/docs/llms-full.txt>, staženo 2026-09-25) a poměr
   kontroluje podle hlavičky souboru (±2 %). **Ověřeno naživo
   2026-09-25:** `google/gemini-3.1-flash-image` s `"4:5"` vrátil
   928×1152 (odchylka 0,7 %), endpoint `aspect_ratio` neignoruje.
   Spec zmiňuje jen Image API (`POST /api/v1/images`); rozhodnutí „chat
   completions" padlo ve Fázi 2 podle zadání.
5. **`report_url`**: `report.html` Fáze 2 negeneruje, `report_url` je
   `null` bez varování. Spec počítá s `null` + varováním jen při selhání
   nahrání.
6. **`callback.json` bez `--callback-url`**: zapisuje se vždy (tělo, které
   by odešlo), ač spec říká „přesně to, co odešlo v callbacku".
7. **`details` v `default` kroku `jev`**: spec „`details` se doplní jako
   `{}`". Framework doplní `{otázka: {}}` pro každou otázku, aby
   `steps.x.details.<q>` existovalo; chybějící klíč uvnitř je pak chyba
   `expression`.
8. **Pole navíc v `default`** (pole, které krok nevrací) je chyba
   `validate` — spec výslovně jen „musí obsahovat všechna pole".
9. **Funkce a indexy**: `join` vyžaduje oba argumenty (tabulka spec
   `join(seznam, oddělovač)`); `min`/`max` jen čísla; `[]` nad textem
   (`"abc"[0]`) je chyba, protože spec zná `[]` jen pro seznam a objekt.
   Index `2.0` je povolený (číslo s nulovou desetinnou částí = integer).
10. **Ukázky ve spec jako konformační testy** (§5.9 bod 3): úryvky kroků
    bez hlavičky odkazují na kroky, které v úryvku nejsou, takže projdou
    jen JSON Schema a syntaxí výrazů/šablon. Plně (validate + běh
    s falešným poskytovatelem) se testuje celý scénář `pozdrav`.
11. **`when` s chybou výrazu** (§3 „chyba ve `when` je chybou kroku"):
    krok dostane `step_started`, `error` a `step_finished` se
    `status: failed` (ne `step_skipped`).
12. **Timeout kroku s agentem**: `timeout` kroku, jinak `limits.timeout`
    agenta, jinak výchozí podle typu, vždy nejvýš `limits.timeout` agenta.

## Fáze 3a (krok `task`, MCP, skilly, `dedupe_key`; framework 0.2.0)

13. **Kořen `{run_dir}/…` neexistuje:** server-filesystem neexistující
    povolenou složku odmítne. Framework před startem stdio serveru vytvoří
    složku pro každý argument, který začíná `{run_dir}` (u ukázky
    `runs/<běh>/work`).
14. **Kdy vzniká `dedupe` `started`:** před prvním voláním **MCP** nástroje
    (vedlejší účinek), ne před `load_skill`. Krok, který žádný MCP nástroj
    nezavolal, zapíše rovnou `succeeded`. Soubor obsahuje přesně
    `{state, run_id, output}`. Klíč se počítá ze jména scénáře, v němž krok
    je (u budoucího `call` jméno volaného scénáře).
15. **Poslední tah `max_turns`:** když model v posledním povoleném tahu
    chce další nástroje, framework je **nespustí** (model by výsledek
    neviděl, vedlejší účinek bez kontroly) a krok končí `budget`.
16. **Selhání handshaku MCP** se neopakuje (`retry` kroku platí pro volání
    API): krok selže třídou `transient` (vzdálený server: síť, 5xx,
    timeout) nebo `config` (stdio: neznámý příkaz, proces skončil, neodpověděl
    na handshake; vzdálený: 4xx). Opakování běhu řeší n8n.
17. **Chyba JSON-RPC u `tools/call`** (ne `isError`, např. neznámý nástroj
    −32602) jde modelu jako chyba nástroje (`is_error: true`, krok
    pokračuje) — server volání odmítl. Spadlé spojení = `config`, timeout
    = `timeout`.
18. **`_submit_output` spolu s jinými nástroji v jednom tahu:** výsledek je
    `_submit_output`, ostatní nástroje se nespustí a zapíše se varování.
    Volání nástrojů s `finish_reason: stop` se přijímá (jako bod 1).
19. **`task` na úrovni `tool_wrapper`:** `_submit_output` je mezi nástroji,
    ale nevynucuje se `tool_choice` (model mezitím volá jiné nástroje).
    Textová odpověď místo `_submit_output` = chyba `schema` → kaskáda na
    `prompt`.
20. **Proměnné z `mcp.yaml`** (`env`, `bearer_token_env`) nesmí být stejné
    jako `*_env` z `config.yaml` (klíč OpenRouteru by odešel MCP serveru) —
    chyba `config`. Mezi servery v `mcp.yaml` sdílení dovoleno. Chybějící
    proměnná se hlásí před během jen u serverů, které běh opravdu použije
    (jako bod 2).
21. **`scenarios` serveru** se kontroluje u serverů, které krok opravdu
    použije (`task.mcp`, jinak `mcp` agenta), ne u všech serverů agenta.
    `ask` MCP nepřipojuje, proto se tam nekontroluje.
22. **Nástroj z allowlistu, který server nenabízí** → krok selže `config`
    za běhu (seznam nabízených nástrojů je v hlášce). Spec chce, aby to
    ukázal `validate --dry-run` (výpis nástrojů serverů a výsledné sady
    kroku) — **ve 3a neimplementováno**: `plan.md` je v `record.py` a CLI,
    které paralelně mění Fáze 3b. Doplnit po sloučení.
23. **Obsah výsledku nástroje:** text a obrázek se předají, jiné typy
    (`resource`, `audio`, …) jako text `[obsah typu X framework
    nepředává]`; `structuredContent` se nepředává (text ho obvykle nese).
    `calls/NN.tool.json` (návrh): `{turn, name, server, tool, arguments,
    allowed, invalid_args, is_error, result, files}`.
24. **Zaseknuté volání poskytovatele** (naměřeno v ostrém běhu 3a: HTTP
    spojení bez odpovědi 160 s, stejný požadavek hned poté 2,1 s) se pozná
    až časovým limitem kroku — HTTP klient nemá čtecí timeout jednoho
    volání (Fáze 2, `Timeout(None, connect=15)`), takže se neopakuje jako
    `transient`. Návrh: čtecí timeout volání (např. 120 s) → `transient`
    s `retry`; pozor na pomalé reasoning modely s velkým `max_tokens`.
    Rozhodne koordinátor.
