# Nálezy API pro GUI (ui/ část 1, čtecí verze)

Co GUI při stavbě čtecí verze (2026-09-26, agencast 0.6.0) od HTTP API
`serve` postrádalo nebo dostalo v nevhodném tvaru (návrh GUI §7). Jádro se
neměnilo; u každého bodu je, jak to GUI zatím obchází. Pořadí zhruba podle
dopadu.

1. **`GET /projects/<p>/runs` a `…/runs/<id>` — běžící a přerušený běh
   nejdou odlišit.** `status: "běží nebo přerušen"` má i běh, jehož proces
   dávno skončil (pád, restart `serve`). GUI ho ukazuje jako „běží“
   a dotazuje se na něj navždy (detail 2 s → 5 s, seznam 5 s).
   *Potřeba:* `running` jen u běhu, který drží živý worker, jinak
   `interrupted` (nebo příznak).
   **Stav (0.7.0):** hotovo — `state` v seznamu i detailu (`running` jen se zámkem `<run>/run.lock` drženým živým procesem, jinak `interrupted`); `status` je `běží` / `přerušen`.

2. **`GET /projects/<p>/runs/<id>` — kroky bez podrobností.** Položka
   `steps` nemá `nn` ani složku kroku, chybovou hlášku, `continued`,
   `default_used`, volání (alias → model, tokeny, `finish_reason`, úroveň
   kaskády), nástroje ani odpovědi Jev. GUI proto stahuje celý
   `…/files/events.jsonl` (při živém běhu při každém dotazu) a složku kroku
   hledá v `files` vzorem `steps/\d+-<id>/` (u `call` vnořeně).
   *Potřeba:* v `steps` aspoň `nn`/`dir`, `error {class, message}`,
   `continued`, `default_used`, a souhrn volání; nebo
   `GET …/runs/<id>/steps/<cesta>` s událostmi jednoho kroku.
   **Stav (0.7.0):** hotovo — `steps` mají `nn`, `dir`, `error {class, message}`, `continued`, `default_used`, `reason`, `calls` (bez úrovně kaskády navíc: `structured_output` je v `calls`), u `task` `turns` a `tool_calls`, u `jev` `answers`; nový `GET …/runs/<id>/steps/<cesta>` (události, `output`, `files`). Chyba vnořeného kroku (`call`, větev) je u něj, ne u nadřazeného.

3. **`GET /projects/<p>` — scénáře bez typů kroků.** `IconChain` na kartě
   scénáře (§2.2) potřebuje typy kroků hlavního seznamu; GUI kvůli tomu volá
   `GET …/scenarios/<s>` pro každý scénář (u `workflows/` repa 20 dotazů
   na jedno otevření projektu). *Potřeba:* `types` (typy kroků hlavního
   seznamu v pořadí souboru) v položce `scenarios`.
   **Stav (0.7.0):** hotovo — `types` v položkách `scenarios`.

4. **Rozbitý `config.yaml` → chyby jen jako texty a bez řádku.**
   `GET /projects/<p>` vrací 422 s `details` (texty), `GET
   …/files/config.yaml` vrací `errors: []`, takže YAML režim Configu nemůže
   označit chybný řádek ani pole. Současně `…/runs` a `…/spend` vrací 422 —
   staré běhy takového projektu nejdou číst. *Potřeba:* `errors` jako objekty
   (`file`, `field`, `line`) i v `files/config.yaml` a v 422 odpovědích;
   čtení běhů nezávislé na platném configu (stačí `runs_dir`).
   **Stav (0.7.0):** hotovo — `files/config.yaml` a `mcp.yaml` vrací všechny chyby jako objekty (`line` jen u syntaxe a duplicitního klíče; u chyb schématu `field`); 422 z `GET /projects/<p>` má i `errors`; `…/runs`, `…/runs/<id>` a `…/spend` fungují s neplatným configem (`runs_dir`, jinak `./runs`).

5. **`GET /projects/<p>/runs` — chybí údaje pro řádek seznamu (§2.6).**
   Chybí `fake` (návrh ukazuje „falešný běh“; GUI ho umí jen v detailu
   z `run_started`), `queue_position` u čekajících (GUI bere pořadí
   v seznamu) a číslo běžícího kroku (návrh „krok 4/8“; GUI ukazuje
   „krok foto_prompt (z 8)“). Dry-run má `scenario` a `started_at` `null`
   (GUI je bere z `run_id`). *Potřeba:* `fake`, `queue_position`,
   `current_nn` nebo počet dokončených kroků, u dry-runu `scenario`.
   **Stav (0.7.0):** hotovo — `fake`, `queue_position` (u `queued`), `current_nn` a `steps_done` (u `running`), u dry-runu `scenario` a `started_at` z `run_id`.

6. **Seznam běhů bez filtru a stránkování.** Karta projektu i karta
   scénáře (stavový čip posledního běhu) stahují celé `…/runs`; s počtem
   běhů to poroste. *Potřeba:* `?scenario=&limit=`, nebo `last_run`
   (stav + čas) přímo v položce `scenarios` a v `GET /projects`.
   **Stav (0.7.0):** hotovo — `GET …/runs?scenario=&limit=` a `last_run {run_id, state, finished_at, cost_usd}` ve `scenarios` i v `GET /projects` (může to být i čekající běh nebo dry-run).

7. **`GET /projects` — chybí důvod nedostupnosti a cesta k registru.**
   Karta nedostupného projektu ukazuje důvod; GUI ho získá jen dalším
   `GET /projects/<p>` a přečte text 404. Nadpis „Registr
   ~/.config/agencast/projects.yaml“ (§2.1) GUI ukázat nemůže.
   *Potřeba:* `reason` u `available: false` a `registry` (cesta)
   v odpovědi.
   **Stav (0.7.0):** hotovo — `reason` u `available: false`, `registry` v odpovědi.

8. **`links.scenario_agent` bez id kroku.** Agent v §2.7 má „Používá:
   ig-post (copy)“; GUI umí jen jména scénářů. *Potřeba:* trojice
   `[scénář, krok, agent]` (nebo zvláštní pole).
   **Stav (0.7.0):** hotovo aditivně — `links.scenario_step_agent` jako trojice `[scénář, krok, agent]`; `scenario_agent` beze změny (GUI část 1 ho čte).

9. **Detail běhu kreslí strom podle současného souboru scénáře.** API nevrací
   strom kroků platný při běhu (`scenario_version` je jen číslo formátu), takže
   po úpravě scénáře může detail starého běhu ukázat karty, které tehdy
   neexistovaly (jako „nedošlo“), a kroky, které zmizely, vynechat.
   *Potřeba:* strom kroků v `run_started` (nebo otisk `etag` scénáře, se
   kterým běh začal).

   **Stav (0.7.0):** hotovo — snímek `<run>/scenario/<jméno>.yaml` (spouštěný i volané přes `call`); `GET …/runs/<id>` vrací `tree` (tvar `steps` z `…/scenarios/<s>`), `callees` a `tree_source` (`snapshot`, u starších běhů `current`). Místo stromu v `run_started` kopie souboru — stejný parser, žádný nový formát.