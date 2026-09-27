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
Projekty  (#/)                                   seznam z registru, sidebar jen se značkou
└ Projekt (#/p/thtd)                             sidebar: ← Projekty, jméno, navigace, útrata
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

### 1.1 Rozložení (shell, redesign V3 0.16.0)

```
┌ sidebar 232 px ───┐┌ hlavní oblast (canvas, obsah max. 1176 px, padding 32) ──────────────────┐
│ ◈ agencast        ││ ← Scénáře                                                                │
│ ← Projekty        ││ ig-post  ✗ 2 chyby                             [▷ Spustit] [Uložit]  ⋯   │
│ ───────────────── ││ Návrh IG příspěvku ke schválení                                          │
│ thtd              ││ [Form | <> YAML]   Neuloženo                                             │
│ ▣ Scénáře         ││                                                                          │
│   Agenti          ││   … obsah stránky (karty, panel, tabulka)                                │
│   Běhy            ││                                                                          │
│   Skilly          ││                                                                          │
│   Config          ││                                                                          │
│                   ││                                                                          │
│ Dnes utraceno     ││                                                                          │
│ 1,20 / 5,00 USD   ││                                                                          │
│ ▬▬▬───────        ││                                                                          │
└───────────────────┘└──────────────────────────────────────────────────────────────────────────┘
```
- `Shell` (`ui/src/components/Shell.tsx`): sidebar `bg-sidebar` s hairline vpravo, hlavní oblast `bg-canvas`,
  obsah max. 1176 px s paddingem 32 px (fidelity §1). Token screen je bez shellu.
- **Rozměry sidebaru** (fidelity §3, `V3 / ProjectSidebar`): šířka 232, padding 28 20, mezera 22. Značka
  `Layers2` 25 px `text-type` + „agencast“ 22 px semibold (`letter-spacing -0.7`). „← Projekty“ je řádek
  44 px (ikona 16, text 14 medium `fg-secondary`), pod ním oddělovač 1 px `line`, jméno projektu 14 semibold
  a položky navigace 44 px, radius 8, mezera 6, padding 0 14, ikona 16 `fg-muted`, text 14 medium
  `fg-secondary`; aktivní `bg-surface-active text-fg` s ikonou `fg`. Útrata: popisek 12 `fg-muted`, částka
  mono 12 medium, pruh 3 px na dráze `bg-track`.
- **Sidebar** nese kontext projektu (G5): značka (odkaz na Projekty), „← Projekty“, jméno projektu, navigace
  Scénáře · Agenti · Běhy · Skilly · Config (`nav` „Části projektu“, aktivní položka `aria-current="page"`;
  editor scénáře patří pod Scénáře, detail běhu pod Běhy) a dole „Dnes utraceno 1,20 / 5,00 USD“ s pruhem
  (zelený, po překročení denního limitu červený; bez limitu jen částka). Na stránce Projekty jen značka, na neexistující adrese značka a „← Projekty“.
  Řádek „server dostupný“ není (G6); při výpadku se dole objeví „Server agencast neodpovídá (…), zkouším
  znovu…“ (`role="alert"`, `data-testid="server-bar"`).
- **Pod 1024 px** se sidebar sbalí do horní lišty: značka + jméno projektu, pod nimi navigace vodorovně
  s přetečením; „← Projekty“ a útrata skryté. Položky navigace mají 44 px.
- **Responzivita obsahu** (ověřeno při 768 / 1024 / 1440 px): editor scénáře má panel vedle sloupce karet
  až od 1280 px (sidebar 232 + sloupec + panel 400); užší obrazovka ukáže panel jako list přes sloupec dole
  (max. 70 % výšky, od 1024 px odsazený od sidebaru), vždy se zavíracím křížkem a Esc. Agenti a Skilly mají
  seznam vedle editoru od 1100 px, jinak nad ním. Tabulka běhů má vodorovný posuv (min. 46rem), řádek
  modelového aliasu v Configu se zalomí. Menu ⋯ se otevírá doleva od tlačítka, rozbalený seznam chyb
  projektu má šířku nejvýš viewport − 2 rem.
- **Hlavička stránky** (`PageHeader`, `ui/src/components/PageHeader.tsx`, G1–G4, fidelity §1): nad titulem
  volitelně odkaz zpět; H1 32 px semibold (`letter-spacing -0.5`) + `meta` (čip chyb, stav běhu), pod ním
  jednořádkový popis 14 `fg-secondary` a `detail` (mono 13 `fg-muted`: cesta registru, run_id); vpravo
  nejvýš primární + jedno sekundární tlačítko (40 px) a menu ⋯ „Další akce“ se zbytkem (nebezpečné položky
  poslední) jako ikonové tlačítko `bg-control` 48 × 48 (v editoru 40 × 40); samostatné ikonové tlačítko
  hlavičky je `headerIconBtn` (48 × 48). Pod hlavičkou 24 px; druhý řádek pro přepínač režimu a stav
  uložení nebo záložky. V editoru a detailu běhu je hlavička přilepená a svou výšku
  hlásí v `--page-header-h` (podle ní se přilepí panel).
- Hlavičky podle stránky:
  - **Projekt:** titul = sekce („Scénáře“, „Agenti“, …), `meta` = čip „N chyb“ s rozbalovacím seznamem
    (odkazy na soubor a krok). V ⋯ je vždy první „Načíst znovu“. Bez cesty projektu, limitů a útraty. Blok
    chyby configu (422) zůstává pod hlavičkou. Hlavičku skládá `ProjectPage` (typ `SectionHeader`) a sekce
    do ní doplní své akce, položky ⋯ a druhý řádek; do načtení dat ji kreslí stránka sama:
    - Scénáře: „+ Nový scénář“ (primární).
    - Agenti / Skilly: „+ Nový agent“ / „+ Nový skill“ (sekundární) a Uložit (primární, Ctrl+S); ⋯ má
      přístupné jméno „Akce pro <jméno>“ a nese Přejmenovat (jen agent) a Smazat (červeně, poslední).
      Druhý řádek: Form | Markdown (jen agent) + stav uložení. Prázdná sekce má jen primární „+ Nový …“.
    - Config: popis = cesta projektu (mono, jediné místo mimo kartu projektu, G5), Uložit; druhý řádek
      Form | YAML + stav uložení.
    - Běhy: titul, `meta` = čip „2 běží · 1 ve frontě“ (mono 12 `running`, jen když něco žije) a ⋯.
  - **Editor scénáře:** „← Scénáře“ (+ drobečky přes `call`), titul = jméno scénáře mono, popis = `description`,
    akce Spustit (primární, Play) a Uložit (sekundární, Save, Ctrl+S); ⋯ 40 × 40: Vrátit zpět (Ctrl+Z), Kopírovat příkaz spuštění, Běhy tohoto
    scénáře, Přejmenovat, Smazat. Druhý řádek: Form | YAML + stav uložení s čipem chyb.
  - **Detail běhu:** viz 2.5.
  - **Neexistující adresa** (návrh V3 / 14): na střed ikona `MapPinX`, „404“ mono 64 `fg-muted`, titul
    „Tahle adresa v GUI neexistuje.“, věta „Vrať se na přehled projektů a pokračuj odtud.“ a primární
    „← Projekty“.
  - **Token serveru** (návrh V3 / 01): karta 420 px, radius 16, padding 32; značka, titul 28, nápověda,
    pole 44 px se zámkem a přepínačem Zobrazit/Skrýt token, chyba jako čip `text-error`, primární
    „✓ Uložit“ a pod ním adresa serveru mono 12.

## 2. Obrazovky

### 2.1 Seznam projektů (karty)

```
Projekty                                                                          [⟳] [+ Přidat projekt]
Spravuj projekty, scénáře a běhy agentů na jednom místě.
~/.config/agencast/projects.yaml
┌────────────────────────┐  ┌────────────────────────┐  ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┐
│ thtd                ⋯  │  │ ukazka              ⋯  │    stary-projekt       ⋯
│ ~/thtd                 │  │ ~/ukazka               │  │ /mnt/disk/stary        │
│                        │  │                        │    ⊘ nedostupný
│ [3 scénáře] [4 agenti] │  │ [1 scénář] [1 agent]   │  │ chybí workflows/       │
│ ────────────────────── │  │ ────────────────────── │    config.yaml
│ ✓ před 12 min dnes 0,42 USD│ bez běhů   dnes 0,00 USD│  └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┘
└────────────────────────┘  └────────────────────────┘
```
Hlavička (fidelity §4): titul, popis „Spravuj projekty, scénáře a běhy agentů na jednom místě.“, `detail` =
cesta registru (mono 13; celé „Registr …“ v `title`), ikonové „Načíst znovu“ 48 × 48 `bg-control` a
„+ Přidat projekt“ (bez práva zápisu registru otevře okno s CLI příkazem). Karta: `bg-surface`, radius 16,
padding 24, min. výška 260, mezera mřížky 20; jméno 20 semibold + ⋯, cesta mono 12 `fg-muted`, čipy počtů
(`bg-nested`, mono 12 `fg-secondary`), pod čarou čip posledního běhu a dnešní útrata mono 12 („dnes 1,20 USD“,
dvě místa, drobné částky pod 0,01 čtyři — `formatSpend`). Dostupný projekt nemá štítek (G6); nedostupný má štítek „nedostupný“,
důvod a čárkovaný okraj bez plochy (bez průhlednosti: text by měl kontrast pod 4,5:1). Celá karta je odkaz. ⋯: Otevřít, Kopírovat cestu, Odebrat z registru
(poslední, nebezpečná). Čárkovaná karta „Přidat projekt“ jen u prázdného seznamu (G8).

### 2.2 Přehled projektu (karty scénářů)

```
Scénáře                                                             [+ Nový scénář]  ⋯
┌───────────────────────────────────┐  ┌───────────────────────────────────┐
│ ▭ ⚖ ⊗ ▭ ⚖ +3                    ⋯ │  │ ⚙ ▣                             ⋯ │
│                                   │  │                                   │
│ ig-post                           │  │ ig-publish                        │
│ Návrh IG příspěvku ke schválení    │  │ Publikace schváleného příspěvku    │
│ 8 kroků · 2 agenti                │  │ 3 kroky · 1 agent (volatelný)      │
│                                   │  │                                   │
│ (✓ před 12 min)          Otevřít ↗ │  │ (✗ 2 chyby)              Otevřít ↗ │
└───────────────────────────────────┘  └───────────────────────────────────┘
```
- Titulek = jméno scénáře (20 px semibold); `description` je podtitul 14 px `fg-secondary`, nejvýš 2 řádky, celý v `title`. Karta (fidelity §5): plný `surface`, hover `surface-hover`, rádius 16, padding 24, min. výška 290, mezera mřížky 20.
- Řetězec ikon = typy kroků v pořadí souboru jako **prosté ikony 16 px `text-type`, mezera 12, bez koleček a šipek**, nejvýš 5, pak „+N“ mono 12 `fg-muted`; `parallel`/`switch` jednou svou ikonou, vnitřek se nerozepisuje. Vpravo menu ⋯.
- Meta řádek mono 12 `fg-muted` „N kroků · N agentů“ (počet, ne jména) a případný čip „volatelný“ (`nested`, text `type`). Spodní řádek: vlevo čip posledního běhu (jako na kartě projektu), chyby validace mají přednost („✗ 2 chyby“); vpravo „Otevřít ↗“ 14 medium `fg` — jen vizuální výzva, odkazem je celá karta (titul). Počty vstupů a výstupů, název `.yaml` ani druhý čas se neukazují.
- ⋯: Otevřít, Běhy tohoto scénáře, Kopírovat příkaz spuštění, Validovat; později Duplikovat, Smazat.
- Tlačítko „+ Nový scénář“ je v hlavičce sekce (G8); čárkovaná karta otevírá stejný dialog jen v prázdném seznamu.
- „Chyby validace“ v hlavičce = součet `errors` všech souborů; klik otevře seznam s odkazy na soubor a krok.

### 2.3 Editor scénáře (karty + panel)

```
← Scénáře
ig-post                                                          [▷ Spustit] [Uložit]  ⋯
Návrh IG příspěvku ke schválení
[Form | <> YAML]   Neuloženo · ✗ 1 chyba

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
Pilulka (fidelity §6): `surface`, výška 96, padding 20 24, mezera 16; hover `surface-hover`, výběr `surface-active` + `ring-1 ring-accent` bez offsetu. Vlevo pořadové číslo mono 12 `fg-muted` (mimo kolečko), pak kolečko `nested` 40 px s ikonou typu 18 px `type`. Texty: řádek `typ · id` mono 12 `type` malými písmeny (+ případná chybová tečka), titul 16 px semibold `fg` (prázdný krok „doplň v panelu“ normal `fg-muted`), třetí řádek mono 12 `fg-muted` s doplňkem a podmínkou `· když …` (podmínka už není vpravo). Vpravo ⋯ uvnitř pilulky. V běhu je v kolečku stavová ikona a vpravo mono „12,4 s · 0,0210 USD“ nad textem stavu 12 `fg-muted`. Nový krok dostane id `<typ>_<n>`. Titul a třetí řádek podle typu (`steps.ts` `stepLines`):

| Typ | Titul | Třetí řádek |
|---|---|---|
| ask, task | „prompt…“ | agent |
| jev | „první otázka“ | typ · „+1 otázka“ |
| image | „prompt…“ | alias · poměr stran · kvalita · rozlišení |
| call | `→ ig-text` | N vstupů |
| set | jména hodnot | — |
| fail | zpráva | — |
| parallel | `kratka ∥ dlouha` (kontejner) | N větví, běží zároveň |
| switch | `podle steps.kontrola.druh: produkt, akce, jinak` (kontejner) | — |
| output | jména výstupů | — |

**Konektor:** šipka ↓ 16 px `fg-muted`, výška 40, se při hoveru nebo fokusu promění v (+) 28 px `control`; vyjmutý krok drží (+) viditelné s `ring-accent`. Pod hlavním sloupcem jsou sekundární tlačítka 40 px „+ Přidat krok“ a „+ output“ vedle sebe na střed; na konci větví zůstává trvale viditelné (+). TypePicker: `surface` r12, položky 40 px, klíčové slovo mono 13 `fg` + popis 13 `fg-muted`, aktivní `surface-active`. Sloupec je 640 px, panel 420 px, mezera 32. Menu ⋯ má „Vložit krok nad / pod“. Kontejnerové karty (`parallel`, `switch`, `call`) mají obal a hlavní kartu s rádiusem `card`. V běhu stavová ikona nahradí číslo; běžící ikona pulzuje jen při povoleném pohybu, přeskočené a nedošlé kroky mají opacity 40 %.

**Koš vně pilulky:** červený kulatý 28 px vpravo vně (v mezeře 32 px mezi sloupcem a panelem), zobrazí se při hoveru a při `focus-within`. Klávesnice: Tab z fokusované karty přejde na koš (je další zastávkou v pořadí, při fokusu se ukáže), nebo klávesa Delete na kartě; `aria-label="Smazat krok kontrola"`. Na dotykovém vstupu (`pointer: coarse`) je koš viditelný trvale ztlumeně. Ochrana mazání z §4.3 platí beze změny. Hlavičková karta koš nemá.

**Panel** (V3: `bg-surface`, rádius panel 16, padding 20; od 1280 px přilepený vedle sloupce pod hlavičkou, užší obrazovka = list dole přes sloupec se zavíracím křížkem, viz §1.1):

```
┌ KROK 2 · JEV                               🗑   ✕ ┐
│ kontrola                                          │
│                                                   │
│ Typ kroku                                         │
│ [jev                                         ▾]   │
│ State                                             │
│ [{{ steps.copy.caption }}                    ]    │
│ Otázky                          [+ Přidat otázku] │
│  [on_brand                                ]   🗑  │
│  [noul ▾]  Instrukce [Odpovídá text tónu…  ]      │
│ ───────────────────────────────────────────────── │
│ Podmínka                                 vždy  ›  │
│ ───────────────────────────────────────────────── │
│ Spolehlivost                          výchozí  ›  │
│ ───────────────────────────────────────────────── │
│ Podrobnosti kroku                    kontrola  ›  │
└───────────────────────────────────────────────────┘
```
- **PanelShell** (redesign V3, fidelity §7): padding 24, mezera polí 20; eyebrow mono 11 px verzálky `letter-spacing 0.08em` `fg-muted` „KROK n · TYP“ (zároveň přístupné jméno panelu), titul 20 semibold = id kroku (mono), vpravo koš (ghost 32 px, červený) a zavřít (ghost 32 px, i Esc). Typ kroku je první pole formuláře (select s volbami „ask · jedno volání agenta“ — mono klíč + popis), ne titul. Pole bez rámovaných info boxů, jedna nápověda 12 px pod polem (G11). Řádky map (otázky Jev, hodnoty `set`, vstupy/výstupy hlavičky) jsou oddělené hairline: klíč (`KeyInput`, mono) + odebrat (`Trash2`), pod tím pole; „+ Přidat …“ jako pilulka u štítku.
- **Hlavička scénáře** (`HeaderPanel`, eyebrow „HLAVIČKA“, titul = jméno scénáře mono jako u panelu Spustit): popis, Vstupy a Výstupy jako řádky (jméno inline, typ, u vstupu povinný / výchozí hodnota, popis, odebrat) a přepínač „Volatelný“ s vysvětlením pod ním.
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
Pravidlo pro začátečníka: **vedle sebe = zároveň, pod sebou = jedna z možností.** Kontejner (fidelity §6): obal `surface` rádius 16, padding 16; hlavní karta jako běžná (bez vlastní plochy), šipka sbalit 20 px vpravo vedle ⋯. Větve a případy mají `nested` bez rámečku, rádius 12, padding 12, štítek mono 12 `fg-muted` a vlastní +; karty uvnitř mají výšku 72 bez pořadového čísla. `call` bez rozbalení je běžná pilulka s odkazem „otevřít ↗“ pod ní. Prázdný `default: []` se ukáže jako „jinak: nic“. Sbalení karty schová vnitřek a ukáže jen počet kroků.

### 2.5 Prohlížeč běhu na kartách (detail běhu)

```
← Běhy
ig-post 20260925-141502-ig-post-9f3c  ✗ chyba: fail v kroku stop_obrazek  falešný běh      4,4 s · 0,0016 USD
VSTUPY tema = „nová káva“ · pomer = „1:1“
Kroky · Souhrn · Report · Soubory                                                         ☐ sledovat běh
│ ✓ ① copy            ask · chytry → claude-haiku-4.5      3,7 s   0,0015 │ ┌ KROK 2 · kontrola · jev ✓ 0,3 s ────┐
│ ✓ ② kontrola        jev · on_brand = 0,91                 0,3 s   0,00002│ │ Odpověď · Vstup · Volání (1) · Soubory│
│ ○ ③ stop            fail · přeskočeno: when … → false                   │ │ on_brand   0,91  ▮▮▮▮▮▮▮▮▮▯          │
│ ✓ ④ foto_prompt     ask · rychly → gemini-3.5-flash-lite  1,8 s   0,0006 │ │ state  „Nová káva je tady…“          │
│ ✓ ⑤ kontrola_obrazku jev · skutecna_osoba = 0,8           0,3 s   0,00002│ │ model  typesafe/jev-1.13-20260917    │
│ ✗ ⑥ stop_obrazek    fail · Popis fotky porušuje pravidla…                │ │ 21 + 4 tokenů · 0,00002 USD          │
│ · ⑦ foto            image · nedošlo                                     │ └──────────────────────────────────────┘
│ · ⑧ out             output · nedošlo                                    │
```
Hlavička (G10, fidelity §8): titul = scénář mono 32 s ikonou ↗ (odkaz do editoru), pod ním run_id mono 13 `fg-muted`; vpravo čip stavu (+ „falešný běh“), mono „32,4 s · 0,0812 USD“ a sekundární „Otevřít scénář“. Vstupy jako karta `bg-nested` (min. 48 px): eyebrow „VSTUPY“ mono 11 + hodnoty mono 13 na jeden řádek (celé v `title`). Záložky podtržené přes celou šířku, „sledovat běh“ vpravo na stejné čáře. „Sledovat běh“ jen dokud běh žije; hláška „Běh skončil: …“ jen pro čtečku (`role="status"`), nápověda přerušeného běhu viditelná. Stejné karty jako v editoru: v kolečku je stavová ikona místo čísla, vpravo mono trvání · cena s tabulárními číslicemi. Přeskočené a nedošlé kroky jsou ztlumené na 40 %, běžící ikona pulzuje jen při povoleném pohybu. Panel podle typu: `ask`/`task` Prompt (prompt.md), Odpověď, Výstup (output.json), Volání (pokusy, tahy, tokeny, `finish_reason`, úroveň kaskády), u `task` navíc Nástroje (`tool_call`, nepovolené a neplatné argumenty zvýrazněné); `image` náhled + prompt; `jev` odpovědi s pravděpodobnostmi; `call` se rozbalí přímo v kartě na vnořené karty (`navrh/copy`); `set` hodnoty; `output` hodnoty + URL nahraných souborů. Přeskočený krok: důvod a „použit default“. Varování (`continued: true`) = `text-warning` trojúhelník + text pod kartou. Záložky: Souhrn = vykreslený summary.md, Report = report.html v sandboxovaném iframe, Soubory = strom z `files` s prohlížečem textu/JSON/PNG.

**Panel kroku v běhu** (redesign V3, fidelity §7): stejný PanelShell (eyebrow „KROK n · typ“, titul = cesta kroku mono). Řádek stavu: stavový čip + mono 12 „12,4 s · 0,0210 USD“ + „3 tahy · 2 volání nástrojů“ (`fg-muted`); pod ním text přeskočení / varování / chyby. Záložky jsou podtržené, výška 40, 14 medium (`role="tablist"`, aktivní `fg` + `border-accent`, neaktivní `fg-secondary`); „Volání (n)“ nese počet. Prompt, Výstup a Odpověď jsou blok kódu (hlavička 40 px s `{}` + názvem souboru mono 13 + čipem „Pouze čtení“, tělo `nested` s čísly řádků mono 12 `fg-muted`, rádius 12, patička „JSON · jen ke čtení“ + „Kopírovat“); soubory kroku jsou řádky `nested` 44 px (ikona + cesta mono 13 + ↗) vedoucí do záložky Soubory; odpovědi Jev = klíč mono, hodnota tabular, pruh 0–1 (`bg-nested` / `accent`); volání a nástroje jako řádky `bg-nested` s rádiusem control, chybové `bg-error/10` s červeným textem; obrázek se zaoblením; seznam souborů jako mono odkazy do záložky Soubory; prázdná záložka „Nic k zobrazení.“ Záložka **Soubory** v detailu běhu: strom vlevo v kartě `surface` r16 (položky 36 px, vybraný soubor `surface-active`), prohlížeč vpravo v kartě `surface` r16 padding 24 (blok kódu, obrázek; report beze změny v sandboxovaném iframe).

### 2.6 Seznam běhů

```
Běhy  ∿ 1 běží · 2 ve frontě                                                              [⋯]
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ 🔍 Hledat scénář nebo ID běhu…            │ Všechny stavy ▾        │ Všechny scénáře ▾       │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
      SCÉNÁŘ / RUN_ID                 STAV              KDY                    TRVÁNÍ        CENA
┌ ◌  ig-post                          běží              krok 4/8 · foto_prompt  00:07   0,0021 USD  › ┐
│    20260926-091502-ig-post-3c1f                                                                   │
┌ ✗  ig-post                          chyba: fail v stop včera 14:15          4,4 s   0,0016 USD  › ┐
│    20260925-141502-ig-post-9f3c · falešný běh · callback nedoručen                                │
```
Fidelity §8: filtrační karta `bg-surface` radius 16 padding 12 — hledání (klientsky podle jména scénáře a
run_id), select stavu (klient), select scénáře (server `?scenario=`); filtr období z návrhu není. Záhlaví
sloupců mono 11 verzálky `fg-muted`. Řádek = karta `bg-surface` radius 12, výška 80, mezera 8, hover
`bg-surface-hover`, celý řádek odkaz: ikona stavu 20 px, jméno scénáře 15 semibold a pod ním run_id mono 12
(+ „falešný běh“, callback); stav jako text v barvě stavu (u chyby „chyba: <důvod>“); KDY, TRVÁNÍ
(„00:42“ od startu u běžících) a CENA („0,0812 USD“, `formatCost` vždy čtyři místa) mono 12; vpravo
chevron. Bez řádku útraty (je v sidebaru), G9. Tabulka
leží ve vodorovném posuvu. Běžící řádek se obnovuje (viz 4.8). Prázdný seznam: „Žádné běhy.“ s CLI řádkem; starší stránky tlačítkem
„Načíst další“.

### 2.7 Agent

```
Agenti  ✗ 1 chyba                                       [+ Nový agent] [Uložit]  ⋯
 copywriter          │ copywriter
 photographer        │ ┌ karta: [Form | <> Markdown]  Uloženo ✓ ──────────────────┐
 publisher  ✗ 1 chyba│ │ Popis *   [Copywriter pro IG značky THTD              ] │
                     │ │ Model *   [chytry — anthropic/claude-haiku-4.5 ▾]       │
                     │ │ Skilly    ☑ thtd-hlas                       SKILL.md  │
                     │ │           ☐ pruzkum                         SKILL.md  │
                     │ │ MCP       ☑ instagram · ☑ create_media                │
                     │ │           ☐ filesystem (vlastník nepovolil)            │
                     │ │ Limity    max_turns [6] budget_usd [0,20] timeout [5m]│
                     │ │ Instrukce [Markdown textarea, nejméně 12 řádků]        │
                     │ │ Používá   [ig-post / copy ↗] [ig-text / napis ↗]       │
                     │ └──────────────────────────────────────────────────────────┘
```
Jedna hlavička sekce (§1.1): „+ Nový agent“, Uložit a ⋯ „Akce pro copywriter“ (Přejmenovat, Smazat).
Druhý řádek Form | Markdown a stav uložení leží v kartě editoru (`bg-surface`, radius 16, padding 24).
Seznam agentů je vlevo (200 px od 1100 px, jinak nad editorem), položky mají 48 px, ikonu a aktivní ring;
jméno vybraného agenta je nad kartou jen jako nadpis (`h2`, mono), bez cesty souboru a bez druhého Uložit.
Jméno = název souboru, jen ke čtení (přejmenování = samostatná akce s kontrolou odkazů). MCP nabízí jen
servery, kde je agent v `agents` v mcp.yaml; ostatní ztlumené s důvodem. `max_turns` je podmíněně povinné:
při zaškrtnutém serveru dostane hvězdičku a nápověda pod polem to řekne. Skilly se vybírají checkboxy;
pořadí v souboru se při vypnutí a zapnutí ostatních položek zachová. Instrukce mají patičku „Podporuje Markdown“.

### 2.8 Config

```
Config                                                                      [Uložit]  ⋯
┌ karta: ~/thtd · [Form | <> YAML] Uloženo ✓ ─────────────────────────────┐
│ Připojení [OPENROUTER_API_KEY] ✓  │ Jev model [jev-1.13] jen ke čtení │
│ Modely                                        [+ Přidat alias]           │
│ ┌ chytry · anthropic/claude-haiku-4.5 · max_tokens · API ───────────┐ │
│ │ používá copywriter                         [Smazat alias disabled] │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│ Úložiště                            │ Webhook a callback              │
│ Limity                              │ Proměnné (stavové řádky)         │
│ MCP servery: vnořená karta, čip Pouze čtení                          │
└───────────────────────────────────────────────────────────────────────┘
```
Hlavička sekce má jediné Uložit; cesta projektu a jediný přepínač Form | YAML se stavem jsou na začátku
karty (YAML režim ukazuje `config.yaml` a pod ním `mcp.yaml`). Dvojice sekcí tvoří dva sloupce, modely
jsou přes celou šířku jako vnořené karty. Pole `_env` ukazují jen jméno proměnné; hodnota se nikde
nezobrazí ani needituje. Pod každým aliasem je meta „používá copywriter“ / „nepoužívá se“; používaný alias nejde smazat.
Na úzké obrazovce se řádek aliasu zalomí (pole ID drží nejmenší šířku). MCP servery jsou jen ke čtení
(„mění se jen v YAML režimu“), bez mcp.yaml věta „Projekt nemá mcp.yaml.“.

### 2.9 Skill

```
Skilly                                                  [+ Nový skill] [Uložit]  ⋯
Uloženo ✓
 thtd-hlas        │ thtd-hlas
 ig-pravidla      │ ┌ SKILL.md (Markdown editor s čísly řádků) ──────────────────────┐
                  │ │ ---                                                            │
                  │ │ name: thtd-hlas …                                              │
                  │ └────────────────────────────────────────────────────────────────┘
                  │ Používají: copywriter · publisher
```
Stejná hlavička jako Agent, bez přepínače režimu (skill je vždy celý SKILL.md); ⋯ má jen Smazat.

## 3. Inventář komponent

| Komponenta | Obsah | Stavy |
|---|---|---|
| `StepCard` | dvouřádková pilulka: eyebrow `TYP · id` + hodnota tučně (tabulka v §2.3); číslo v kruhu 36 px; vpravo `když` / v běhu čas + cena; chyba pod kartou | výchozí, hover, vybraná (ring s mezerou), s chybou, sbalená; v běhu stavová ikona místo čísla, nedošlo a přeskočeno ztlumené čárkovaným obrysem bez plochy a tlumeným textem (ne průhledností, kvůli kontrastu) |
| `DeleteButton` | červený kulatý 28 px vně pilulky | hover / focus-within / trvale na dotyku |
| `ScenarioCard` | `IconChain` (max 5 + „+N“) a ⋯ nahoře, čip posledního běhu s časem vpravo dole (chyby validace mají přednost), titul = jméno, podtitul = description, meta „N kroků · agenti“ + štítek „volatelný“ | výchozí, hover, s chybami validace |
| `ProjectCard` | jméno + ⋯, cesta mono, počty, pod čarou čip posledního běhu + dnešní útrata | dostupný bez štítku; nedostupný čárkovaný okraj bez plochy + štítek a důvod |
| `PageHeader` | H1 + `meta` + popis, vpravo nejvýš dvě tlačítka a ⋯ (`menu`, `menuLabel`), nad titulem `back`, druhý řádek `children` | přilepená (`sticky`, výška v `--page-header-h`) v editoru a detailu běhu |
| `AddCard` | čárkovaná karta s +; scénář → dialog Nový scénář (čtecí fáze: CLI příkaz s kopírováním); projekt → CLI příkaz s kopírováním | |
| `IconChain` | ikona typu v kolečku 28 px `bg-nested text-type`, šipka → mezi nimi, pořadí souboru | |
| `HeaderCard` | vstupy a výstupy scénáře | jako karta, nesmazatelná, vždy první |
| `Connector` + `AddButton` | šipka ↓ jako glyph mezi pilulkami (mezera ~40 px), na hover/focus se promění v (+) 28 px; trvalé (+) jen na konci každého seznamu | výchozí, focus, „vložit vyjmutý krok“ |
| `BranchColumn` / `CaseSection` | větev `parallel` vedle sebe / případ `switch` pod sebou, každý s vlastním seznamem a + | aktivní, v běhu přeskočená (ztlumená s důvodem) |
| `TypePicker` | prostý seznam vpravo od + (bez ikon a nadpisů skupin, dvě hairline), klíčové slovo mono + 2–4 slova popisu šedě; `bg-surface ring-1 ring-line rounded-[var(--radius-card)] p-1 w-60`, řádek `h-9 px-3 rounded-[var(--radius-control)]`, zvýrazněný `bg-surface-hover`; `role="listbox"` | `output` se nenabízí; po Vyjmout navíc „Vložit … sem“ |
| `StepPanel` | plovoucí zaoblený panel (16 px, okraj 16 px od hran), eyebrow „KROK n“ + typ jako select, koš a ×; pole typu nahoře; dole tři sbalené řádky Podmínka / Spolehlivost / Podrobnosti kroku jako akordeon (`h-12 text-[15px]`, hodnota `text-fg-muted`, `divide-y divide-line`, `aria-expanded`) | čtení, editace, s chybami; v běhu záložky Prompt/Odpověď/Výstup/Volání/Soubory |
| `Toggle` (`FormYamlToggle`) | segmentová pilulka `bg-nested` s paddingem 4 px; segment 32 px, aktivní `bg-accent text-ink`, neaktivní `text-fg-secondary`; `role="radiogroup"`; u agentů a skillů druhý segment Markdown | syntaktická chyba YAML = návrat do Form zakázán s důvodem v `title` a `aria-description` |
| `YamlEditor`, `CodeView`, `CodeBlock`, `Markdown` | hlavička s názvem a čipem, tělo `bg-nested` mono 13 px, čísla řádků mono 12 px, zvýraznění `surface-active`, patička s nápovědou/polohou nebo Kopírovat; Markdown používá `CodeBlock` | bez chyb, se syntaktickou chybou (Form zakázán), s významovými chybami |
| `Button` (`btn`) | výška 40 px, radius 10 px, padding 18 px; `primary`: `bg-accent text-ink`; `secondary`: `bg-control text-fg`; `icon`: 40 px, `iconLg`: 48 px; `danger`: `bg-error/15 text-error`; `ghost`: pouze text | výchozí, hover, focus, disabled |
| `StatusIcon`, `StatusBadge`, `StatusChip` | vždy ikona + text (u ikony text pro čtečku); čip `bg-nested`, padding 6×12 px, text mono 12 px v barvě stavu | `succeeded` → `success`; `failed` → `error`; `warning`, `cancelled`, `interrupted` → `warning`; `running` → `running` (pulz jen `motion-safe`); `queued`, `skipped`, `dry-run`, `none` → `neutral` |
| `Menu` | tlačítko ⋯ (`btn.icon`) a seznam `bg-surface ring-line` radius 12; položka 40 px, hover `surface-hover`; `MenuItem.danger` = `text-error`, `MenuItem.disabled` = důvod v `title`, `aria-disabled` | šipky pro pohyb, Esc zavře a vrátí fokus |
| `TabLinks`, `Collapsible` | záložky 40 px s podtržením 2 px `accent`; řádek akordeonu 48 px s oddělovačem, hodnota mono 12 px `fg-muted` | aktivní záložka `aria-current`, akordeon `aria-expanded` |
| `FormField`, `CodeInput`, `JsonInput`, `ValueInput` | štítek `fg-secondary` 13 px medium, nápověda `fg-muted` 12 px, chyba mono `error`; pole 44 px `bg-nested ring-line` radius 8 s fokusem `accent`; proměnné `variable` | invalid `ring-error`; našeptávač i menu proměnných ovladatelné klávesnicí; souborový vstup disabled |
| `Modal` | podklad `canvas/70`, panel `bg-surface` radius 16 s paddingem 24 px, akční tlačítka 40 px vpravo | Esc zavírá, Tab zůstává v dialogu, nebezpečná akce používá `btn.danger` |
| `CostChip`, `DurationChip` | `0,0015 USD` (čárka, ≥ 4 místa, nula = `0`, `USD` za číslem s pevnou mezerou), `17,5 s` / `1 min 12 s`; mono | u obrázků „z toho obrázky …“ v hlavičce |
| `ExprInput`, `TemplateInput` | mono pole; našeptávač `inputs.` a `steps.<id>.<pole>` jen pro kroky nad a ve stejné větvi; nabídka proměnných tlačítkem u pole | chyba s hláškou a stříškou `^` ze serveru |
| `ValidationError` | text pod polem + červená tečka u karty + počet v hlavičce „Neuloženo · 2 chyby“ (klik = skok na první) | |
| `ConflictBar` | v editoru scénáře poslední řádek přilepené hlavičky (panel vedle sloupce se řadí pod něj), u agenta a Configu sticky pruh nad formulářem | viz 4.6 |
| `EmptyState` | `bg-surface` radius 16, padding 32 px, ikona a text na střed, volitelně `CliLine` s příkazem | projekt bez scénářů, bez běhů, běh ve frontě, nedostupný projekt |
| `Skeleton`, `Loading` | pulzující bloky `bg-surface`; žádné spinnery mimo tlačítka | načítání seznamů a karet |
| `ServerBar` → sidebar | „Server agencast neodpovídá (localhost:8787), zkouším znovu…“ dole v sidebaru (`role="alert"`); 401 = obrazovka Token serveru; 422 config = blok pod hlavičkou projektu s odkazem na Config | |

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
4. **Uložení:** výslovně tlačítkem nebo Ctrl+S, žádný autosave (soubor je pravda, rozdělaný stav nesmí na disk). Během editace validace přes server s prodlevou 500 ms, chyby u karet a polí. Uložit posílá celý text s otiskem verze; 422 = soubor se nezapsal, hlavička „Neuloženo · N chyb“, skok na první; varování zastarávání uložit dovolí. Odchod s neuloženými změnami se ptá. Rozpracovaný text drží `localStorage` (klíč soubor + otisk) pro případ obnovení stránky. Form režim validuje rozpracovaný strom průběžně přes `POST …/render` (operace → text a chyby bez zápisu, API 0.8.0), YAML režim přes `POST …/validate` s textem; Uložit ve Form posílá jednu dávku `POST …/batch` (vše, nebo nic).
5. **Form / YAML:** jeden zdroj = surový text souboru; úpravy z formuláře jsou cílené záplaty do textu, aby přežily komentáře a pořadí (ig-post.yaml má číslované komentáře). YAML režim nahradí sloupec karet i panel jedním blokem přes celou šířku a výšku, jako v Buzz:

```
← Scénáře
ig-post                                                          [▷ Spustit] [Uložit]  ⋯
[Form | <> YAML]   Neuloženo · ✗ 1 chyba
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
   - **Chyby:** při psaní (500 ms) `POST validate`; chybný řádek má podklad `error/10` a vlevo svislou značku `error`, pod blokem seznam chyb (řádek · krok · hláška), klik skočí na řádek. Syntaktická chyba YAML se ukáže hned s řádkem a blokuje návrat do Form (přepínač ztlumený, tooltip „Oprav YAML: řádek 12“); významové chyby (neznámý agent) návrat neblokují, zobrazí se na kartách. Uložit je zakázané, dokud je jakákoli chyba.
   - Přepnutí Form → YAML položí kurzor na řádek `- id:` vybraného kroku a na chvíli podbarví jeho řádky; hlavičková karta vede na začátek souboru. YAML → Form: znovu vybere krok, ve kterém stál kurzor.
   - Totéž pro Config (`config.yaml`; `mcp.yaml` jako druhý blok pod ním), pro agenty a skilly je druhý segment `<> Markdown` a blok ukazuje celý soubor včetně frontmatteru.
6. **Konflikt souboru:** GUI si drží otisk; kontrola při fokusu okna a každých 5 s. Změna na disku bez lokálních úprav = tiché znovunačtení + krátká hláška „Načteno z disku (14:05)“. S lokálními úpravami sticky pruh: „Soubor se na disku změnil“ [Zobrazit rozdíl] [Načíst z disku a zahodit moje změny] [Ponechat moje]; Uložit pak vyžaduje potvrzení „Přepsat verzi na disku“. Nikdy automatické slučování.
7. **`call`:** karta ukazuje cílový scénář a počet vstupů; „otevřít“ načte cílový scénář v témže editoru s drobečky `ig-post › navrh › ig-text`, zpět vrací na kartu. Cíl bez `callable: true` = chyba u karty s odkazem na hlavičku cílového scénáře. V běhu se `call` rozbalí přímo v kartě na vnořené karty se stavem.
8. **Živý běh:** dokud je běh `queued`/`running`, GUI čte `GET /runs/<id>` každé 2 s (po 2 min každých 5 s). Běžící karta pulzuje, uplynulý čas tiká lokálně mezi dotazy, cena v hlavičce roste. „Sledovat běh“ posouvá pohled na aktivní kartu. Po konci pruh „Běh skončil: úspěch/chyba“ a načtení Souhrnu. Seznam běhů se obnovuje každých 5 s, když něco běží. SSE později bez změny obrazovky.
9. **Změna typu kroku** v panelu: zachová id a `když`, ostatní pole zahodí; modál jen když by se vyplněná pole ztratila.

## 5. Vizuální principy (Tailwind) — podle screenshotu Buzz

**Tokeny (V3).** Závazné názvy a hodnoty barev, písem a rádiusů jsou v [plánu redesignu, §1](redesign-plan.md#1-tokeny-kontrakt-pro-vsechny). Pravidla G7, G8 a G15 platí nad referenčními exporty.

- **Žebřík ploch:** stránka `bg-canvas`, karta a panel `bg-surface`, hover `bg-surface-hover`, pole, čipy a větve `bg-nested` s případným `ring-line`. Vybraná karta má `ring-2 ring-accent` bez offsetu. Bez průhledných ploch a `backdrop-blur`.
- **Barva:** primární text `fg`, popisky `fg-secondary`, meta `fg-muted`, ikony typů `type`; stav běhu má ikonu a text s barvami `success`, `error`, `running`, `warning` a `neutral`. Pulz jen `motion-safe`.
- **Tvary:** pilulka kroku `rounded-full` s kruhem 36 px, kontejner/karta scénáře `rounded-card`, panel `rounded-panel`, ovládací prvky `rounded-control`; malé (+) kruh 28 px s `ring-line`.
- **Text v pilulce:** typ 11 px uppercase, id mono 13 px `fg-secondary`, hodnota 14 px semibold `fg`, meta 13 px `fg-muted`. Mono i pro výrazy, `run_id`, ceny a YAML.
- **Rozestupy:** 8px škála; pilulka `px-5 py-3`, číslo v kruhu s mezerou 12 px od textu, šipka mezi pilulkami ve 40px mezeře, panel `p-5` s vnitřním rozestupem sekcí 20 px, okraj panelu od hran 16 px.
- **Šířky:** sloupec karet max 640 px centrovaný, panel přibližně 400 px; rozložení panelu řídí §2.3 a responzivita G14.
- **Ikony typů** (lucide, 16 px, tah 1,5, vždy s textovým názvem typu): ask `message-square`, task `bot`, jev `scale`, image `image`, parallel `columns-2`, switch `split`, call `corner-down-right`, set `equal`, fail `octagon-x`, output `package-check`.
- **Nedělat:** rámečky kolem pilulek a sekcí (jen prstenec u vybrané), stíny, vnořené boxy nad dvě úrovně, linky místo šipek mezi kroky, víc než dva štítky na kartě, stav jen barvou, tooltip jako jediný nositel informace, 12px text na obsah, překryvné spinnery.

- **Mřížka karet:** `grid gap-4`, karta min 340 px, `bg-surface rounded-card p-5`; čárkovaná karta je jen v prázdném seznamu.
- **Ikony typů na kartách scénářů:** kolečka 28 px `bg-nested text-type`, mezi nimi šipka `fg-muted`, pak případně čip `+N`.
- **Koš:** `bg-error/15 text-error hover:bg-error/25`.
- **Stavový čip na kartě scénáře:** ikona + text 12 px, `bg-nested rounded-full px-2`; barva jen ikona.

## 6. Přístupnost a klávesnice

- Karty jsou tlačítka v seznamu: ↑/↓ přesouvají fokus, Enter/mezera otevře panel, Esc zavře a vrátí fokus na kartu, Delete maže (s ochranou), Alt+↑/↓ přesouvá, Ctrl+S ukládá, Ctrl+Z vrací.
- + je skutečné tlačítko v pořadí tabulátoru, viditelné i bez hoveru. Panel je `aside` s `aria-labelledby`; formulářová pole mají štítek nad polem, `aria-describedby` na nápovědu i chybu.
- Fokus `:focus-visible` = `ring-2 ring-accent ring-offset-2 ring-offset-canvas` globálně v `index.css`; kontrast čitelného textu ≥ 4,5:1 (měření tokenů v plánu redesignu §1); stav vždy ikona + text (u samotné tečky `sr-only`); živý běh hlásí změny přes `aria-live="polite"` („krok foto běží“).
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
5. *Spouštění běhu z GUI s formulářem vstupů?* — **Ano**, `POST /projects/<p>/runs` s volitelnou callback URL. Vyžaduje úpravu API. Panel „Spustit běh“ (redesign V3): eyebrow „SPUSTIT BĚH“, titul = scénář; vstupy podle typu; „Režim běhu“ (eyebrow mono 11) jako dvě volitelné karty 72 px `nested` r12 s radiem uvnitř (Dry-run — jen plán, zdarma / Ostrý běh — volá modely a stojí peníze; vybraná má `ring-1 ring-accent`); „Limity“ (na běh, z toho obrázky, čas běhu, dnes utraceno / limit) jako řádky s oddělovači (štítek 13 `fg-secondary` vlevo, hodnota mono 13 vpravo) jen u ostrého běhu; varování v `bg-warning/10` s ikonou pro neuložené změny a vstup `file`; chyba API; vpravo sekundární „Zrušit“ (zavře panel jako ✕ a Esc) a primární „▷ Spustit dry-run“ / „Spustit ostrý běh“ / „Spouštím…“ (fidelity §7, 0.16.1; na úzké obrazovce pod sebou přes celou šířku).

Body 7.2–7.4 a 8.5 jdou do navazujícího úkolu „API doplňky pro GUI“ po 0.5.0.

Nabídka proměnných se inspiruje Webflow: tlačítko u výrazu a šablony otevře dostupné hodnoty a výběr vloží proměnnou na pozici kurzoru. Fialová označuje proměnnou, modrá zůstává typům kroků na kartách.
