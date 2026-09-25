# Díl 3 — Rozhodování

**Čas:** asi 20 minut · **Útrata:** jeden ostrý běh za ~0,0007 USD
**Co budeš umět:** nechat Jev posoudit text (`noul`, `choice`, `score`),
podle výsledku krok přeskočit (`when`), běh záměrně ukončit (`fail`),
větvit (`switch`) a psát výrazy tak, aby jim framework rozuměl.

Předpoklad: díly 1 a 2 (agenti `tutorial-pojmenovavac`,
`tutorial-sloganista`, zkratka `maw`).

---

## Krok 1 — co je Jev

Jev je levný a rychlý „rozhodčí" (~0,00002 USD, ~0,5 s za volání).
Dostane text (`state`) a otázky a na každou vrátí hodnotu. Typy otázek:

| Typ | Vrací | Příklad hodnoty | Kdy |
|---|---|---|---|
| `noul` | číslo 0–1 = „jak moc ano" | `0.85` | ano/ne otázka |
| `choice` | klíč jedné z možností v `criteria` | `"hravy"` | výběr z pojmenovaných možností |
| `score` | číslo na stupnici 0…n (může být i mezi) | `0.64` | stupnice; `criteria` = popisy stupňů od 0 |

**Jev nikdy sám nerozhodne „ano" nebo „ne".** Vrátí číslo a práh (`< 0.5`)
píšeš ty, vždy výslovně ve scénáři. Žádný výchozí práh neexistuje.

---

## Krok 2 — scénář

Vytvoř `workflows/scenarios/tutorial-03-rozhodovani.yaml`:

```yaml
version: 1
name: tutorial-03-rozhodovani
description: Vymyslí název, nechá ho posoudit Jevem a podle tónu napíše slogan (tutoriál, díl 3)

inputs:
  produkt:
    type: string
    required: true
    description: Jaký produkt pojmenováváme

outputs:
  nazev:
    type: string
  ton:
    type: string
    description: Tón názvu podle Jevu (hravy / vazny)
  slogan:
    type: string
  zapamatovatelnost:
    type: integer
    description: Jak moc je název zapamatovatelný, v procentech

steps:
  # 1. Jeden název.
  - id: navrh
    ask:
      agent: tutorial-pojmenovavac
      prompt: "Vymysli jeden název pro tento produkt: {{ inputs.produkt }}."
      schema:
        nazev: string

  # 2. Jev název posoudí: ano/ne (noul), výběr (choice) a stupnici (score).
  - id: kontrola
    jev:
      state: "Produkt: {{ inputs.produkt }}. Navržený název: {{ steps.navrh.nazev }}"
      questions:
        zapamatovatelny:
          type: noul
          instructions: Je název snadno zapamatovatelný a dá se snadno vyslovit?
        ton:
          type: choice
          instructions: Jaký tón má navržený název?
          criteria:
            hravy: Hravý, vtipný, uvolněný
            vazny: Vážný, elegantní, věcný
        originalita:
          type: score
          instructions: Jak originální je navržený název?
          criteria:
            - Běžný, obyčejný název
            - Zajímavý název
            - Výjimečně originální název

  # 3. Práh je vždy výslovně ve scénáři.
  - id: stop
    when: steps.kontrola.zapamatovatelny < 0.5
    fail: "Název {{ steps.navrh.nazev }} není zapamatovatelný (zapamatovatelny = {{ steps.kontrola.zapamatovatelny }})"

  # 4. Podle tónu jiný slogan.
  - id: podle_tonu
    switch:
      value: steps.kontrola.ton
      cases:
        hravy:
          - id: slogan_hravy
            default: { slogan: "" }
            ask:
              agent: tutorial-sloganista
              prompt: "Napiš hravý, vtipný slogan pro produkt {{ inputs.produkt }} s názvem {{ steps.navrh.nazev }}."
              schema:
                slogan: string
        vazny:
          - id: slogan_vazny
            default: { slogan: "" }
            ask:
              agent: tutorial-sloganista
              prompt: "Napiš vážný, elegantní slogan pro produkt {{ inputs.produkt }} s názvem {{ steps.navrh.nazev }}."
              schema:
                slogan: string
      default:
        - id: neznamy_ton
          fail: "Neznámý tón: {{ steps.kontrola.ton }}"

  # 5. Proběhla jen jedna větev; druhá má výstup z default (prázdný text).
  - id: vysledek
    set:
      slogan: steps.slogan_hravy.slogan + steps.slogan_vazny.slogan
      procenta: round(steps.kontrola.zapamatovatelny * 100)

  - id: out
    output:
      nazev: "{{ steps.navrh.nazev }}"
      ton: "{{ steps.kontrola.ton }}"
      slogan: "{{ steps.vysledek.slogan }}"
      zapamatovatelnost: "{{ steps.vysledek.procenta }}"
```

