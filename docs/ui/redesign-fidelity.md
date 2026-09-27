# Věrnost návrhu V3 — rozdíly mezi nasazeným GUI (0.16.0) a `.pen` a co se má změnit

Koordinátor porovnal screenshoty nasazeného GUI (1440 px) s rámečky návrhu
`docs/ui/design/agencast-design.pen` (exporty v `docs/ui/design/ref/png/`, přesné hodnoty
komponent v `docs/ui/design/ref/component-specs.md`, HTML s Tailwind třídami v `ref/html/`).
Struktura (sidebar, karty, sloupec kroků, panel) sedí, ale **měřítko, tvary a hustota ne**:
GUI je o třídu menší, plošší a tmavší než návrh. Tento dokument je závazné zadání pro vlnu E.

Pravidla zjednodušení z `redesign-plan.md` §2 platí dál (jedna hlavička, jedno Uložit, ⋯ menu,
žádné duplicity, bez štítků „dostupný“ / `skills[]` apod.). Kde návrh ukazuje něco, co §2 ruší,
zůstává §2. Všechno ostatní má vypadat **jako v návrhu**, včetně velikostí v px.

## 0. Tokeny — doplnit do `ui/src/index.css` (vlastní E2, ostatní používají)

| token | hodnota | použití v návrhu |
|---|---|---|
| `--color-control` | `#31455F` | výplň sekundárního tlačítka a ikonového tlačítka (`V3 / Button / secondary`, `V3 / IconButton`) |
| `--color-control-hover` | `#3B5170` | hover sekundárního tlačítka |
| `--color-surface-active` | `#1B2A3D` | aktivní položka sidebaru a seznamu, vybraná karta kroku, hover řádku |
| `--color-track` | `#25374A` | dráha progress baru |
| `--radius-button` | `10px` | tlačítka |

## 1. Měřítko a typografie (všude)

- **H1 stránky 32 px semibold** (`letter-spacing -0.5`), pod ním popis 14 px `fg-secondary`, pak meta řádek (mono 13 `fg-muted`, např. cesta registru). Blok hlavičky má horní odsazení 32 px a mezeru 24 px pod sebou. Dnes je H1 18 px.
- Titul editoru scénáře a detailu běhu: **mono 32 px semibold**. Titul panelu 20 px semibold; eyebrow 11 px mono verzálky `letter-spacing 0.08em` `fg-muted`.
- Nadpis sekce ve formuláři 16 px semibold `fg`; štítek pole 13 px **medium** `fg-secondary` (ne bold); nápověda 12 px `fg-muted`.
- Meta údaje (počty, časy, ceny, id) jsou **mono 12 px** `fg-muted` (návrh používá JetBrains Mono na všechna čísla a technické texty). Dnes je meta v Interu 13 px.
- Obsah stránky: padding 32 px, max. šířka 1176 px (1440 − 232 − 2×16), mezera mřížky karet 20 px.

## 2. Tlačítka a ovládací prvky (`ui.tsx`, `form.tsx`)

- Primární: výška **40 px**, padding 0 18, radius **10**, `bg-accent text-ink` 14 px semibold, ikona 16 px. Sekundární: totéž s `bg-control text-fg` (ne průhledné s ringem). Nebezpečná: `bg-control` s `text-error` (v návrhu „Smazat“ = `#3A2530`-ish výplň s růžovým textem; použij `bg-error/15 text-error`). Ghost (jen text) jen v menu.
- Ikonové tlačítko: **40 × 40** (v hlavičce stránky 48 × 48), radius 10, `bg-control`, ikona 18–20 px `fg`. Ne průhledné.
- Pole: výška **44 px**, radius 8, `bg-nested`, ring 1 `line`, text 14 px, placeholder `fg-muted`; fokus ring 2 `accent`; mono varianta 13 px. Textarea padding 12, radius 8. Select má chevron 16 px `fg-muted` vpravo.
- Segmentový přepínač (Form | YAML): pilulka `bg-nested` padding 4, segment výška 32, **aktivní segment `bg-accent text-ink`** (v návrhu světlý), neaktivní `fg-secondary`.
- Záložky (Kroky · Souhrn …): výška 40, text 14 medium, aktivní `fg` s podtržením 2 px `accent`, neaktivní `fg-secondary`.
- Stavový čip: pilulka `bg-nested`, padding 6 12, ikona 14 px, **text mono 12 v barvě stavu** (zelená „před 12 min“, modrá „běží“, růžová „2 chyby“, neutrální „bez běhů“). Dnes je text šedý.
- Menu ⋯: `bg-surface` radius 12, položky 40 px, 14 px; nebezpečná červeně.
- Akordeon (Podmínka / Spolehlivost / Podrobnosti): řádek 48 px, titul 15 medium, hodnota mono 12 `fg-muted`, oddělovač `line` mezi řádky.
- Blok kódu („CodeViewer“ v návrhu): hlavička 40 px (ikona `{}` + název souboru mono 13 + čip „Pouze čtení“ / „YAML“), tělo `bg-nested` s číslováním řádků (mono 12 `fg-muted`), radius 12, patička s „Kopírovat“ (sekundární tlačítko). Použít pro Výstup/Prompt/Odpověď v běhu, pro YAML editor (číslování už je) a pro soubory.

