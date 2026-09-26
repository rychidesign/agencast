# Návrh GUI AgenCast

Stav: **návrh** (UX designér, 2026-09-26), podklad pro stavbu `ui/` v tomto repu
(DESIGN „Obálky“: samostatná obálka nad HTTP API `serve`, vložená do záložky
Skynet Soul). Vizuální vzor: Buzz, obrazovka Create workflow — svislý sloupec
kroků, pravý panel s formulářem, přepínač Form / YAML, tmavé téma bez rámečků.

Rozhodnutí koordinátora k otázkám v §8 jsou na konci dokumentu.

Podklady: DESIGN.md (Obálky, §5), spec scenario/agent/config/skill/api/projects/run-record, ig-post.yaml, SKILL.md agencast-create.

Vizuální reference: screenshot obrazovky Create workflow z Buzz, který uživatel poslal přímo; prohlédnut a promítnut do sekcí 2.3, 3 a 5. Kopie: `~/workspace/ux-reference/buzz-create-workflow.png`.

## 1. Informační architektura

```
Projekty  (#/)                                   celá obrazovka, seznam z registru
└ Projekt (#/p/thtd)                             hlavička projektu + záložky
   ├ Scénáře (výchozí)   seznam → Editor scénáře (#/p/thtd/scenare/ig-post?krok=kontrola)
   ├ Agenti              seznam vlevo + formulář (#/p/thtd/agenti/copywriter)
   ├ Config              jeden formulář: config.yaml + sekce MCP servery (mcp.yaml)
   ├ Skilly              seznam vlevo + text (#/p/thtd/skilly/thtd-hlas)
   └ Běhy                seznam → Detail běhu (#/p/thtd/behy/<run_id>?krok=navrh/copy)
```

- Hloubka nejvýš 2 pod projektem. Editor scénáře a detail běhu jsou celé obrazovky se stejným sloupcem karet; vpravo **panel** (420 px, nikdy modál) s krokem.
- **Modály jen pro rozhodnutí:** mazání s dopadem, konflikt souboru, změna typu kroku. Výběr typu u + je popover, ne modál.
- Vybraný krok je v URL (`?krok=`), aby šel poslat odkaz. Hash routing kvůli iframe v Skynet Soul; iframe posílá `postMessage` s aktuální cestou pro deep link z dashboardu.
- Čtecí verze (podle DESIGN) = stejné obrazovky bez +, bez Uložit, panel jen ke čtení. Editor je nadmnožina, nic se nepřekresluje.

## 2. Obrazovky

### 2.1 Seznam projektů (karty)

```
Projekty                                                                                        ⟳
Registr ~/.config/agencast/projects.yaml
┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐  ┌────────────────────────┐  ┌────────────────────────┐  ┌────────────────────────┐
                        │ ● dostupný          ⋯  │  │ ● dostupný          ⋯  │  │ ○ nedostupný        ⋯  │
          +             │ thtd                   │  │ ukazka                 │  │ stary-projekt          │
   agencast projects    │ ~/thtd                 │  │ ~/ukazka               │  │ /mnt/disk/stary        │
   add <cesta> [kopír.] │                        │  │                        │  │ chybí workflows/       │
                        │ 3 scénáře · 4 agenti   │  │ 1 scénář · 1 agent     │  │ config.yaml            │
└ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘  │ dnes 0,42 USD ✓ 12 min │  │ dnes 0        bez běhů │  │                        │
                        └────────────────────────┘  └────────────────────────┘  └────────────────────────┘
```
Karta: dostupnost + ⋯ nahoře, jméno jako titulek, cesta mono, patička počty vlevo a dnešní útrata + poslední běh vpravo (`GET /projects`, čísla z `GET /projects/<p>` a `spend`, skeleton do té doby). Nedostupný projekt: 50 % opacity, čárkovaný prstenec, důvod místo patičky. Karta + ukazuje CLI příkaz s tlačítkem kopírovat (registr nemá zápis přes API); až bude, nahradí ho formulář jméno + cesta. ⋯: Otevřít, Kopírovat cestu.

### 2.2 Přehled projektu (karty scénářů)

