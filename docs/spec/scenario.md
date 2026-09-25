# Formát scénáře — specifikace v1

Scénář je jeden soubor `workflows/scenarios/<name>.yaml`. Čte se shora
dolů: nahoře co dostane (`inputs`) a co vrátí (`outputs`), pod tím kroky
v pořadí, v jakém proběhnou.

Strojová podoba: [`schema/scenario.schema.json`](schema/scenario.schema.json).
Ukázka: `workflows/scenarios/ig-post.yaml`.

Značení: **návrh** = DESIGN.md to neřeší, jde o navržené výchozí chování
ke schválení. Čísla § odkazují na `docs/DESIGN.md`.

Obsah:
1. [Hlavička scénáře](#1-hlavička-scénáře)
2. [Jak scénář běží](#2-jak-scénář-běží)
3. [Společné vlastnosti kroků](#3-společné-vlastnosti-kroků)
4. [Typy kroků](#4-typy-kroků) — `ask`, `task`, `jev`, `image`, `parallel`,
   `switch`, `call`, `set`, `fail`, `output`
5. [Hodnoty: šablony `{{ }}` a výrazy](#5-hodnoty-šablony--a-výrazy)
6. [Chyby](#6-chyby)
7. [Co kontroluje `validate`](#7-co-kontroluje-validate)

---

## Celý malý příklad

```yaml
version: 1
name: pozdrav
description: Napíše krátký pozdrav a vrátí ho

inputs:
  jmeno: { type: string, required: true }

outputs:
  text: { type: string }

steps:
  - id: napis
    ask:
      agent: copywriter
      prompt: "Napiš jednovětý pozdrav pro {{ inputs.jmeno }}."

  - id: out
    output:
      text: "{{ steps.napis.text }}"
```

---

## 1. Hlavička scénáře

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `version` | ano | Verze formátu scénáře (R7). Zatím jen `1`. | `validate`: chyba `config`. | `version: 1` |
| `name` | ano | Jméno scénáře; shoduje se s názvem souboru bez `.yaml`. Tímto jménem se scénář spouští i volá (`call`). Malá písmena, číslice, pomlčka. | Chyba `config`. | `name: ig-post` |
| `description` | ano | Jedna věta pro člověka: co scénář dělá. Objeví se v `summary.md`. | Chyba `config`. | `description: Návrh IG příspěvku ke schválení` |
| `inputs` | ne | Co scénář dostane zvenku (webhook, CLI, `call`). Viz níže. | Scénář nemá vstupy. | viz níže |
| `outputs` | ne | Co scénář vrací — smlouva pro callback i pro `call` (§5.3). Hodnoty dodá krok `output`. | Scénář nic nevrací (callback nese jen stav). | viz níže |
| `steps` | ano | Seznam kroků. Alespoň jeden. | Chyba `config`. | viz [§4](#4-typy-kroků) |

Jiná pole na nejvyšší úrovni nejsou povolená — překlep je chyba, ne tiše
ignorované pole. Totéž platí v každém kroku.

### `inputs`

Každý vstup má jméno (malá písmena, číslice, `_`) a popis:

```yaml
inputs:
  tema:
    type: string
    required: true
    description: O čem má příspěvek být
  jazyk:
    type: string
    default: cs
```

| Pole vstupu | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `type` | ano | Typ hodnoty: `string`, `number`, `integer`, `boolean`, `list`, `object`. Hodnota zvenku se proti němu kontroluje před startem běhu. | Chyba `config`. | `type: string` |
| `required` | viz text | `true` = vstup musí přijít zvenku. | — | `required: true` |
| `default` | viz text | Hodnota, když vstup nepřijde. Musí odpovídat `type`. | — | `default: cs` |
| `description` | ne | Vysvětlení pro člověka. | Nic. | `description: O čem psát` |

Pravidlo: každý vstup má **buď** `required: true`, **nebo** `default` —
nikdy obojí a nikdy nic z toho. Díky tomu není hodnota vstupu nikdy
„neznámá". Chybějící povinný vstup při spuštění → běh vůbec nezačne, chyba
`config` se vrátí hned (webhook i CLI).

### `outputs`

```yaml
outputs:
  caption:  { type: string, description: Text příspěvku }
  hashtags: { type: list }
  image:    { type: file, description: Fotka — v callbacku jako URL }
```

| Pole výstupu | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `type` | ano | Jako u vstupů, navíc `file` (soubor z kroku `image`). | Chyba `config`. | `type: file` |
| `description` | ne | Vysvětlení pro člověka. | Nic. | |

Hodnota typu `file` se na konci běhu nahraje do úložiště z `config.yaml`
a callback místo ní nese URL (§5.7). Když scénář běží přes `call`, soubor
se nenahrává — předá se volajícímu scénáři jako `file`.

---

## 2. Jak scénář běží

- Kroky běží **jeden po druhém** v pořadí, jak jsou napsané. Výjimka:
  větve uvnitř `parallel`.
- Krok vidí výstupy jen těch kroků, které jsou v souboru **nad ním**
  (a proběhly nebo mají `default`).
- Běh končí, když:
  - doběhne krok `output` → stav `succeeded`,
  - doběhne krok `fail` nebo krok selže → stav `failed`,
  - dojdou kroky a scénář nemá `outputs` → stav `succeeded`.
- Callback se posílá **vždy** (D2), viz [run-record.md](run-record.md).

Výstup kroku je dostupný jako `steps.<id>.<pole>`. Co které typy kroků
vracejí:

| Krok | Výstup |
|---|---|
| `ask`, `task` bez `schema` | `steps.<id>.text` — odpověď jako text |
| `ask`, `task` se `schema` | pole ze schématu, např. `steps.copy.caption` |
| `jev` | `steps.<id>.<otázka>` — hodnota; `steps.<id>.details.<otázka>` — pravděpodobnosti apod. |
| `image` | `steps.<id>.file` — uložený obrázek (typ `file`) |
| `set` | pojmenované hodnoty, např. `steps.texty.delka` |
| `call` | `outputs` volaného scénáře |
| `parallel`, `switch`, `fail`, `output` | nic (výstupy mají kroky uvnitř větví) |

---

## 3. Společné vlastnosti kroků

Každý krok je položka seznamu `steps` se svým `id`, **právě jedním**
klíčem typu kroku (`ask:`, `jev:`, …) a případně společnými vlastnostmi:

```yaml
- id: foto                 # jméno kroku
  when: steps.kontrola.on_brand >= 0.7
  timeout: 3m
  budget_usd: 0.10
  retry: 1
  on_error: continue
  default: { file: null }
  image:                   # typ kroku a jeho pole
    model: gemini-image
    prompt: "{{ steps.copy.image_prompt }}"
```

| Vlastnost | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `id` | ano | Jméno kroku; pod ním je výstup (`steps.<id>`) i složka v záznamu běhu. Malá písmena, číslice, `_`, začíná písmenem; unikátní v celém souboru (i uvnitř větví). Nesmí být klíčové slovo Pythonu (`and`, `or`, `not`, `in`, `is`, `if`, …), jinak by nešel použít ve výrazu. | Chyba `config`. | `id: copy` |
| `when` | ne | Podmínka ([výraz](#výrazy)). `false` → krok se přeskočí a v záznamu je důvod `when: <výraz> → false`. Výsledek musí být `true`/`false`, ne text ani číslo. | Krok běží vždy. | `when: inputs.jazyk == "cs"` |
| `timeout` | ne | Nejdelší doba kroku, formát `<číslo>s`, `m`, `h`. Překročení → chyba třídy `timeout`. | Výchozí: `ask` 2m, `task` 15m, `jev` 30s, `image` 3m (**návrh**); u agenta nejvýš jeho `limits.timeout`. Vždy platí i limit celého běhu. | `timeout: 90s` |
| `budget_usd` | ne | Kolik USD smí krok stát (všechna volání včetně opakování). Kontroluje se po každém volání; další volání se už nespustí. Překročení → chyba třídy `budget`. | U `ask`/`task` rozpočet agenta; jinak jen rozpočet běhu. | `budget_usd: 0.10` |
| `retry` | ne | Kolikrát se **jedno volání API** zopakuje při chybě `transient` nebo `schema` (§5.1). U `task` platí pro každé volání ve smyčce zvlášť. Prodleva 2 s, 4 s, 8 s…, nebo podle hlavičky `Retry-After`. | `2` (**návrh**). | `retry: 0` |
| `on_error` | ne | `fail` = chyba kroku ukončí běh. `continue` = běh pokračuje, krok má výstup `default` a v souhrnu běhu je **varování** (§5.1 bod 4). | `fail`. | `on_error: continue` |
| `default` | viz text | Výstup kroku pro případ, že krok neproběhne (přeskočen přes `when`, neprošla větev `switch`, selhal s `on_error: continue`). Tvar musí odpovídat výstupu kroku. | Pokud se na výstup kroku, který nemusí proběhnout, odkazuje jiný krok, je to chyba `validate` (§5.4). | `default: { on_brand: 0 }` |
| `dedupe_key` | ne | Jen u `task` (krok s vedlejším účinkem, např. publikace). Šablona dávající text. Když už dřív **úspěšně** doběhl krok se stejným klíčem, krok se znovu neprovede, použije se uložený výstup a v záznamu je důvod `dedupe`. (§5.2) | Krok proběhne pokaždé. | `dedupe_key: "ig-{{ inputs.post_id }}"` |
| `schema` | ne | Jen u `ask` a `task`; píše se **uvnitř** bloku kroku. Viz [`ask`](#ask). | Výstup je text. | |

Kde která vlastnost dává smysl (jinde je chyba `config`):

| | `when` | `timeout` | `budget_usd` | `retry` | `on_error` | `default` |
|---|---|---|---|---|---|---|
| `ask`, `task`, `jev`, `image` | ano | ano | ano | ano | ano | ano |
| `call` | ano | ano | ano | — | ano | ano |
| `parallel` | ano | ano | ano | — | — | — |
| `set` | ano | — | — | — | — | ano |
| `switch`, `fail` | ano | — | — | — | — | — |
| `output` | — | — | — | — | — | — |

Úložiště pro `dedupe_key` (**návrh**): soubor `dedupe.jsonl` vedle složek
běhů (`<runs>/dedupe.jsonl`), záznam = klíč, `run_id`, výstup kroku. Na
Modalu na stejném Volume.

---

## 4. Typy kroků

### `ask`

Jedno volání modelu přes agenta, bez nástrojů (D1b).

```yaml
- id: copy
  ask:
    agent: copywriter
    prompt: "Napiš IG příspěvek na téma: {{ inputs.tema }}"
    schema:
      caption: string
      hashtags: [string]
      image_prompt: string
```

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `agent` | ano | Jméno agenta z `workflows/agents/`. Agent dává model, instrukce a skilly. | Chyba `config`. | `agent: copywriter` |
| `prompt` | ano | Zpráva pro model ([šablona](#šablony-)). | Chyba `config`. | `prompt: "Téma: {{ inputs.tema }}"` |
| `schema` | ne | Tvar JSON, který model musí vrátit. Framework ho vynutí kaskádou (nativní schéma → nástroj-obal → prompt + kontrola, §5.5); nevalidní odpověď je chyba `schema` a opakuje se s chybou jako zpětnou vazbou. | Výstup je `steps.<id>.text`. | viz níže |

Zápis `schema` (zkrácený, **návrh**; framework z něj udělá JSON Schema se
`strict: true`):

| Zápis | Znamená |
|---|---|
| `string`, `number`, `integer`, `boolean` | hodnota daného typu |
| `[string]` | seznam hodnot typu `string` (funguje s každým typem) |
| vnořená mapa `{ a: string, b: number }` | objekt s těmito poli |

Všechna pole jsou povinná, jiná pole nejsou povolená. Popis toho, co má
v poli být, patří do `prompt` nebo instrukcí agenta.

Kdy je `ask` úspěšný (§5.1 bod 8 — **HTTP 200 nestačí**): odpověď má
`finish_reason: stop`, neprázdný obsah, a pokud je `schema`, obsah jde
naparsovat a odpovídá schématu. Co se stane jinak, viz [§6](#6-chyby).

### `task`

Autonomní agent: smyčka model ↔ nástroje (MCP) s limity (D1b).

```yaml
- id: publikace
  dedupe_key: "ig-publish-{{ inputs.post_id }}"
  budget_usd: 0.10
  task:
    agent: publisher
    prompt: |
      Zveřejni příspěvek.
      Text: {{ inputs.caption }}
      Obrázek: {{ inputs.image_url }}
    max_turns: 4
    tools: { instagram: [create_media, publish_media] }
    schema: { post_url: string }
```

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `agent` | ano | Agent; jeho `mcp`, `tools` a `limits` jsou **maximum** (§5.2). | Chyba `config`. | `agent: publisher` |
| `prompt` | ano | Zadání úkolu ([šablona](#šablony-)). | Chyba `config`. | |
| `max_turns` | ne | Nejvýš tolik volání modelu. Smí být jen menší nebo rovno `limits.max_turns` agenta. | Platí `limits.max_turns` agenta — limit tahů tedy existuje vždy (§5.1 bod 6). | `max_turns: 4` |
| `mcp` | ne | Podmnožina `mcp` agenta. | Všechny servery agenta. | `mcp: [instagram]` |
| `tools` | ne | Zúžení nástrojů na serveru (podmnožina toho, co povoluje agent). | Nástroje podle agenta. | `tools: { instagram: [publish_media] }` |
| `schema` | ne | Tvar finální odpovědi, stejně jako u `ask`. | `steps.<id>.text`. | |

Smyčka končí, když model odpoví bez volání nástroje (`finish_reason:
stop`). Dosažení `max_turns` bez finální odpovědi → chyba třídy `budget`.
Chyba nástroje (MCP vrátí chybu) krok neukončí: vrátí se modelu jako
výsledek nástroje a zapíše se do záznamu.

### `jev`

Rozhodnutí přes Jev (OpenRouter `POST /api/v1/systemone`, DESIGN §9).
Levné (~0,00003 USD) a rychlé (~0,3 s).

```yaml
- id: kontrola
  jev:
    state: "{{ steps.copy.caption }}"
    questions:
      on_brand:
        type: noul
        instructions: Odpovídá text tónu značky THTD?
      druh:
        type: choice
        instructions: O jaký druh příspěvku jde?
        criteria:
          produkt: Představení produktu
          akce: Sleva nebo soutěž
```

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `state` | ano | Text, který Jev posuzuje ([šablona](#šablony-)). Když šablona dá seznam nebo objekt, vloží se jako JSON text — vždy bezpečně (§5.4). | Chyba `config`. | `state: "{{ steps.copy.caption }}"` |
| `questions` | ano | Otázky; klíč = jméno výstupu (jako `id`; `details` je vyhrazené). | Chyba `config`. | |
| `questions.<q>.type` | ano | `noul` (ano/ne jako číslo 0–1), `choice` (výběr z možností), `score` (stupnice 0…n). | Chyba `config`. | `type: noul` |
| `questions.<q>.instructions` | ano | Otázka pro Jev. | Chyba `config`. | |
| `questions.<q>.criteria` | u `choice` a `score` | `choice`: mapa `možnost: popis`; `score`: seznam popisů stupňů od 0. U `noul` není povoleno. | Chyba `config`. | viz příklad |

Výstup:

| | Typ | Příklad |
|---|---|---|
| `steps.<id>.<q>` u `noul` | `number` 0–1 | `0.97` |
| `steps.<id>.<q>` u `choice` | `string` (klíč z `criteria`) | `"produkt"` |
| `steps.<id>.<q>` u `score` | `number` | `1.07` |
| `steps.<id>.details.<q>` | `object` — co Jev vrátil navíc (`probabilities`, `confidence`, `legend`) | `details.druh.probabilities.akce` |

Práh je ve scénáři vždy **výslovně** (`< 0.7`) — Jev nemá žádný
„správný" výchozí práh (DESIGN §9). Model Jev je v `config.yaml`
(`openrouter.jev_model`).

### `image`

Vygeneruje obrázek přes OpenRouter a uloží ho do složky běhu (§5.7).

```yaml
- id: foto
  image:
    model: gemini-image
    prompt: "{{ steps.copy.image_prompt }}"
    aspect_ratio: "4:5"
```

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `model` | ano | Alias obrazového modelu z `config.yaml`. | Chyba `config`. Alias modelu bez obrazového výstupu zachytí `validate` (§5.7). | `model: gemini-image` |
| `prompt` | ano | Popis obrázku ([šablona](#šablony-)). | Chyba `config`. | |
| `aspect_ratio` | ne | Poměr stran jako text `"šířka:výška"` (pro IG `"1:1"` nebo `"4:5"`; vždy v uvozovkách, jinak YAML může `4:5` číst jinak). | Výchozí modelu (u `gemini-3.1-flash-image` 1408×768). | `aspect_ratio: "4:5"` |

Výstup `steps.<id>.file` — soubor `steps/<nn>-<id>/image.png` ve složce
běhu. V záznamu nikdy není base64, jen cesta (§5.7).

Pozor: poskytovatel **neodmítá** ani podobizny skutečných osob (spike (a)).
Politiku obsahu vynucuje scénář — typicky krok `jev` nad promptem před
`image` (viz `ig-post.yaml`).

`aspect_ratio` je zdokumentovaný u OpenRouter Image API
(`POST /api/v1/images`,
<https://openrouter.ai/docs/features/multimodal/image-generation>, staženo
2026-09-25). U chat completions, které použil spike, ověřený není — který
endpoint framework použije, rozhodne Fáze 2; formát kroku se tím nemění.

### `parallel`

Pojmenované větve, které běží souběžně uvnitř jednoho běhu (D1d).

```yaml
- id: varianty
  parallel:
    kratka:
      - id: kratky_text
        ask: { agent: copywriter, prompt: "Krátký text: {{ inputs.tema }}" }
    dlouha:
      - id: dlouhy_text
        ask: { agent: copywriter, prompt: "Dlouhý text: {{ inputs.tema }}" }

- id: out
  output:
    kratky: "{{ steps.kratky_text.text }}"
    dlouhy: "{{ steps.dlouhy_text.text }}"
```

- Klíč pod `parallel` je **jméno větve** (malá písmena, číslice, `_`),
  hodnota je seznam kroků, které ve větvi běží jeden po druhém. Alespoň
  dvě větve.
- **Pojmenování výstupů:** kroky ve větvích mají vlastní `id` (unikátní
  v celém souboru) a jejich výstupy se čtou normálně přes `steps.<id>`.
  Jméno větve slouží jen pro čitelnost a v záznamu běhu. Krok `parallel`
  sám žádný výstup nemá.
- Krok ve větvi smí číst kroky nad `parallel` a kroky nad sebou ve **stejné**
  větvi. Odkaz do jiné větve je chyba `validate` (nevíme, co doběhne dřív).
- Krok za `parallel` začne, až doběhnou všechny větve.
- Když krok ve větvi selže (bez `on_error: continue`), ostatní větve se
  zruší a běh skončí `failed` (**návrh**).
- Uvnitř větve nesmí být `output`.

### `switch`

Větvení podle hodnoty. `default` je **povinný** (D1d).

```yaml
- id: podle_druhu
  switch:
    value: steps.kontrola.druh
    cases:
      produkt:
        - id: produktovy_text
          ask: { agent: copywriter, prompt: "Produktový text…" }
      akce:
        - id: akcni_text
          ask: { agent: copywriter, prompt: "Text k akci…" }
    default:
      - id: neznamy_druh
        fail: "Neznámý druh příspěvku: {{ steps.kontrola.druh }}"
```

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `value` | ano | [Výraz](#výrazy), jehož výsledek musí být `string`. | Chyba `config`. | `value: steps.kontrola.druh` |
| `cases` | ano | Mapa `hodnota: [kroky]`. Proběhnou kroky u hodnoty, která se přesně rovná `value`. Alespoň jedna. | Chyba `config`. | |
| `default` | ano | Kroky, když žádná hodnota nesedí. Vědomé „nic nedělej" je `default: []`. | Chyba `config`. | `default: []` |

- Pole se jmenuje `value`, ne `on` — YAML čte slovo `on` jako `true`.
  Ze stejného důvodu piš hodnoty jako `yes`, `no`, `true`, `1` v `cases`
  v uvozovkách.
- Pro číselné prahy (`< 0.7`) použij `when`, ne `switch`.
- Kroky ve větvi, která neproběhla, se zapíšou jako přeskočené s důvodem
  `switch: podle_druhu = "akce"`. Kdo čte jejich výstup za `switch`,
  potřebuje u nich `default` (§5.4).
- Uvnitř větve nesmí být `output`.

### `call`

Spustí jiný scénář **uvnitř stejného běhu** (§5.3).

```yaml
- id: navrh
  call:
    scenario: ig-post
    inputs:
      tema: "{{ inputs.tema }}"
```

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `scenario` | ano | Jméno scénáře z `workflows/scenarios/`. | Chyba `config`. | `scenario: ig-post` |
| `inputs` | ne | Hodnoty vstupů volaného scénáře ([šablony](#šablony-)). | Volaný scénář dostane jen své `default`. | `tema: "{{ inputs.tema }}"` |

Smlouva (§5.3):

- Výstup kroku jsou `outputs` volaného scénáře: `steps.navrh.caption`.
- `validate` staticky kontroluje, že volání dává všechny `required` vstupy,
  žádné navíc a se správnými typy, a že se čtou jen deklarované `outputs`.
- **Stejný běh:** stejný rozpočet a časový limit, záznam volaného scénáře
  je podsložka `steps/<nn>-<id>/` (viz [run-record.md](run-record.md)).
  Fronta o `call` neví.
- **Cykly** (A volá B, B volá A — i nepřímo) `validate` odmítne.
- **Hloubka** vnoření má limit `limits.max_call_depth` z `config.yaml`
  (výchozí 3, **návrh**).
- Soubory (`file`) z volaného scénáře se nenahrávají; nahraje je až
  nejvyšší scénář, pokud je dá do svého `output`.
- Scénář **nikdy nespouští nový běh frameworku a nečeká na něj** (se
  sekvenční frontou by se zablokoval). Nový běh jde spustit jen stylem
  „pošli a nečekej" přes n8n.

### `set`

Spočítá nebo přetvoří hodnoty bez LLM.

```yaml
- id: texty
  set:
    hashtagy: join(steps.copy.hashtags, " ")
    delka: len(steps.copy.caption)
    prilis_dlouhy: len(steps.copy.caption) > 2200
```

- Klíč = jméno výstupu (`steps.texty.delka`), hodnota = [výraz](#výrazy)
  (ne šablona). Čísla, `true`, `false`, `null` lze napsat přímo; text
  jako výraz musí být v uvozovkách uvnitř YAML: `stitek: '"novinka"'`.
- Hodnoty v jednom `set` na sebe neodkazují; potřebuješ-li to, dej dva
  kroky `set` za sebou.

### `fail`

Záměrně ukončí běh s chybou a zprávou.

```yaml
- id: stop
  when: steps.kontrola.on_brand < 0.7
  fail: "Text neodpovídá značce (on_brand = {{ steps.kontrola.on_brand }})"
```

Hodnota `fail` je zpráva ([šablona](#šablony-)). Běh skončí `failed`,
třída chyby `fail` (**návrh** — nová třída vedle §5.1, aby callback
odlišil záměrné ukončení od poruchy), callback nese `id` kroku a zprávu.
Kroky za nepodmíněným `fail` ve stejném seznamu jsou nedosažitelné —
chyba `validate`.

### `output`

Co běh vrací. Poslední krok scénáře.

```yaml
- id: out
  output:
    caption: "{{ steps.copy.caption }}"
    hashtags: "{{ steps.copy.hashtags }}"
    image: "{{ steps.foto.file }}"
```

- Klíče = přesně ty z `outputs` v hlavičce, typy musí sedět. Chybějící
  nebo přebývající klíč je chyba `validate`.
- Hodnoty jsou [šablony](#šablony-) nebo pevné hodnoty.
- `output` smí být jen jednou a jen jako **poslední krok** hlavního
  seznamu `steps` (ne ve větvích, bez `when`). Scénář s `outputs` ho mít
  musí; scénář bez `outputs` ho mít nesmí. Různé výsledky podle větví se
  řeší přes `default` a `set` před `output`.

---

## 5. Hodnoty: šablony `{{ }}` a výrazy

Ve scénáři jsou dva různé zápisy (D1c). Jednoduché pravidlo:

| Kde | Zápis | Příklad |
|---|---|---|
| `when`, `switch.value`, hodnoty v `set` | **výraz** — bez závorek | `steps.kontrola.on_brand < 0.7` |
| všude jinde, kde je hodnota (prompt, state, zpráva `fail`, `output`, vstupy `call`, `dedupe_key`) | **šablona** — `{{ }}` jen vkládá hodnotu | `"Téma: {{ inputs.tema }}"` |

Jména, `id`, typy kroků, aliasy modelů a agenti jsou vždy pevný text —
šablona v nich je chyba `validate`.

### Co je vidět (jména)

- `inputs.<jméno>` — vstupy scénáře.
- `steps.<id>.<pole>` — výstupy kroků nad aktuálním krokem.
- `item` je rezervované pro budoucí `foreach`; ve v1 neexistuje.

Nic jiného (proměnné prostředí, soubory, konfigurace) vidět není. Tajné
klíče se tak do promptu nedostanou ani omylem (§5.2).

### Šablony `{{ }}`

- Uvnitř `{{ }}` smí být **jen cesta k hodnotě**: tečky a číselný index,
  např. `{{ steps.copy.hashtags[0] }}`. Žádné operátory ani funkce —
  výpočet patří do kroku `set`.
- **Hodnota je celá jedna šablona** (`"{{ steps.copy.hashtags }}"`) →
  vloží se hodnota **se svým typem** (seznam zůstane seznamem, číslo
  číslem, soubor souborem).
- **Šablona uvnitř textu** (`"Téma: {{ inputs.tema }}"`) → výsledek je
  text; text se vloží beze změny, číslo jako číslo (`0.62`), `true` /
  `false`, seznam a objekt jako JSON. `null` v textu je chyba (hodnota
  chybí — nic se nevloží potichu).
- Výsledek šablony se **nikdy znovu nevyhodnocuje** (§5.4): když model
  napíše do textu `{{ inputs.x }}`, zůstane to doslova.
- Šablony se vyhodnocují nad už načteným YAML, takže uvozovky nebo
  složené závorky v textu od modelu nemůžou rozbít strukturu kroku ani
  JSON pro Jev (§5.4). Scénář JSON nikdy neskládá ručně.
- Doslovné `{{` ve v1 napsat nejde (**návrh**; přidá se, až bude potřeba).

### Výrazy

Bezpečně vyhodnocované výrazy v pythonovském stylu (D1c):

| Co | Příklad |
|---|---|
| cesta k hodnotě | `steps.copy.caption`, `steps.copy.hashtags[0]` |
| text, číslo, `true`, `false`, `null` | `"cs"`, `0.7`, `true` |
| porovnání | `==`, `!=`, `<`, `<=`, `>`, `>=` |
| logika | `and`, `or`, `not` |
| aritmetika | `+`, `-`, `*`, `/` (`+` spojí i dva texty) |
| závorky | `(a or b) and c` |
| funkce | `len(x)`, `min(a, b)`, `max(a, b)`, `round(x, 2)`, `str(x)`, `int(x)`, `float(x)`, `join(seznam, oddělovač)` |

Zakázané (chyba `validate`): volání metod (`x.upper()`), `import`, jiné
funkce, `{{ }}` uvnitř výrazu, podtržítko na začátku jména.

Pravidla typů (§5.4):

- Typy `string`, `number` (celé i desetinné), `boolean`, `null`, `list`,
  `object`, `file` se nemíchají: `steps.jev.on_brand < "0.7"` je chyba
  `validate`. Převod musí být výslovný: `float(x)`, `str(x)`.
- Porovnání s `null` (`x == null`, `x != null`) je dovolené u každého typu.
- `when` musí dát `true`/`false`. Text nebo číslo se „nepravdivostí"
  nepřevádí.
- Co `validate` staticky nepozná (např. index mimo seznam), skončí za
  běhu chybou `config` s přesnou hláškou a jménem kroku.

Literály `true`, `false`, `null` se píšou stejně jako v YAML a JSON
(ne pythonovské `True`/`None`) — **návrh**, aby uživatel neviděl dva
zápisy téhož.

Na co dát v YAML pozor: výraz, který začíná uvozovkou, `[` nebo `{`, nebo
obsahuje `: ` či ` #`, obal celý do jednoduchých uvozovek:
`when: '"x" == inputs.jazyk'`.

### Přeskočené kroky a `default` (§5.4)

Krok „nemusí proběhnout", když má `when`, je ve větvi `switch` nebo má
`on_error: continue` (nebo je uvnitř takového kroku, např. ve větvi
`parallel` s `when`). Odkaz na výstup takového kroku je chyba `validate`,
pokud krok nemá `default`. Když krok neproběhne, jeho výstup je `default`
a v záznamu je u kroku důvod.

---

## 6. Chyby

Výchozí chování: **chyba kroku ukončí běh** se stavem `failed` a callback
nese třídu chyby, `id` kroku a zprávu (§5.1). Nic neselže potichu.

### Třídy chyb

| Třída | Kdy | Co framework udělá |
|---|---|---|
| `transient` | HTTP 408, 429, 5xx, výpadek sítě; HTTP 200 s `finish_reason: error`; HTTP 200 bez obsahu a bez odmítnutí | zopakuje volání (`retry`) s prodlevou, pak chyba |
| `schema` | odpověď nejde naparsovat nebo nesedí na `schema` | zopakuje volání (`retry`), model dostane chybu jako zpětnou vazbu |
| `content` | model nebo filtr odmítl obsah: HTTP 403 (`content_policy_violation`, `refusal`), HTTP 200 s `finish_reason: content_filter` nebo vyplněným `refusal`, `image` bez obrázku | neopakuje, chyba |
| `budget` | překročen `budget_usd` kroku, agenta nebo běhu; `max_turns` bez odpovědi; HTTP 402 (došel kredit / limit klíče) | ukončí, neopakuje |
| `timeout` | překročen `timeout` kroku nebo běhu | ukončí, neopakuje |
| `config` | chyba ve scénáři, agentovi nebo konfiguraci — hlavně z `validate` před během; za běhu HTTP 400/401/403 (mimo obsah)/404, `finish_reason: length` (useknuto limitem `max_tokens`; opakování nepomůže — zvyš `max_tokens` aliasu v `config.yaml`), chyba výrazu za běhu | ukončí, neopakuje |
| `fail` | krok `fail` (**návrh**) | ukončí |
| `internal` | chyba frameworku samotného (**návrh**) — vždy s celou hláškou v záznamu | ukončí |

Zdroj hodnot `finish_reason` (`stop`, `tool_calls`, `length`,
`content_filter`, `error`) a chybových kódů:
<https://openrouter.ai/docs/api-reference/overview>,
<https://openrouter.ai/docs/api-reference/errors> (staženo 2026-09-25).
Tvar odmítnutí obrázku zatím nikdo nenaměřil (DESIGN §7 bod 7).

### HTTP 200 není úspěch (§5.1 bod 8)

Krok s modelem (`ask`, `task`, `jev`, `image`) je úspěšný teprve, když:

1. HTTP status je 200 **a** tělo nemá `error`,
2. `finish_reason` je `stop` (u `task` průběžně i `tool_calls`),
3. je tam obsah: text, JSON podle `schema`, odpovědi Jev na všechny
   otázky, u `image` aspoň jeden obrázek,
4. cena (`usage.cost`) je známá — když chybí, zapíše se varování
   (rozpočet pak nejde hlídat přesně).

Příklad ze spiku (a): Gemini vrátilo HTTP 200 s `finish_reason: "error"`,
`completion_tokens: 0` a useknutým JSON → třída `transient`, opakování.

### `on_error: continue`

Jen výslovně, jen u kroků z tabulky v [§3](#3-společné-vlastnosti-kroků).
Selhaný krok má výstup `default`, v `events.jsonl` je `error` a
`step_finished` se `status: failed`, `continued: true`, v `summary.md` a
v callbacku je **varování**. Chyby `budget` a `timeout` celého běhu
`on_error` nepřebije — běh končí vždy.

---

## 7. Co kontroluje `validate`

Před každým během (a samostatně `validate`, `--dry-run`) — všechno je
třída `config`:

- soubor odpovídá JSON Schema (neznámá pole, chybějící povinná, typy),
- `name` = jméno souboru, `version` je známá,
- agenti, scénáře (`call`), aliasy modelů, MCP servery a nástroje existují;
  krok nerozšiřuje oprávnění agenta,
- `id` unikátní, šablony a výrazy jdou přečíst, odkazy vedou jen na kroky
  výš (a ne do jiné větve `parallel`), typy ve výrazech sedí,
- odkaz na krok, který nemusí proběhnout, má `default`,
- `output` je poslední a sedí na `outputs`; `call` sedí na `inputs` a
  `outputs` volaného scénáře; žádné cykly, hloubka v limitu,
- žádný nedosažitelný krok za nepodmíněným `fail`,
- aliasy modelů existují v `GET /api/v1/models` a obrazové aliasy umí
  výstup obrázku (§5.5, §5.7).

`--dry-run` navíc vypíše plán: pořadí kroků, výsledné nástroje každého
`task` a limity.
