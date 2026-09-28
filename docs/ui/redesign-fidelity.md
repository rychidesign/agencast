# Věrnost návrhu V3 — rozdíly mezi nasazeným GUI (0.16.0) a `.pen` a co se má změnit

Koordinátor porovnal screenshoty nasazeného GUI (1440 px) s rámečky návrhu
`docs/ui/design/agencast-design.pen` (exporty v `docs/ui/design/ref/png/`, přesné hodnoty
komponent v `docs/ui/design/ref/component-specs.md`, HTML s Tailwind třídami v `ref/html/`).
Struktura (sidebar, karty, sloupec kroků, panel) sedí, ale **měřítko, tvary a hustota ne**:
GUI je o třídu menší, plošší a tmavší než návrh. Tento dokument je závazné zadání pro vlnu E.

**Vlna F (2026-09-28):** hodnoty níže jsou srovnané s `.pen` (HTML export a PNG rámečky 1440 px). Kde se
první odhad lišil, je u hodnoty „změřeno z .pen“; rozhodl koordinátor: vyhrává `.pen`, nad ním jen §11 a
`redesign-plan.md` §2.

Pravidla zjednodušení z `redesign-plan.md` §2 platí dál (jedna hlavička, jedno Uložit, ⋯ menu,
žádné duplicity, bez štítků „dostupný“ / `skills[]` apod.). Kde návrh ukazuje něco, co §2 ruší,
zůstává §2. Všechno ostatní má vypadat **jako v návrhu**, včetně velikostí v px.

## 0. Tokeny — doplnit do `ui/src/index.css` (vlastní E2, ostatní používají)

| token | hodnota | použití v návrhu |
|---|---|---|
| `--color-control` | `#31455F` | výplň sekundárního tlačítka a ikonového tlačítka (`V3 / Button / secondary`, `V3 / IconButton`) |
| `--color-control-hover` | `#3B5170` | hover sekundárního tlačítka |
| `--color-surface-active` | `#253B50` (změřeno z .pen; odhad byl `#1B2A3D`) | aktivní položka sidebaru a seznamu, vybraná karta kroku |
| `--color-track` | `#25374A` | dráha progress baru |
| `--radius-button` | `10px` | tlačítka |
| `--radius-tile` | `14px` (změřeno z .pen) | karta projektu, scénáře, položka seznamu, kontejner kroků, filtry běhů, modál |
| `--color-danger` / `-hover` | `#492937` / `#5A3142` (změřeno z .pen) | výplň nebezpečného tlačítka |
| gradient `bg-app` | `linear-gradient(-112.6deg, #1A2833 11%, #0C1A26 48%, #132430 89%)` (změřeno z .pen) | pozadí aplikace a přilepené hlavičky |

## 1. Měřítko a typografie (všude)

- **H1 stránky 28/42 px regular** (změřeno z .pen; odhad byl 32 semibold), pod ním popis 14/21 `fg-secondary` (mezera 12). Meta řádek (cesta registru) mono 12 je samostatný řádek pod hlavičkou; run_id v detailu běhu mono 13 je 8 px pod titulem. Blok hlavičky má horní odsazení 32 px a mezeru 24 px pod sebou.
- Titul editoru scénáře **mono 27/41 regular**, titul detailu běhu **mono 26/39 regular** (změřeno z .pen). Titul panelu 18/26 semibold; eyebrow panelu 10 px mono verzálky `letter-spacing 0.08em` `fg-muted` (změřeno z .pen).
- Nadpis sekce ve formuláři 16 px semibold `fg`; štítek pole 13 px **medium** `fg-secondary` (ne bold); nápověda 12 px `fg-muted`.
- Meta údaje (počty, časy, ceny, id) jsou **mono 12 px** `fg-muted` (návrh používá JetBrains Mono na všechna čísla a technické texty). Dnes je meta v Interu 13 px.
- Obsah stránky: padding 32 px, max. šířka 1176 px (1440 − 232 − 2×16), mezera mřížky karet 20 px.

## 2. Tlačítka a ovládací prvky (`ui.tsx`, `form.tsx`)