```
← Projekty   thtd   ~/thtd            dnes 0,42 / 5,00 USD ▮▮▯▯▯    limity 1,00 USD · 1 h                   ⟳
Scénáře · Agenti · Config · Skilly · Běhy
┌ ─ ─ ─ ─ ─ ─ ─ ─ ┐  ┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐
                      │ [ask]→[jev]→[fail]→[ask]→[jev] +3     │  │ [task]→[output]                       │
        +             │                          ✓ 12 min  ⋯  │  │                         ✗ 2 chyby  ⋯  │
   Nový scénář        │ Návrh IG příspěvku ke schválení       │  │ Publikace schváleného příspěvku       │
                      │ 8 kroků · copywriter, photographer    │  │ 3 kroky · publisher · volatelný       │
                      │ · 1 vstup · 3 výstupy                 │  │                                       │
└ ─ ─ ─ ─ ─ ─ ─ ─ ┘  │ ig-post.yaml            včera 14:03   │  │ ig-publish.yaml            bez běhů   │
                      └──────────────────────────────────────┘  └──────────────────────────────────────┘
```
- Titulek = `description` scénáře (povinná věta pro člověka, autor ji píše sám; generovat větu z kroků nebudeme, u `jev` a `switch` by lhala).
- Řetězec ikon = typy kroků v pořadí souboru, nejvýš 5, pak čip „+N“; `parallel`/`switch` jednou svou ikonou, vnitřek se nerozepisuje.
- **Místo přepínače** stavový čip posledního běhu (✓ před 12 min · ✗ chyba · ◌ běží · bez běhů); chyby validace mají přednost („✗ 2 chyby“). `callable` je textový štítek „volatelný“ v meta řádku, ne přepínač: mění soubor a chrání schvalování (DESIGN §5.2), patří do formuláře hlavičky v editoru s vysvětlením.
- Patička: soubor mono vlevo, čas posledního běhu vpravo (datum vytvoření jako v Buzz nemá pro scénář hodnotu; API zatím mtime nedává).
- ⋯: Otevřít, Běhy tohoto scénáře, Kopírovat příkaz spuštění, Validovat; později Duplikovat, Smazat.
- Karta + otevře dialog „Nový scénář“ (jméno jako slug s kontrolou, popis); ve čtecí fázi ukáže `agencast new scenario <jméno>` s kopírováním.
- „Chyby validace“ v hlavičce = součet `errors` všech souborů; klik otevře seznam s odkazy na soubor a krok.

### 2.3 Editor scénáře (karty + panel)

```
← thtd / Scénáře    ig-post ✎  Návrh IG příspěvku ke schválení ✎     [Form | <> YAML]     Neuloženo · 1 chyba   [Uložit]

      ( ≡  HLAVIČKA                                                            )
      (    1 vstup: tema · 3 výstupy: caption, hashtags, image                 )
                                     ↓
      ( 1  ASK · copy                                                          )
      (    copywriter: „Napiš IG příspěvek na téma: {{ inputs.tema }}“         )
                                     ↓
    ╭─( 2  JEV · kontrola                                                      )─╮   (🗑)
    ╰─(    „Odpovídá text tónu značky THTD…?“ · noul                           )─╯
                                     ↓
      ( 3  FAIL · stop                                     když on_brand < 0.7 )
      (    „Text neodpovídá značce (on_brand = …)“                             )
                                     ↓
      ( 4  ASK · foto_prompt                                                   )
      (    photographer: „Navrhni fotku k textu…“                              )
        ✗ agent „fotograf“ neexistuje
                                     ↓  …
      ( 7  IMAGE · foto                                                        )
      (    gemini-image · 4:5 · „{{ steps.foto_prompt.popis_fotky }}“          )
                                     ↓
      ( 8  OUTPUT · out                                                        )
      (    caption, hashtags, image                                            )
                                    (+)
```
Pilulka přesně jako v Buzz: eyebrow `TYP · id` (typ uppercase, id mono), pod ním hodnota tučně na jeden řádek s výpustkou. Vpravo v pilulce jen `když …` (šedě, mono), v prohlížeči běhu čas + cena. Hlavičková karta má místo čísla ikonu v zaobleném čtverci jako trigger v Buzz. Nový krok dostane id `<typ>_<n>` jako Buzz `step_2`; jeho pilulka má jen eyebrow `ASK · ask_2` a druhý řádek šedý zástupný text „doplň v panelu“, dokud nemá hodnotu. Hodnota podle typu:

| Typ | Hodnota |
|---|---|
| ask, task | `agent: „prompt…“` |
| jev | první otázka · typ; „+1 otázka“ |
| image | alias · poměr stran · „prompt…“ |
| call | `→ ig-text` · N vstupů |
| set | jména hodnot |
| fail | zpráva |
| parallel | `kratka ∥ dlouha` (kontejner) |
| switch | `podle steps.kontrola.druh: produkt, akce, jinak` (kontejner) |
| output | jména výstupů |

**Konektor:** šipka ↓ mezi kartami se při hoveru nebo fokusu promění v (+) 28 px; trvale viditelné (+) je jen na konci každého seznamu (hlavní i každá větev). Menu ⋯ karty má navíc „Vložit krok nad / pod“ jako klávesovou cestu. Kontejnerové karty (`parallel`, `switch`) z 2.4 nejsou pilulky, ale zaoblené obdélníky (16 px), uvnitř nich zase pilulky. V prohlížeči běhu (2.5) stavová ikona nahradí číslo v kruhu a pravá strana pilulky nese čas a cenu.

**Koš vně pilulky:** červený kulatý 28 px vpravo vně, zobrazí se při hoveru a při `focus-within`. Klávesnice: Tab z fokusované karty přejde na koš (je další zastávkou v pořadí, při fokusu se ukáže), nebo klávesa Delete na kartě; `aria-label="Smazat krok kontrola"`. Na dotykovém vstupu (`pointer: coarse`) je koš viditelný trvale ztlumeně. Ochrana mazání z §4.3 platí beze změny. Hlavičková karta koš nemá.

