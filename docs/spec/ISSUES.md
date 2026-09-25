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
   nahrání. *(Vyřešeno ve 3b: report se generuje a nahrává.)*
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

## Fáze 3b (call, webhook, report.html)

13. **Složka kroku `call`**: zadání 3b zmiňuje `steps/<nn>-<id>/call/`,
    spec (run-record.md) `steps/03-navrh/steps/01-copy/`. Framework drží
    spec; navíc zapisuje `steps/<nn>-<id>/inputs.json` (vstupy volání)
    a `output.json` (výstup = `outputs` volaného scénáře). `summary.md`
    má v tabulce jen kroky volajícího scénáře (u `call` poznámka se
    jménem scénáře), vnořené kroky jsou v `events.jsonl` a `report.html`.
14. **`callback_url` na `http://127.0.0.1`**: spec chce „jen `https://`".
    Framework povolí i `http://127.0.0.1:<port>/…` (testy, lokální
    přijímač podle zadání 3b) — ve webhooku i v `maw run --callback-url`.
    `localhost` ani jiné `http://` ne.
15. **`queue_position`**: počet požadavků ve frontě včetně právě
    běžícího a tohoto (1 = začne hned). Spec jen „pozice ve frontě".
16. **`GET /runs/<run_id>`** ve spec není (zadání 3b ano): chce stejný
    token; vrací `{status: queued, queue_position}`, `{status: running}`,
    nebo tělo `callback.json` + `callback_failed`; neznámý běh 404.
17. **Tělo webhooku**: neznámé pole je 422 (jako „překlep je chyba"
    u formátů). Opakovaný `request_key` vrátí 200 s původním `run_id`
    i tehdy, když se zbytek těla liší (kontroluje se hned po tokenu).
18. **Běh, který nezačne** (validate selže po vyzvednutí z fronty, nebo
    běh přerušil restart serveru): složka má `run_started` se
    `scenario_version: null` a bez kroků, `error` a `run_finished`
    s třídou `config` / `internal`, `report.html` a callback. Přerušený
    běh se neopakuje (mohl mít vedlejší účinky) a callback nese
    `internal`, i když běh mohl doběhnout, jen callback neodešel.
19. **`on_error: continue` u `call`** pokryje i chybu kroku uvnitř
    volaného scénáře (`error.step` zůstává cesta `navrh/copy`) a
    vyčerpání vlastního `budget_usd`/`timeout` kroku `call`; rozpočet
    a čas běhu ne (scenario.md §6).
20. **`report.html` vzniká před `run_finished`**, aby varování
    o nepovedeném nahrání bylo v `run_finished` i v callbacku; stav
    doručení callbacku proto v reportu není (je v `summary.md`
    a `events.jsonl`).

