# Díl 2 — Navazování kroků

**Čas:** asi 15 minut · **Útrata:** jeden ostrý běh za ~0,0008 USD
**Co budeš umět:** poslat výstup jednoho kroku do dalšího, dostat od modelu
data místo volného textu (`schema`), počítat bez modelu (`set`), vrátit
víc polí a číst hlášky `validate`.

Předpoklad: díl 1 (agent `tutorial-pojmenovavac`, zkratka
`alias maw="uv run --project framework maw"`).

---

## Krok 1 — druhý agent

Vytvoř `workflows/agents/tutorial-sloganista.md`:

```markdown
---
version: 1
name: tutorial-sloganista
description: Píše krátké reklamní slogany k názvu produktu (tutoriál, díl 2)
model: chytry
limits:
  budget_usd: 0.01
---
Jsi copywriter. Píšeš česky krátké reklamní slogany.

Pravidla:
- Slogan má nejvýš 8 slov.
- Bez uvozovek, bez emoji, bez hashtagů.
```

Nic nového — stejný tvar jako pojmenovávač.

---

## Krok 2 — scénář, kde krok 2 čte krok 1

Vytvoř `workflows/scenarios/tutorial-02-nazev-a-slogan.yaml`:

```yaml
version: 1
name: tutorial-02-nazev-a-slogan
description: Vymyslí názvy produktu a k prvnímu napíše slogan (tutoriál, díl 2)

inputs:
  produkt:
    type: string
    required: true
    description: Jaký produkt pojmenováváme

outputs:
  nazev:
    type: string
    description: Vybraný název (první z návrhů)
  slogan:
    type: string
    description: Slogan k vybranému názvu
  vsechny_nazvy:
    type: string
    description: Všechny návrhy oddělené čárkou
  pocet:
    type: integer
    description: Kolik názvů agent navrhl

steps:
  # 1. Agent vymyslí názvy — díky schema jako seznam, ne jako volný text.
  - id: navrh
    ask:
      agent: tutorial-pojmenovavac
      prompt: "Vymysli 3 názvy pro tento produkt: {{ inputs.produkt }}."
      schema:
        nazvy: [string]

  # 2. Druhý agent napíše slogan k prvnímu názvu.
  - id: slogan
    ask:
      agent: tutorial-sloganista
      prompt: |
        Produkt: {{ inputs.produkt }}
        Název: {{ steps.navrh.nazvy[0] }}
        Napiš k němu jeden slogan.
      schema:
        slogan: string

  # 3. Výpočty bez modelu.
  - id: souhrn
    set:
      vsechny: join(steps.navrh.nazvy, ", ")
      pocet: len(steps.navrh.nazvy)

  # 4. Výsledek.
  - id: out
    output:
      nazev: "{{ steps.navrh.nazvy[0] }}"
      slogan: "{{ steps.slogan.slogan }}"
      vsechny_nazvy: "{{ steps.souhrn.vsechny }}"
      pocet: "{{ steps.souhrn.pocet }}"
```

Co je nové:

### `{{ steps.<id>.<pole> }}` — výstup jiného kroku

Krok vidí výstupy kroků **nad sebou**. `steps.navrh.nazvy` = pole `nazvy`
z výstupu kroku `navrh`. `[0]` = první prvek seznamu (`[-1]` by byl
poslední).

### `schema` — data místo volného textu

V dílu 1 vrátil `ask` jeden text (`steps.navrh.text`). Když chceš s odpovědí
dál pracovat — vzít první název, spočítat je — potřebuješ **data**.
`schema` říká, jaký JSON má model vrátit:

| Zápis | Znamená |
|---|---|
| `string`, `number`, `integer`, `boolean` | hodnota daného typu |
| `[string]` | seznam textů (funguje s každým typem) |
| `{ a: string, b: number }` | vnořený objekt |

Kořen je vždy mapa (pole pod `schema:`). Všechna pole jsou povinná. **Co**
v poli má být, píšeš do promptu nebo do agenta — `schema` hlídá jen tvar.

Jak to framework zařídí: pošle modelu JSON Schema a odpověď zkontroluje.
Nesedí-li, zkusí to znovu a modelu pošle chybu jako zpětnou vazbu (víc
v kroku 5).

### `set` — výpočet bez modelu

Každý klíč pod `set` je nový výstup (`steps.souhrn.pocet`), hodnota je
**výraz**. Výraz se píše **bez** `{{ }}` — to je jediný rozdíl, který si
teď potřebuješ pamatovat:

| Kde | Zápis |
|---|---|
| `prompt`, hodnoty v `output`, `fail` | šablona `"{{ steps.navrh.nazvy[0] }}"` |
| `set`, `when` (díl 3) | výraz `len(steps.navrh.nazvy)` |

`join(seznam, oddělovač)` spojí seznam textů, `len(x)` spočítá délku.

### `output` s více poli

Klíče pod `output` jsou **přesně** ty z `outputs` v hlavičce. Když je
hodnota celá jedna šablona (`"{{ steps.souhrn.pocet }}"`), vloží se se
svým typem — `pocet` zůstane číslem, ne textem `"3"`.

---

## Krok 3 — fixtura pro krok se `schema`

Krok se `schema` dostává ve fixtuře `json:` místo `text:`. Vytvoř
`framework/tests/golden/tutorial-02-nazev-a-slogan.yaml`:

```yaml
# Skriptované odpovědi pro tutorial-02-nazev-a-slogan.
# Krok se schema dostává odpověď jako json: {pole: hodnota}.
navrh:
  - json:
      nazvy: ["Ovesňák", "Mrazík Oves", "Zmrzlá Pláň"]
slogan:
  - json:
      slogan: "Zmrzlina, která roste na poli"
```

```bash
maw validate workflows/scenarios/tutorial-02-nazev-a-slogan.yaml
maw run workflows/scenarios/tutorial-02-nazev-a-slogan.yaml -i produkt="veganská zmrzlina z ovesného mléka" --fake framework/tests/golden/tutorial-02-nazev-a-slogan.yaml
```

```
v pořádku: tutorial-02-nazev-a-slogan (4 kroků)
běh 20260925-151207-tutorial-02-nazev-a-slogan-6952: úspěch · 0,0 s · 0,0002 USD
záznam: ~/orca/workspaces/multiagent-workflows/tutorials/runs/20260925-151207-tutorial-02-nazev-a-slogan-6952/summary.md
```

```bash
cat runs/20260925-151207-tutorial-02-nazev-a-slogan-6952/summary.md
```

```
# tutorial-02-nazev-a-slogan — úspěch

Vymyslí názvy produktu a k prvnímu napíše slogan (tutoriál, díl 2)
Běh `20260925-151207-tutorial-02-nazev-a-slogan-6952` · 25. 9. 2026 15:12:07 UTC · 0,0 s · 0,0002 USD

## Vstupy
- produkt: veganská zmrzlina z ovesného mléka

## Kroky
| # | Krok | Typ | Stav | Čas | Cena | Poznámka |
|---|---|---|---|---|---|---|
| 1 | navrh | ask | ✓ | 0,0 s | 0,0001 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | slogan | ask | ✓ | 0,0 s | 0,0001 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 3 | souhrn | set | ✓ | 0,0 s | 0,0000 |  |
| 4 | out | output | ✓ | 0,0 s | 0,0000 |  |

## Varování
žádná

## Výstup
- nazev: „Ovesňák"
- slogan: „Zmrzlina, která roste na poli"
- vsechny_nazvy: „Ovesňák, Mrazík Oves, Zmrzlá Pláň"
- pocet: 3
```

`(native_schema)` v poznámce říká, jakým způsobem framework JSON od modelu
vynutil — tady nativním JSON Schema. Podívej se, co přesně krok 2 dostal:

```bash
sed -n '/# Zpráva/,$p' runs/20260925-151207-tutorial-02-nazev-a-slogan-6952/steps/02-slogan/prompt.md
```

```
# Zpráva

Produkt: veganská zmrzlina z ovesného mléka
Název: Ovesňák
Napiš k němu jeden slogan.
```

A výstupy kroků 1 a 3:

```bash
cat runs/20260925-151207-tutorial-02-nazev-a-slogan-6952/steps/01-navrh/output.json
cat runs/20260925-151207-tutorial-02-nazev-a-slogan-6952/steps/03-souhrn/output.json
```

```
{
  "nazvy": [
    "Ovesňák",
    "Mrazík Oves",
    "Zmrzlá Pláň"
  ]
}
{
  "vsechny": "Ovesňák, Mrazík Oves, Zmrzlá Pláň",
  "pocet": 3
}
```

