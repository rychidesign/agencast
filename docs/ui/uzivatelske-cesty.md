# Uživatelské cesty pro Playwright E2E — GUI AgenCast

Návrhové zadání z 2026-09-26 a mapa pokrytí E2E testů v `ui/e2e/`. Značky
**[hotovo]**, **[obcházeno]** a **[nehotové]** zachycují stav při sepsání
scénářů; aktuální pokrytí ukazují testy a současný popis v `ui/README.md`.

Zdroj: `docs/ui/navrh-gui.md`, `docs/spec/api.md`, `docs/spec/projects.md`,
reporty ui-1/2/3, `docs/ui/nalezy-api.md` a implementace `ui/src/`.

## Společný výchozí stav (fixture)

```bash
export AGENCAST_CONFIG_DIR=$TMP/cfg AGENCAST_TOKEN=test-token
agencast new project $TMP/demo          # registr „demo“: agents/pisatel.md, scenarios/ukazka.yaml (napis → vystup, vstup tema default „káva“)
agencast serve --fake $TMP/fake.yaml --port 8787   # mimo projekt = režim registru; GUI = sestavené ui/ (npm run build) na http://127.0.0.1:8787/
```
- `fake.yaml` = mapa `id kroku: [odpověď…]` (fake.py): `napis: [{text: "Dvě věty."}]`, pro živý běh `pomalu: [{text: "…", sleep: 4}]` (krok `pomalu` ve fixture `dlouhy.yaml`). Jeden skript na proces `serve` → kroky s jiným chováním musí mít jiné id.
- Playwright `storageState`: `localStorage["agencast.token"]="test-token"` (kromě C1). Soubory se ověřují přes `fs` + YAML parser; GUI zapisuje jen přes API, nic neparsuje samo.
- Hash cesty: `#/` · `#/p/demo` (= scenare) · `#/p/demo/{agenti|config|skilly|behy}[/item]` · `#/p/demo/scenare/<s>?krok=<id|_hlavicka>&rezim=yaml&z=…` · `#/p/demo/behy/<run_id>?zalozka=…&krok=…&spusteno=1`.
- Stabilní háčky, které už existují: karta kroku `button[data-step-card="<id>"]` s `aria-label="Krok n: <typ> <id>[ — stav][ — vyjmuto]"` a `aria-pressed`; hlavička `[data-step-card=""]`; panel `role=complementary` (aside `aria-labelledby=step-panel-title` / `run-panel-title`); přepínač `radiogroup "Zobrazení"` s `radio "Form"` / `"YAML"` / `"Markdown"`; menu ⋯ `button "Akce pro <jméno>"` → `menuitem`; TypePicker `listbox "Typ nového kroku"` → `option` (text `ask jedno volání agenta`); YAML `textbox "scenarios/<s>.yaml"`; sloupec `section "Kroky scénáře"`; záložky `nav "Části projektu"` / `nav "Části běhu"` s `aria-current=page`.
- Značky stavu: **[hotovo]** · **[obcházeno]** = test napsat jako expected fail s poznámkou · **[nehotové]** = totéž, cíl teprve vzniká.

## Navržené `data-testid` (kde text nestačí)

| testid | kde a proč |
|---|---|
| `save-status` | text stavu uložení v hlavičce editoru/agenta (mění se s časem „Uloženo ✓ 14:05“) |
| `run-state`, `run-cost`, `run-duration` | odznak stavu a mono čas/cena v hlavičce běhu (dnes bez štítku) |
| `step-cost-<id>`, `step-duration-<id>` | pravá strana karty v běhu |
| `add-after-<id>` (nebo `aria-label="Vložit krok za <id>"`) | všechna (+) mezi kartami mají stejné `"Vložit krok sem"`, test dnes indexuje |
| `branch-<jméno>`, `case-<hodnota>`, `case-default` | sekce větví/případů mají `aria-label` = surové jméno |
| `yaml-line-<n>` | chybný řádek v YAML editoru je dnes jen třída |
| `conflict-bar`, `server-bar` | oba jsou `role=alert`, kolidují s chybami polí |
| `project-card-<name>`, `scenario-card-<name>`, `run-row-<run_id>` | karty a řádky (dnes jen odkaz jménem) |
| panel kroku v běhu: `tablist` přejmenovat na `"Části kroku"` | dnes `"Části běhu"` stejně jako záložky stránky |

## Cesty (podle důležitosti pro začátečníka)

### C1 První spuštění: token **[hotovo]**
Cíl: dostat se bez terminálu k projektům. Stav: prázdné localStorage.
1. Otevřít `/` → `h1 "Token serveru"`, `textbox "Token"` (type=password), nápověda „V režimu registru proměnná AGENCAST_TOKEN…“, `button "Uložit"` disabled; žádný fetch na `/projects`.
2. Napsat `spatny`, Enter → `role=alert "Token serveru nesedí — server vrátil 401."`, formulář zůstává, token není v URL.
3. Napsat `test-token`, Enter → `h1 "Projekty"`, popis „Registr …/cfg/projects.yaml“, karta `demo` **bez** štítku „dostupný“ (G6), s „1 scénář · 1 agent“, „dnes 0 USD“, „bez běhů“.
Playwright: `localStorage.agencast.token === "test-token"`; `Authorization: Bearer` v požadavku (route intercept).