**Panel** (plovoucí zaoblený obdélník vpravo, okraj 16 px od hran):

```
┌ KROK 2                                    🗑   ✕ ┐
│ jev ▾                                             │
│                                                   │
│ State                                             │
│ [{{ steps.copy.caption }}                    ]    │
│ Otázky                          [+ Přidat otázku] │
│  on_brand   noul ▾   Odpovídá text tónu…      🗑  │
│ ───────────────────────────────────────────────── │
│ Podmínka                                 vždy  ›  │
│ ───────────────────────────────────────────────── │
│ Spolehlivost                          výchozí  ›  │
│ ───────────────────────────────────────────────── │
│ Podrobnosti kroku                    kontrola  ›  │
└───────────────────────────────────────────────────┘
```
- Jako v Buzz: pole typu nahoře, společné věci dole ve třech sbalených řádcích (hodnota vpravo šedě, hairline mezi nimi). Řádek se rozbalí na místě (akordeon, chevron se otočí), aby zůstal kontext panelu.
- **Podmínka:** sbalený řádek ukazuje `vždy`, nebo zkrácený výraz (`steps.kontrola.on_brand < 0.7`); rozbalený = `ExprInput` + nápověda „Když vyjde nepravda, krok se přeskočí; kdo čte jeho výstup, potřebuje default.“ U `output` řádek není.
- **Spolehlivost:** timeout, budget_usd, retry, on_error, default; jen pro typy z tabulky §3 spec.
- **Podrobnosti kroku:** id (přejmenování s kontrolou `refs` a nabídkou přepsat odkazy), „Čte z“ a „Výstup čtou“ jako čipy (klik skočí na kartu), odkaz „Otevřít v YAML“ (skočí na řádek kroku).
- Chyba validace je přímo pod kartou a u pole v panelu.

### 2.4 Karty `parallel`, `switch`, `call`

```
│ ⑤ varianty        parallel · 2 větve, běží zároveň                     │
│   ┌ kratka ──────────────┐   ┌ dlouha ──────────────┐                 │
│   │ ⑥ kratky_text   ask  │   │ ⑦ dlouhy_text   ask  │                 │
│   │      +               │   │      +               │                 │
│   └──────────────────────┘   └──────────────────────┘   + větev       │
│      │  +                                                              │
│ ⑧ podle_druhu     switch · podle  steps.kontrola.druh                  │
│   = produkt                                                            │
│     ⑨ produktovy_text   ask · copywriter                               │
│          +                                                             │
│   = akce                                                               │
│     ⑩ akcni_text        ask · copywriter                               │
│          +                                                             │
│   jinak (default)                                                      │
│     ⑪ neznamy_druh      fail                                           │
│          +                                                  + případ   │
│      │  +                                                              │
│ ⑫ navrh           call → ig-text  (otevřít ↗) · 1 vstup                │
```
Pravidlo pro začátečníka: **vedle sebe = zároveň, pod sebou = jedna z možností.** Větve a případy jsou o odstín světlejší plocha bez rámečku, každá s vlastním +. Prázdný `default: []` se ukáže jako „jinak: nic“. Sbalení karty (šipka u čísla) schová vnitřek a ukáže jen počet kroků.

### 2.5 Prohlížeč běhu na kartách (detail běhu)

```
← thtd / Běhy   ig-post · 20260925-141502-ig-post-9f3c      ✗ chyba: fail v kroku stop_obrazek    4,4 s · 0,0016 USD
Vstupy  tema = „nová káva“              Kroky · Souhrn · Report · Soubory                   ☐ sledovat běh
│ ✓ ① copy            ask · chytry → claude-haiku-4.5      3,7 s   0,0015 │ ┌ KROK 2 · kontrola · jev ✓ 0,3 s ────┐
│ ✓ ② kontrola        jev · on_brand = 0,91                 0,3 s   0,00002│ │ Odpověď · Vstup · Volání (1) · Soubory│
│ ○ ③ stop            fail · přeskočeno: when … → false                   │ │ on_brand   0,91  ▮▮▮▮▮▮▮▮▮▯          │
│ ✓ ④ foto_prompt     ask · rychly → gemini-3.5-flash-lite  1,8 s   0,0006 │ │ state  „Nová káva je tady…“          │
│ ✓ ⑤ kontrola_obrazku jev · skutecna_osoba = 0,8           0,3 s   0,00002│ │ model  typesafe/jev-1.13-20260917    │
│ ✗ ⑥ stop_obrazek    fail · Popis fotky porušuje pravidla…                │ │ 21 + 4 tokenů · 0,00002 USD          │
│ · ⑦ foto            image · nedošlo                                     │ └──────────────────────────────────────┘
│ · ⑧ out             output · nedošlo                                    │
```
Stejné karty jako v editoru, navíc stav vlevo, čas a cena vpravo. Panel podle typu: `ask`/`task` Prompt (prompt.md), Odpověď, Výstup (output.json), Volání (pokusy, tahy, tokeny, `finish_reason`, úroveň kaskády), u `task` navíc Nástroje (`tool_call`, nepovolené a neplatné argumenty zvýrazněné); `image` náhled + prompt; `jev` odpovědi s pravděpodobnostmi; `call` se rozbalí přímo v kartě na vnořené karty (`navrh/copy`); `set` hodnoty; `output` hodnoty + URL nahraných souborů. Přeskočený krok: důvod a „použit default“. Varování (`continued: true`) = žlutý trojúhelník + text. Záložky: Souhrn = vykreslený summary.md, Report = report.html v sandboxovaném iframe, Soubory = strom z `files` s prohlížečem textu/JSON/PNG.