Projdi nové věci:

### `jev`

- `state` — co Jev posuzuje (šablona). Dej mu i kontext (produkt), ne jen
  samotný název.
- `questions` — klíč = jméno výstupu (`steps.kontrola.zapamatovatelny`).
  Každá otázka má `type` a `instructions`; `choice` a `score` navíc
  `criteria`.
- `steps.kontrola.details.<otázka>` — co Jev vrátil navíc
  (pravděpodobnosti). Uvidíš v kroku 4.

### `when` + `fail`

`when` je **výraz** (bez `{{ }}`), který musí dát `true`/`false`. Když
dá `false`, krok se přeskočí. `fail` ukončí běh s chybou třídy `fail`
a tvou zprávou. Dohromady: „když je název nezapamatovatelný, skonči".

### `switch`

- `value` — výraz, který dá **text** (tady odpověď `choice`).
- `cases` — pro každou hodnotu seznam kroků.
- `default` — **povinný**: co dělat, když nic nesedí. Vědomé „nic" je
  `default: []`. Tady raději skončíme chybou.

Pro číselné prahy (`< 0.5`) používej `when`, ne `switch`.

### Proč mají kroky ve větvích `default`

Krok `vysledek` čte `steps.slogan_hravy` **i** `steps.slogan_vazny`, ale
proběhne jen jeden z nich. Výstup kroku, který neproběhl, je jeho
`default` — tady prázdný text. `slogan_hravy + slogan_vazny` tak dá vždy
ten jeden napsaný slogan. Bez `default` by `validate` scénář odmítl
(krok 6).

Tohle je obecný vzor: **různé výsledky podle větví se sjednotí v `set`
před `output`** (`output` smí být jen jeden, jako poslední krok).

---

## Krok 3 — fixtura pro Jev

`framework/tests/golden/tutorial-03-rozhodovani.yaml`:

```yaml
# Skriptované odpovědi pro tutorial-03-rozhodovani.
# Jev dostává answers: {otázka: hodnota}; u choice je hodnota klíč z criteria.
navrh:
  - json:
      nazev: "Ovesňák"
kontrola:
  - answers:
      zapamatovatelny: 0.835
      ton: hravy
      originalita: 1.4
slogan_hravy:
  - json:
      slogan: "Ovesňák — zmrzlina, co roste na poli"
```

Pro `slogan_vazny` odpověď nepotřebuješ — při `ton: hravy` se nezavolá.

```bash
maw validate workflows/scenarios/tutorial-03-rozhodovani.yaml
maw run workflows/scenarios/tutorial-03-rozhodovani.yaml -i produkt="veganská zmrzlina z ovesného mléka" --fake framework/tests/golden/tutorial-03-rozhodovani.yaml
```

```
v pořádku: tutorial-03-rozhodovani (9 kroků)
běh 20260925-151444-tutorial-03-rozhodovani-f56a: úspěch · 0,0 s · 0,0003 USD
záznam: ~/orca/workspaces/multiagent-workflows/tutorials/runs/20260925-151444-tutorial-03-rozhodovani-f56a/summary.md
```

`9 kroků` — počítají se i kroky uvnitř větví `switch`. Tabulka kroků
v `summary.md`:

```
| # | Krok | Typ | Stav | Čas | Cena | Poznámka |
|---|---|---|---|---|---|---|
| 1 | navrh | ask | ✓ | 0,0 s | 0,0001 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | kontrola | jev | ✓ | 0,0 s | 0,0001 | zapamatovatelny = 0,83, ton = hravy, originalita = 1,40 |
| 3 | stop | fail | přeskočeno |  |  | when: steps.kontrola.zapamatovatelny < 0.5 → false |
| 4 | podle_tonu | switch | ✓ | 0,0 s | 0,0001 | větev hravy |
| 5 | slogan_hravy | ask | ✓ | 0,0 s | 0,0001 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 6 | slogan_vazny | ask | přeskočeno |  |  | switch: podle_tonu = "hravy" |
| 7 | neznamy_ton | fail | přeskočeno |  |  | switch: podle_tonu = "hravy" |
| 8 | vysledek | set | ✓ | 0,0 s | 0,0000 |  |
| 9 | out | output | ✓ | 0,0 s | 0,0000 |  |

## Varování
žádná

## Výstup
- nazev: „Ovesňák"
- ton: „hravy"
- slogan: „Ovesňák — zmrzlina, co roste na poli"
- zapamatovatelnost: 84
```

Všimni si:

- **Každý přeskočený krok má důvod** — `when: … → false` nebo
  `switch: podle_tonu = "hravy"`. Nic se neděje potichu.
- `summary.md` ukazuje čísla na 2 místa (`0,83`), přesná hodnota
  (`0.835`) je v `steps/02-kontrola/output.json`. Proto
  `round(0.835 * 100)` = `84`.

### Cesta k `fail`

Fixtura nemusí vyjmenovat všechny otázky — chybějící doplní falešný
poskytovatel (`noul` 0,5, `choice` první možnost, `score` 0).
`/tmp/nezapamatovatelny.yaml`:

```yaml
navrh:
  - json:
      nazev: "Xyzqwrt Ovsprl"
kontrola:
  - answers:
      zapamatovatelny: 0.12
```

```bash
maw run workflows/scenarios/tutorial-03-rozhodovani.yaml -i produkt="veganská zmrzlina z ovesného mléka" --fake /tmp/nezapamatovatelny.yaml
```

```
fail v kroku stop: Název Xyzqwrt Ovsprl není zapamatovatelný (zapamatovatelny = 0.12)
běh 20260925-151455-tutorial-03-rozhodovani-967b: chyba · 0,0 s · 0,0002 USD
záznam: ~/orca/workspaces/multiagent-workflows/tutorials/runs/20260925-151455-tutorial-03-rozhodovani-967b/summary.md
```

A přesně tohle by dostalo n8n (soubor `callback.json` ve složce běhu):

```
{
  "run_id": "20260925-151455-tutorial-03-rozhodovani-967b",
  "scenario": "tutorial-03-rozhodovani",
  "request_key": null,
  "status": "failed",
  "outputs": null,
  "error": {
    "class": "fail",
    "step": "stop",
    "message": "Název Xyzqwrt Ovsprl není zapamatovatelný (zapamatovatelny = 0.12)"
  },
  "warnings": [],
  "cost_usd": 0.0002,
  "duration_s": 0.002,
  "report_url": null,
  "sent_at": "2026-09-25T15:14:55.963Z"
}
```

Třída `fail` říká „scénář skončil záměrně", ne „něco se rozbilo". V n8n
podle ní odlišíš „text neprošel kontrolou" od poruchy.

---

## Krok 4 — ostrý běh

```bash
maw run workflows/scenarios/tutorial-03-rozhodovani.yaml -i produkt="veganská zmrzlina z ovesného mléka"
```

```
běh 20260925-151536-tutorial-03-rozhodovani-b547: úspěch · 5,9 s · 0,0007 USD
záznam: ~/orca/workspaces/multiagent-workflows/tutorials/runs/20260925-151536-tutorial-03-rozhodovani-b547/summary.md
```