### C2 Založení projektu z GUI **[hotovo]**
Cíl: nový projekt bez terminálu. Stav: registr jen `demo`.
1. `#/` → klik „Přidat projekt“ (tlačítko v hlavičce; čárkovaná karta jen u prázdného seznamu) → dialog (`role=dialog`) „Nový projekt“: `textbox "Jméno"` (slug; napsané jméno se upraví už při psaní — `Můj projekt` → `muj-projekt`; chyba „„demo“ už existuje.“), `textbox "Cesta"`, `button "Vytvořit"`.
2. `muj-web` + `$TMP/muj-web`, Vytvořit → `#/p/muj-web`, `h1 "Scénáře"`, jméno „muj-web“ a `nav "Části projektu"` v sidebaru (cesta projektu na stránce není, G5), karta scénáře `ukazka` s podtitulem „Napíše krátký text na zadané téma“ a meta „2 kroky · pisatel“ (bez počtu vstupů/výstupů a bez „ukazka.yaml“, G7).
3. Disk: `muj-web/workflows/config.yaml`, `agents/pisatel.md`, `scenarios/ukazka.yaml`, `.env.example`, `.gitignore`; `cfg/projects.yaml` má `name: muj-web, root: …`.
4. Zpět `#/` → dvě karty. Kolize jména/cesty → chyba API v dialogu (`role=alert`), nic nevzniklo.

### C3 Nový agent **[hotovo; dialog nemá popis ani model, ač API 0.8.0 umí — šablona zapíše `description: TODO`]**
Cíl: agent s vlastními instrukcemi. Stav: `demo`.
1. `#/p/demo/agenti` → jedna hlavička sekce: `h1 "Agenti"`, `button "Nový agent"` (sekundární), `button "Uložit"` a ⋯ `button "Akce pro pisatel"`. Vlevo `nav "Agenti"` se seznamem 200 px (položky 48 px, ikona, aktivní ring), vpravo `h2 "pisatel"` nad kartou editoru (`bg-surface`, radius 16, padding 24). První řádek karty je `radiogroup "Zobrazení"` a stav uložení; uvnitř karty není další název ani Uložit.
2. Nový agent → dialog „Nový agent“, `textbox "Jméno"` (autofocus); `Písatel` se při psaní upraví na `pisatel` → „„pisatel“ už existuje.“; `korektor` → Vytvořit.
3. → `#/p/demo/agenti/korektor`, `h2 "korektor"`, karta s `radiogroup "Zobrazení"` (Form | Markdown) a `testid save-status` „Uloženo ✓“; pole `textbox "popis"` (obsahuje `TODO`), `combobox "model"` = `chytry`, skilly a MCP servery jako seznamy checkboxů v `bg-nested`, limity ve třech sloupcích, `textbox "Instrukce (system prompt)"` (nejméně 12 řádků, patička „Podporuje Markdown“), „Používá: –“. Disk: `agents/korektor.md` s frontmatter `model: chytry`, `budget_usd: 0.02`.
4. Popis „Kontroluje pravopis“, instrukce „Opravuj jen chyby.“ → „Neuloženo“ → Ctrl+S → „Uloženo ✓ HH:MM“; disk: `description:` změněn, tělo nahrazeno, ostatní řádky beze změny.
5. Přepnout `radio "Markdown"` → `textbox "agents/korektor.md"` s celým souborem včetně `---`; nápověda „Upravuješ přímo soubor workflows/agents/korektor.md…“.
6. `button "Akce pro korektor"` → `menuitem "Smazat"` (červeně, poslední; před ním „Načíst znovu“ a „Přejmenovat“) → dialog „Smazat agenta „korektor“?“ → Smazat → zpět `#/p/demo/agenti`, v seznamu jen `pisatel`, soubor pryč. Varianta: smazat `pisatel` → v dialogu `role=alert` „agent 'pisatel' nejde smazat — používá ho: ukazka“, soubor zůstal.

Skill: `#/p/demo/skilly` → „Nový skill“ vytvoří `skills/pruzkum/SKILL.md`; seznam 200 px má položky 48 px a ikonu knihy. Vpravo je `h2 "pruzkum"` nad kartou, v ní Markdown editor a „Používají“. V agentovi zaškrtnout `pruzkum` v seznamu skillů → Uložit → vazba se zapíše do `agents/pisatel.md`; po návratu na skill odkaz „pisatel ↗“ vede zpět na agenta. Test `fidelity-agenti-config.spec.ts`.

### C4 Nový scénář se dvěma kroky a `output` **[hotovo; uložení = několik operací po sobě, ne dávka → nález 11 obcházeno]**
Cíl: vlastní scénář „napiš a zkontroluj“. Stav: `demo` s `pisatel`.
1. `#/p/demo` → klik `button "Nový scénář"` (primární v hlavičce sekce) → dialog: `textbox "Jméno"` (nápověda „Stane se i jménem souboru.“), `textbox "popis"`; `clanek` + „Napíše a ohodnotí článek“ → Vytvořit.
2. → `#/p/demo/scenare/clanek?krok=_hlavicka`; hlavička `h1 "clanek"` + popis; panel `complementary` s eyebrow „HLAVIČKA“, `textbox "popis"` = zadaný text, sekce „Vstupy“ (řádek `tema`, `checkbox "povinný"` nezaškrtnutý, `textbox "Výchozí hodnota tema"` = `káva`) a „Výstupy“ (`text`). Karty: `[data-step-card=""]` „1 vstup: tema · 1 výstup: text“, „Krok 1: ask napis“ (hodnota `pisatel: „Napiš dvě věty…“`), „Krok 2: output vystup“ („text“). Disk: `scenarios/clanek.yaml` s `description: Napíše a ohodnotí článek`.
3. Klik druhé `button "Vložit krok sem"` (mezi napis a vystup; navrženo `add-after-napis`) → `listbox "Typ nového kroku"`; napsat `j` → zbývá `option "jev levné rozhodnutí Jev"`; Enter → nová karta „Krok 2: jev jev_1“ s šedým „doplň v panelu“, panel „KROK 2“, `combobox "Typ kroku"` = jev, `aria-live` „Přidán krok jev_1.“, URL `?krok=jev_1`, `save-status` „Neuloženo“.
4. `combobox "State"` → `{{ steps.` → našeptávač `listbox` nabízí jen `steps.napis.text` (Enter doplní); klik `button "Přidat otázku"` (sekundární tlačítko s ikonou +) → řádek `q_1`: `textbox "Jméno"`, `combobox "Typ otázky q_1"`, `combobox "Otázka"`; přejmenovat na `ok`, otázka „Je text česky a bez chyb?“.
5. Karta „Krok 3: output vystup“ → panel, `combobox "text"` = `{{ steps.napis.text }}`; sbalené řádky „Podmínka vždy“, „Podrobnosti kroku vystup“ (`aria-expanded`).
6. `button "Uložit"` → „Uloženo ✓“, `POST …/scenarios/clanek/batch` 200. Disk: pořadí id `[napis, jev_1, vystup]`, blok `jev: {state, questions: {ok: {type: noul, instructions: …}}}`, komentáře šablony zachované. Karta `clanek` v přehledu: titul `clanek`, podtitul „Napíše a ohodnotí článek“, meta „3 kroky · pisatel“, bez názvu `.yaml`; řetězec ikon `aria-label "Typy kroků: ask, jev, output"`.