- Primární: výška **44 px** (změřeno z .pen: všechna tlačítka na obrazovkách 44; komponenta v knihovně 40), padding 0 18, radius **10**, `bg-accent text-ink` 14 px semibold, ikona 16 px. Sekundární: totéž s `bg-control text-fg`. Nebezpečná: výplň `#492937` (`bg-danger`) s `text-error` (změřeno z .pen). Ghost (jen text) jen v menu.
- Ikonové tlačítko: **44 × 44** i v hlavičce (změřeno z .pen), radius 10, `bg-control`, ikona 18–20 px `fg`. ⋯ na kartách (projekt, scénář, krok) je **bez výplně** (klikací plocha 44, ikona 18), plocha `control` až při hoveru a otevření (změřeno z .pen).
- Pole: výška **44 px**, radius **6** (změřeno z .pen), `bg-nested`, **v klidu bez rámečku** (stroke v `.pen` průhledný; vlna G), text 14 px, placeholder `fg-muted`; fokus ring 2 `accent` bez odsazení, neplatné ring 2 `error`; mono varianta 13 px. Textarea padding 12. Select má chevron `fg-muted` vpravo. Tlačítko `{}` v poli s proměnnými je uvnitř boxu, bez výplně, 44 × 44, `text-variable`. Víceřádková šablona a JSON (`V3 / CodeInput`): box `nested` r8, toolbar (štítek 13 + „šablona“/„JSON“ mono 11 `text-type` + `{}`) s linkou, editor p16, patička se stavem a „Ctrl + mezerník pro nabídku“.
- Segmentový přepínač (Form | YAML): obal `bg-nested` radius 9 padding 4 gap 4, **segment 44 px radius 7**, 13 px (změřeno z .pen), aktivní `bg-accent text-ink`, neaktivní `fg-muted`.
- Záložky detailu běhu: výška 47, padding 12 18, mezera 28, text 13 medium (změřeno z .pen), aktivní `fg` s podtržením 2 px `accent`, neaktivní `fg-secondary`. Záložky v panelu kroku 13 regular, mezera 24.
- Stavový čip: pilulka `bg-nested`, padding 7 10, mezera 8, ikona 14 px, **text mono 12 medium v barvě stavu** (změřeno z .pen). Pulzuje jen ikona „běží“ (pulzující text by neměl kontrast).
- Menu ⋯: `bg-surface` radius 12, položky 40 px, 14 px; nebezpečná červeně.
- Akordeon (Podmínka / Spolehlivost / Podrobnosti): řádek 52 px (padding 16), **šipka 16 vlevo**, titul 14 medium, hodnota mono 11 `fg-muted` vpravo (změřeno z .pen).
- Blok kódu („CodeViewer“): `bg-surface` radius **16**, hlavička padding 14 18 s linkou (ikona 18 + název mono 13 + čip radius 6 s obrysem, mono 11), tělo `bg-nested` padding 18 0 s řádky 27 px (číslo mono 12 `fg-muted` šířka 26, mezera 14), patička padding 14 s popisem mono 11 vlevo a „Kopírovat“ s obrysem vpravo (změřeno z .pen). Jedna komponenta `CodeBlock` v `ui.tsx` pro Výstup/Prompt/Odpověď, soubory i bloky v Markdownu; `CodeView` (YAML jen ke čtení) a YAML editor mají stejnou hlavičku a řádek 27 px.
- Modál („ModalShell“): radius 14, hlavička padding 24 s linkou (titul 22 semibold + zavřít 44), obsah padding 24 mezera 18, patička padding 18 24 s linkou, tlačítka vpravo **Zrušit, pak akce** (změřeno z .pen).
- Prázdný stav: `bg-surface` radius 12 padding 28 mezera 14, ikona 28, titul 18 semibold, popis 13 (změřeno z .pen).

## 3. Sidebar (`Shell.tsx`)