```
| 1 | navrh | ask | ✓ | 3,6 s | 0,0003 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | kontrola | jev | ✓ | 0,5 s | 0,0000 | zapamatovatelny = 0,85, ton = hravy, originalita = 0,64 |
| 3 | stop | fail | přeskočeno |  |  | when: steps.kontrola.zapamatovatelny < 0.5 → false |
| 4 | podle_tonu | switch | ✓ | 1,8 s | 0,0004 | větev hravy |
| 5 | slogan_hravy | ask | ✓ | 1,8 s | 0,0004 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 6 | slogan_vazny | ask | přeskočeno |  |  | switch: podle_tonu = "hravy" |
| 7 | neznamy_ton | fail | přeskočeno |  |  | switch: podle_tonu = "hravy" |
| 8 | vysledek | set | ✓ | 0,0 s | 0,0000 |  |
| 9 | out | output | ✓ | 0,0 s | 0,0000 |  |
…
## Výstup
- nazev: „Ověnka"
- ton: „hravy"
- slogan: „Ověnka - rostlinná vláka, která rozpouští srdce"
- zapamatovatelnost: 85
```

Jev stál 0,00002 USD (v tabulce se zaokrouhlí na 0,0000). Co vrátil
doopravdy:

```bash
cat runs/20260925-151536-tutorial-03-rozhodovani-b547/steps/02-kontrola/output.json
```

```
{
  "zapamatovatelny": 0.85,
  "ton": "hravy",
  "originalita": 0.64,
  "details": {
    "zapamatovatelny": {},
    "ton": {
      "probabilities": {
        "hravy": 0.66,
        "vazny": 0.34
      },
      "confidence": 0.31
    },
    "originalita": {
      "legend": {
        "0": "Běžný, obyčejný název",
        "1": "Zajímavý název",
        "2": "Výjimečně originální název"
      },
      "probabilities": {
        "0": 0.37,
        "1": 0.62,
        "2": 0.01
      },
      "confidence": 0.43
    }
  }
}
```

- `ton` = `"hravy"`, ale jen s pravděpodobností 0,66. Chceš-li mít jistotu,
  můžeš v `when` číst i `steps.kontrola.details.ton.probabilities.hravy`.
- `originalita` = `0.64` — stupnice není celé číslo; je to vážený průměr
  (0,37 × 0 + 0,62 × 1 + 0,01 × 2). Práh na `score` proto piš jako
  `< 0.5`, ne `== 0`.

---

## Krok 5 — pravidla výrazů

Výrazy (`when`, `switch.value`, `set`) vypadají jako Python, ale jsou
přísnější. Nejrychleji je pochopíš na **hřišti výrazů** — scénáři bez
modelu, který nic nestojí. `workflows/scenarios/tutorial-03-vyrazy.yaml`:

```yaml
version: 1
name: tutorial-03-vyrazy
description: Hřiště výrazů — jen krok set, žádný model, nic nestojí (tutoriál, díl 3)

inputs:
  jazyk:
    type: string
    default: cs
  delitel:
    type: number
    default: 2

outputs:
  vysledky:
    type: object
    description: Všechny spočítané hodnoty

steps:
  - id: ukazky
    set:
      # Zaokrouhlení: půlka jde vždy od nuly (jinak než v Pythonu).
      round_2_5: round(2.5)
      round_minus_2_5: round(-2.5)
      round_0_125_na_2: round(0.125, 2)
      # Dělení dává vždy desetinné číslo.
      sedm_lomeno_dvema: 7 / 2
      ctyri_lomeno_dvema: 4 / 2
      deleni_vstupem: 10 / inputs.delitel
      # Převody musí být výslovné.
      text_plus_cislo: '"verze " + str(2)'
      z_textu_na_cislo: float("0.7") + 0.1
      a_zaokrouhlene: round(float("0.7") + 0.1, 2)
      # in: prvek v seznamu, podřetězec v textu.
      cesky_nebo_slovensky: inputs.jazyk in ["cs", "sk"]
      obsahuje_ves: '"oves" in "ovesné mléko"'
      # null lze porovnat s čímkoli.
      jazyk_zadan: inputs.jazyk != null
      # Logika jen nad true/false.
      obe_podminky: len(inputs.jazyk) == 2 and not (inputs.delitel < 0)

  - id: out
    output:
      vysledky: "{{ steps.ukazky }}"
```