### C5 Validace s chybou a její oprava — v panelu i v YAML **[hotovo; Form validuje přes `render`, YAML → Form převádí neuložený text přes `render {text}`]**
Cíl: pochopit, co je špatně, a opravit to bez terminálu. Stav: `demo/ukazka`.
1. Editor `ukazka`, karta `napis` → `combobox "Prompt"` → `Téma: {{ steps.nic.text }}` → Uložit.
2. → do 500 ms `save-status` „Neuloženo · 1 chyba“, chip `button "1 chyba"` (klik skočí na krok), pod kartou `napis` i pod polem text `krok 'nic' neexistuje (dostupné: …)`, pole `aria-invalid=true`; disk beze změny (etag).
3. Oprava na `Téma: {{ inputs.tema }}` → Uložit → „Uloženo ✓“, chyby pryč; disk má nový prompt na jednom řádku (uvozovky kvůli `{{ }}`).
4. `radio "YAML"` → `textbox "scenarios/ukazka.yaml"`, nápověda se jménem souboru, Uložit disabled. Rozbít odsazení řádku `- id: napis` → do ≤ 1 s seznam chyb „řádek N · …“ (klik = kurzor na řádek), značka u řádku (`yaml-line-N`), Uložit disabled; klik na Form otevře dialog „Neuložené změny“.
5. Vrátit odsazení, změnit `agent: pisatel` na `agent: nikdo` → chyba „napis · agent 'nikdo' neexistuje…“, Form už povolen, Uložit stále disabled (podle §4.5). Opravit → chyby žádné, Uložit povolen → `PUT files/…` → „Uloženo ✓“; zpět do Form vybere krok pod kurzorem (`?krok=napis`).
6. Validní YAML s neuloženými změnami → Form převezme strom přes `POST …/render {text}` bez dialogu a bez zápisu. Dialog „Neuložené změny“ zůstává pro YAML se syntaktickou chybou.

### C6 Spuštění běhu s formulářem vstupů (dry-run, ostrý, živý) **[hotovo; po 202 čte GUI 15 s i stav `dry_run` (hack `?spusteno=1`, nález 15 — v 0.8.0 už není třeba)]**
Cíl: spustit scénář a vidět, že běží. Stav: `ukazka` + fixture `dlouhy.yaml` (krok `pomalu` se `sleep: 4`).
1. Editor `ukazka` → `button "Spustit"` → panel eyebrow „SPUSTIT BĚH“, `textbox "tema"` předvyplněný `káva`, nápověda „string · O čem psát“, `group "Režim běhu"` se dvěma kartami (radio uvnitř, klik kamkoli na kartu vybírá, vybraná má ring), `radio "Dry-run"` zaškrtnuté (nápověda „Jen plán… zdarma.“), vpravo `button "Zrušit"` (zavře panel jako ✕ a Esc) a `button "Spustit dry-run"`; limity jen u ostrého běhu (PN2).
2. Vymazat tema, `checkbox "povinný"` je ve fixture zapnutý (varianta scénáře bez default) → odeslat → pod polem „Povinný vstup.“, žádný POST.
3. `tema` = „nová káva“, Spustit dry-run → `POST /projects/demo/runs {dry_run: true}` 200 → `#/p/demo/behy/<run_id>`, `run-state` „jen plán (dry-run)“, text „Tohle je jen plán (dry-run) — běh neproběhl.“, vykreslený `plan.md`. Disk: `demo/runs/<run_id>/plan.md`, `inputs.json` (`{"tema":"nová káva"}`), bez `events.jsonl`.
4. Znovu Spustit, `radio "Ostrý běh"` → `dl "Limity běhu"`: „na běh 1,00 USD“, „čas běhu 1h“, „dnes utraceno 0 / 5,00 USD“ (spend ignoruje falešné běhy); s neuloženou změnou navíc varování s ikonou „Máš neuložené změny — běh použije verzi na disku.“ → `button "Spustit ostrý běh"` → 202 → `…?spusteno=1`.
5. Na `dlouhy`: hlavička „běží“, chip „falešný běh“, karta `[data-step-card="pomalu"]` `aria-label` „… — běží“ (pulz), čas tiká, `aria-live` „krok pomalu běží“, `checkbox "sledovat běh"`; po ≈ 4 s `role=status` „Běh skončil: úspěch“, karta „— úspěch“, checkbox zmizí, dotazování skončí (žádný další GET do 6 s).
6. Záložka `Běhy`: řádek `run-row` s ikonou + sr „běží“, „krok 1/2 · pomalu“ (stav se v řádku neopakuje), „falešný běh“, vpravo „1 běží · 0 ve frontě“; dva starty naráz → druhý „ve frontě (2.)“. Disk: `runs/<run_id>/{run.lock, events.jsonl, scenario/dlouhy.yaml, steps/01-pomalu/…, summary.md, report.html}`.