- Šířka 232, padding 28 20, `bg-sidebar`, pravý hairline. Aktivní položka `#253B50` (změřeno z .pen). Značka: ikona `Layers2` 25 px v `text-type` + „agencast“ 22 px semibold `letter-spacing -0.7`. Mezera pod značkou 22.
- „← Projekty“ jako řádek 44 px (ikona 16 + text 14 medium `fg-secondary`), pak oddělovač 1 px `line`, pak jméno projektu (14 semibold) a navigace: položky **44 px**, radius 8, gap 6, padding 0 14, ikona 16 `fg-muted`, text 14 medium `fg-secondary`; aktivní `bg-surface-active text-fg` a ikona `fg`.
- Dole: „Dnes utraceno“ 12 `fg-muted`, částka mono 12 medium `fg` (`1,20 / 5,00 USD`), progress 3 px, dráha `track`, výplň `success` (přes limit `error`). Hlášku výpadku serveru zachovat.

## 4. Projekty (`Projects.tsx`)

- Hlavička: H1 „Projekty“ 28, popis „Spravuj projekty, scénáře a běhy agentů na jednom místě.“ 14 `fg-secondary`, pod hlavičkou cesta registru mono 12. Vpravo ikonové tlačítko Načíst znovu 44 × 44 `bg-control` a „+ Přidat projekt“ primární 44 px.
- Karta projektu: `bg-surface`, radius **14**, padding **22**, mezery 20, min. výška 260 (změřeno z .pen). Obsah: horní řádek s ⋯ bez výplně vpravo (bez štítku „dostupný“, §2 G6; nedostupný má v tomto řádku čip „nedostupný“ a dole důvod), název **20/29 semibold**, cesta mono 12 `fg-muted`, **čipy počtů** (radius 6, padding 5 9, mono 11 `fg-secondary`), oddělovač 1 px `line` s odsazením 14, spodní řádek: stavový čip posledního běhu + útrata mono 12 („dnes 1,20 USD“).

## 5. Přehled scénářů (`Scenarios.tsx`, `TypeIcon.tsx`)

- Toolbar nad mřížkou je v `PageHeader` (už je): „+ Nový scénář“ primární 40 px.
- Karta scénáře: `bg-surface`, radius **14**, padding 24, výška **292**, mezera 18 (změřeno z .pen). Nahoře řádek 32 px: **řetěz ikon typů jako prosté ikony 18 px v `text-type`, gap 10, bez koleček a bez šipek** (max. 5, pak „+N“ mono 12), vpravo ⋯ bez výplně. Název **18/26 semibold** (jméno scénáře), popis 14 `fg-secondary` (2 řádky, výpustka), meta **mono 11 `fg-secondary`**: „7 kroků · 3 agenti“ + čip „volatelný“. Spodní řádek: stavový čip posledního běhu (nebo čip chyb) vlevo, vpravo „Otevřít ↗“ 13 `fg` (změřeno z .pen).
- Dnes se řetěz ikon s šipkami zalamuje na dva řádky a tlačí čip stavu; to zmizí.

## 6. Editor scénáře (`Scenario.tsx`, `StepCards.tsx`, `TypePicker.tsx`)