Tip: `--fake` **bez** fixtury u kroku se `schema` vyrobí hodnoty podle
schématu sám — `nazev: „falešný text (nazvy)"`, `pocet: 1`. Na kontrolu,
že scénář projde, to stačí.

---

## Krok 4 — ostrý běh

```bash
maw run workflows/scenarios/tutorial-02-nazev-a-slogan.yaml -i produkt="veganská zmrzlina z ovesného mléka"
```

```
běh 20260925-151245-tutorial-02-nazev-a-slogan-8c39: úspěch · 4,2 s · 0,0008 USD
záznam: ~/orca/workspaces/multiagent-workflows/tutorials/runs/20260925-151245-tutorial-02-nazev-a-slogan-8c39/summary.md
```

Z `summary.md`:

```
| 1 | navrh | ask | ✓ | 2,0 s | 0,0004 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | slogan | ask | ✓ | 2,2 s | 0,0004 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 3 | souhrn | set | ✓ | 0,0 s | 0,0000 |  |
| 4 | out | output | ✓ | 0,0 s | 0,0000 |  |

## Varování
žádná

## Výstup
- nazev: „OvesKréma"
- slogan: „OvesKréma - čistá dobrota bez výčitek"
- vsechny_nazvy: „OvesKréma, VeganChil, MléčnoLed"
- pocet: 3
```

`set` a `output` stojí vždy 0 — model nevolají.

---

## Krok 5 — co když model JSON pokazí

Fixtura umí nasimulovat model, který na první pokus odpoví textem místo
JSON. Ulož si kamkoli (třeba `/tmp/spatny-json.yaml`):

```yaml
navrh:
  - text: "Tady jsou názvy: Ovesňák, Mrazík Oves, Zmrzlá Pláň"
  - json:
      nazvy: ["Ovesňák", "Mrazík Oves", "Zmrzlá Pláň"]
slogan:
  - json:
      slogan: "Zmrzlina, která roste na poli"
```

```bash
maw run workflows/scenarios/tutorial-02-nazev-a-slogan.yaml -i produkt="zmrzlina" --fake /tmp/spatny-json.yaml
```

```
běh 20260925-151235-tutorial-02-nazev-a-slogan-6286: úspěch · 0,0 s · 0,0003 USD
```

Běh prošel. V `summary.md` je u kroku 1 `(tool_wrapper)` místo
`(native_schema)` a v `events.jsonl` je vidět, proč:

```bash
grep '"error"' runs/20260925-151235-tutorial-02-nazev-a-slogan-6286/events.jsonl
```

```
{"ts":"2026-09-25T15:12:35.304Z","type":"error","step":"navrh","class":"schema","message":"odpověď není JSON (Expecting value: line 1 column 1 (char 0)): Tady jsou názvy: Ovesňák, Mrazík Oves, Zmrzlá Pláň","attempt":1,"will_retry":true,"http_status":null}
{"ts":"2026-09-25T15:12:35.306Z","type":"run_finished","status":"succeeded","error":null,"warnings":[],"duration_s":0.003,"usage":{"input_tokens":300,"output_tokens":60,"cost_usd":0.0003},"image_cost_usd":0.0,"image_duration_s":0.0}
```

(Druhý řádek grep chytil jen proto, že obsahuje `"error":null`.) První
pokus skončil chybou třídy **`schema`**, `will_retry: true`. Druhý pokus
šel „o úroveň níž" (JSON přes nástroj-obal, `tool_wrapper`) a prošel.
Ve složce kroku jsou proto dvě volání: `calls/01.*` a `calls/02.*`. Oba
pokusy se platí — proto je cena kroku dvojnásobná.

**Bez `schema`** by se nic z toho nedělo: výstupem by byl jen
`steps.navrh.text` a s „Tady jsou názvy: …" bys dál pracovat nemohl.
A `validate` by ti to řekl dřív, než cokoli zaplatíš — viz další krok.

---

## Krok 6 — hlášky `validate` a jak je číst

Všechny hlášky mají stejnou stavbu:

```
config: <soubor>: krok "<id>", <kde>: <co je špatně>
  <výraz nebo šablona>
      ^ ← místo chyby
```

Vyzkoušej si je — vždy jednu změnu, `validate`, a vrať zpět.

**Smaž `schema` z kroku `navrh`.** Výstupem je pak jen `text`:

```
config: tutorial-02-nazev-a-slogan.yaml: krok "slogan", ask.prompt: 'steps.navrh' nemá klíč 'nazvy' (dostupné: text)
  {{ steps.navrh.nazvy[0] }}
                 ^
config: tutorial-02-nazev-a-slogan.yaml: krok "souhrn", set.vsechny: 'steps.navrh' nemá klíč 'nazvy' (dostupné: text)
  join(steps.navrh.nazvy, ", ")
                   ^
config: tutorial-02-nazev-a-slogan.yaml: krok "souhrn", set.pocet: 'steps.navrh' nemá klíč 'nazvy' (dostupné: text)
  len(steps.navrh.nazvy)
                  ^
config: tutorial-02-nazev-a-slogan.yaml: krok "out", output.nazev: 'steps.navrh' nemá klíč 'nazvy' (dostupné: text)
  {{ steps.navrh.nazvy[0] }}
                 ^
```

Čti vždy **první** hlášku; ostatní jsou často následek téže chyby.
„(dostupné: text)" ti říká, co krok opravdu vrací.

**Překlep v id kroku** — `{{ steps.nvrh.nazvy[0] }}`:

```
config: tutorial-02-nazev-a-slogan.yaml: krok "slogan", ask.prompt: krok 'nvrh' neexistuje (dostupné: navrh)
  {{ steps.nvrh.nazvy[0] }}
           ^
```

**Chybějící pole** — `slogan: "{{ steps.slogan.text }}"` (krok má `schema`,
takže `text` nemá):

```
config: tutorial-02-nazev-a-slogan.yaml: krok "out", output.slogan: 'steps.slogan' nemá klíč 'text' (dostupné: slogan)
  {{ steps.slogan.text }}
                  ^
```

**Odkaz na krok níž** — do promptu kroku `slogan` přidej
`{{ steps.souhrn.pocet }}`:

```
config: tutorial-02-nazev-a-slogan.yaml: krok "slogan", ask.prompt: krok 'souhrn' je až níž — výraz vidí jen kroky nad sebou
  {{ steps.souhrn.pocet }}
           ^
```

**`output` nesedí na hlavičku** — smaž řádek `pocet:` z kroku `out`:

```
config: tutorial-02-nazev-a-slogan.yaml: krok "out", output: chybí výstupy z hlavičky: pocet
```

**Špatný typ výstupu** — `pocet: "{{ steps.souhrn.vsechny }}"`:

```
config: tutorial-02-nazev-a-slogan.yaml: krok "out", output.pocet: výstup má typ integer, hodnota je string
```

**`null`** — framework nikdy nevloží `null` potichu. Přidej do `set`
řádek `poznamka: null` a do výstupu `"{{ steps.souhrn.vsechny }} {{ steps.souhrn.poznamka }}"`:

```
config: tutorial-02-nazev-a-slogan.yaml: krok "out", output.vsechny_nazvy: 'steps.souhrn.poznamka' je vždy null — šablona null nevloží
  {{ steps.souhrn.poznamka }}
     ^
```

**Šablona tam, kde patří výraz** — `pocet: "{{ steps.navrh.nazvy }}"` v `set`:

```
config: tutorial-02-nazev-a-slogan.yaml: krok "souhrn", set.pocet: šablona {{ }} tu není povolená — smí být jen v prompt, jev.state, jev.questions (instructions, criteria), fail, hodnotách output, call.inputs a dedupe_key
config: tutorial-02-nazev-a-slogan.yaml: krok "souhrn", set.pocet: konstrukce 'Set' není ve výrazech povolená
  {{ steps.navrh.nazvy }}
  ^
```

Tady je důležitá první hláška; druhá je vnitřní detail (hlášeno
v [BUGS.md](BUGS.md)).

### Chyba, kterou `validate` poznat nemůže

`validate` neví, co model vrátí. Když vrátí prázdný seznam, `[0]` nemá
co vzít. Nasimuluj to fixturou `/tmp/prazdne.yaml`:

```yaml
navrh:
  - json:
      nazvy: []
```

```bash
maw run workflows/scenarios/tutorial-02-nazev-a-slogan.yaml -i produkt="zmrzlina" --fake /tmp/prazdne.yaml
```

```
expression v kroku slogan: ask.prompt: index 0 mimo rozsah 'steps.navrh.nazvy' (délka 0)
  {{ steps.navrh.nazvy[0] }}
                       ^
běh 20260925-151229-tutorial-02-nazev-a-slogan-ec41: chyba · 0,0 s · 0,0001 USD
záznam: ~/orca/workspaces/multiagent-workflows/tutorials/runs/20260925-151229-tutorial-02-nazev-a-slogan-ec41/summary.md
```