## 3. Sidebar (`Shell.tsx`)

- Šířka 232, padding 28 20, `bg-sidebar`, pravý hairline. Značka: ikona `Layers2` 25 px v `text-type` + „agencast“ 22 px semibold `letter-spacing -0.7`. Mezera pod značkou 22.
- „← Projekty“ jako řádek 44 px (ikona 16 + text 14 medium `fg-secondary`), pak oddělovač 1 px `line`, pak jméno projektu (14 semibold) a navigace: položky **44 px**, radius 8, gap 6, padding 0 14, ikona 16 `fg-muted`, text 14 medium `fg-secondary`; aktivní `bg-surface-active text-fg` a ikona `fg`.
- Dole: „Dnes utraceno“ 12 `fg-muted`, částka mono 12 medium `fg` (`1,20 / 5,00 USD`), progress 3 px, dráha `track`, výplň `success` (přes limit `error`). Hlášku výpadku serveru zachovat.

## 4. Projekty (`Projects.tsx`)

- Hlavička: H1 „Projekty“ 32, popis „Spravuj projekty, scénáře a běhy agentů na jednom místě.“ 14 `fg-secondary`, meta cesta registru mono 13. Vpravo ikonové tlačítko Načíst znovu 48 × 48 `bg-control` a „+ Přidat projekt“ primární 40 px.
- Karta projektu: `bg-surface`, radius **16**, padding **24**, min. výška 260. Obsah: řádek s menu ⋯ vpravo (bez štítku „dostupný“, §2 G6; nedostupný má čip „nedostupný“ + důvod), název **20 px semibold**, cesta mono 12 `fg-muted`, **čipy počtů** („8 scénářů“, „4 agenti“ jako pilulky `bg-nested` mono 12 `fg-secondary`), oddělovač 1 px `line`, spodní řádek: stavový čip posledního běhu + útrata mono 12 („dnes 1,20 USD“, vždy dvě desetinná místa, ne „0 USD“).

## 5. Přehled scénářů (`Scenarios.tsx`, `TypeIcon.tsx`)

- Toolbar nad mřížkou je v `PageHeader` (už je): „+ Nový scénář“ primární 40 px.
- Karta scénáře: `bg-surface`, radius 16, padding 24, min. výška 290. Nahoře **řetěz ikon typů jako prosté ikony 16 px v `text-type`, gap 12, bez koleček a bez šipek** (max. 5, pak „+N“ mono 12), vpravo ⋯. Název **20 px semibold** (jméno scénáře), popis 14 `fg-secondary` (2 řádky, výpustka), meta **mono 12 `fg-muted`**: „7 kroků · 3 agenti“ + čip „volatelný“. Spodní řádek: stavový čip posledního běhu (nebo čip chyb) vlevo, vpravo odkaz „Otevřít ↗“ 14 medium `fg`.
- Dnes se řetěz ikon s šipkami zalamuje na dva řádky a tlačí čip stavu; to zmizí.

## 6. Editor scénáře (`Scenario.tsx`, `StepCards.tsx`, `TypePicker.tsx`)