- Hlavička: „← Scénáře“ (12 `fg-secondary`), titul **mono 27/41 regular**, popis 13/20 `fg-secondary` (změřeno z .pen); vpravo **„Spustit“ primární** (ikona Play) a **„Uložit“ sekundární** (ikona Save; disabled = 50 % opacity), pak ⋯ 44 × 44 `bg-control`. Druhý řádek: segmentový přepínač + SaveNote jako stavový čip („Uloženo ✓ 14:02“ `success`, „Neuloženo“ `warning`).
- Sloupec kroků do **676**, panel **440**, mezera **28** (změřeno z .pen: 1144 − 440 − 28). Konektor: výška **44**, šipka 16 px `fg-muted`; (+) kolečko **44 px** `bg-surface`, na hover `control`.
- **Karta kroku** (pilulka, radius 999, `bg-surface`, výška **96**, padding **16**, gap **14**; změřeno z .pen): vlevo pořadové číslo mono 11 `fg-muted` (jen v editoru), pak **kolečko 40 px s plochou `type/7` a ikonou typu 16 px `text-type`**, pak texty (mezera 4): řádek typu **mono 11 `text-type` malými** „ask · navrh“, titul **15/22 semibold** `fg`, třetí řádek **mono 12 `fg-secondary`** (u `ask`/`task` agent + úryvek promptu, u `image` model · poměr, podmínka „když …“); vpravo ⋯ bez výplně. V běhu je ve třetím řádku „12,4 s · 0,0210 USD“ a vpravo stav 11 px.
- Vybraná karta: jen plocha `bg-surface-active` (bez rámečku, změřeno z .pen). Hover `bg-surface-hover`.
- Hlavičková karta: **obdélník** `bg-surface` radius 14 padding 22 mezera 16, ikona `AlignJustify` 24 px `text-type`, titul „HLAVIČKA“ 21 semibold, pod ním vstupy · výstupy mono 13 `fg-secondary`; vybraná má navíc prstenec 1 px `accent` (změřeno z .pen).
- Kontejnery (parallel/switch/call): obal `bg-surface` radius **14** padding 16; záhlaví = ikona 20 bez kolečka, titul 15/22, mono 10 `fg-muted` „3 · parallel · varianty“, šipka sbalit 16 vpravo; větve `bg-nested` radius **8** padding 12 se štítkem mono 11 `text-variable`, paralelní větve vedle sebe; karty ve větvi padding 10, kolečko 30, titul 13 (změřeno z .pen).
- Tlačítka pod sloupcem: „+ Přidat krok“ a „+ output“ sekundární 44 px vedle sebe na střed.
- TypePicker: `bg-surface` radius 12, položky 40 px: klíčové slovo mono 13 `fg` + popis 13 `fg-muted` (u aktivní `fg-secondary` kvůli kontrastu na `surface-active`).

## 7. Panel (`StepPanel.tsx`, `RunPanel.tsx`, `RunStepPanel.tsx`)

- `bg-surface` radius 16; **hlavička** padding 20 s linkou dole: ikona panelu 16, eyebrow mono 10 `fg-muted` verzálky, titul 18/26 semibold, zavřít ghost 44; **tělo** padding 20, mezera polí 18 (změřeno z .pen). Šířka 440 (panel kroku v běhu **520**).
- Pole podle §2 (výška 44, štítky 13 medium). Select „Typ kroku“ ukazuje „ask · jedno volání agenta“ (mono klíč + popis). Vstupy a výstupy v panelu hlavičky jsou vnořené karty `nested` r8 p14, „+ Přidat …“ je sekundární tlačítko.
- Panel spuštění: eyebrow „SPUSTIT BĚH“, mezery 20; štítek „REŽIM BĚHU“ 11 px verzálky; karty režimu `bg-nested` radius 8 padding 14 (řádek s radiem 20 px 44 px, popis 12), vybraná ring 1 `accent`; „Limity“ jako řádky 32 px s oddělovači (štítek 12 `fg-secondary`, hodnota mono 12 `fg`); varování `warning/10` r8 p12 text 12; vpravo „Zrušit“ + „Spustit dry-run“ (změřeno z .pen).
- Panel kroku v běhu: řádek stavu = čip stavu + mono 11 „12,4 s · 0,0210 USD“; záložky 13 px; obsah = blok kódu (viz §2) a řádek souboru `bg-nested` r8 p12 výška 52 (cesta mono 12 + ↗).

## 8. Běhy (`Runs.tsx`, `format.ts`) a detail běhu (`Run.tsx`)

