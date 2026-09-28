# Formát scénáře — specifikace v1

Scénář je jeden soubor `workflows/scenarios/<name>.yaml`. Čte se shora
dolů: nahoře co dostane (`inputs`) a co vrátí (`outputs`), pod tím kroky
v pořadí, v jakém proběhnou.

Strojová podoba: [`schema/scenario.schema.json`](schema/scenario.schema.json).
Ukázka: `examples/showcase/workflows/scenarios/ig-post.yaml`. Spuštění přes webhook:
[webhook.md](webhook.md).

**Jak se soubor čte (B6):** jako **YAML 1.2 core** — booleany jsou jen
`true`/`false` (i `True`/`TRUE`), slova `yes`, `no`, `on`, `off` jsou
obyčejný text, `4:5` je text (ne číslo), datum `2026-09-25` je text.
Stejný klíč dvakrát v jedné mapě je chyba `config` s číslem řádku.
Čtou se jen soubory přímo ve `workflows/scenarios/`; podsložky se
ignorují (hodí se třeba na archiv). Ukázky se ověřují stejným načítáním:
[`tools/check.py`](tools/check.py). Z kořene repozitáře jej spusťte příkazem
`uv run --project framework python docs/spec/tools/check.py`.

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
| `outputs` | ne | Co scénář vrací — smlouva pro callback i pro `call` (§5.3). Hodnoty dodá krok `output`. Když je uvedené, má aspoň jednu položku. | Scénář nic nevrací (callback nese jen stav). | viz níže |
| `callable` | ne | `true` = scénář smí volat jiný scénář krokem `call`. Spustit přes webhook/CLI jde každý scénář. Chrání schvalování: část 1 nesmí zavolat část 2 (publikaci) a obejít n8n (DESIGN §5.2). | `false` — `call` na tento scénář je chyba `config`. | `callable: true` |
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
| `type` | ano | Typ hodnoty: `string`, `number`, `integer`, `boolean`, `list`, `object`, a `file` (jen když scénář volá jiný scénář přes `call` — z webhooku a CLI je vstup `file` chyba `config`). Hodnota zvenku se proti němu kontroluje před startem běhu. | Chyba `config`. | `type: string` |
| `required` | viz text | `true` = vstup musí přijít zvenku. | — | `required: true` |
| `default` | viz text | Hodnota, když vstup nepřijde. Musí odpovídat `type`. | — | `default: cs` |
| `description` | ne | Vysvětlení pro člověka. | Nic. | `description: O čem psát` |

Pravidlo: každý vstup má **buď** `required: true`, **nebo** `default` —
nikdy obojí a nikdy nic z toho. Díky tomu není hodnota vstupu nikdy
„neznámá". Chybějící nebo špatný vstup při spuštění → běh vůbec nezačne:
webhook odpoví hned HTTP 422 bez `run_id` a bez callbacku
([webhook.md](webhook.md)), CLI skončí chybou `config`.

### `outputs`

```yaml
outputs:
  caption:  { type: string, description: Text příspěvku }
  hashtags: { type: list }
  image:    { type: file, description: Fotka — v callbacku jako URL }
```

| Pole výstupu | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `type` | ano | Jako u vstupů včetně `file` (soubor z kroku `image`). | Chyba `config`. | `type: file` |
| `description` | ne | Vysvětlení pro člověka. | Nic. | |