Třída **`expression`** = chyba výrazu **za běhu**. Neopakuje se, běh
končí. V `summary.md`:

```
# tutorial-02-nazev-a-slogan — chyba
…
## Chyba
- třída: `expression`
- krok: `slogan`
- zpráva:

…
Běh skončil v kroku slogan.
…
| 1 | navrh | ask | ✓ | 0,0 s | 0,0001 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | slogan | ask | chyba | 0,0 s | 0,0000 | viz Chyba |
```

Rozdíl, který stojí za zapamatování:

| Třída | Kdy | Běh |
|---|---|---|
| `config` | `validate`, **před** během | vůbec nezačne, nic nestojí |
| `expression` | **za běhu**, hodnota nesedí | skončí v kroku, zaplacené kroky zůstanou zaplacené |

---

## Co sis zapamatoval

- `{{ steps.<id>.<pole> }}` čte výstup kroku **nad** sebou.
- `schema` z odpovědi udělá data; bez ní máš jen `steps.<id>.text`.
  Ve fixtuře `json:` místo `text:`.
- `set` počítá **výrazy** (bez `{{ }}`), zadarmo.
- `output` = přesně pole z `outputs`, se správnými typy.
- Hlášky: čti první, hledej `^` a „(dostupné: …)".

---

## Cvičení

Přidej do scénáře výstup **`kratky_slogan`** (typ `boolean`): `true`, když
má slogan nejvýš 40 znaků. Spočítej ho v kroku `souhrn`. Ulož jako
`workflows/scenarios/tutorial-02-cviceni.yaml` s fixturou.

<details>
<summary>Řešení</summary>

Rozdíl proti `tutorial-02-nazev-a-slogan.yaml` (celý soubor je
v `workflows/scenarios/tutorial-02-cviceni.yaml`):

```bash
diff workflows/scenarios/tutorial-02-nazev-a-slogan.yaml workflows/scenarios/tutorial-02-cviceni.yaml
```

```
2,3c2,3
< name: tutorial-02-nazev-a-slogan
< description: Vymyslí názvy produktu a k prvnímu napíše slogan (tutoriál, díl 2)
---
> name: tutorial-02-cviceni
> description: Vymyslí názvy produktu a k prvnímu napíše slogan (tutoriál, díl 2 — řešení cvičení)
23a24,26
>   kratky_slogan:
>     type: boolean
>     description: Má slogan nejvýš 40 znaků?
49a53
>       kratky: len(steps.slogan.slogan) <= 40
57a62
>       kratky_slogan: "{{ steps.souhrn.kratky }}"
```

Porovnání `<=` dává `true`/`false`, takže typ `boolean` sedí.
Krok `souhrn` smí číst `steps.slogan`, protože `slogan` je nad ním.

Fixtura `framework/tests/golden/tutorial-02-cviceni.yaml` je stejná jako
u hlavního scénáře (kroky se nezměnily):

```yaml
# Skriptované odpovědi pro tutorial-02-cviceni (řešení cvičení z dílu 2).
# Krok se schema dostává odpověď jako json: {pole: hodnota}.
navrh:
  - json:
      nazvy: ["Ovesňák", "Mrazík Oves", "Zmrzlá Pláň"]
slogan:
  - json:
      slogan: "Zmrzlina, která roste na poli"
```

```bash
maw validate workflows/scenarios/tutorial-02-cviceni.yaml
maw run workflows/scenarios/tutorial-02-cviceni.yaml -i produkt="veganská zmrzlina" --fake framework/tests/golden/tutorial-02-cviceni.yaml
```

```
v pořádku: tutorial-02-cviceni (4 kroků)
běh 20260925-151257-tutorial-02-cviceni-1680: úspěch · 0,0 s · 0,0002 USD
```

Konec `summary.md`:

```
## Výstup
- nazev: „Ovesňák"
- slogan: „Zmrzlina, která roste na poli"
- vsechny_nazvy: „Ovesňák, Mrazík Oves, Zmrzlá Pláň"
- pocet: 3
- kratky_slogan: true
```

(„Zmrzlina, která roste na poli" má 29 znaků.)

</details>

**Další díl:** [Rozhodování](03-rozhodovani.md) — Jev, `when`, `fail`,
`switch` a pravidla výrazů.