- Hlavička: „← Scénáře“ (14 `fg-secondary`), titul mono 32, popis 14 `fg-secondary`; vpravo **„Spustit“ primární** (ikona Play) a **„Uložit“ sekundární** (ikona Save, `bg-control`; disabled = 50 % opacity), pak ⋯ 40 × 40 `bg-control`. Druhý řádek: segmentový přepínač + SaveNote (čip „Uloženo ✓ 14:02“ v `success` mono 12; „Neuloženo“ `warning`).
- Sloupec kroků šířka **640**, panel **420**, mezera 32. Konektor: šipka 16 px `fg-muted`, výška 40.
- **Karta kroku** (pilulka, radius 999, `bg-surface`, výška **96**, padding 20 24, gap 16): vlevo pořadové číslo mono 12 `fg-muted` (mimo kolečko), pak **kolečko 40 px `bg-nested` s ikonou typu 18 px `text-type`**, pak texty: řádek typu **mono 12 `text-type` malými písmeny** „ask · navrh“, titul 16 semibold `fg` (hodnota kroku), třetí řádek mono 12 `fg-muted` (u `ask`/`task` agent + úryvek promptu, u `image` model · poměr, u ostatních podmínka „když …“ nebo nic); vpravo ⋯ (ghost). Podmínka „když …“ se zobrazí jako třetí řádek, ne vpravo.
- Vybraná karta: `bg-surface-active` + ring 1 px `accent`. Hover `bg-surface-hover`.
- Hlavičková karta: stejná pilulka, kolečko s ikonou `AlignJustify`, eyebrow „HLAVIČKA“ mono 12 `text-type`, titul 16.
- Kontejnery (parallel/switch/call): obal `bg-surface` radius 16 padding 16; hlavní karta jako běžná (titul 16, mono řádek „3 · parallel · varianty“), šipka sbalit vpravo 20 px; větve `bg-nested` radius 12 padding 12 se štítkem mono 12 `fg-muted`; karty uvnitř výška 72.
- Tlačítka pod sloupcem: „+ Přidat krok“ sekundární 40 px, „+ output“ sekundární 40 px, vedle sebe na střed. (+) na konektoru: 28 px `bg-control` na hover.
- TypePicker: `bg-surface` radius 12, položky 40 px: klíčové slovo mono 13 `fg` + popis 13 `fg-muted`.

## 7. Panel (`StepPanel.tsx`, `RunPanel.tsx`, `RunStepPanel.tsx`)

- `bg-surface` radius 16, **padding 24**, gap polí 20. Eyebrow mono 11 `fg-muted` verzálky, titul 20 semibold, zavřít = ikonové tlačítko 32 ghost.
- Pole podle §2 (výška 44, štítky 13 medium). Select „Typ kroku“ ukazuje „ask · jedno volání agenta“ (mono klíč + popis).
- Panel spuštění: eyebrow „SPUSTIT BĚH“, karty režimu 72 px `bg-nested` radius 12, vybraná ring 1 `accent` a radio vyplněné; „Limity“ jako řádky s oddělovači (štítek 13 `fg-secondary` vlevo, hodnota mono 13 vpravo); varování v `bg-warning/10` s ikonou; tlačítka vpravo: „Zrušit“ sekundární + „Spustit dry-run“ primární.
- Panel kroku v běhu: řádek stavu = čip stavu + mono 12 „12,4 s · 0,0210 USD“; záložky podtržené; obsah = blok kódu s hlavičkou (viz §2) a řádek souboru („files/obrazek.png“ mono + ikona ↗ v `bg-nested` řádku 44 px).

## 8. Běhy (`Runs.tsx`, `format.ts`) a detail běhu (`Run.tsx`)