- Hlavička „Běhy“ H1 32 + vedle čip „2 běží · 1 ve frontě“ (mono 12 `running`).
- **Filtrační lišta** jako karta `bg-surface` radius **14** padding 12, obrys `line`, mezera 10, selecty 210 px (změřeno z .pen): pole hledání (ikona lupy, placeholder „Hledat scénář nebo ID běhu…“, filtruje klientsky podle jména scénáře a run_id), select „Všechny stavy“, select „Všechny scénáře“. (Filtr období z návrhu neimplementovat.)
- **Záhlaví sloupců** mono **10** verzálky `fg-muted` (změřeno z .pen): SCÉNÁŘ / RUN_ID, STAV, KDY, TRVÁNÍ, CENA.
- **Řádek běhu jako karta**: `bg-surface` radius **8**, výška **72** (padding 16 20), mezera 8 (změřeno z .pen); vlevo ikona stavu 20 px v kolečku, pak jméno scénáře 15 semibold `fg` a pod ním run_id mono 12 `fg-muted`; sloupec stav = text v barvě stavu 14 („běží“ modře, „úspěch“ zeleně, „chyba: timeout“ růžově, „jen plán (dry-run)“ neutrálně); KDY mono 12 („krok 3/7 · navrh“, „ve frontě (2.)“, „před 12 min“, „dnes 14:02“); TRVÁNÍ mono 12 („32,4 s“, „00:42“ u běžících); CENA mono 12 „0,0812 USD“; vpravo chevron 16 px. Hover `bg-surface-hover`, celý řádek odkaz.
- `formatCost`: **vždy čtyři desetinná místa** a jednotka tam, kde návrh ukazuje USD („0,0000 USD“, „0,0812 USD“), nikdy „0“ ani „0,000013128“. Na kartě projektu „dnes 1,20 USD“ (dvě místa u částek ≥ 0,01, jinak čtyři).
- „Načíst další“ sekundární 40 px s ikonou chevron-down.
- Detail běhu: titul **mono 26/39** + ikona ↗ (odkaz na scénář), 8 px pod ním run_id mono 13 `fg-muted`; vpravo čip stavu, mono 13 „32,4 s · 0,0812 USD“ a sekundární tlačítko „Otevřít scénář“. Vstupy jako `bg-nested` karta radius 8 padding 14: štítek „VSTUPY“ 10 px + hodnoty mono 12 `fg-secondary` (změřeno z .pen). Fronta: řádek „ve frontě (2.)“ mono 12 `neutral` a prázdný stav 380 px s ikonou hodin; dry-run: řádek stavu 12 `neutral` a plán v kartě `surface` r12 p24 s eyebrow „PLÁN BĚHU“. Soubory: strom 300 px (`surface` r10 p12, položky mono 12 s ikonou), prohlížeč `surface` r12 p24, u Markdownu přepínač Náhled | Kód. Záložky podtržené + „sledovat běh“ checkbox vpravo. Karty kroků v běhu jako v editoru (kolečko se stavovou ikonou, vpravo mono „12,4 s · 0,0210 USD“ a text stavu 12 `fg-muted`).

## 9. Agenti a skilly (`Agents.tsx`)

- Levý seznam šířka **240**: položky jako karty radius **14** padding **16** mezera 14 `bg-surface`, mono 14 semibold, ikona typu (Bot/BookOpen) **22 `text-type`**, aktivní jen `bg-surface-active`, chyby jako druhý řádek mono 11 `error` + ikona (změřeno z .pen); „+ Nový agent“ sekundární 40 px nad seznamem (nebo v hlavičce, §2 G8).
- Editor vpravo **v kartě** `bg-surface` radius 16 padding 24 (dnes je formulář „nahý“ na pozadí). Uvnitř žádný duplicitní název (§2 G1); první řádek karty = segmentový přepínač Form | Markdown + SaveNote vlevo, Uložit v hlavičce stránky zůstává jediné.
- Pole po 18 px, nadpisy sekcí 16 semibold s odsazením 10 nad (změřeno z .pen): štítky „Popis“, „Model“ 13 px; **Skilly jako seznam checkboxů** v `bg-nested` kartě radius 10 padding 14 (řádky 40 px, checkbox 18, název 13, vpravo mono 11 „SKILL.md“; změřeno z .pen) — ne čipy + select; MCP servery stejným stylem (checkbox serveru, pod ním odsazené nástroje, poznámka „vlastník nepovolil“ jako `fg-muted`); Limity ve **třech sloupcích**; Instrukce = textarea mono 13 min. 12 řádků v `bg-nested` radius 12 s patičkou „Podporuje Markdown“ 12 `fg-muted`; Používá = řádky `bg-nested` 44 px s odkazem a ikonou ↗.

## 10. Config (`Config.tsx`)