### C7 Čtení výsledku a ceny **[hotovo]**
Cíl: pochopit, co běh vyrobil a kolik stál. Stav: dokončený běh `ukazka` (C6).
1. Detail: nad titulem „← Běhy“, `h1` = odkaz `ukazka` + malé mono `run_id`, `run-state` „úspěch“, `run-duration` `\d+,\d s`, `run-cost` `/^(0|\d+,\d{4,}) USD$/` (čárka, USD za číslem), řádek „Vstupy tema = „nová káva““, `nav "Části běhu"` = Kroky · Souhrn · Report · Soubory.
2. Karty: „Krok 1: ask napis — úspěch“ s hodnotou `chytry → anthropic/claude-haiku-4.5` a vpravo čas + cena; „Krok 2: output vystup — úspěch“ s hodnotou. Klik na `napis` → panel „KROK 1 · napis“, `tablist` s `tab "Prompt"`, „Odpověď“, „Výstup“, „Volání“, „Soubory“; Volání: „pokus 1“, `alias → model`, „N + M tokenů“; Výstup = JSON `{"text": "Dvě věty."}`; `GET …/runs/<id>/steps/napis`.
3. `tab "Souhrn"` → Markdown se sekcí „Celkem“; `tab "Report"` → `iframe[sandbox]` (title „Report běhu“); `tab "Soubory"` → `nav "Soubory"` se stromem, klik `summary.md` → text, `?soubor=`.
4. Zpět `#/p/demo`: karta `ukazka` má čip posledního běhu (ikona úspěchu + „právě teď“) jako jediný čas na kartě (G7); sidebar „Dnes utraceno“ `spend-today` „0,00 USD“ (+ „/ limit“, je-li denní limit; fake ledger je zvlášť — v testu proto vždy 0; cíl s ostrým během netestovatelný).
5. Seznam běhů (bez sloupce run_id a bez útraty, G9; stav = ikona + text, run_id v `title` řádku): filtr `combobox "scénář:"` = ukazka → jen její řádky (`?scenario=ukazka&limit=50`), `combobox "stav:"` = úspěch; sloupce trvání/cena mono; „Načíst další“ jen při 50+.

### C8 Chybný běh (fail) **[hotovo]**
Cíl: poznat, kde a proč běh skončil. Stav: fixture `chyba.yaml`: `napis → stop (fail: "Zastaveno naschvál") → vystup`.
1. Spustit ostrý běh → hlavička `run-state` „chyba: fail v stop“ (ikona `error` + text), Souhrn má nadpis „— chyba“ a blok **Chyba**.
2. Karty: `napis` „— úspěch“, `stop` „— chyba“ s hodnotou = hláška, `vystup` „— nedošlo“ (čárkovaný obrys, `aria-label` končí „— nedošlo“). Panel `stop`: hláška s třídou `fail`.
3. Přeskočený krok (varianta s `when: false` a `default`) → karta „přeskočeno: when … → false“ + „použit default“; `on_error: continue` → řádek „Varování: krok selhal, běh pokračoval (on_error: continue).“
4. Seznam běhů: poznámka „fail v stop · falešný běh“; karta scénáře čip „chyba“. Disk: `events.jsonl` má `run_finished status: failed`, `summary.md` obsahuje „Zastaveno naschvál“.

### C9 Konflikt souboru (změna na disku během editace) **[hotovo]**
Cíl: neztratit ani svou, ani cizí změnu. Stav: editor `ukazka`, karta `napis` vybraná.
1. Změnit Prompt (Neuloženo). Test přes `fs.appendFile` přidá do `ukazka.yaml` komentář `# ručně`.
2. Do 5 s (nebo po `window.dispatchEvent(new Event("focus"))`) → `conflict-bar` „Soubor se na disku změnil.“ s tlačítky „Zobrazit rozdíl“, „Načíst z disku a zahodit moje změny“ (nebezpečné, červené) a „Ponechat moje“ pod textem; Uložit disabled.
3. „Zobrazit rozdíl“ → dialog „Rozdíl proti disku“, poznámka „− je verze, ze které vycházíš, + …“, řádek `+ # ručně` zeleně → Zavřít.
4. „Ponechat moje“ → pruh zmizí, Uložit → dialog „Přepsat verzi na disku?“ → „Přepsat verzi na disku“ → `PATCH` s aktuálním etag → „Uloženo ✓“; disk má `# ručně` i nový prompt.
5. Varianta bez lokálních změn: úprava na disku → tiché znovunačtení, `save-status` „Načteno z disku (HH:MM)“, karta ukazuje nový text. Varianta po obnovení stránky s rozpracovaným draftem ke staré verzi → pruh „Rozpracované změny v prohlížeči patří ke starší verzi souboru.“