Hodnota typu `file` se na konci běhu nahraje do úložiště z `config.yaml`
a callback místo ní nese URL (§5.7). Když scénář běží přes `call`, soubor
se nenahrává — předá se volajícímu scénáři jako `file`. Pravidla pro
`file` viz [Typ `file`](#typ-file).

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
- Callback se posílá **vždy**, jakmile běh dostal `run_id` (D2), viz
  [run-record.md](run-record.md#callback).
- Kroky, na které běh po selhání nedošel, se nezapisují; `summary.md`
  uvádí „běh skončil v kroku X".

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
    prompt: "{{ steps.foto_prompt.popis_fotky }}"
```

| Vlastnost | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `id` | ano | Jméno kroku; pod ním je výstup (`steps.<id>`) i složka v záznamu běhu. Malá písmena, číslice, `_`, začíná písmenem; unikátní v celém souboru (i uvnitř větví). Nesmí být klíčové slovo Pythonu (`and`, `or`, `not`, `in`, `is`, `if`, …), jinak by nešel použít ve výrazu. | Chyba `config`. | `id: copy` |
| `when` | ne | Podmínka ([výraz](#výrazy)). `false` → krok se přeskočí a v záznamu je důvod `when: <výraz> → false`. Výsledek musí být `true`/`false`, ne text ani číslo. Chyba ve `when` je chybou kroku — `on_error` kroku ji pokrývá. | Krok běží vždy. | `when: inputs.jazyk == "cs"` |
| `timeout` | ne | Nejdelší doba kroku, formát `<číslo>s`, `m`, `h`. Překročení → chyba třídy `timeout`. U `parallel` a `call` = doba od startu do konce posledního kroku uvnitř. | Výchozí: `ask` 2m, `task` 15m, `jev` 30s, `image` 3m (**návrh**); u agenta nejvýš jeho `limits.timeout`. Vždy platí i limit celého běhu. | `timeout: 90s` |
| `budget_usd` | ne | Kolik USD smí krok stát (všechna volání včetně opakování). U `parallel` a `call` = součet všech kroků uvnitř. Pravidla kontroly viz [Rozpočet](#rozpočet). Překročení → chyba třídy `budget`. | U `ask`/`task` rozpočet agenta; jinak jen rozpočet běhu. | `budget_usd: 0.10` |
| `retry` | ne | Kolikrát se **jedno volání API** zopakuje při chybě `transient` nebo `schema` (§5.1). U `task` platí pro každý tah zvlášť; opakování se nepočítá do `max_turns`, jen do `budget_usd`. Prodleva 2 s, 4 s, 8 s…, nebo podle hlavičky `Retry-After`. | `2` (**návrh**). | `retry: 0` |
| `on_error` | ne | `fail` = chyba kroku ukončí běh. `continue` = běh pokračuje, krok má výstup `default` a v souhrnu běhu je **varování** (§5.1 bod 4). | `fail`. | `on_error: continue` |
| `default` | viz text | Výstup kroku pro případ, že krok neproběhne (přeskočen přes `when`, neprošla větev `switch`, selhal s `on_error: continue`). Musí obsahovat **všechna** pole výstupu kroku (u `jev` všechny otázky; `details` se doplní jako `{}` samo); chybějící pole je chyba `validate`. | Pokud se na výstup kroku, který nemusí proběhnout, odkazuje jiný krok, je to chyba `validate` (§5.4). | `default: { on_brand: 0 }` |
| `dedupe_key` | ne | Jen u `task` (krok s vedlejším účinkem, např. publikace). Šablona dávající text. Zajistí, že vedlejší účinek proběhne nejvýš jednou, i když n8n běh zopakuje — viz [dedupe](#dedupe_key--jednou-a-dost). (§5.2) | Krok proběhne pokaždé. | `dedupe_key: "ig-{{ inputs.post_id }}"` |
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

Proč jen tyto kombinace (a ne „libovolný krok" z D1d), viz
OPEN-QUESTIONS 13.

### `dedupe_key` — jednou a dost

Dedupe je jediná výjimka z pravidla „běhy si nesdílí soubory" (D2, stejně
jako `state`; OPEN-QUESTIONS 12):

- Každý klíč je **samostatný soubor**
  `<runs>/_dedupe/<sha256(scénář + "/" + id kroku + "/" + klíč)>.json`,
  vytvořený atomicky („vytvoř, jen když neexistuje"). Nikdy jeden sdílený
  log. Klíč je tak vázaný na scénář a krok — stejný text v jiném scénáři
  se nesplete.
- Obsah: `{"state": "started" | "succeeded", "run_id": "…", "output": {…}}`.
- `started` vznikne **před prvním voláním nástroje** kroku; `succeeded`
  (s výstupem) po úspěšném konci kroku.
- Při dalším běhu:
  - `succeeded` → krok se neprovede, výstup se vezme ze souboru, v záznamu
    `step_skipped` s důvodem `dedupe`;
  - `started` bez `succeeded` → krok se **nespustí**, chyba `config`:
    „krok mohl proběhnout jen částečně, ověř ručně a smaž
    `<runs>/_dedupe/<…>.json`". Nic se tiše neopakuje.
- Falešný běh (`--fake`) používá stejnou strukturu v `<runs>/_dedupe-fake/`;
  ostrý a falešný běh si záznamy nikdy nečtou navzájem — vymyšlený výstup
  nesmí přeskočit ostrý vedlejší účinek (od frameworku 0.2.2).

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
      image_idea: string
```

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `agent` | ano | Jméno agenta z `workflows/agents/`. Agent dává model, instrukce a skilly (u `ask` vložené celé, viz [agent.md](agent.md#jak-vznikne-system-prompt)). | Chyba `config`. | `agent: copywriter` |
| `prompt` | ano | Zpráva pro model ([šablona](#šablony-)). | Chyba `config`. | `prompt: "Téma: {{ inputs.tema }}"` |
| `schema` | ne | Tvar JSON, který model musí vrátit. Framework ho vynutí kaskádou (nativní schéma → nástroj-obal → prompt + kontrola, §5.5); nevalidní odpověď je chyba `schema` a opakuje se s chybou jako zpětnou vazbou. | Výstup je `steps.<id>.text`. | viz níže |

Zápis `schema` (zkrácený, **návrh**; framework z něj udělá JSON Schema se
`strict: true`):

| Zápis | Znamená |
|---|---|
| `string`, `number`, `integer`, `boolean` | hodnota daného typu |
| `[string]` | seznam hodnot typu `string` (funguje s každým typem) |
| vnořená mapa `{ a: string, b: number }` | objekt s těmito poli |

**Kořen `schema` je vždy mapa** (výstup se čte jako `steps.<id>.<pole>` a
poskytovatelé chtějí jako kořen objekt). Všechna pole jsou povinná, jiná
pole nejsou povolená. Popis toho, co má v poli být, patří do `prompt` nebo
instrukcí agenta.

#### Kaskáda strukturovaného výstupu (§5.5)

- Úroveň začíná na `models.<alias>.structured_output` z `config.yaml`:
  `native_schema` (nativní JSON schema) | `tool_wrapper` (nástroj jako
  obal) | `prompt` (popis v promptu + kontrola). Výchozí `native_schema`;
  hodnotu nastavuje vlastník podle konformačního scénáře aliasu.
- Po chybě `schema` jde další pokus o **úroveň níž**. Pokus se počítá do
  `retry`. Použitá úroveň je v záznamu (`model_call.structured_output`).
- Na úrovni `tool_wrapper` je správná odpověď volání nástroje
  `_submit_output` s argumenty podle `schema` (`finish_reason:
  tool_calls`). U `task` toto volání smyčku ukončí. `_submit_output` se
  nikdy neposílá na MCP server a nepodléhá allowlistu nástrojů.

Kdy je `ask` úspěšný (§5.1 bod 8 — **HTTP 200 nestačí**): odpověď má
`finish_reason: stop` (na úrovni `tool_wrapper` `tool_calls` s voláním
`_submit_output`), neprázdný obsah, a pokud je `schema`, obsah jde
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
| `max_turns` | ne | Nejvýš tolik **tahů** (odpovědí modelu, které smyčka zpracovala; opakování po `transient`/`schema` se nepočítá). Smí být jen menší nebo rovno `limits.max_turns` agenta. | Platí `limits.max_turns` agenta. Agent bez `limits.max_turns` v `task` je chyba `config` — limit tahů tedy existuje vždy (§5.1 bod 6). | `max_turns: 4` |
| `mcp` | ne | Podmnožina `mcp` agenta. | Všechny servery agenta. | `mcp: [instagram]` |
| `tools` | ne | Zúžení nástrojů na serveru (podmnožina toho, co povoluje agent). | Nástroje podle agenta. | `tools: { instagram: [publish_media] }` |
| `schema` | ne | Tvar finální odpovědi, stejně jako u `ask`. | `steps.<id>.text`. | |

Smyčka končí, když model odpoví bez volání nástroje (`finish_reason:
stop`), nebo zavolá `_submit_output` (kaskáda, viz [`ask`](#ask)).
Dosažení `max_turns` bez finální odpovědi → chyba třídy `budget`.
Model vidí jen povolené nástroje (agent ∩ krok ∩ `mcp.yaml`) a nástroj
`load_skill`, pokud má agent skilly ([agent.md](agent.md)).

MCP servery a chyby nástrojů (DESIGN §5.8):

- Stdio servery startují **jednou za běh**, při prvním `task`, který je
  potřebuje, a sdílí je i větve `parallel`. Na konci běhu se ukončí.
- Nástroj vrátí `isError` → výsledek jde modelu, krok pokračuje.
- Argumenty od modelu nesedí na schéma nástroje → nástroj se nespustí,
  model dostane chybu validace jako výsledek (tah se počítá).
- Timeout volání nástroje (`mcp.yaml` → `timeouts.call`) → krok selže,
  třída `timeout` (nástroj mohl proběhnout — proto `dedupe_key`).
- Selhání spuštění nebo handshaku serveru → `transient` (síť, 5xx),
  jinak `config` (proces neběží, 401, neznámý příkaz).
- Obrázek ve výsledku nástroje se uloží jako soubor
  (`steps/<nn>-<id>/tool-<NN>-<k>.png`) a modelu jde v user zprávě hned za
  tool zprávou; v tool zprávě je jen text „obrázek v další zprávě:
  tool-<NN>-<k>.png" (Gemini obrázek v tool zprávě odmítne).

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
        instructions: Odpovídá text tónu značky Lumen?
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
    prompt: "{{ steps.foto_prompt.popis_fotky }}"
    aspect_ratio: "4:5"
```

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `model` | ano | Alias obrazového modelu z `config.yaml`. | Chyba `config`. Alias modelu bez obrazového výstupu zachytí `validate` (§5.7). | `model: gemini-image` |
| `prompt` | ano | Popis obrázku ([šablona](#šablony-)). | Chyba `config`. | |
| `aspect_ratio` | ne | Poměr stran jako text `"šířka:výška"` nebo šablona `"{{ inputs.pomer }}"` (pro IG `"1:1"` nebo `"4:5"`). Po uložení framework porovná poměr stran z hlavičky souboru; odchylka > 2 % = chyba `config` („model nepodporuje aspect_ratio"), nic se tiše neořízne. | Výchozí modelu (u `gemini-3.1-flash-image` 1408×768). | `aspect_ratio: "4:5"` |
| `quality` | ne | Kvalita `auto`, `low`, `medium`, `high` nebo šablona. | `models.<alias>.quality`, jinak výchozí modelu. | `quality: "{{ inputs.kvalita }}"` |
| `resolution` | ne | Rozlišení jako text `"512"`, `"1K"`, `"2K"`, `"4K"` nebo šablona. | Výchozí modelu. | `resolution: "1K"` |

Výstup `steps.<id>.file` — soubor `steps/<nn>-<id>/image.png` ve složce
běhu. V záznamu nikdy není base64, jen cesta (§5.7).

Když odpověď neobsahuje obrázek: je-li `refusal` neprázdné nebo
`finish_reason: content_filter` → třída `content`. Jinak `transient`
(opakuje se) a po vyčerpání `retry` třída `content` se zprávou „model
nevrátil obrázek".

Pozor: poskytovatel **neodmítá** ani podobizny skutečných osob (spike (a)).
Politiku obsahu vynucuje scénář — typicky krok `jev` nad promptem před
`image` (viz `ig-post.yaml`).

`aspect_ratio` je zdokumentovaný u OpenRouter Image API
(`POST /api/v1/images`,
<https://openrouter.ai/docs/features/multimodal/image-generation>, ověřeno
2026-09-27). Endpoint určuje `models.<alias>.api` v `config.yaml`:
`chat` (výchozí) používá chat completions s `modalities: [image, text]`,
`images` používá `POST /api/v1/images` a odešle `aspect_ratio`, `quality` a
`resolution` přímo. Přednost kvality: krok > `models.<alias>.quality` > nic.
Po dosazení šablon se kontroluje tvar poměru a uvedené výčty; neplatná hodnota
končí chybou `config` s dosazeným textem. Chat API posílá poměr přes
`image_config`, kvalitu a rozlišení ignoruje s varováním v záznamu běhu
(`summary.md` i events). Dosazené parametry jsou také v `prompt.md` kroku.
Statická validace kontroluje pevné hodnoty proti `supported_parameters`
z `/images/models`, pokud parametr uvádí `values`; stejně kontroluje
`default` vstupu v jediné šabloně `{{ inputs.x }}`. Validace samostatná
varování nepodporuje, ignorování parametrů chat API hlásí až běh.
Formát scénáře zůstává `version: 1`.

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
  zruší a běh skončí `failed` (**návrh**). Rozběhnutý krok, který se tím
  zruší, dostane `step_finished` se `status: cancelled` a cenou dosavadních
  volání; nerozběhnutý dostane `step_skipped` s důvodem `cancelled`.
- Když je `parallel` přeskočen (`when`), dostane každý krok uvnitř
  `step_skipped` se stejným důvodem.
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
| `value` | ano | [Výraz](#výrazy), jehož výsledek musí být `string`. `null` nebo jiný typ = chyba `expression` (ne větev `default`); když je typ známý předem, chyba `validate`. | Chyba `config`. | `value: steps.kontrola.druh` |
| `cases` | ano | Mapa `hodnota: [kroky]`. Proběhnou kroky u hodnoty, která se přesně rovná `value`. Alespoň jedna. | Chyba `config`. | |
| `default` | ano | Kroky, když žádná hodnota nesedí. Vědomé „nic nedělej" je `default: []`. | Chyba `config`. | `default: []` |

- Klíče `cases` jsou vždy text (YAML 1.2: `yes`, `on` i `1` jsou text).
  Když `value` je odpověď `choice` z `jev`, `validate` ověří, že klíče
  `cases` jsou mezi klíči `criteria`.
- Pro číselné prahy (`< 0.7`) použij `when`, ne `switch`.
- Kroky ve větvi, která neproběhla (i v celém přeskočeném `switch`), se
  zapíšou každý jako přeskočené s důvodem `switch: podle_druhu = "akce"`. Kdo čte jejich výstup za `switch`,
  potřebuje u nich `default` (§5.4).
- Uvnitř větve nesmí být `output`.

### `call`

Spustí jiný scénář **uvnitř stejného běhu** (§5.3).

```yaml
- id: navrh
  call:
    scenario: ig-text        # ig-text.yaml má callable: true
    inputs:
      tema: "{{ inputs.tema }}"
```

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `scenario` | ano | Jméno scénáře z `workflows/scenarios/`, který má v hlavičce `callable: true`. Jinak chyba `config`. | Chyba `config`. | `scenario: ig-text` |
| `inputs` | ne | Hodnoty vstupů volaného scénáře ([šablony](#šablony-)). | Volaný scénář dostane jen své `default`. | `tema: "{{ inputs.tema }}"` |

Smlouva (§5.3):

- Výstup kroku jsou `outputs` volaného scénáře: `steps.navrh.caption`.
- `validate` staticky kontroluje, že volaný scénář má `callable: true`,
  že volání dává všechny `required` vstupy, žádné navíc a se správnými
  typy, a že se čtou jen deklarované `outputs`. Typ vstupu, který nejde
  ověřit předem, se kontroluje při `call`; nesoulad = `expression`.
- Vstup typu `file` jde předat jen přes `call` (obrázek z jednoho scénáře
  do druhého).
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
- Hodnoty jsou [šablony](#šablony-) nebo pevné hodnoty; pro výstup typu
  `file` jen šablona, která vede na `file` (viz [Typ `file`](#typ-file)).
- Selhání nahrání souboru do úložiště = `transient` s opakováním, pak běh
  `failed`, třída `transient`, krok `output`.
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
| **jen** v: `ask.prompt`, `task.prompt`, `image.prompt`, `image.aspect_ratio`, `image.quality`, `image.resolution`, `jev.state`, `jev.questions.*.instructions`, `jev.questions.*.criteria` (hodnoty), `fail`, hodnotách `output`, `call.inputs`, `dedupe_key` | **šablona** — `{{ }}` jen vkládá hodnotu | `"Téma: {{ inputs.tema }}"` |

`{{` kdekoli jinde (jména, `id`, typy kroků, aliasy, agenti,
`max_turns`, klíče `cases`, …) je chyba `validate`.

### Co je vidět (jména)

- `inputs.<jméno>` — vstupy scénáře.
- `steps.<id>.<pole>` — výstupy kroků nad aktuálním krokem.
- `item` je rezervované pro budoucí `foreach`; ve v1 neexistuje.

Nic jiného (proměnné prostředí, soubory, konfigurace) vidět není. Tajné
klíče se tak do promptu nedostanou ani omylem (§5.2).

### Šablony `{{ }}`

- Uvnitř `{{ }}` smí být **jen cesta k hodnotě** se stejnými pravidly
  jako ve výrazech ([tečka a hranaté závorky](#cesta-k-hodnotě-tečka-a-hranaté-závorky)),
  např. `{{ steps.copy.hashtags[0] }}`. Žádné operátory ani funkce —
  výpočet patří do kroku `set`.
- **Hodnota je celá jedna šablona** (`"{{ steps.copy.hashtags }}"`) →
  vloží se hodnota **se svým typem** (seznam zůstane seznamem, číslo
  číslem, soubor souborem).
- **Šablona uvnitř textu** (`"Téma: {{ inputs.tema }}"`) → výsledek je
  text; text se vloží beze změny, číslo jako číslo (`0.62`), `true` /
  `false`, seznam a objekt jako JSON.
- **`null` se nevkládá potichu.** Odkaz `{{ x }}`, kde `x` je `null`, je
  chyba — v `validate` (třída `config`), když to jde poznat předem, jinak
  za běhu (třída `expression`). Platí pro celou hodnotu i pro šablonu
  v textu. Jediná výjimka: `null` pochází z výslovného `default` kroku
  (autor ho zvolil vědomě) — pak se vloží `null`, v textu jako `null`
  (stejně jako `str(null)`). (§5.4; rozhodnutí koordinátora, viz
  OPEN-QUESTIONS 10.)
- Výsledek šablony se **nikdy znovu nevyhodnocuje** (§5.4): když model
  napíše do textu `{{ inputs.x }}`, zůstane to doslova.
- Šablony se vyhodnocují nad už načteným YAML, takže uvozovky nebo
  složené závorky v textu od modelu nemůžou rozbít strukturu kroku ani
  JSON pro Jev (§5.4). Scénář JSON nikdy neskládá ručně.
- Doslovné `{{` ve v1 napsat nejde (**návrh**; přidá se, až bude potřeba).

### Výrazy

Bezpečně vyhodnocované výrazy v pythonovském stylu (D1c). Tato část
popisuje **jazyk** — co smí autor scénáře napsat a co se stane. Výrazy
vyhodnocuje vlastní malý evaluátor frameworku (rozhodnutí po spiku (c),
report na větvi `spike-expressions`; spike byl vyřazen ze stromu,
výstupy jsou v historii repozitáře do commitu fe90e05); Python se
nikdy nespouští.

#### Co v jazyce je

| Co | Příklad |
|---|---|
| cesta k hodnotě | `steps.copy.caption`, `steps.copy.hashtags[0]`, `steps.copy.hashtags[-1]` |
| literály: text, číslo, `true`, `false`, `null` | `"cs"`, `'cs'`, `0.7`, `3`, `true`, `null` |
| seznamový literál | `["cs", "sk"]` |
| porovnání | `==`, `!=`, `<`, `<=`, `>`, `>=` |
| obsahuje | `in` — prvek v seznamu, podřetězec v textu: `inputs.jazyk in ["cs", "sk"]` |
| logika | `and`, `or`, `not` — jen nad `true`/`false` |
| aritmetika | `+`, `-`, `*`, `/`, `%` (`+` spojí i dva texty) |
| závorky | `(a or b) and c` |
| funkce | jen `len`, `min`, `max`, `round`, `str`, `int`, `float`, `join` (níže) |

Literály `true`, `false`, `null` se píšou stejně jako v YAML a JSON, ne
pythonovské `True`/`False`/`None` (rozhodnuto, OPEN-QUESTIONS 7).
`True` nebo `None` je neznámé jméno → chyba `validate`.

#### Co v jazyce není

Chyba `validate`, běh se nespustí: podmínka `x if c else y`, řezy
`xs[1:3]`, mocnina `**`, volání metod (`"x".upper()`,
`steps.copy.caption.lower()`), přiřazení (`=`, `:=`), `lambda`,
comprehension (`[x for x in …]`), atributy a dunder (`__class__`),
`import`, jiné funkce než ty z tabulky, `{{ }}` uvnitř výrazu.

#### Cesta k hodnotě: tečka a hranaté závorky

- **Tečka čte klíč z objektu**, nic jiného. `steps.copy.hashtags` funguje
  i pro kroky a pole pojmenované `copy`, `items`, `keys`, `get`, `values`
  … (tečka nikdy nesahá na vnitřek Pythonu).
- **Hranaté závorky** jsou index do seznamu (i záporný: `[-1]` = poslední)
  nebo klíč objektu jako text: `steps.kontrola.details["on_brand"]`.
- Chybějící klíč nebo index mimo seznam je chyba (viz níže), nikdy tiché
  `null`.

#### Typy (§5.4)

- Typy `string`, `number` (celé i desetinné), `boolean`, `null`, `list`,
  `object`, `file` se nemíchají. Převod musí být výslovný: `float(x)`,
  `int(x)`, `str(x)`.
- **Porovnání napříč typy je chyba** (`==` i `<`):
  `steps.kontrola.on_brand < "0.7"`, `inputs.limit == "3"`. Jediná
  výjimka: `x == null` a `x != null` jsou dovolené u každého typu. Když
  typy nejsou známé předem, pozná se chyba až za běhu (OPEN-QUESTIONS 14).
- **`and`, `or`, `not` berou jen `true`/`false`.** Žádná pythonová
  „pravdivost" textu, čísla nebo seznamu: `steps.copy.hashtags and …` je
  chyba s radou napsat porovnání, např. `len(steps.copy.hashtags) > 0`.
  (Rozhodnutí koordinátora, OPEN-QUESTIONS 8.)
- **`boolean` není číslo:** `true + 1` je chyba.
- **Operátory a typy:** `-`, `*`, `/`, `%` jen číslo s číslem (`"a" * 3`
  je chyba). `+` jen číslo + číslo, text + text, seznam + seznam.
  **Text + číslo je chyba:** `"on_brand = " + 0.9` → napiš
  `"on_brand = " + str(0.9)`. Výsledný text nebo seznam delší než
  100 000 znaků/prvků = chyba `expression`.
- **`/` dává vždy desetinné číslo:** `7 / 2` = `3.5`, `4 / 2` = `2.0`.
  `%` je zbytek po dělení. Dělení nulou je chyba.
- **`x in y`:** `y` je seznam (prvky musí mít typ `x`, jinak chyba — `3 in
  ["3"]` je chyba, ne `false`), text (`x` je text, hledá se podřetězec)
  nebo objekt (`x` je text, hledá se klíč).
- **Čísla:** celé číslo i číslo s nulovou desetinnou částí (`2.0`) se
  přijme tam, kde se čeká `integer`. `nan` a nekonečno nejsou dovolené —
  výsledek, který by jím byl, je chyba `expression`. Číslo v textu (šablona,
  `str`) má nejkratší zápis, který se přečte zpět stejně:
  `0.1 + 0.2` → `0.30000000000000004`, `4 / 2` → `2.0`.
- `when` a `switch.value` musí dát `boolean`, resp. `string`.

#### Funkce

| Funkce | Co dělá | Typy |
|---|---|---|
| `len(x)` | délka | `string`, `list`, `object` → `number` |
| `min(a, b, …)`, `max(a, b, …)` | nejmenší / největší | čísla (nebo jeden seznam čísel) → `number` |
| `round(x)`, `round(x, n)` | zaokrouhlí na `n` desetinných míst; `round(x)` bez `n` dává celé číslo (`round(2.5)` = `3`, ne `3.0`) | `number` → `number` |
| `str(x)` | převod na text | cokoliv → `string` |
| `int(x)` | z čísla uřízne desetinnou část (`int(2.7)` = `2`); z textu přijme jen celé číslo (`int("3")` = `3`, `int("2.7")` je chyba) | `number`, `string` → `number` |
| `float(x)` | převod na desetinné číslo (`float("0.7")`) | `number`, `string` → `number` |
| `join(seznam, oddělovač)` | spojí seznam textů | `list` textů, `string` → `string` |

- **`round` zaokrouhluje půlku směrem od nuly:** `round(2.5)` = `3`,
  `round(-2.5)` = `-3`, `round(0.125, 2)` = `0.13`. To je **výslovná
  odchylka od Pythonu** (ten zaokrouhluje bankéřsky: `round(2.5)` = `2`),
  protože autor scénáře čeká školní zaokrouhlení. (Rozhodnutí
  koordinátora, OPEN-QUESTIONS 9.)
- `str` dává stejný text jako šablona: `str(null)` = `"null"`,
  `str(true)` = `"true"`, `str(0.62)` = `"0.62"`.
- Funkce kontrolují typy argumentů; špatný typ je chyba s hláškou.

#### Limity

Výraz má nejvýš **2000 znaků** — kontroluje se **před** čtením výrazu,
takže ani obrovský výraz nemůže shodit framework. Hloubka vnoření
(závorky, operátory) je nejvýš **100** — kontroluje se po přečtení, před
vyhodnocením. Výsledný text nebo seznam má nejvýš 100 000 znaků/prvků.

#### Kdy se chyba výrazu pozná

| Kdy | Co | Třída | Následek |
|---|---|---|---|
| `validate` (staticky, před během) | syntaxe; zakázaná konstrukce; neznámá funkce nebo jméno (`True`, `open`); překročený limit; odkaz na neexistující krok, na krok níž nebo v jiné větvi `parallel`; odkaz na krok, který nemusí proběhnout, bez `default`; neznámé pole kroku, jehož výstup je známý (`schema`, `jev`, `set`, `outputs` při `call`); porovnání nebo operace napříč typy, když jsou typy známé předem; `null` v šabloně, když je to vidět předem | `config` | běh se vůbec nespustí |
| za běhu | chybějící klíč (např. v `details` od Jev), špatný typ hodnoty, index mimo seznam, dělení nulou, převod `int("abc")`, `nan`/nekonečno, příliš dlouhý výsledek, `null` v šabloně, `switch.value` není text | `expression` | krok selže, **neopakuje se**; běh končí `failed` (jako `fail` kroku), pokud krok nemá `on_error: continue` |

#### Chybové hlášky

Hlášky jsou česky, ukazují výraz, stříškou `^` místo chyby a u
chybějícího klíče vyjmenují dostupné klíče. Příklady:

```
config: krok "stop", when: porovnání number s string — převeď typ výslovně (float(), str())
  steps.kontrola.on_brand < "0.7"
                            ^
```

```
expression: krok "souhrn": 'steps' nemá klíč 'kontrol' (dostupné: copy, kontrola, foto_prompt)
  steps.kontrol.on_brand
        ^
```

```
config: krok "podle_delky", when: 'and' chce true/false, dostal list — porovnej výslovně (např. len(x) > 0)
  steps.copy.hashtags and inputs.jazyk == "cs"
  ^
```

#### Pozor na YAML

Výraz, který začíná uvozovkou, `[` nebo `{`, nebo obsahuje `: ` či ` #`,
obal celý do jednoduchých uvozovek: `when: '"x" == inputs.jazyk'`,
`when: '["cs", "sk"] == inputs.jazyky'`.

### Typ `file`

- Hodnota `file` vzniká **jen** z kroku `image` (a z obrázku, který vrátí
  nástroj v `task`). Z textu ji vytvořit nejde: text v místě, kde se čeká
  `file` (`image: "/home/x/.env"`), je chyba `validate`.
- Cesta je vždy uvnitř složky běhu; framework to před nahráním ověří
  (skutečná cesta po rozbalení odkazů). Jinak chyba `config`.
- `file: null` z výslovného `default` jde do callbacku jako `null` (nic se
  nenahraje).

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
| `transient` | HTTP 408, 429, 5xx, výpadek sítě; HTTP 200 s `finish_reason: error`; HTTP 200 bez obsahu a bez odmítnutí; chybějící `usage.cost`; selhání handshaku MCP kvůli síti/5xx; selhání nahrání souboru; `validate` bez sítě a bez cache `/models` | zopakuje volání (`retry`) s prodlevou, pak chyba |
| `schema` | odpověď nejde naparsovat nebo nesedí na `schema` | zopakuje volání (`retry`), model dostane chybu jako zpětnou vazbu |
| `content` | model nebo filtr odmítl obsah: HTTP 403 (`content_policy_violation`, `refusal`), HTTP 200 s `finish_reason: content_filter` nebo vyplněným `refusal`; `image` bez obrázku po vyčerpání `retry` (viz [`image`](#image)) | neopakuje, chyba |
| `budget` | rozpočet kroku, agenta nebo běhu vyčerpán ([Rozpočet](#rozpočet)); `max_turns` bez odpovědi; HTTP 402 (došel kredit / limit klíče); cena zůstala neznámá i po `retry` („cena neznámá") | ukončí, neopakuje |
| `timeout` | překročen `timeout` kroku nebo běhu; timeout volání nástroje MCP | ukončí, neopakuje |
| `config` | chyba ve scénáři, agentovi nebo konfiguraci — hlavně z `validate` před během (včetně statické kontroly výrazů a šablon, viz [§5](#kdy-se-chyba-výrazu-pozná)); za běhu HTTP 400/401/403 (mimo obsah)/404, selhání spuštění MCP serveru (proces neběží, 401), `dedupe` ve stavu `started`, poměr stran obrázku nesedí na `aspect_ratio`, `finish_reason: length` (useknuto limitem `max_tokens`; opakování nepomůže — zvyš `max_tokens` aliasu v `config.yaml`) | ukončí, neopakuje |
| `expression` | výraz nebo šablona selhaly **za běhu**: chybějící klíč, špatný typ hodnoty, index mimo seznam, dělení nulou, `null` v šabloně (viz [§5](#kdy-se-chyba-výrazu-pozná)) | chová se jako `fail` kroku: neopakuje, ukončí (pokud krok nemá `on_error: continue`) |
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
2. `finish_reason` je `stop` (u `task` průběžně i `tool_calls`; na úrovni
   kaskády `tool_wrapper` `tool_calls` s `_submit_output`),
3. je tam obsah: text, JSON podle `schema`, odpovědi Jev na všechny
   otázky, u `image` aspoň jeden obrázek.

Navíc musí být známá cena (`usage.cost`), jinak nejde hlídat rozpočet —
viz [Rozpočet](#rozpočet).

Příklad ze spiku (a): Gemini vrátilo HTTP 200 s `finish_reason: "error"`,
`completion_tokens: 0` a useknutým JSON → třída `transient`, opakování.

### Rozpočet

- **Před každým voláním:** když útrata kroku, agenta nebo běhu už dosáhla
  rozpočtu, volání se nespustí → chyba `budget`.
- Volání, které rozpočet **překročí**, se dokončí a jeho výsledek platí;
  zapíše se varování „rozpočet překročen o X USD".
- Ve `parallel` platí totéž pro každou větev: překročení je nejvýš o jedno
  volání na větev.
- Chybějící `usage.cost` = opakovat jako `transient`; po vyčerpání
  `retry` třída `budget` se zprávou „cena neznámá". Nic se nedopočítává
  odhadem.
- Obrázky hlídá navíc `limits.run_image_budget_usd`; jejich čas se ve
  záznamu uvádí zvlášť (`run_finished.image_duration_s`), samostatný
  časový limit pro obrázky ve v1 není.

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
- soubor se čte jako YAML 1.2 core, bez duplicitních klíčů; čtou se jen
  soubory přímo ve složce, podsložky se ignorují (hodí se třeba na archiv),
- `call` jen na scénář s `callable: true`,
- oprávnění podle `mcp.yaml`: agent se serverem, u kterého není v
  `agents`; scénář mimo `scenarios` serveru; nástroj mimo `tools` serveru
  → chyba (viz [config.md](config.md#mcpyaml--registr-mcp-serverů)),
- `id` unikátní; výrazy a šablony podle tabulky „Kdy se chyba výrazu
  pozná" v [§5](#kdy-se-chyba-výrazu-pozná) (syntaxe, zakázané
  konstrukce, funkce, limity, odkazy jen na kroky výš a ne do jiné větve
  `parallel`, typy tam, kde jsou známé předem),
- odkaz na krok, který nemusí proběhnout, má `default`,
- `output` je poslední a sedí na `outputs`; `call` sedí na `inputs` a
  `outputs` volaného scénáře; žádné cykly, hloubka v limitu,
- žádný nedosažitelný krok za nepodmíněným `fail`,
- `models.<alias>.id` existuje v `GET /api/v1/models` (výsledek se
  cachuje na 24 h v `<runs>/_models.json`; bez sítě a bez cache →
  `transient`; s `base_url` falešného poskytovatele se ptá jeho `/models`),
- obrazové aliasy umí výstup obrázku; alias agenta použitého v `task`
  má v `supported_parameters` `tools`; alias kroku se `schema` má
  `structured_outputs` nebo `tools` (§5.5, §5.7),
- dva povolené nástroje se po normalizaci jména (`server__tool`, jen
  `[a-zA-Z0-9_-]`, max 64 znaků, DESIGN §5.8) nesmí jmenovat stejně.

`--dry-run` navíc vypíše plán: pořadí kroků, výsledné nástroje každého
`task`, nástroje, které každý MCP server nabízí (aby šel napsat seznam
`tools`), a limity.