21. **Prodleva `retry` u chyby `schema`** (scenario.md §3 `retry`: „při
    chybě `transient` nebo `schema` … Prodleva 2 s, 4 s, 8 s…"): framework
    čeká jen po `transient`; po `schema` zkouší hned další úroveň kaskády
    (běh `tutorial-02-nazev-a-slogan` s fixturou `text:` místo `json:`
    trval 0,003 s). Čekání u `schema` nic nepřináší, ale spec ho čte jinak.
    (Zjištěno při psaní tutoriálů.)
22. **URL callbacku v záznamu bez portu** (run-record.md „Z URL callbacku
    se loguje jen `schéma://host/cesta`"): `--callback-url
    https://127.0.0.1:8443/webhook-waiting/4711` je v `callback_sent` jako
    `https://127.0.0.1/webhook-waiting/4711`. Doslova podle spec, ale při
    ladění n8n na nestandardním portu port chybí. (Zjištěno při psaní
    tutoriálů.)

## Fáze 3a (krok `task`, MCP, skilly, `dedupe_key`; framework 0.2.0)

23. **Kořen `{run_dir}/…` neexistuje:** server-filesystem neexistující
    povolenou složku odmítne. Framework před startem stdio serveru vytvoří
    složku pro každý argument, který začíná `{run_dir}` (u ukázky
    `runs/<běh>/work`).
24. **Kdy vzniká `dedupe` `started`:** před prvním voláním **MCP** nástroje
    (vedlejší účinek), ne před `load_skill`. Krok, který žádný MCP nástroj
    nezavolal, zapíše rovnou `succeeded`. Soubor obsahuje přesně
    `{state, run_id, output}`. Klíč se počítá ze jména scénáře, v němž krok
    je (u `call` jméno volaného scénáře a `id` kroku v jeho souboru).
25. **Poslední tah `max_turns`:** když model v posledním povoleném tahu
    chce další nástroje, framework je **nespustí** (model by výsledek
    neviděl, vedlejší účinek bez kontroly) a krok končí `budget`.
26. **Selhání handshaku MCP** se neopakuje (`retry` kroku platí pro volání
    API): krok selže třídou `transient` (vzdálený server: síť, 5xx,
    timeout) nebo `config` (stdio: neznámý příkaz, proces skončil, neodpověděl
    na handshake; vzdálený: 4xx). Opakování běhu řeší n8n.
27. **Chyba JSON-RPC u `tools/call`** (ne `isError`, např. neznámý nástroj
    −32602) jde modelu jako chyba nástroje (`is_error: true`, krok
    pokračuje) — server volání odmítl. Spadlé spojení = `config`, timeout
    = `timeout`.
28. **`_submit_output` spolu s jinými nástroji v jednom tahu:** výsledek je
    `_submit_output`, ostatní nástroje se nespustí a zapíše se varování.
    Volání nástrojů s `finish_reason: stop` se přijímá (jako bod 1).
29. **`task` na úrovni `tool_wrapper`:** `_submit_output` je mezi nástroji,
    ale nevynucuje se `tool_choice` (model mezitím volá jiné nástroje).
    Textová odpověď místo `_submit_output` = chyba `schema` → kaskáda na
    `prompt`.
30. **Proměnné z `mcp.yaml`** (`env`, `bearer_token_env`) nesmí být stejné
    jako `*_env` z `config.yaml` (klíč OpenRouteru by odešel MCP serveru) —
    chyba `config`. Mezi servery v `mcp.yaml` sdílení dovoleno. Chybějící
    proměnná se hlásí před během jen u serverů, které běh opravdu použije
    (jako bod 2).
31. **`scenarios` serveru** se kontroluje u serverů, které krok opravdu
    použije (`task.mcp`, jinak `mcp` agenta), ne u všech serverů agenta.
    `ask` MCP nepřipojuje, proto se tam nekontroluje.
32. **Nástroj z allowlistu, který server nenabízí** → krok selže `config`
    za běhu (seznam nabízených nástrojů je v hlášce). Spec chce, aby to
    ukázal `--dry-run`: `maw run … --dry-run` servery, které běh může
    spustit, kvůli `tools/list` spustí v dočasné složce (složka plánu
    zůstane jen s `plan.md`) a `plan.md` vypíše, co nabízejí, a výslednou
    sadu nástrojů každého `task` (doplněno při sloučení 3a + 3b).
33. **Obsah výsledku nástroje:** text a obrázek se předají, jiné typy
    (`resource`, `audio`, …) jako text `[obsah typu X framework
    nepředává]`; `structuredContent` se nepředává (text ho obvykle nese).
    `calls/NN.tool.json` (návrh): `{turn, name, server, tool, arguments,
    allowed, invalid_args, is_error, result, files}`.
34. **Zaseknuté volání poskytovatele** (naměřeno v ostrém běhu 3a: HTTP
    spojení bez odpovědi 160 s, stejný požadavek hned poté 2,1 s) se pozná
    až časovým limitem kroku — HTTP klient nemá čtecí timeout jednoho
    volání (Fáze 2, `Timeout(None, connect=15)`), takže se neopakuje jako
    `transient`. Návrh: čtecí timeout volání (např. 120 s) → `transient`
    s `retry`; pozor na pomalé reasoning modely s velkým `max_tokens`.
    Rozhodne koordinátor.
    **Vyřešeno v 0.2.1:** timeout každého volání = min(zbývající čas
    kroku, 120 s chat/obrázek/tah `task`, 30 s Jev), vypršení = `transient`
    (opakuje se podle `retry`), hodnota v `model_call`/`jev_call` jako
    `timeout_s`. Je to čtecí timeout httpx (ticho mezi bajty odpovědi),
    ne celková doba — tu dál hlídá timeout kroku.