### C10 Přesun a smazání kroku s ochranou odkazů **[hotovo; smazání čteného kroku + úprava čtenářů jde dnes jako dvě operace, dávka 0.8.0 se nepoužívá → 422, pokud druhá operace nestihne]**
Cíl: přeskládat scénář a nerozbít odkazy. Stav: `clanek` z C4 (`napis, jev_1, vystup`).
1. Fokus karty `jev_1` (klik), `Alt+↑` → `aria-label` „Krok 1: jev jev_1“, `napis` je „Krok 2“; menu ⋯ „Další akce“ v hlavičce → `menuitem "Vrátit zpět"` (zkratka Ctrl+Z vpravo, nebo Ctrl+Z na klávesnici) vrátí; menu `"Akce pro jev_1"` má `menuitem` „Posunout nahoru“ (Alt+↑ vpravo), „Posunout dolů“ (Alt+↓), „Vyjmout“ (Ctrl+X), „Vložit krok nad“, „Vložit krok pod“, červené „Smazat“ (Del). Na dotykovém zařízení jsou zkratky skryté.
2. `Ctrl+X` na `jev_1` → `aria-live` „Krok jev_1 vyjmut — vlož ho tlačítkem + na novém místě.“, karta 50 % s „— vyjmuto“, všechna (+) trvale vidět; klik + nad `napis` → první `option` „Vložit „jev_1“ sem“ → Enter → „Krok jev_1 vložen.“, pořadí `[jev_1, napis, vystup]`; validace u karty `jev_1` hlásí `steps.napis` níže (po Uložit 422 „krok 'napis' … níže/neexistuje“) → Ctrl+Z.
3. Delete na `napis` (čte ho `jev_1` i `vystup`) → dialog „Smazat krok „napis“?“ s textem „Krok „napis“ čtou jev_1, vystup. Uložení projde, jen když jejich odkazy upravíš nebo je smažeš taky.“ → „Smazat i tak“ → `aria-live` „Krok napis smazán. Vrátit zpět: Ctrl+Z.“; Uložit → 422 s hláškou u `vystup`, disk beze změny. Cíl (dávka): úprava čtenářů + smazání v jedné dávce, zapíše se vše nebo nic.
4. Delete na `jev_1` (nikdo nečte) → hned pryč, bez dialogu; stejné mazání spustí ⋯ → „Smazat“ nebo koš v hlavičce panelu. Uložit → `DELETE …/steps/1` → disk má `[napis, vystup]`. Smazání kontejneru s kroky → dialog „Smaže i N kroků uvnitř.“ Karta `output` nemá Posunout/Vyjmout/Vložit pod; u karet není samostatný koš.

### C11 `parallel` a `switch` **[hotovo — nová větev musí začít novým krokem (nález 13); přejmenování/mazání větví jen v YAML]**
Cíl: „vedle sebe = zároveň, pod sebou = jedna z možností“. Stav: `clanek`.
1. + za `napis` → `option "parallel větve zároveň"` → karta (zaoblený obdélník) „Krok 2: parallel parallel_1“, panel „Větve: . Kroky do nich přidáš tlačítkem + v kartě.“; `button "+ větev"` → dialog „větev“ `textbox "Jméno"` (`^[a-z0-9_]+$`) → `kratka` → sekce `section "kratka"` s `h4 kratka` a `button "Přidat krok na konec"`; tak i `dlouha`. Uložit bez kroku ve větvi → `save-status` „Nová větev v kroku parallel_1 musí začínat novým krokem.“ (lokálně, bez POST).
2. V každé větvi + → `ask` → agent `pisatel`, prompt → Uložit → jeden `POST …/steps` s celým krokem `{id, parallel: {kratka: [...], dlouha: [...]}}`; disk odpovídá; karta má meta „kratka ∥ dlouha · 2 větve, běží zároveň“; TypePicker uvnitř větve nenabízí `output`.
3. `button "Sbalit parallel_1"` (`aria-expanded`) → vnitřek zmizí, text „2 kroky“; „Rozbalit parallel_1“ vrátí.
4. + → `switch` → panel `combobox "Hodnota"` = `steps.jev_1.ok`, sekce `"jinak (default)"` je vidět vždy; `button "+ případ"` → dialog „případ“ (`pattern [^/]`) → `= true`; přidat kroky; Uložit → disk `switch: {value, cases: {"true": [...]}, default: [...]}`; bez `default` → text „„jinak“ je povinné“ v panelu a 422 z API.
5. V běhu (fixture `vetve.yaml` + fake): nevybraný případ ztlumený s důvodem, karty ve větvích se stavem; `call` se rozbalí v kartě (`section "<cíl>"`).

### C12 Přejmenování kroku s přepisem odkazů (dávka) **[obcházeno — GUI čtený krok přejmenovat nepustí a nabídne YAML; API 0.8.0 `batch rename_step` existuje]**
Cíl: přejmenovat `napis` na `text_clanku` a nic nerozbít. Stav: `ukazka` (`vystup` čte `steps.napis.text`).
1. Karta `napis` → panel → `button "Podrobnosti kroku"` (`aria-expanded=true`) → `textbox "id"`, čipy „Čte z: nic“, „Výstup čtou: vystup“ (klik na čip vybere `vystup`), odkaz „Otevřít v YAML“ (`?rezim=yaml&krok=napis`).
2. Dnes: přepsat id, Tab → pod polem „Krok čtou vystup — přejmenování by jim rozbilo odkazy a API ho po jednom neuloží.“ + odkaz „Přejmenovat i s odkazy v YAML režimu“; id se nezmění.
3. Cíl: Tab → karta „Krok 1: ask text_clanku“, karta `vystup` bez chyby, `?krok=text_clanku`; Uložit → `POST …/scenarios/ukazka/batch` s `rename_step` (`rename_refs: true`) → disk: `- id: text_clanku` a v `vystup` `{{ steps.text_clanku.text }}`, komentáře zachované; `aria-live` „Uloženo ✓“. Id se upraví už při psaní (`Výstup` → `vystup`, `1` → prázdné); prázdné nebo existující `vystup` → „Malá písmena, číslice a _, začíná písmenem.“ / „„vystup“ už existuje.“ a bez změny.