```bash
maw run workflows/scenarios/tutorial-03-vyrazy.yaml --fake
cat runs/20260925-151532-tutorial-03-vyrazy-6194/steps/01-ukazky/output.json
```

```
běh 20260925-151532-tutorial-03-vyrazy-6194: úspěch · 0,0 s · 0,0000 USD
záznam: ~/orca/workspaces/multiagent-workflows/tutorials/runs/20260925-151532-tutorial-03-vyrazy-6194/summary.md
{
  "round_2_5": 3,
  "round_minus_2_5": -3,
  "round_0_125_na_2": 0.13,
  "sedm_lomeno_dvema": 3.5,
  "ctyri_lomeno_dvema": 2.0,
  "deleni_vstupem": 5.0,
  "text_plus_cislo": "verze 2",
  "z_textu_na_cislo": 0.7999999999999999,
  "a_zaokrouhlene": 0.8,
  "cesky_nebo_slovensky": true,
  "obsahuje_ves": true,
  "jazyk_zadan": true,
  "obe_podminky": true
}
```

Pravidla, která z toho plynou:

1. **`round` zaokrouhluje „školně"** — půlka od nuly: `round(2.5)` = `3`,
   `round(-2.5)` = `-3`. (Python by dal `2`.) `round(x)` bez počtu míst
   dává celé číslo.
2. **`/` dává vždy desetinné číslo** (`4 / 2` = `2.0`). Dělení nulou je
   chyba.
3. **Desetinná čísla nejsou přesná** (`0.7 + 0.1` = `0.7999999999999999`).
   Na výstup pro lidi použij `round(…, 2)`.
4. **Typy se nemíchají.** Text + číslo nejde, převeď výslovně: `str()`,
   `float()`, `int()`.
5. **Text jako hodnota v `set` potřebuje dvoje uvozovky:** vnější pro
   YAML, vnitřní pro výraz — `'"verze " + str(2)'`. Totéž platí pro každý
   výraz, který začíná uvozovkou, `[` nebo `{`.
6. **Literály jsou `true`, `false`, `null`** (jako v YAML), ne `True`/`None`.
7. **Tečka čte klíč, nic jiného** — `steps.kontrola.ton`, nikdy metodu.

Zkus `delitel=0`:

```bash
maw run workflows/scenarios/tutorial-03-vyrazy.yaml --fake -i delitel=0
```

```
expression v kroku ukazky: set.deleni_vstupem: dělení nulou
  10 / inputs.delitel
       ^
běh 20260925-151526-tutorial-03-vyrazy-9181: chyba · 0,0 s · 0,0000 USD
záznam: ~/orca/workspaces/multiagent-workflows/tutorials/runs/20260925-151526-tutorial-03-vyrazy-9181/summary.md
```

`validate` hodnotu vstupu předem nezná, proto chyba přišla až za běhu
(třída `expression`).

---

## Krok 6 — skutečné chybové hlášky

Všechny tyto hlášky dá `validate`, **před během**. Každou jsem vyzkoušel
výměnou řádku `when:` v kroku `stop` (a pak ho vrátil).

**Porovnání čísla s textem:** `when: steps.kontrola.zapamatovatelny < "0.5"`

```
config: tutorial-03-rozhodovani.yaml: krok "stop", when: porovnání number s string — převeď typ výslovně (float(), str())
  steps.kontrola.zapamatovatelny < "0.5"
                                   ^
```

Stejně `steps.kontrola.ton == 1` → `porovnání string s number`.

**`when` bez porovnání:** `when: steps.kontrola.zapamatovatelny`

