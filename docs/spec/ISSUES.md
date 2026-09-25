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
13. **Prodleva `retry` u chyby `schema`** (scenario.md §3 `retry`: „při
    chybě `transient` nebo `schema` … Prodleva 2 s, 4 s, 8 s…"): framework
    čeká jen po `transient`; po `schema` zkouší hned další úroveň kaskády
    (běh `tutorial-02-nazev-a-slogan` s fixturou `text:` místo `json:`
    trval 0,003 s). Čekání u `schema` nic nepřináší, ale spec ho čte jinak.
    (Zjištěno při psaní tutoriálů.)
14. **URL callbacku v záznamu bez portu** (run-record.md „Z URL callbacku
    se loguje jen `schéma://host/cesta`"): `--callback-url
    https://127.0.0.1:8443/webhook-waiting/4711` je v `callback_sent` jako
    `https://127.0.0.1/webhook-waiting/4711`. Doslova podle spec, ale při
    ladění n8n na nestandardním portu port chybí. (Zjištěno při psaní
    tutoriálů.)