### C13 Přidání existujícího projektu **[hotovo]**
Stav: složka `$TMP/cizi` vytvořená `agencast new project` **bez** registru (`AGENCAST_CONFIG_DIR` jiný při vytvoření), pak smazaná z registru.
1. `#/` → „Přidat projekt“ → dialog s přepínačem „Založit nový“ / „Přidat existující“ (nebo druhé tlačítko) → `textbox "Cesta"` = `$TMP/cizi`, jméno předvyplněné `cizi` → Vytvořit/Přidat.
2. → karta `cizi` s počty; `cfg/projects.yaml` má druhou položku; na disku `cizi/` beze změny (žádné nové soubory). Cesta bez `workflows/config.yaml` → chyba v dialogu `role=alert` (text API), nic nezapsáno. Stejná cesta podruhé → chyba kolize s nápovědou `--name`.

### C14 Odebrání projektu z registru **[hotovo]**
1. `#/` → `button "Akce pro cizi"` → `menuitem "Odebrat z registru"` → dialog „Odebrat „cizi“ z registru?“ s větou, že soubory zůstanou → potvrdit.
2. → karta zmizí bez reloadu, registr bez položky, `$TMP/cizi/workflows/` netknuté; přímý `#/p/cizi` → `role=alert` s 404 textem + odkaz „Projekty“. Odebrání nedostupného projektu funguje stejně (karta „nedostupný“ má menu).

### C15 Klávesnicová cesta bez myši **[hotovo; ⋯ je přístupné přes Tab]**
Cíl: celý C4 jen klávesami. Stav: `demo`.
1. `#/` Tab → odkaz `demo` (Enter) → `h1 "Scénáře"` → Tab přes `nav "Části projektu"` v sidebaru → „Nový scénář“ Enter → dialog (fokus v „Jméno“, Tab uvnitř cyklí, Esc zavře) → jméno, Enter = Vytvořit.
2. V editoru: Tab na `[data-step-card=""]`, `↓` → `napis` (`document.activeElement` = karta), Enter → panel (`?krok=napis`), fokus v panelu; Esc → panel pryč, fokus zpět na kartě `napis`.
3. Tab z karty → `"Akce pro napis"` → (+) `"Vložit krok sem"` (fokus ho zviditelní); Enter na + → `listbox` má fokus, psaní filtruje (`aria-live` „filtr: j“), Enter vybere, Esc vrátí fokus na +. Mazání je v ⋯ nebo na klávese Delete.
4. `Delete` na kartě = smazání s dialogem (fokus na první tlačítko), `Alt+↓` posun, `Ctrl+X` vyjmout, `Ctrl+Z` zpět, `Ctrl+S` uložit (ne uvnitř textarea u Ctrl+Z); menu ⋯: Enter otevře, `↓` cyklí `menuitem`, Esc vrátí fokus na tlačítko.
5. Kontrola: každý fokusovaný prvek má viditelný ring (`focus-visible`), pořadí Tab = pořadí dokumentu, `aria-live` texty přítomné v DOM (Playwright `getByRole("status")` / `[aria-live]`).

### C16 Mobilní šířka 375 px (panel jako list) **[hotovo — panel je list dole přes sloupec pod 1280 px; agenti a skilly pod 1100 px jako karty s editorem ve spodním sheetu; tabulka běhů ve vodorovném posuvu; test `mobil.spec.ts`]**
Viewport 375×667 (iPhone SE emulace, `pointer: coarse`).
1. `#/p/demo/scenare/ukazka` → karty v jednom sloupci, `document.documentElement.scrollWidth <= 375`; hlavička editoru se zalomí (Form/YAML, stav, Uložit vidět bez horizontálního scrollu).
2. Klik na kartu → `complementary` má `boundingBox` u spodní hrany (`y + height ≈ 667 - 16`), výška ≤ 70 % (≤ 467 px), překrývá karty (list), stín; Esc / `button "Zavřít"` ho schová.
3. `pointer: coarse`: mazání kroku je v ⋯ a v panelu; cíl tlačítek ≥ 44 px (změřit `+` 28 px → **nesplní**, zaznamenat jako nález, ne selhání testu).
4. `#/p/demo/agenti` a `#/p/demo/behy` → bez přetečení šířky: `nav "Agenti"` nad `h2` editoru, tabulka běhů ve scroll kontejneru (`region "Běhy"`).
5. Spuštění z mobilu: panel „SPUSTIT BĚH“ jako list, `textbox "tema"` font ≥ 16 px (jinak iOS zoom), tlačítko „Spustit dry-run“ na plnou šířku.
6. Tablet (768 a 1024 px, ruční kontrola vlny C): pod 1024 px horní lišta místo sidebaru; editor scénáře má panel jako list přes sloupec (od 1024 px odsazený od sidebaru) se zavíracím křížkem, vedle sloupce až od 1280 px; řádek aliasu v Configu se zalomí bez přetečení.

### C17 Alias modelu v Configu **[hotovo — ladění 2026-09-26, 0.10.3]**

