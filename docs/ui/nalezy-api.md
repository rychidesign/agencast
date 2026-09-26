# Nálezy API pro GUI (ui/ část 1 čtecí verze, část 2 editace, část 3 API 0.7.0, část 4 API 0.8.0–0.9.0)

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

## Část 2 (editační verze)

Co chybělo při stavbě editoru (2026-09-26, agencast 0.6.0), ověřeno proti
`agencast serve --fake`. Jádro se neměnilo; u bodu je, jak to GUI obchází.

10. **Přejmenování kroku, který někdo čte, nejde uložit.** Každá operace
    se validuje zvlášť a nesmí přidat novou chybu: `PATCH …/steps/<a>`
    s novým `id` rozbije odkazy čtenářů (422), úprava odkazů předem
    odkazuje na neexistující id (422). Totéž smazání čteného kroku,
    dokud čtenáři odkaz mají. *GUI:* přejmenování čteného kroku ve
    formuláři nepustí a nabídne YAML režim; mazání varuje, že uložení
    projde jen s upravenými čtenáři. *Potřeba:* `PATCH` s `rename_refs:
    true` (přepíše `steps.<old>.` ve všech krocích), nebo dávka operací
    validovaná jako celek (`POST …/scenarios/<s>/batch`).
    **Stav (0.8.0):** `POST …/scenarios/<s>/batch` s operací `rename_step` (`rename_refs`, výchozí `true`); smazání čteného kroku + úprava čtenářů v jedné dávce. `PATCH` s `rename_refs` není — dávka to pokrývá.

11. **Řada operací není atomická.** Uložení z formuláře = několik
    operací po sobě; když n-tá dostane 422/409, předchozí už jsou na
    disku. *GUI:* po selhání načte soubor znovu, kroky na disku převezme
    (uid ← id) a zbytek nechá rozpracovaný s hláškou „na disku je N
    operací z uložení“. *Potřeba:* dávka (viz 10) se zápisem jen při
    úspěchu všech.
    **Stav (0.8.0):** dávka zapíše všechno, nebo nic; chyba operace = 422 s `op` (index), chyba výsledku = 422 bez `op`.

12. **Rozpracovaný stav nejde validovat ani převést mezi režimy.**
    `POST …/validate` bere jen text; formulář drží strom a YAML
    nesestavuje, takže průběžná validace ve Form režimu není (odchylka
    u §4.4 návrhu) a Form ↔ YAML s neuloženými změnami se musí nejdřív
    uložit nebo zahodit. *Potřeba:* `validate` s operacemi (`{path,
    ops: [...]}`) a vrácením výsledného textu/stromu, nebo
    `POST …/scenarios/<s>/render` (operace → text bez zápisu).
    **Stav (0.8.0):** `POST …/scenarios/<s>/render` `{etag?, ops}` → `{text, tree, errors}` bez zápisu (všechny chyby, 200 i s chybami).

13. **Nový krok nejde uložit neúplný.** Prázdný `ask` (bez agenta
    a promptu) je nová chyba → 422; nový `parallel`/`switch` potřebuje
    kroky ve větvích a nová větev existujícího kontejneru jde přidat jen
    s prvním krokem (`PATCH` s `{parallel: {<větev>: [krok]}}`).
    *GUI:* nový krok drží lokálně a pošle ho jedním `POST …/steps` až
    s vyplněnými poli; větev bez nového kroku ohlásí před odesláním.
    **Stav (0.8.0):** validace beze změny; krok vložit a doplnit (nebo větev přidat operací `add_branch` a naplnit) v jedné dávce, rozpracovaný stav přes `render`.

14. **Merge patch neumí hodnotu `null`** (api.md to uvádí) — `default:
    {file: null}` jde jen v YAML režimu. *GUI:* formulář takovou změnu
    odmítne s odkazem na YAML. *Potřeba:* `PUT …/steps/<a>` s celým
    krokem (nahrazení), nebo JSON Patch.
    **Stav (0.8.0):** `PUT …/steps/<adresa>` `{step}` a operace dávky `replace_step` — celý krok, umí `null`.

15. **Čerstvě spuštěný běh je na okamžik `dry-run`.** Hned po `202` na
    `POST /projects/<p>/runs` vrací `GET …/runs/<id>` `status:
    "dry-run"` (složka má `plan.md`, ještě ne `events.jsonl`); GUI by
    přestalo číst. *GUI:* po ostrém spuštění (`?spusteno=1`) čte detail
    dál ještě 15 s. *Potřeba:* `queued`/`running` od první chvíle
    (třeba podle záznamu ve frontě), `dry-run` jen u skutečného plánu.
    **Stav (0.8.0):** záznam ve frontě `_queue/` → `queued` (s `queue_position`), dokud běh nedrží zámek (`running`) nebo neskončí; `dry_run` jen bez `run.lock` (dry-run ho nikdy neměl) — formát záznamu beze změny.

