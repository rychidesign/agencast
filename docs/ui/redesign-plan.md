# Redesign GUI podle návrhu V3 — plán implementace

Zdroj návrhu: `docs/ui/design/agencast-design.pen` (pen.dev, rámečky pojmenované `V3 · …`).
Reference pro workery (negitované, generuje se z `.pen` přes `pen interactive`):
`docs/ui/design/ref/png/*.png` (rámečky 1:1) a `docs/ui/design/ref/html/*.html` (export `html-tailwind`,
hodí se na přesné barvy, mezery a velikosti; třídy jsou s pevnými pixely, do kódu je nekopíruj).
Zadání, podle kterého návrh vznikl: `docs/ui/zadani-redesign-pen.md`.

Návrh je **náhled**, ne pixelová předloha. Obrazovky v něm jsou přeplněné a některé věci se opakují.
Cíl: nové rozložení s levým sidebarem, nové základní prvky a karty, a **vizuální zjednodušení**
podle pravidel v §2. Kde se návrh a pravidla v §2 rozcházejí, platí §2.

Co se nemění: routy (`#/…`), API, formát souborů, texty chyb z API, klávesové zkratky, chování
ukládání (etag, konflikt, validace před zápisem), přístupnost (stav = ikona + text, `aria-*`,
fokus). Spec v1 je zmrazená.

---

## 1. Tokeny (kontrakt pro všechny)

Tailwind 4, definice v `ui/src/index.css` v bloku `@theme`. Jména jsou závazná, ostatní úkoly
je používají jako třídy (`bg-canvas`, `text-fg-muted`, `ring-line`, `font-mono`, …).

| token | hodnota | použití |
|---|---|---|
| `--color-canvas` | `#0B1220` | pozadí stránky |
| `--color-sidebar` | `#0B1524` | pozadí sidebaru |
| `--color-surface` | `#172436` | karta, panel, menu, modál |
| `--color-surface-hover` | `#1D2D42` | hover karty / položky |
| `--color-nested` | `#0D192A` | pole, čip, blok kódu, vnořený prvek |
| `--color-line` | `#BDD9F026` | hairline, ring polí |
| `--color-fg` | `#EDF5FF` | primární text |
| `--color-fg-secondary` | `#B5C6DB` | popisky, štítky |
| `--color-fg-muted` | `#8497B0` | meta, nápověda (vlna C: z `#8194AD`, viz kontrast níže) |
| `--color-accent` | `#D2E4FA` | primární tlačítko, fokus ring, aktivní prvek |
| `--color-ink` | `#132236` | text na akcentu |
| `--color-success` | `#6ED5AB` | úspěch |
| `--color-error` | `#FF8F9D` | chyba, nebezpečná akce |
| `--color-warning` | `#EBC477` | varování, konflikt, přerušeno, zrušeno |
| `--color-running` | `#73BAFF` | běží |
| `--color-neutral` | `#A5B2C5` | čeká, přeskočeno, dry-run, bez běhu |
| `--color-variable` | `#D6A2FF` | proměnná (tlačítko `{}`, položky nabídky proměnných) |
| `--color-type` | `#8BDCDF` | ikona typu kroku |
| `--font-sans` | `"Inter Variable", Inter, system-ui, sans-serif` | text |
| `--font-mono` | `"JetBrains Mono Variable", ui-monospace, monospace` | id, cesty, výrazy, YAML, čísla |
| `--radius-control` | `8px` | tlačítka, pole |
| `--radius-card` | `12px` | karty, menu |
| `--radius-panel` | `16px` | panel, modál |

Velikosti: ovládací prvek 36 px (kompaktní 32, dotyk 44), ikona 16 px tah 1,5, písmo 12 (nápověda),
13 (štítek, mono, meta), 14 (tělo), 18 (nadpis), eyebrow 11 px verzálky. Fonty se bundlují
(`@fontsource-variable/inter`, `@fontsource-variable/jetbrains-mono`), žádné CDN — GUI běží
jen na Tailscale a musí fungovat offline.

Barvy `zinc-*` z kódu postupně mizí; nový kód je nepoužívá. Od vlny C v `ui/src` žádné `zinc-*` ani
napevno zapsané barvy nejsou (výjimka: bílé pozadí iframe `report.html` a barvy v testovacích fixture);
šipka selectu se kreslí gradientem z `var(--color-fg-muted)`, ne SVG s barvou.

Kontrast (WCAG 2.1, vlna C, 2026-09-28): `fg-muted` `#8497B0` má na `canvas` 6,3:1, `surface` 5,24:1,
`nested` 5,91:1 a `surface-hover` 4,67:1. Původní `#8194AD` měl na `surface-hover` jen 4,50:1 (4,496),
proto posun o 3 body jasu. `fg-secondary` ≥ 8,0:1, `error` ≥ 6,4:1, `warning` ≥ 8,4:1, `success` ≥ 7,8:1,
`running` ≥ 6,8:1, `neutral` ≥ 6,5:1 na všech plochách; `ink` na `accent` 12,4:1.