### 2.6 Seznam běhů

```
Běhy      dnes 0,42 / 5,00 USD        scénář: vše ▾   stav: vše ▾                     ● 1 běží · 2 ve frontě
 ● 20260926-091502-ig-post-3c1f   ig-post   běží · krok 4/8 foto_prompt   0:07        0,0021
 ◌ 20260926-091540-ig-post-9a0e   ig-post   ve frontě (2.)
 ✓ 20260925-140311-ig-post-a1b2   ig-post   včera 14:03     17,5 s     0,0693     callback ✓
 ✗ 20260925-141502-ig-post-9f3c   ig-post   včera 14:15     4,4 s      0,0016     fail: stop_obrazek · callback nedoručen
 ✓ 20260925-120000-ukazka-0f0f    ukazka    včera 12:00     2,1 s      0          falešný běh
```
Sloupce ze `runs` (id, stav, cena, trvání, callback); scénář a čas z `run_id`. Běžící řádek se obnovuje (viz 4.8).

### 2.7 Agent

```
Agenti                     │ copywriter                                   Form | Markdown    Uloženo ✓
 copywriter                │ popis    [Copywriter pro IG značky THTD               ]
 photographer              │ model    [chytry ▾]   anthropic/claude-haiku-4.5
 publisher   ✗ 1 chyba     │ skilly   [thtd-hlas ×] [+]
                           │ MCP      ☑ instagram: ☑ create_media ☑ publish_media     ☐ filesystem (vlastník nepovolil)
                           │ limity   max_turns [6]   budget_usd [0,20]   timeout [5m]
                           │ ── Instrukce (system prompt) ──────────────────────────────────────
                           │ Jsi copywriter značky THTD …
                           │ Používá: ig-post (copy) · ig-text (napis)
```
Jméno = název souboru, jen ke čtení (přejmenování = samostatná akce s kontrolou odkazů). MCP nabízí jen servery, kde je agent v `agents` v mcp.yaml; ostatní ztlumené s důvodem. `max_turns` se zvýrazní jako povinný, jakmile je zaškrtnutý server.

### 2.8 Config

```
Config   config.yaml · mcp.yaml                                                    Form | YAML   Uloženo ✓
 OpenRouter   klíč z proměnné [OPENROUTER_API_KEY]  ✓ nastavena na serveru     Jev model [jev-1.13]
 Modely       chytry         anthropic/claude-haiku-4.5     native_schema   max_tokens –    používá 3 agenti
              rychly         google/gemini-3.5-flash-lite   tool_wrapper
              gemini-image   google/gemini-3.1-flash-image                                  + alias
 Úložiště     r2 ▾   bucket [thtd-posts]   veřejná URL [https://files…]   proměnné R2_ACCOUNT_ID ✓ …
 Limity       na běh [1,00] USD · obrázky [0,30] · čas [1h] · hloubka call [3] · souběžně [2] · denně [5,00]
 Webhook      token z proměnné [WEBHOOK_TOKEN] ✓        Callback   tajemství z proměnné [CALLBACK_SECRET] ✓
 MCP servery  instagram   http · agenti: publisher · scénáře: ig-publish · nástroje: create_media, publish_media
```
Pole `_env` ukazují jen jméno proměnné; hodnota se nikde nezobrazí ani needituje. „používá N agentů“ brání smazání aliasu, který je v užití.

### 2.9 Skill

```
Skilly            │ thtd-hlas                                                          Uloženo ✓
 thtd-hlas        │ popis   [Tón a slovník značky THTD pro texty na sociální sítě]
 ig-pravidla      │ ── Text skillu ───────────────────────────────────────────────────
                  │ Tykáme. Krátké věty. …
                  │ Používají: copywriter · publisher
```

## 3. Inventář komponent

