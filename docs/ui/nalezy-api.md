# Nálezy API pro GUI (ui/ část 1 čtecí verze, část 2 editace)

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

2. **`GET /projects/<p>/runs/<id>` — kroky bez podrobností.** Položka
   `steps` nemá `nn` ani složku kroku, chybovou hlášku, `continued`,
   `default_used`, volání (alias → model, tokeny, `finish_reason`, úroveň
   kaskády), nástroje ani odpovědi Jev. GUI proto stahuje celý
   `…/files/events.jsonl` (při živém běhu při každém dotazu) a složku kroku
   hledá v `files` vzorem `steps/\d+-<id>/` (u `call` vnořeně).
   *Potřeba:* v `steps` aspoň `nn`/`dir`, `error {class, message}`,
   `continued`, `default_used`, a souhrn volání; nebo
   `GET …/runs/<id>/steps/<cesta>` s událostmi jednoho kroku.

3. **`GET /projects/<p>` — scénáře bez typů kroků.** `IconChain` na kartě
   scénáře (§2.2) potřebuje typy kroků hlavního seznamu; GUI kvůli tomu volá
   `GET …/scenarios/<s>` pro každý scénář (u `workflows/` repa 20 dotazů
   na jedno otevření projektu). *Potřeba:* `types` (typy kroků hlavního
   seznamu v pořadí souboru) v položce `scenarios`.

4. **Rozbitý `config.yaml` → chyby jen jako texty a bez řádku.**
   `GET /projects/<p>` vrací 422 s `details` (texty), `GET
   …/files/config.yaml` vrací `errors: []`, takže YAML režim Configu nemůže
   označit chybný řádek ani pole. Současně `…/runs` a `…/spend` vrací 422 —
   staré běhy takového projektu nejdou číst. *Potřeba:* `errors` jako objekty
   (`file`, `field`, `line`) i v `files/config.yaml` a v 422 odpovědích;
   čtení běhů nezávislé na platném configu (stačí `runs_dir`).

5. **`GET /projects/<p>/runs` — chybí údaje pro řádek seznamu (§2.6).**
   Chybí `fake` (návrh ukazuje „falešný běh“; GUI ho umí jen v detailu
   z `run_started`), `queue_position` u čekajících (GUI bere pořadí
   v seznamu) a číslo běžícího kroku (návrh „krok 4/8“; GUI ukazuje
   „krok foto_prompt (z 8)“). Dry-run má `scenario` a `started_at` `null`
   (GUI je bere z `run_id`). *Potřeba:* `fake`, `queue_position`,
   `current_nn` nebo počet dokončených kroků, u dry-runu `scenario`.

6. **Seznam běhů bez filtru a stránkování.** Karta projektu i karta
   scénáře (stavový čip posledního běhu) stahují celé `…/runs`; s počtem
   běhů to poroste. *Potřeba:* `?scenario=&limit=`, nebo `last_run`
   (stav + čas) přímo v položce `scenarios` a v `GET /projects`.

7. **`GET /projects` — chybí důvod nedostupnosti a cesta k registru.**
   Karta nedostupného projektu ukazuje důvod; GUI ho získá jen dalším
   `GET /projects/<p>` a přečte text 404. Nadpis „Registr
   ~/.config/agencast/projects.yaml“ (§2.1) GUI ukázat nemůže.
   *Potřeba:* `reason` u `available: false` a `registry` (cesta)
   v odpovědi.

8. **`links.scenario_agent` bez id kroku.** Agent v §2.7 má „Používá:
   ig-post (copy)“; GUI umí jen jména scénářů. *Potřeba:* trojice
   `[scénář, krok, agent]` (nebo zvláštní pole).