```
config: tutorial-03-rozhodovani.yaml: krok "stop", when: výraz musí dát true/false, dá number
  steps.kontrola.zapamatovatelny
```

V Pythonu by `0.85` „platilo". Tady ne: napiš, co myslíš (`> 0.5`).

**`and` s textem:** `when: steps.navrh.nazev and steps.kontrola.zapamatovatelny < 0.5`

```
config: tutorial-03-rozhodovani.yaml: krok "stop", when: 'and' chce true/false, dostal string — porovnej výslovně (např. len(x) > 0)
  steps.navrh.nazev and steps.kontrola.zapamatovatelny < 0.5
  ^
```

**Pythonovské `True`:** `… and True`

```
config: tutorial-03-rozhodovani.yaml: krok "stop", when: neznámé jméno 'True' — literály se píšou true, false, null
  steps.kontrola.zapamatovatelny < 0.5 and True
                                           ^
```

**Metoda:** `when: steps.navrh.nazev.lower() == "x"`

```
config: tutorial-03-rozhodovani.yaml: krok "stop", when: volání metod není povolené
  steps.navrh.nazev.lower() == "x"
  ^
```

**Podmíněný výraz:** `… if true else false`

```
config: tutorial-03-rozhodovani.yaml: krok "stop", when: podmínka 'x if c else y' není povolená
  steps.kontrola.zapamatovatelny < 0.5 if true else false
  ^
```

**Překlep v klíči:** `steps.kontrola.detail.ton…` (místo `details`)

```
config: tutorial-03-rozhodovani.yaml: krok "stop", when: 'steps.kontrola' nemá klíč 'detail' (dostupné: zapamatovatelny, ton, originalita, details)
  steps.kontrola.detail.ton.probabilities.hravy < 0.5
                 ^
```

**Šablona ve výrazu:** `when: '{{ steps.kontrola.zapamatovatelny }} < 0.5'`

```
config: tutorial-03-rozhodovani.yaml: krok "stop", when: šablona {{ }} tu není povolená — smí být jen v prompt, jev.state, jev.questions (instructions, criteria), fail, hodnotách output, call.inputs a dedupe_key
  {{ steps.kontrola.zapamatovatelny }} < 0.5
  ^
```

Bez uvozovek (`when: {{ … }} < 0.5`) je to dokonce chyba YAML —
`{` na začátku hodnoty YAML čte jako mapu:

```
config: tutorial-03-rozhodovani.yaml, řádek 56: YAML nejde přečíst — hodnota s {, [, ': ' nebo ' #' patří do uvozovek (scenario.md §5 „Pozor na YAML“)
  expected <block end>, but found '<scalar>'
```

**`switch` bez `default`:**

```
config: tutorial-03-rozhodovani.yaml: krok 'podle_tonu': switch: chybí povinné pole 'default'
```

**Případ, který Jev nikdy nevrátí** (`vazne:` místo `vazny:`):

```
config: tutorial-03-rozhodovani.yaml: krok "podle_tonu", switch.cases: vazne není mezi možnostmi criteria otázky 'ton' (hravy, vazny)
```

**Krok ve větvi bez `default`** (smaž `default:` u `slogan_hravy`):

```
config: tutorial-03-rozhodovani.yaml: krok "vysledek", set.slogan: krok 'slogan_hravy' nemusí proběhnout (je ve větvi switch 'podle_tonu') a nemá default — doplň mu default se všemi poli výstupu (§5.4)
  steps.slogan_hravy.slogan + steps.slogan_vazny.slogan
        ^
```

---

## Co sis zapamatoval

- `jev`: `noul` (0–1), `choice` (klíč), `score` (0…n, i mezi). Práh píšeš
  vždy sám.
- `when` = výraz, který dá `true`/`false`; `false` → krok přeskočen
  s důvodem.
- `fail` = záměrný konec, třída `fail`.
- `switch` = větve podle textu, `default` povinný; kroky ve větvích,
  které čteš dál, potřebují `default`.