| Komponenta | Obsah | Stavy |
|---|---|---|
| `StepCard` | dvouřádková pilulka: eyebrow `TYP · id` + hodnota tučně (tabulka v §2.3); číslo v kruhu 36 px; vpravo `když` / v běhu čas + cena; chyba pod kartou | výchozí, hover, vybraná (ring s mezerou), s chybou, sbalená; v běhu stavová ikona místo čísla, nedošlo (40 % opacity) |
| `DeleteButton` | červený kulatý 28 px vně pilulky | hover / focus-within / trvale na dotyku |
| `ScenarioCard` | `IconChain` (max 5 + „+N“), stavový čip posledního běhu vpravo nahoře, ⋯, titulek = description, meta řádek, patička soubor + poslední běh | výchozí, hover, s chybami validace |
| `ProjectCard` | dostupnost, jméno, cesta mono, patička počty + dnešní útrata + poslední běh | dostupný; nedostupný 50 % + čárkovaný prstenec + důvod |
| `AddCard` | čárkovaná karta s +; scénář → dialog Nový scénář (čtecí fáze: CLI příkaz s kopírováním); projekt → CLI příkaz s kopírováním | |
| `IconChain` | ikona typu v zaobleném čtverci 32 px, šipka → mezi nimi, pořadí souboru | |
| `HeaderCard` | vstupy a výstupy scénáře | jako karta, nesmazatelná, vždy první |
| `Connector` + `AddButton` | šipka ↓ jako glyph mezi pilulkami (mezera ~40 px), na hover/focus se promění v (+) 28 px; trvalé (+) jen na konci každého seznamu | výchozí, focus, „vložit vyjmutý krok“ |
| `BranchColumn` / `CaseSection` | větev `parallel` vedle sebe / případ `switch` pod sebou, každý s vlastním seznamem a + | aktivní, v běhu přeskočená (ztlumená s důvodem) |
| `TypePicker` | prostý seznam vpravo od + (bez ikon a nadpisů skupin, dvě hairline), klíčové slovo mono + 2–4 slova popisu šedě; `bg-zinc-800 ring-1 ring-zinc-700 rounded-xl p-1 w-60`, řádek `h-9 px-3 rounded-lg`, zvýrazněný `bg-zinc-700`; `role="listbox"` | `output` se nenabízí; po Vyjmout navíc „Vložit … sem“ |
| `StepPanel` | plovoucí zaoblený panel (16 px, okraj 16 px od hran), eyebrow „KROK n“ + typ jako select, koš a ×; pole typu nahoře; dole tři sbalené řádky Podmínka / Spolehlivost / Podrobnosti kroku jako akordeon (`h-12 text-[15px]`, hodnota `text-zinc-400`, `divide-y divide-zinc-700`, `aria-expanded`) | čtení, editace, s chybami; v běhu záložky Prompt/Odpověď/Výstup/Volání/Soubory |
| `FormYamlToggle` | tmavá segmentová pilulka Form / `<>` YAML jako v Buzz, v lepící horní liště editoru: `bg-zinc-800 rounded-full p-0.5`, segment `px-3 h-8 rounded-full text-sm`, aktivní `bg-zinc-700 text-zinc-100`, neaktivní `text-zinc-400` s ikonou `code-xml` 14 px; `role="radiogroup"`; u agentů a skillů druhý segment `<> Markdown` | syntaktická chyba YAML = návrat do Form zakázán s nápovědou (řádek) |
| `YamlEditor` | blok přes celou šířku a výšku: `bg-zinc-800/60 ring-1 ring-zinc-700 rounded-xl p-4 font-mono text-sm leading-6`, čísla řádků `text-zinc-500`, chybový řádek `border-l-2 border-rose-400 bg-rose-500/5`; pod blokem nápověda se jménem souboru (`text-zinc-400 text-xs mt-2`) a seznam chyb 13 px | bez chyb, se syntaktickou chybou (Form zakázán), s významovými chybami |
| `Button` | primární = světlá pilulka (`bg-zinc-100 text-zinc-900`), sekundární = tmavá pilulka (`bg-zinc-800 text-zinc-100`), drobná „+ Přidat …“ pilulka vpravo od štítku sekce (jako „+ Add header“) | výchozí, hover, focus, disabled |
| `StatusBadge` | ikona + text: ✓ úspěch, ✗ chyba, ○ přeskočeno, ● běží (pulz), ◌ ve frontě, ⚠ varování, zrušeno | nikdy jen barva |
| `CostChip`, `DurationChip` | `0,0015 USD` (čárka, ≥ 4 místa, nula = `0`, `USD` za číslem s pevnou mezerou), `17,5 s` / `1 min 12 s`; mono | u obrázků „z toho obrázky …“ v hlavičce |
| `ExprInput`, `TemplateInput` | mono pole; našeptávač `inputs.` a `steps.<id>.<pole>` jen pro kroky nad a ve stejné větvi | chyba s hláškou a stříškou `^` ze serveru |
| `ValidationError` | text pod polem + červená tečka u karty + počet v hlavičce „Neuloženo · 2 chyby“ (klik = skok na první) | |
| `ConflictBar` | sticky pruh nad kartami | viz 4.6 |
| `EmptyState` | jedna věta + jedna akce + CLI ekvivalent (`agencast new scenario …`) | projekt bez scénářů, bez běhů, běh ve frontě, nedostupný projekt |
| `Skeleton` | 3 šedé pilulky kroků / 5 řádků tabulky; žádné spinnery mimo tlačítka | |
| `ServerBar` | „Server agencast neodpovídá (localhost:8787), zkouším znovu…“, 401 „Token serveru nesedí“, 422 config s odkazem na Config | |