16. **Změny na disku jen dotazováním.** Konflikt (§4.6) GUI pozná
    `GET` celého scénáře/souboru každých 5 s a při fokusu okna. *Potřeba:*
    lehký `HEAD`/`GET …/files/<cesta>?etag_only=1`, nebo SSE se změnami
    souborů.
    **Stav (0.8.0):** `HEAD /projects/<p>/files/<cesta>` (hlavička `ETag`, s `--cors` vystavená) a `GET …?etag_only=1` → `{etag}`. SSE ne.

17. **`GET …/files/<cesta>` hlásí jen chyby loaderu.** `errors` nejsou
    chyby `validate`, takže YAML režim volá hned po načtení
    `POST …/validate` s textem z disku. *Potřeba:* v `files/` stejné
    `errors` jako v `GET /projects/<p>` pro daný soubor.
    **Stav (0.8.0):** `errors` v `GET …/files/<cesta>` = chyby `validate` souboru, stejné jako u položky v `GET /projects/<p>`.

18. **`POST …/agents` a `POST …/scenarios` jen se jménem.** Popis nového
    scénáře jde až druhou operací (`PUT` hlavičky), nový agent má
    šablonový popis `TODO`. *Potřeba:* volitelné `description` (a u
    agenta `model`) v těle.
    **Stav (0.8.0):** volitelné `description`, u agenta `model` (alias z configu, jiný → 422).

19. **Použití aliasu modelu v krocích `image`.** `links` má jen agent →
    alias přes `agents[].model`; alias použitý jen v `image.model` GUI
    neumí označit jako „v užití“ (smazání pak odmítne až validace, 422).
    *Potřeba:* `links.scenario_model` (nebo `models_used`).
    **Stav (0.8.0):** `links.scenario_model` (dvojice scénář–alias z `image.model`) a `models_used` (`{alias: [agents/…md, scenarios/…yaml]}`, všechny aliasy).

20. **`openrouter.jev_model` a `runs_dir` přes `PUT …/config` měnit nejde**
    (povolené jen `openrouter.api_key_env` a pět sekcí); GUI je ukazuje
    jen ke čtení a odkazuje na YAML režim. Je-li to záměr, stačí věta
    v api.md.
    **Stav (0.8.0):** povoleno i `runs_dir` a `openrouter.jev_model`; `version` a `openrouter.base_url` zůstávají zakázané (api.md „`PUT …/config`“ — formát, kam odchází klíč).


## Část 3 (GUI nad API 0.7.0)

GUI přešlo na `state`, `steps` s podrobnostmi, `GET …/steps/<cesta>`, `tree`/`callees`,
`types`/`last_run`, `?scenario=&limit=`, `scenario_step_agent`, `reason`/`registry` (body 1–9).
Ověřeno 2026-09-26 proti `agencast serve --fake` (framework 0.7.0 z větve). Jádro se neměnilo.

21. **Restart `serve` udělá z přerušeného běhu `failed`.** Běh, který běžel pod `serve`
    v okamžiku pádu, dostane po startu `serve` dopsaný `run_started` + `error internal`
    („běh přerušen — server skončil uprostřed běhu…“) + `run_finished failed`. `state:
    interrupted` je tak vidět jen mezi pádem a restartem (a u běhu z CLI, který nikdo
    nedokončí). Navíc: `status` je `failed (internal v None)` (krok `null` → „None“),
    `started_at` je čas obnovy (druhý `run_started`) a `duration_s` `0.0`. *GUI:* ukáže, co
    přijde (`chyba: internal v None`). *Potřeba:* `status` bez „v None“, `started_at` z prvního
    `run_started`; zvážit, jestli obnovený běh nemá zůstat `interrupted` (nebo nést příznak).
    **Stav (0.10.0):** obnova zachová původní `run_started` a doplní chybu `internal` s posledním
    rozběhnutým krokem a zprávou „běh přerušen restartem serveru“; `run_finished.status` je `failed`,
    ale API `state` zůstává `interrupted` a `started_at` původní.
22. **Krok bez konce má v ukončeném běhu `status: running`.** Položka `steps` kroku, který
    měl `step_started` a pak běh spadl, zůstane `running` i u `state` `interrupted`/`failed`.
    *GUI:* když běh není `queued`/`running`, ukáže takový krok jako „přerušen“ (nepulzuje).
    *Potřeba:* u neživého běhu `status: interrupted` (nebo `null`) místo `running`.
    **Stav (0.10.0):** krok bez `step_finished` má `status: interrupted`, když ho nedrží živý worker.