1. Config → karta radius 16 má jako první cestu projektu (mono 13), přepínač Form | YAML a stav uložení; Připojení | Jev model jsou vedle sebe. „+ Přidat alias“ přidá vnořenou kartu `model-1`; pole Alias bere jméno jako u agenta (malá písmena, číslice, pomlčka — `gpt-image`), neplatné se při opuštění pole vrátí a pravidlo je v `title` pole i pod seznamem.
2. Id modelu, Uložit → `PUT …/config` (merge patch); nový alias se do `config.yaml` zapíše stejným řádkovým stylem `{ id: … }` jako ostatní, přejmenování maže starý klíč první.
3. Pod každou kartou aliasu je meta „používá pisatel“ nebo „nepoužívá se“; používaný alias má „Smazat alias“ neaktivní s důvodem v `title`. Úložiště | Webhook a callback a Limity | Proměnné jsou ve dvojicích sloupců; proměnné tvoří řádky 40 px s barevným stavem a MCP server má vnořenou kartu s čipem „Pouze čtení“.
4. Po načtení je alias v nabídce modelu agenta. Test: `editor.spec.ts` „C17“, `fidelity-agenti-config.spec.ts`; hlavička Configu má `h1 "Config"`, jedno Uložit a ⋯ s „Načíst znovu“. Cesta projektu a jediný přepínač Form | YAML jsou v kartě.

### C18 Vložení proměnné z nabídky

1. `ukazka` → krok `napis` → Prompt; klik doprostřed textu → „Vložit proměnnou“ → `inputs.tema`. Proměnná se vloží na místo kurzoru jako `{{ inputs.tema }}` a fokus i kurzor zůstanou v poli.
2. Uložit → „Uloženo ✓“; `project.read("scenarios/ukazka.yaml")` obsahuje vloženou šablonu.
3. Klávesami: Tab z pole na tlačítko → Enter → šipka dolů → Enter; stejný výsledek. Test: `editor.spec.ts` „C18“.

### C19 Přejmenování scénáře a agenta

1. V editoru scénáře otevři menu ⋯ „Další akce“ → „Přejmenovat“; v sekci Agenti menu ⋯ v hlavičce
   (`button "Akce pro <agent>"`) → „Přejmenovat“. Dialog předvyplní
   současný slug, odmítne neplatný či obsazený název; při neuloženém draftu
   se nejdřív nabídne jeho uložení nebo zahození.
2. Potvrzení pošle `POST …/scenarios/<staré>/rename` nebo
   `POST …/agents/<staré>/rename` s `{etag, name}`. Scénář přepíše i
   `call.scenario`; agent přepíše odkazy v `ask`/`task` a seznamech
   `agents` v `mcp.yaml`. Komentáře zůstanou.
3. Po úspěchu zmizí draft staré cesty, seznam se obnoví a editor přejde na
   nové jméno. Když se změnilo více souborů, zobrazí se jejich cesty.
   `runs/` se nemění; starší běhy dál ukazují původní jméno.
   E2E: `editor.spec.ts` „C19“ ověří přejmenování `ukazka` → `uvod`,
   odkaz z dalšího scénáře přes `call`, obsah souborů a novou URL.

### C20 Shell: sidebar, hlavičky a lišta pod 1024 px (redesign V3, 0.16.0)

1. `#/` → sidebar jen se značkou (`link "agencast"`), bez „Dnes utraceno“ a bez „server dostupný“;
   „Přidat projekt“ je jediné tlačítko (v hlavičce), dokud seznam není prázdný.
2. Karta `demo` → `nav "Části projektu"` = Scénáře · Agenti · Běhy · Skilly · Config, aktivní
   `aria-current="page"` (právě jedna); dole „Dnes utraceno“ a `spend-today` „0,00 USD“ (s limitem
   „0,00 / 5,00 USD“ a pruhem). Klik na Běhy → `#/p/demo/behy`, `h1 "Běhy"`. Editor scénáře zvýrazní
   Scénáře, detail běhu Běhy. „← Projekty“ vede zpět.
3. Editor `ukazka`: `h1 "ukazka"`, tlačítka „Spustit“ a „Uložit“ (disabled bez změn), žádné viditelné
   „Přejmenovat“; `button "Další akce"` → `menuitem` Vrátit zpět (Ctrl+Z vpravo) · Kopírovat příkaz spuštění ·
   Běhy tohoto scénáře · Přejmenovat · Smazat; „Běhy tohoto scénáře“ → `#/p/demo/behy?scenar=ukazka`
   s předvybraným filtrem.
4. Viewport 900 px: lišta nahoře obsahuje značku a projekt; FAB „Navigace“ 56 px vpravo dole otevře
   nabídku s projekty, položkami 48 px a dnešní útratou. Esc, klik mimo a výběr položky ji zavřou; `scrollWidth ≤ 900`.
5. Každá sekce projektu má jedinou hlavičku (`h1` = název sekce) a v ⋯ „Další akce“ jako první
   „Načíst znovu“ (dřív ikona). Scénáře: „+ Nový scénář“; Agenti / Skilly: „+ Nový agent“ / „+ Nový
   skill“ + Uložit + ⋯ „Akce pro <jméno>“; Config: cesta projektu jako popis + Uložit. Druhé Uložit ani
   druhý přepínač režimu na stránce není (G1–G3).
   E2E: `redesign-shell.spec.ts` R1–R3, `redesign-panely.spec.ts` PN3–PN4, `redesign-integrace.spec.ts` IC1–IC2, `projekty.spec.ts` N2
   (Načíst znovu přes ⋯), vitest `editor.test.tsx` (jediné `h1 "Agenti"`).

## Negativní a okrajové stavy