## 4. Interakce

1. **Vložení kroku:** klik na + (nebo Enter na fokusovaném +) otevře `TypePicker` — prostý seznam vpravo od + jako v Buzz (bez místa se překlopí vlevo), bez ikon a nadpisů skupin, skupiny drží jen dvě hairline; klíčové slovo typu mono (přesně to, co bude v YAML) a 2–4 slova popisu šedě na stejném řádku, aby začátečník rozeznal `jev` od `ask`. Šipky, Enter, Esc, psaní filtruje (`j` skočí na jev). Po „Vyjmout“ je nahoře navíc položka „Vložit ‚kontrola‘ sem“. Výběr vloží kartu s id `<typ>_<n>` a otevře panel. `output` v seznamu není: jde jen na konec hlavního seznamu, přidá se nabídkou na konci, když chybí; + pod ním není. Ve větvi se `output` nenabízí.

```
   (+)  ┌──────────────────────────────────────┐
        │ Vložit „kontrola“ sem                │   jen po Vyjmout
        │ ──────────────────────────────────── │
        │ ask       jedno volání agenta        │   zvýrazněná
        │ task      agent s nástroji           │
        │ jev       levné rozhodnutí Jev       │
        │ image     vygenerovat obrázek        │
        │ ──────────────────────────────────── │
        │ parallel  větve zároveň              │
        │ switch    jedna z možností           │
        │ call      spustit jiný scénář        │
        │ fail      zastavit běh s chybou      │
        │ ──────────────────────────────────── │
        │ set       spočítat hodnoty bez LLM   │
        └──────────────────────────────────────┘
```
2. **Přesun:** menu ⋯ na kartě „Posunout nahoru/dolů“ (klávesy Alt+↑/↓) uvnitř seznamu. Mezi seznamy (do větve, ven): „Vyjmout“ (Ctrl+X), poté každé + nabídne „Vložit ‚kontrola‘ sem“. Bez drag & drop. Odkaz na krok níž po přesunu chytí validace u karty.
3. **Mazání:** ⋯ → Smazat nebo klávesa Delete. Když krok čte jiný krok (`refs`) nebo má vnořené kroky: modál „Krok ‚kontrola‘ čtou stop a out. Smazat i tak?“ / „Smaže i 3 kroky uvnitř“. Jinak hned, s „Vrátit zpět“ v hlavičce (Ctrl+Z, dokud není uloženo).
4. **Uložení:** výslovně tlačítkem nebo Ctrl+S, žádný autosave (soubor je pravda, rozdělaný stav nesmí na disk). Během editace validace přes server s prodlevou 500 ms, chyby u karet a polí. Uložit posílá celý text s otiskem verze; 422 = soubor se nezapsal, hlavička „Neuloženo · N chyb“, skok na první; varování zastarávání uložit dovolí. Odchod s neuloženými změnami se ptá. Rozpracovaný text drží `localStorage` (klíč soubor + otisk) pro případ obnovení stránky. *Odchylka (ui část 2):* GUI YAML nesestavuje, proto se v režimu Form validuje až při Uložit (chyby nesou odpovědi operací) a průběžně (`POST …/validate` s textem) jen v režimu YAML.
5. **Form / YAML:** jeden zdroj = surový text souboru; úpravy z formuláře jsou cílené záplaty do textu, aby přežily komentáře a pořadí (ig-post.yaml má číslované komentáře). YAML režim nahradí sloupec karet i panel jedním blokem přes celou šířku a výšku, jako v Buzz:

```
← thtd / Scénáře    ig-post ✎  Návrh IG příspěvku ke schválení ✎     [Form | <> YAML]     Neuloženo · 1 chyba   [Uložit]
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│  1  version: 1                                                                             │
│  2  name: ig-post                                                                          │
│  …                                                                                         │
│ 52    - id: foto_prompt                                                                    │
│ 53      ask:                                                                               │
│▌54        agent: fotograf                                                                  │
│ 55        prompt: |                                                                        │
│  …                                                                                         │
└────────────────────────────────────────────────────────────────────────────────────────────┘
Upravuješ přímo soubor workflows/scenarios/ig-post.yaml. Uloží se až tlačítkem Uložit.
✗ řádek 54 · krok foto_prompt · agent „fotograf“ neexistuje (dostupní: copywriter, photographer, publisher)
```
   - Odchylka od Buzz: úzký šedý sloupec s čísly řádků, protože hlášky `validate` i chyby YAML loaderu (duplicitní klíč) odkazují na řádek. Zvýraznění syntaxe jen dvěma odstíny (klíče světle, komentáře ztlumeně), žádné barvy.
   - Nápověda pod blokem jmenuje soubor (připomínka „soubor je pravda“), ne obecnou větu.
   - **Chyby:** při psaní (500 ms) `POST validate`; chybný řádek má vlevo svislou rose značku, pod blokem seznam chyb (řádek · krok · hláška), klik skočí na řádek. Syntaktická chyba YAML se ukáže hned s řádkem a blokuje návrat do Form (přepínač ztlumený, tooltip „Oprav YAML: řádek 12“); významové chyby (neznámý agent) návrat neblokují, zobrazí se na kartách. Uložit je zakázané, dokud je jakákoli chyba.
   - Přepnutí Form → YAML položí kurzor na řádek `- id:` vybraného kroku a na chvíli podbarví jeho řádky; hlavičková karta vede na začátek souboru. YAML → Form: znovu vybere krok, ve kterém stál kurzor.
   - Totéž pro Config (`config.yaml`; `mcp.yaml` jako druhý blok pod ním), pro agenty a skilly je druhý segment `<> Markdown` a blok ukazuje celý soubor včetně frontmatteru.