---

## 2. Pravidla zjednodušení (platí nad návrhem)

- **G1 Jedna hlavička na stránku.** H1 + volitelný jednořádkový popis + akce vpravo: nejvýš dvě
  viditelná tlačítka (primární + jedno sekundární) a menu ⋯ se zbytkem. Uvnitř karet a formulářů
  se název znovu neopakuje (žádné „Agent · pisatel“ pod hlavičkou „pisatel“, žádné
  `agents/pisatel.yaml`).
- **G2 Jedno Uložit.** Jen v hlavičce stránky. Žádný spodní řádek „Zrušit / Uložit změny“.
- **G3 Jeden přepínač režimu** (Form | YAML, Form | Markdown) v druhém řádku hlavičky, vedle stavu
  uložení (SaveNote). Ne znovu uvnitř formuláře.
- **G4 Sekundární akce do ⋯:** Přejmenovat, Smazat, Vrátit zpět (s nápovědou Ctrl+Z), Validovat,
  Kopírovat příkaz spuštění, Kopírovat cestu, Odebrat z registru, Běhy tohoto scénáře,
  Otevřít v YAML. Nebezpečné položky (Smazat, Odebrat) červeně a jako poslední.
- **G5 Kontext projektu žije v sidebaru:** logo, odkaz „← Projekty“, jméno projektu, navigace
  Scénáře · Agenti · Běhy · Skilly · Config, dole „Dnes utraceno 1,20 / 5,00 USD“ s pruhem.
  Hlavičky stránek jméno projektu ani cestu neopakují. Limity běhu („běh 2,00 USD · 300 s“) se v
  hlavičce nezobrazují (jsou v Config a v panelu Spustit). Cesta projektu je jen na kartě v
  Projektech a jako první řádek v Config.
- **G6 Stav jen když něco říká.** Karta dostupného projektu nemá štítek „dostupný“; nedostupný má
  štítek + důvod. Řádek „server dostupný“ se neukazuje; při výpadku se v sidebaru dole objeví
  „Server neodpovídá, zkouším znovu…“ (nahrazuje dnešní ServerBar, stejné `role="alert"`).
- **G7 Čas jednou.** Čip posledního běhu nese i čas („✓ před 12 min“); druhý údaj času na kartě
  scénáře se ruší. Na kartě scénáře je titul = jméno, podtitul = popis; přípona `.yaml` pryč.
  Meta řádek: „N kroků · agenti“; „volatelný“ jako malý štítek; počty vstupů/výstupů pryč.
- **G8 Přidání je tlačítko v hlavičce** („+ Přidat projekt“, „+ Nový scénář“, „+ Nový agent“).
  Čárkovaná karta se ukazuje jen jako prázdný stav (seznam bez položek).
- **G9 Seznam běhů** bez sloupce run_id (je v detailu) a bez řádku útraty (je v sidebaru).
  Zůstávají filtry, živý ukazatel „2 běží · 1 ve frontě“ a „Načíst další“.
- **G10 Detail běhu:** titul = scénář (odkaz), vedle malé mono run_id; badge stavu; trvání · cena;
  vstupy na jeden řádek; záložky; „sledovat běh“ jen dokud běh žije; hláška „Běh skončil: …“ jen
  pro čtečku (`sr-only`, `aria-live`); hint pro přerušený běh zůstává viditelný.
- **G11 Nápověda jednou a prostě.** Jedna nápověda pod polem, 12 px muted. Žádné rámované
  „info boxy“ pro to, co říká nápověda. Bez technických štítků u sekcí (`skills[]`, `mcp[]`,
  `system_prompt`, `providers`) — kdo chce klíče YAML, přepne do YAML.
- **G12 Sekce formuláře** = nadpis + pole. Žádné odznaky, počty ani „Používá se“ tlačítka; text
  „používají 2 agenti“ zůstává jako obyčejná meta věta.
- **G13 Zachovat** klávesové zkratky, `data-testid`, přístupná jména a role; testy měnit vědomě,
  ne kvůli náhodné změně textu.
- **G14 Responzivita.** Od 1024 px sidebar pevný 232 px. Pod 1024 px se sidebar sbalí do horní
  lišty (logo, jméno projektu, navigace vodorovně, ⋯). Dotykové cíle 44 px (`pointer-coarse`).
- **G15 Hustota.** Obsah max. šířka 1200 px; karta padding 20, rádius 12; panel rádius 16;
  žádný `backdrop-blur` (výkon na tabletu), povrchy plné barvy.

---

## 3. Vlny a vlastnictví souborů

Každý úkol má vlastní worktree z `main`. **Nikdo neupravuje soubory jiného úkolu.** Když je změna
jinde nutná, popíše ji v reportu a vyřeší ji vlna C.