- Celý formulář **v kartě** `bg-surface` radius 16 padding 24; první řádek cesta projektu mono 13 `fg-muted`; přepínač Form | YAML + SaveNote; Uložit jen v hlavičce.
- Sekce ve **dvou sloupcích** (gap 24): Připojení (api_key_env + stav) | Jev model (jen ke čtení, mono, poznámka); Modely přes celou šířku: každý alias jako **`bg-nested` karta** (radius 12, padding 16) s řádkem polí Alias / ID modelu / max_tokens / API + kvalita a pod ním meta „používá pisatel“ mono 12 + vpravo „Smazat alias“ (nebezpečné, disabled s důvodem); „+ Přidat alias“ sekundární vpravo nad seznamem; Úložiště | Webhook a callback (stavy `*_env` jako řádky s ikonou); Limity (dva sloupce polí) | Proměnné (řádky `bg-nested` 40 px: název mono + stav vpravo v barvě); MCP servery jako `bg-nested` karta: název 15 semibold, řádky Transport / Povolení agenti / Nástroje (mono 12), čip „Pouze čtení“.

## 11. Co zůstává jinak než v návrhu (záměrně)

Doplněno ve vlně F (záměrná zjednodušení a rozhodnutí z dřívějších vln, `.pen` je nepřebíjí): panel kroku má
titul = id kroku mono (návrh ukazuje lidský název), bez pole „id“ (přejmenování je v ⋯) a bez patičky
„Uloženo / Hotovo“ (G2); panel spuštění má šířku 440 jako ostatní (návrh 480) a limity jen u ostrého běhu
(PN2); karty kroků v běhu nemají ⋯ (žádná akce); koš zůstává vně pilulky (§2.3 navrh-gui); hláška „Běh
skončil: …“ jen pro čtečku (G10); drobečky jen „← Scénáře“ / „← Běhy“ (G5); YAML dvoubarevně podle
navrh-gui §4.5; zvýraznění kroku v YAML jen bliknutím; skill se edituje jako Markdown (bez polí Název / Popis
/ Soubor a lišty formátování; API ukládá SKILL.md jen celý), pod editorem je náhled; stav fronty neutrálně
(tokeny §1: `neutral` = čeká); záložky v panelu běhu mají podtržení aktivní (ne jen barvu).


Bez štítků „dostupný“ a `skills[]`/`mcp[]`; bez opakovaných názvů v kartách formulářů; bez druhého Uložit a druhého přepínače; bez sloupce s časem navíc; bez „Přidat projekt“ karty v neprázdném seznamu; bez filtru období v bězích; Přejmenovat / Smazat / Vrátit zpět v menu ⋯; typy kroků jen ask, task, jev, image, parallel, switch, call, set, fail, output.

## 12. Mobil a tablet (vlna G; návrh mobil nemá)

- Do 1023 px lišta 56 px (`bg-sidebar`, hairline): značka, projekt (truncate), ☰ 44 px → drawer přes celou výšku
  (z-50, „← Projekty“, položky 48 px, útrata dole; Esc, klik mimo, fokus zpět na ☰). Obsah p16, od 768 px p24.
- Do 767 px hlavička H1 24, popis 13, jen primární akce + ⋯ (sekundární akce jdou do ⋯, `PageHeader compact`),
  titul se láme (`overflow-wrap:anywhere`); pod 1024 px se hlavička nepřilepuje.
- Do 1279 px je panel (krok, hlavička, spuštění, krok v běhu) plnoobrazovkový sheet (`role="dialog"`, fokus past,
  Esc, po zavření fokus zpět na kartu). Do 767 px karta kroku 80 px bez čísla (kolečko 36), konektor 32 px s (+)
  32 px a dotykovou plochou 44, sloupec přes celou šířku (koš jen v ⋯), TypePicker jako list u spodního okraje.
- Běhy do 767 px bez záhlaví: karta o dvou řádcích (stav + jméno + stav textem; run_id, kdy, trvání · cena),
  chevron vpravo. Záložky detailu běhu s vodorovným posuvem. Agenti/Skilly pod 1100 px jako vodorovné čipy.