- Výrazy: typy se nemíchají, `and/or/not` jen nad `true/false`,
  `true/false/null` malými, `round` školně.

---

## Cvičení

Název, který Jev ohodnotí jako obyčejný (`originalita` pod 0,5), nechceš.
Přidej krok, který v takovém případě běh ukončí se zprávou, ve které je
název i hodnota. Ulož jako `workflows/scenarios/tutorial-03-cviceni.yaml`
s fixturou, se kterou běh projde. Pak falešným během ověř, že název
s `originalita: 0.2` běh zastaví.

<details>
<summary>Řešení</summary>

Rozdíl proti `tutorial-03-rozhodovani.yaml`:

```bash
diff workflows/scenarios/tutorial-03-rozhodovani.yaml workflows/scenarios/tutorial-03-cviceni.yaml
```

```
2,3c2,3
< name: tutorial-03-rozhodovani
< description: Vymyslí název, nechá ho posoudit Jevem a podle tónu napíše slogan (tutoriál, díl 3)
---
> name: tutorial-03-cviceni
> description: Vymyslí název, nechá ho posoudit Jevem a podle tónu napíše slogan (tutoriál, díl 3 — řešení cvičení)
57a58,62
> 
>   # 3b. Příliš obyčejný název taky nechceme. Score 0 = běžný, 1 = zajímavý, 2 = výjimečný.
>   - id: stop_originalita
>     when: steps.kontrola.originalita < 0.5
>     fail: "Název {{ steps.navrh.nazev }} je příliš obyčejný (originalita = {{ steps.kontrola.originalita }})"
```

Fixtura `framework/tests/golden/tutorial-03-cviceni.yaml` je stejná jako
u hlavního scénáře (`originalita: 1.4` → běh projde):

```yaml
# Skriptované odpovědi pro tutorial-03-cviceni (řešení cvičení z dílu 3).
# Jev dostává answers: {otázka: hodnota}; u choice je hodnota klíč z criteria.
navrh:
  - json:
      nazev: "Ovesňák"
kontrola:
  - answers:
      zapamatovatelny: 0.835
      ton: hravy
      originalita: 1.4
slogan_hravy:
  - json:
      slogan: "Ovesňák — zmrzlina, co roste na poli"
```

```bash
maw validate workflows/scenarios/tutorial-03-cviceni.yaml
maw run workflows/scenarios/tutorial-03-cviceni.yaml -i produkt="veganská zmrzlina" --fake framework/tests/golden/tutorial-03-cviceni.yaml
```

```
v pořádku: tutorial-03-cviceni (10 kroků)
běh 20260925-151552-tutorial-03-cviceni-7a12: úspěch · 0,0 s · 0,0003 USD
```

Obyčejný název, `/tmp/obycejny.yaml`:

```yaml
navrh:
  - json:
      nazev: "Zmrzlina"
kontrola:
  - answers:
      zapamatovatelny: 0.95
      originalita: 0.2
```

```bash
maw run workflows/scenarios/tutorial-03-cviceni.yaml -i produkt="veganská zmrzlina" --fake /tmp/obycejny.yaml
```

```
fail v kroku stop_originalita: Název Zmrzlina je příliš obyčejný (originalita = 0.2)
běh 20260925-151553-tutorial-03-cviceni-c3c6: chyba · 0,0 s · 0,0002 USD
```

```
| 1 | navrh | ask | ✓ | 0,0 s | 0,0001 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | kontrola | jev | ✓ | 0,0 s | 0,0001 | zapamatovatelny = 0,95, ton = hravy, originalita = 0,20 |
| 3 | stop | fail | přeskočeno |  |  | when: steps.kontrola.zapamatovatelny < 0.5 → false |
| 4 | stop_originalita | fail | chyba | 0,0 s | 0,0000 | viz Chyba |
```

Krok musí být **za** `kontrola` (čte její výstup) a **před** `podle_tonu`
(ať se za slogan zbytečně neplatí).

</details>

**Další díl:** [Paralelně a s obrázkem](04-paralelne-a-obrazek.md).