23. **Chyby schématu `config.yaml` bez řádku.** `files/config.yaml` vrací u chyb schématu jen
    `field` (`limits.run_budget_usd`), `line` jen u syntaxe a duplicitního klíče (jak api.md
    uvádí). YAML režim Configu proto u nich řádek neoznačí, jen vypíše hlášku. *Potřeba:*
    `line` i u chyb schématu (loader zná pozici uzlu).
    **Stav (0.10.0):** chyby schématu `config.yaml` obsahují `line` podle klíče v YAML, v `files/config.yaml`
    i v 422 z `GET /projects/<p>`.
24. **`GET /projects` bez počtů.** Karta projektu ukazuje „20 scénářů · 8 agentů“ a dnešní
    útratu, takže dál volá na každý dostupný projekt `GET /projects/<p>` (celý projekt kvůli
    dvěma číslům) a `…/spend`. *Potřeba:* `counts {scenarios, agents}` a `spend_today_usd`
    v položce `GET /projects`.
    **Stav (0.10.0):** dostupné i nedostupné položky vrací počty podle výpisu souborů a `spend_today_usd`
    z denní knihy bez validace projektu.
25. **Stránkování jen `limit`.** „Načíst další“ stáhne znovu celý delší seznam (`limit`
    +50); `last_run` nemá `started_at`, takže čas u čekajícího/přerušeného běhu a dry-runu
    GUI bere z `run_id`. *Potřeba (až bude běhů hodně):* kurzor `?before=<run_id>`; v `last_run`
    `started_at`.
    **Stav (0.10.0):** `before` stránkuje podle názvu složky a `next_before` se vrací, když jsou další běhy;
    `last_run.started_at` je aditivní.


## Část 4 (projekty z GUI, dávky 0.8.0, Playwright E2E)

GUI přešlo na `POST /projects/new`, `POST /projects`, `DELETE /projects/<p>`, `projects_root`/`writable`
(0.9.0), dávku `…/batch`, náhled `…/render`, `HEAD …/files/<cesta>`, `description`/`model` v `POST`
(0.8.0) — body 10–18 GUI už neobchází. Ověřeno 2026-09-26 E2E testy (`ui/e2e/`, Playwright proti
`agencast serve --fake` z větve, framework 0.9.0). Jádro se neměnilo. Nálezy 21 a 22 platí i v 0.9.0
(E2E test `N5b` je očekávané selhání: po restartu `serve` „chyba: internal v None“).

26. **`render` bere jen operace, ne text.** Form → YAML s neuloženými změnami jde (`render` vrátí
    `text`), ale opačně ne: GUI YAML nesestavuje ani neparsuje a žádný endpoint z rozpracovaného
    textu nevrátí strom (`validate` vrací jen `errors`). *GUI:* YAML → Form s neuloženým textem se dál
    ptá „Uložit a přepnout“ / „Zahodit a přepnout“. *Potřeba:* `POST …/scenarios/<s>/render`
    (nebo `validate`) s `{text}` místo `ops`, který vrátí `tree` a `errors` bez zápisu.
    **Stav (0.10.0):** `render` přijímá `{text}` a vrací `{tree, errors}`; `validate` u textu scénáře
    vrací `tree` navíc k `errors`, bez zápisu.
27. **Chyba operace dávky nemá krok.** 422 s `op` nese v `errors` jen `message`
    (`ops[0] update_step: …`), bez `step`/`field`. *GUI:* drží si ke každé operaci id kroku, ze kterého
    vznikla, a chybu ukáže u jeho karty. *Potřeba:* `step` (id kroku podle `address` před operací)
    v chybě operace, u `add_step` id vkládaného kroku.
    **Stav (0.10.0):** chyby operace dávky vrací `step` podle adresy před operací (u `add_step` podle vloženého
    kroku) a `field`, pokud ho chyba určuje.
28. **Ostrý (i falešný) běh v registru chce `CALLBACK_SECRET`, i když se callback neposílá.**
    `POST /projects/<p>/runs` bez `callback_url` vrátí u projektu ze šablony 422 „chybí proměnná
    prostředí CALLBACK_SECRET (.env nebo prostředí)“, dokud proměnnou nemá prostředí `serve` (ověřeno
    s `--fake`; E2E proto nastavuje `CALLBACK_SECRET` a `WEBHOOK_TOKEN` na zástupné hodnoty). Projekt
    založený z GUI tak nejde spustit, i když callback nepotřebuje. *GUI:* ukáže 422 i s `details`
    v panelu spuštění. *Potřeba:* kontrolovat `callback.secret_env` jen s `callback_url` (a
    `webhook.token_env` jen tam, kde se token opravdu čte).
    **Stav (0.10.0):** `callback.secret_env` se vyžaduje jen při callbacku; `webhook.token_env` jen v režimu
    jednoho projektu. Projekt ze šablony lze spustit s `--fake` bez `CALLBACK_SECRET`.