- Hlavička „Běhy“ H1 32 + vedle čip „2 běží · 1 ve frontě“ (mono 12 `running`).
- **Filtrační lišta** jako karta `bg-surface` radius 16 padding 12: pole hledání (ikona lupy, placeholder „Hledat scénář nebo ID běhu…“, filtruje klientsky podle jména scénáře a run_id), select „Všechny stavy“, select „Všechny scénáře“. (Filtr období z návrhu neimplementovat.)
- **Záhlaví sloupců** mono 11 verzálky `fg-muted`: SCÉNÁŘ / RUN_ID, STAV, KDY, TRVÁNÍ, CENA.
- **Řádek běhu jako karta**: `bg-surface` radius 12, výška 80, mezera 8; vlevo ikona stavu 20 px v kolečku, pak jméno scénáře 15 semibold `fg` a pod ním run_id mono 12 `fg-muted`; sloupec stav = text v barvě stavu 14 („běží“ modře, „úspěch“ zeleně, „chyba: timeout“ růžově, „jen plán (dry-run)“ neutrálně); KDY mono 12 („krok 3/7 · navrh“, „ve frontě (2.)“, „před 12 min“, „dnes 14:02“); TRVÁNÍ mono 12 („32,4 s“, „00:42“ u běžících); CENA mono 12 „0,0812 USD“; vpravo chevron 16 px. Hover `bg-surface-hover`, celý řádek odkaz.
- `formatCost`: **vždy čtyři desetinná místa** a jednotka tam, kde návrh ukazuje USD („0,0000 USD“, „0,0812 USD“), nikdy „0“ ani „0,000013128“. Na kartě projektu „dnes 1,20 USD“ (dvě místa u částek ≥ 0,01, jinak čtyři).
- „Načíst další“ sekundární 40 px s ikonou chevron-down.
- Detail běhu: titul mono 32 + ikona ↗ (odkaz na scénář), pod ním run_id mono 13 `fg-muted`; vpravo čip stavu, mono „32,4 s · 0,0812 USD“ a sekundární tlačítko „Otevřít scénář“. Řádek vstupů jako `bg-nested` karta 48 px: eyebrow „VSTUPY“ mono 11 + hodnoty mono 13. Záložky podtržené + „sledovat běh“ checkbox vpravo. Karty kroků v běhu jako v editoru (kolečko se stavovou ikonou, vpravo mono „12,4 s · 0,0210 USD“ a text stavu 12 `fg-muted`).

## 9. Agenti a skilly (`Agents.tsx`)

- Levý seznam šířka 200: položky jako karty **48 px** radius 10 `bg-surface`, mono 14, ikona typu (Bot/BookOpen) 16 `fg-muted`, aktivní `bg-surface-active` s ringem 1 `accent`, čip chyb vpravo; „+ Nový agent“ sekundární 40 px nad seznamem (nebo v hlavičce, §2 G8).
- Editor vpravo **v kartě** `bg-surface` radius 16 padding 24 (dnes je formulář „nahý“ na pozadí). Uvnitř žádný duplicitní název (§2 G1); první řádek karty = segmentový přepínač Form | Markdown + SaveNote vlevo, Uložit v hlavičce stránky zůstává jediné.
- Sekce (nadpis 16 semibold, mezera 28): Popis, Model; **Skilly jako seznam checkboxů** v `bg-nested` kartě (řádky 40 px, název mono 14, vpravo mono 11 „SKILL.md“) — ne čipy + select; MCP servery stejným stylem (checkbox serveru, pod ním odsazené nástroje, poznámka „vlastník nepovolil“ jako `fg-muted`); Limity ve **třech sloupcích**; Instrukce = textarea mono 13 min. 12 řádků v `bg-nested` radius 12 s patičkou „Podporuje Markdown“ 12 `fg-muted`; Používá = řádky `bg-nested` 44 px s odkazem a ikonou ↗.

## 10. Config (`Config.tsx`)

- Celý formulář **v kartě** `bg-surface` radius 16 padding 24; první řádek cesta projektu mono 13 `fg-muted`; přepínač Form | YAML + SaveNote; Uložit jen v hlavičce.
- Sekce ve **dvou sloupcích** (gap 24): Připojení (api_key_env + stav) | Jev model (jen ke čtení, mono, poznámka); Modely přes celou šířku: každý alias jako **`bg-nested` karta** (radius 12, padding 16) s řádkem polí Alias / ID modelu / max_tokens / API + kvalita a pod ním meta „používá pisatel“ mono 12 + vpravo „Smazat alias“ (nebezpečné, disabled s důvodem); „+ Přidat alias“ sekundární vpravo nad seznamem; Úložiště | Webhook a callback (stavy `*_env` jako řádky s ikonou); Limity (dva sloupce polí) | Proměnné (řádky `bg-nested` 40 px: název mono + stav vpravo v barvě); MCP servery jako `bg-nested` karta: název 15 semibold, řádky Transport / Povolení agenti / Nástroje (mono 12), čip „Pouze čtení“.

## 11. Co zůstává jinak než v návrhu (záměrně)

Bez štítků „dostupný“ a `skills[]`/`mcp[]`; bez opakovaných názvů v kartách formulářů; bez druhého Uložit a druhého přepínače; bez sloupce s časem navíc; bez „Přidat projekt“ karty v neprázdném seznamu; bez filtru období v bězích; Přejmenovat / Smazat / Vrátit zpět v menu ⋯; typy kroků jen ask, task, jev, image, parallel, switch, call, set, fail, output.