Sdílené soubory, pravidla pro paralelní vlnu B:
- `ui/src/locales/cs.json`: nové klíče **jen na konec objektu**, nepřeskupovat; nepoužité klíče
  vlastního úkolu smazat.
- `framework/CHANGELOG.md`: odrážky pod nadpis `## 0.16.0 (nevydáno)` (založí vlna A), s prefixem
  oblasti („Shell:“, „Prvky:“, „Karty:“, „Panely:“). Verzi v `pyproject`/`__init__` nikdo nemění.
- `docs/ui/navrh-gui.md`, `docs/ui/uzivatelske-cesty.md`: jen odstavce své oblasti.
- E2E: nové testy do nového souboru `ui/e2e/redesign-<oblast>.spec.ts`; v existujících specech
  jen nezbytné změny asercí.

### Vlna A — tokeny (1 úkol, Codex Luna max)

`ui/src/index.css` (`@theme`, base: `body` = canvas/fg, fokus ring accent), fonty přes
`@fontsource-variable`, `ui/package.json`. Nic jiného nerestylovat. Založit `## 0.16.0 (nevydáno)`
v changelogu. Testy musí projít beze změn.

### Vlna B — 4 paralelní úkoly

| úkol | model | vlastní soubory |
|---|---|---|
| **B1 Shell a sidebar** | Claude Opus 5.5 high | `ui/src/App.tsx` (vč. TokenScreen, ServerBar → sidebar), nové `ui/src/components/Shell.tsx` (+ `Sidebar.tsx`, `PageHeader.tsx`), `ui/src/pages/Project.tsx`, `ui/src/pages/Projects.tsx` (vč. ProjectCard, dialogů), `ui/src/pages/Scenario.tsx` (hlavička, rozložení sloupec + panel), `ui/src/pages/Run.tsx` (hlavička, rozložení), `ui/src/pages/Runs.tsx` (filtry, RunRow), `ui/src/router.ts`, `ui/e2e/projekty.spec.ts`, docs §1–§2 rozložení |
| **B2 Základní prvky** | Codex Sol xhigh | `ui/src/components/ui.tsx`, `form.tsx`, `YamlEditor.tsx`, `CodeView.tsx`, `Markdown.tsx`, jejich vitest testy, docs §3 inventář |
| **B3 Karty a tok** | Codex Sol xhigh | `ui/src/components/StepCards.tsx`, `TypeIcon.tsx`, `TypePicker.tsx`, `RunBadge.tsx`, `ui/src/pages/Scenarios.tsx` (ScenarioCard, seznam), `ui/src/steps.ts`, `ui/src/run.ts`, jejich testy, docs §2.2–§2.4, §5 |
| **B4 Panely a formuláře** | Claude Opus 5.5 high | `ui/src/components/StepPanel.tsx`, `RunPanel.tsx`, `RunStepPanel.tsx`, `RunFiles.tsx`, `ui/src/pages/Agents.tsx` (seznam, EditorBar, formuláře), `ui/src/pages/Config.tsx`, jejich testy, docs §2.5, §8, cesty pro agenty/config |

B2 drží **stabilní exportované API** (`btn`, `StatusChip`, `Menu`, `Toggle`, `Modal`, `FormField`,
`CodeInput`, …), aby ostatní soubory dál fungovaly bez úprav. Přidávat smí (např. `MenuItem.danger`),
odebírat ne. Ostatní úkoly primitiva jen používají; nový prvek, který chybí, si napíšou lokálně
a napíšou to do reportu.

B1 vytvoří `PageHeader` (title, description, actions, menu) a použije ho na svých stránkách. Agenti
a Config na něj přejdou ve vlně C.

### Vlna C — integrace (1 úkol, Claude Opus 5.5 high)

Po sloučení B1–B4: sjednotit hlavičky (Agenti, Config na `PageHeader`), odstranit zbytky `zinc-*`,
projít všechny obrazovky proti §2, responzivita 768/1024/1440, doladit kontrasty, dopsat
`docs/ui/uzivatelske-cesty.md`, verze 0.16.0 (`pyproject`, `__init__`, `uv.lock`), changelog,
`npm run build`. Po tom koordinátor restartuje službu.

---

## 4. Hotovo znamená

- `npm run typecheck`, `npx vitest run`, `npm run e2e` procházejí ve worktree úkolu
  (E2E si spouští vlastní `agencast serve --fake`; žádné živé API).
- `uv run pytest -q` beze změny (UI úkoly framework nemění).
- Žádné nové závislosti kromě fontů (vlna A). Žádný CDN, žádný `backdrop-blur`.
- Report v `/tmp/agencast-<úkol>-report.md`: co se změnilo, rozhodnutí mimo zadání, co zůstalo
  jinému úkolu, výsledky testů, model a effort (ze stavového řádku agenta).
- Commit na vlastní větvi, bez merge do `main`, bez push.