6. **Konflikt souboru:** GUI si drží otisk; kontrola při fokusu okna a každých 5 s. Změna na disku bez lokálních úprav = tiché znovunačtení + krátká hláška „Načteno z disku (14:05)“. S lokálními úpravami sticky pruh: „Soubor se na disku změnil“ [Zobrazit rozdíl] [Načíst z disku a zahodit moje změny] [Ponechat moje]; Uložit pak vyžaduje potvrzení „Přepsat verzi na disku“. Nikdy automatické slučování.
7. **`call`:** karta ukazuje cílový scénář a počet vstupů; „otevřít“ načte cílový scénář v témže editoru s drobečky `ig-post › navrh › ig-text`, zpět vrací na kartu. Cíl bez `callable: true` = chyba u karty s odkazem na hlavičku cílového scénáře. V běhu se `call` rozbalí přímo v kartě na vnořené karty se stavem.
8. **Živý běh:** dokud je běh `queued`/`running`, GUI čte `GET /runs/<id>` každé 2 s (po 2 min každých 5 s). Běžící karta pulzuje, uplynulý čas tiká lokálně mezi dotazy, cena v hlavičce roste. „Sledovat běh“ posouvá pohled na aktivní kartu. Po konci pruh „Běh skončil: úspěch/chyba“ a načtení Souhrnu. Seznam běhů se obnovuje každých 5 s, když něco běží. SSE později bez změny obrazovky.
9. **Změna typu kroku** v panelu: zachová id a `když`, ostatní pole zahodí; modál jen když by se vyplněná pole ztratila.

## 5. Vizuální principy (Tailwind) — podle screenshotu Buzz

- **Žebřík ploch podle Buzz:** stránka nejtmavší, pilulka kroku o stupeň světlejší, panel o další stupeň světlejší, vstupy uvnitř panelu zpět o stupeň tmavší s 1px linkou. Tailwind: stránka `bg-zinc-900` (nebo pozadí dashboardu), karta `bg-zinc-800/60`, hover `bg-zinc-800`, vybraná `bg-zinc-800 ring-1 ring-zinc-400/60 ring-offset-2 ring-offset-zinc-900`, panel `bg-zinc-800 rounded-2xl`, vstupy `bg-zinc-900 ring-1 ring-zinc-700`, větev/případ uvnitř kontejneru `bg-zinc-900/60`.
- **Žádný akcent.** UI je celé šedé jako Buzz. Barva zůstává jen stavům běhu (úspěch `emerald-400`, chyba `rose-400`, běží `sky-400` s pulzem, vypnout při `prefers-reduced-motion`, zrušeno/varování `amber-400`, přeskočeno `zinc-400` s čárkovaným prstencem) a chybám validace (`rose-400`). Výběr, fokus (`ring-zinc-300`) a odkazy (podtržení) jsou šedobílé.
- **Tvary, tři poloměry:** listová karta kroku `rounded-full` (56–64 px, číslo v kruhu 36 px), kontejnerové karty a panel `rounded-2xl`, vstupy a tlačítka `rounded-lg`; malé (+) kruh 28 px s `ring-1 ring-zinc-600`.
- **Text v pilulce:** eyebrow typu 11 px `uppercase tracking-wider text-zinc-400`, id 14 px semibold `text-zinc-100`, sekundární údaj 13 px `text-zinc-400`. Panel: štítky polí 12–13 px semibold nad polem, sbalené řádky 15 px. Nadpis obrazovky 18 semibold; jméno scénáře v hlavičce mono s tužkou (jako jméno workflow v Buzz). Mono i pro id, výrazy, `run_id`, ceny, YAML. Písmo dashboardu (Inter/system).
- **Rozestupy:** 8px škála; pilulka `px-5 py-3`, číslo v kruhu s mezerou 12 px od textu, šipka mezi pilulkami ve 40px mezeře, panel `p-5` s vnitřním rozestupem sekcí 20 px, okraj panelu od hran 16 px.
- **Šířky:** sloupec karet max 640 px centrovaný (Buzz má 380, u nás víc kvůli větvím `parallel` a sekundárním údajům); panel 400 px plovoucí; od 1100 px vedle sebe, pod tím panel jako vysouvací list (jediné místo se stínem).
- **Ikony typů** (lucide, 16 px, tah 1,5, vždy s textovým názvem typu): ask `message-square`, task `bot`, jev `scale`, image `image`, parallel `columns-2`, switch `split`, call `corner-down-right`, set `equal`, fail `octagon-x`, output `package-check`.
- **Nedělat:** akcentová barva na tlačítkách nebo výběru, rámečky kolem pilulek a sekcí (jen prstenec u vybrané), stíny, vnořené boxy nad dvě úrovně, linky místo šipek mezi kroky, víc než dva štítky na kartě, stav jen barvou, tooltip jako jediný nositel informace, 12px text na obsah, překryvné spinnery, modál tam, kde stačí panel.