- **N1 Server neodpovídá** — Stav: `page.route("**/projects*", r => r.abort())` nebo zastavený `serve`. Očekávání: `server-bar` `role=alert` dole v sidebaru (pod 1024 px v horní liště) „Server agencast neodpovídá (127.0.0.1:8787), zkouším znovu…“, obsah zůstává (poslední data), žádná chybová hláška navíc; po obnovení routy do 5 s pruh zmizí sám. V editoru s rozpracovanou změnou zůstává „Neuloženo“ a draft v `localStorage` (`agencast.draft.*`). **[hotovo]**
- **N2 Špatný token** — viz C1 krok 2; navíc: platný token → server restartován s jiným `AGENCAST_TOKEN` → první 401 vrátí obrazovku tokenu s alertem, token v localStorage se přepíše až novým zadáním. **[hotovo]**
- **N3 Nedostupný projekt** — Stav: registr obsahuje `stary` s `root` bez `workflows/config.yaml`. `#/` → karta „nedostupný“ (čárkovaný rámeček bez plochy) s důvodem „chybí …/workflows/config.yaml“ z `reason`, menu jen Otevřít/Kopírovat cestu, žádný GET detailu; `#/p/stary` → `role=alert` s textem 404 API. Neznámé jméno `#/p/neni` → totéž; `#/x` → v shellu se značkou hlavička `h1 "Tahle adresa v GUI neexistuje."` + odkaz „Projekty“ (vzhled sekundárního tlačítka). **[hotovo]**
- **N4 Rozbitý config** — Stav: v `demo/workflows/config.yaml` duplicitní klíč `runs_dir` (nebo `limits.run_budget_usd: "x"`). `#/p/demo` → `role=alert` „config.yaml projektu neprošel kontrolou: …“ + seznam + odkaz „Otevřít Config“; záložka Config rovnou v YAML (Form zakázán s „config.yaml neprošel kontrolou — oprav ho v YAML“), chyba „řádek 20 · …“ se značkou u syntaxe; chyba schématu jen s textem (nález 23, **[obcházeno]**); záložka Běhy funguje; oprava v YAML + Uložit → alert zmizí, Scénáře se načtou. **[hotovo]**
- **N5 Přerušený běh** — (a) CLI `agencast --project $TMP/demo run dlouhy --fake $TMP/fake.yaml` a `kill -9` uprostřed `sleep` → detail „přerušen“ (ikona `warning`), věta „Běh skončil bez záznamu o konci (proces spadl nebo byl zabit); GUI se na něj už nedotazuje.“, karta `pomalu` „— přerušen“ (nepulzuje), žádný další GET do 6 s; seznam: sloupec stavu „přerušen“, poznámka jen „falešný běh“ (stav se v poznámce neopakuje). (b) Běh spuštěný ze `serve`, `serve` zabit a znovu spuštěn → API ho dopíše jako `failed (internal v None)`, GUI ukáže „chyba: internal v None“ (nálezy 21/22, **[obcházeno]** — očekávaný text ohlásit jako známou vadu). **[hotovo]**
- **N6 Odchod s neuloženými změnami** — `beforeunload` dialog při reloadu (Playwright `page.on("dialog")`), po přijetí je draft stále v localStorage a po návratu „Neuloženo“ + text (C5 var.). Navigace hash odkazem (zpět na Scénáře) **neptá se** — návrh §4.4 to chce; **[obcházeno]**.

## Co testem nezachytíme
- Vzhled podle Buzz: žebřík ploch, ring vybrané karty, pulz, hover stavy, `prefers-reduced-motion` — jen snímky (screenshot diff) s tolerancí, ne asserty.
- Výkon (LCP, velikost bundle 96 kB gz, 20 karet × N+1 u projektů — nález 24) a chování při stovkách běhů (kurzor, nález 25).
- Skutečné modely, ceny a `spend` (fake ledger je oddělený → „dnes 0 USD“ vždy), callbacky, úložiště R2, MCP servery.
- Iframe v Skynet Soul (`postMessage` s cestou), CORS s `vite dev`, skutečné čtečky obrazovky (jen struktura ARIA), systémová schránka („Kopírovat“ jen s `clipboard-read` právy).
- Časové popisky („před 3 min“, „včera 14:03“) a `title` s UTC — testovat regexem, ne hodnotou.

## Otázky designéra a rozhodnutí koordinátora (2026-09-26)

1. *Testy proti sestavenému GUI ze `serve`, nebo proti `vite dev` + `--cors`?* — **Proti sestavenému GUI ze `serve`** (jedna adresa, stejná cesta jako v provozu). `npm run e2e` nejdřív sestaví `ui/`.
2. *Jeden `serve --fake` na celý běh testů, nebo na worker?* — **Jeden `serve` na Playwright worker** s vlastním portem a vlastním `AGENCAST_CONFIG_DIR`; každý test si založí vlastní projekt (jménem podle testu), aby se zápisy nekřížily. Varianty chování falešného poskytovatele přes různá id kroků v jednom skriptu.
3. *Formulář nového projektu: jméno + cesta, nebo cesta odvozená?* — **Jméno + cesta, cesta předvyplněná z `projects_root` (`<projects_root>/<jméno>`) a editovatelná.** Přepínač „Založit nový“ / „Přidat existující“ v jednom dialogu.
4. *Přejmenování s odkazy: mlčky, nebo se ptát?* — **Ptát se jednou: „Přepsat odkazy v N krocích?“** s výčtem kroků; potvrzení odešle dávku `rename_step` s `rename_refs: true`. Bez čtenářů bez dialogu.

## Dialogy (0.16.2)
Dialog má hlavičku s titulem a křížkem „Zavřít“ (informační dialog bez akcí jen „Zavřít“ dole) a patičku
„Zrušit“, pak akce. Fokus po otevření je na první akci (nebo na poli s `data-autofocus`), Tab cyklí uvnitř
(z poslední akce na křížek), Esc a klik mimo zavřou. Na telefonu je dialog spodní sheet s kulatými horními rohy,
stínem a viditelným pruhem stránky nad ním. Test: `redesign-prvky.spec.ts` P3, `fidelity.spec.ts`.