9. **Detail běhu kreslí strom podle současného souboru scénáře.** API nevrací
   strom kroků platný při běhu (`scenario_version` je jen číslo formátu), takže
   po úpravě scénáře může detail starého běhu ukázat karty, které tehdy
   neexistovaly (jako „nedošlo“), a kroky, které zmizely, vynechat.
   *Potřeba:* strom kroků v `run_started` (nebo otisk `etag` scénáře, se
   kterým běh začal).

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
11. **Řada operací není atomická.** Uložení z formuláře = několik
    operací po sobě; když n-tá dostane 422/409, předchozí už jsou na
    disku. *GUI:* po selhání načte soubor znovu, kroky na disku převezme
    (uid ← id) a zbytek nechá rozpracovaný s hláškou „na disku je N
    operací z uložení“. *Potřeba:* dávka (viz 10) se zápisem jen při
    úspěchu všech.
12. **Rozpracovaný stav nejde validovat ani převést mezi režimy.**
    `POST …/validate` bere jen text; formulář drží strom a YAML
    nesestavuje, takže průběžná validace ve Form režimu není (odchylka
    u §4.4 návrhu) a Form ↔ YAML s neuloženými změnami se musí nejdřív
    uložit nebo zahodit. *Potřeba:* `validate` s operacemi (`{path,
    ops: [...]}`) a vrácením výsledného textu/stromu, nebo
    `POST …/scenarios/<s>/render` (operace → text bez zápisu).
13. **Nový krok nejde uložit neúplný.** Prázdný `ask` (bez agenta
    a promptu) je nová chyba → 422; nový `parallel`/`switch` potřebuje
    kroky ve větvích a nová větev existujícího kontejneru jde přidat jen
    s prvním krokem (`PATCH` s `{parallel: {<větev>: [krok]}}`).
    *GUI:* nový krok drží lokálně a pošle ho jedním `POST …/steps` až
    s vyplněnými poli; větev bez nového kroku ohlásí před odesláním.
14. **Merge patch neumí hodnotu `null`** (api.md to uvádí) — `default:
    {file: null}` jde jen v YAML režimu. *GUI:* formulář takovou změnu
    odmítne s odkazem na YAML. *Potřeba:* `PUT …/steps/<a>` s celým
    krokem (nahrazení), nebo JSON Patch.
15. **Čerstvě spuštěný běh je na okamžik `dry-run`.** Hned po `202` na
    `POST /projects/<p>/runs` vrací `GET …/runs/<id>` `status:
    "dry-run"` (složka má `plan.md`, ještě ne `events.jsonl`); GUI by
    přestalo číst. *GUI:* po ostrém spuštění (`?spusteno=1`) čte detail
    dál ještě 15 s. *Potřeba:* `queued`/`running` od první chvíle
    (třeba podle záznamu ve frontě), `dry-run` jen u skutečného plánu.
16. **Změny na disku jen dotazováním.** Konflikt (§4.6) GUI pozná
    `GET` celého scénáře/souboru každých 5 s a při fokusu okna. *Potřeba:*
    lehký `HEAD`/`GET …/files/<cesta>?etag_only=1`, nebo SSE se změnami
    souborů.
17. **`GET …/files/<cesta>` hlásí jen chyby loaderu.** `errors` nejsou
    chyby `validate`, takže YAML režim volá hned po načtení
    `POST …/validate` s textem z disku. *Potřeba:* v `files/` stejné
    `errors` jako v `GET /projects/<p>` pro daný soubor.
18. **`POST …/agents` a `POST …/scenarios` jen se jménem.** Popis nového
    scénáře jde až druhou operací (`PUT` hlavičky), nový agent má
    šablonový popis `TODO`. *Potřeba:* volitelné `description` (a u
    agenta `model`) v těle.
19. **Použití aliasu modelu v krocích `image`.** `links` má jen agent →
    alias přes `agents[].model`; alias použitý jen v `image.model` GUI
    neumí označit jako „v užití“ (smazání pak odmítne až validace, 422).
    *Potřeba:* `links.scenario_model` (nebo `models_used`).
20. **`openrouter.jev_model` a `runs_dir` přes `PUT …/config` měnit nejde**
    (povolené jen `openrouter.api_key_env` a pět sekcí); GUI je ukazuje
    jen ke čtení a odkazuje na YAML režim. Je-li to záměr, stačí věta
    v api.md.