- **Mřížka karet** (projekty, scénáře): `grid gap-4`, karta min 340 px, `bg-zinc-800/60 rounded-xl p-5`, karta + `ring-1 ring-dashed ring-zinc-600 bg-transparent`.
- **Ikony typů na kartách scénářů** v zaoblených čtvercích 32 px, `rounded-lg`. Buzz tu jako jediné místo používá modrou; totéž u nás: akcent (barva dashboardu Skynet Soul, jinak `bg-blue-500 text-white`) **jen** na tyto čtverce, všude jinde šedá.
- **Koš:** `bg-rose-500/15 text-rose-400 hover:bg-rose-500/25`; jediná červená v editoru vedle chyb validace.
- **Stavový čip na kartě scénáře:** ikona + text 12 px, `bg-zinc-900 rounded-full px-2`; barva jen ikona (emerald/rose/sky), text šedý.

## 6. Přístupnost a klávesnice

- Karty jsou tlačítka v seznamu: ↑/↓ přesouvají fokus, Enter/mezera otevře panel, Esc zavře a vrátí fokus na kartu, Delete maže (s ochranou), Alt+↑/↓ přesouvá, Ctrl+S ukládá, Ctrl+Z vrací.
- + je skutečné tlačítko v pořadí tabulátoru, viditelné i bez hoveru. Panel je `aside` s `aria-labelledby`; formulářová pole mají štítek nad polem, `aria-describedby` na nápovědu i chybu.
- Fokus `focus-visible:ring-2 ring-offset-2 ring-offset-zinc-950`; kontrast čitelného textu ≥ 4,5:1; stav vždy ikona + text (u samotné tečky `sr-only`); živý běh hlásí změny přes `aria-live="polite"` („krok foto běží“).
- `lang="cs"`, všechny řetězce v `locales/cs.json` (klíče typu `step.type.ask`, `run.status.skipped`), plurály ICU (`{n, plural, one {# krok} few {# kroky} other {# kroků}}`), čísla přes `Intl.NumberFormat("cs")`, časy lokálně s UTC v tooltipu.

## 7. Co GUI potřebuje od API navíc (mění, co jde postavit)

1. `GET` surového textu souboru s otiskem a `PUT` s otiskem (konflikt = 409), pro scénáře, agenty, skilly, config. *(0.5.0: `files` s `etag` = sha256, 409 při neshodě.)*
2. `POST …/validate` bez zápisu, chyby jako `{file, step, field, line, message}`.
3. `GET /projects/<p>/config` bez tajemství (+ volitelně příznak „proměnná nastavena“), tělo agenta a skillu.
4. V seznamu běhů `scenario`, `started_at` a u běžícího `current_step`; dnes jde jen odvodit z `run_id`.

## 8. Otázky pro uživatele a rozhodnutí

1. *První verze jen čtení, nebo hned editor?* — **Editor hned**; prohlížeč běhů je jeho čtecí režim (rozhodnuto 2026-09-26, uživatel chce editační variantu).
2. *Zachovat komentáře a pořadí v YAML?* — **Ano**, round-trip na serveru (agencast 0.5.0, ruamel.yaml), GUI posílá operace, ne text.
3. *Akcent ze Skynet Soul, nebo šedě jako Buzz?* — **Šedě jako Buzz**; barva jen pro stavy běhu a chyby a **jediné akcentové místo jsou čtverce ikon typů na kartách scénářů** (jako modré čtverce v seznamu Buzz), barva převzatá z dashboardu Skynet Soul. Pozadí a písmo také ze Soulu. (Doporučení designéra po snímcích, koordinátor přijal; uživatel může změnit.)
4. *Ukazovat, zda je proměnná prostředí nastavená (jen ✓/✗)?* — **Ano**, nikdy hodnotu. Vyžaduje bod 7.3.
5. *Spouštění běhu z GUI s formulářem vstupů?* — **Ano**, `POST /projects/<p>/runs` s volitelnou callback URL. Vyžaduje úpravu API.

Body 7.2–7.4 a 8.5 jdou do navazujícího úkolu „API doplňky pro GUI“ po 0.5.0.
