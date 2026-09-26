# Díl 4 — Paralelně a s obrázkem

**Čas:** asi 20 minut · **Útrata:** jeden ostrý běh s obrázkem za ~0,07 USD
**Co budeš umět:** pustit dvě větve souběžně (`parallel`), vygenerovat
obrázek (`image`), hlídat peníze (`budget_usd`) a čas (`timeout`),
nastavit opakování (`retry`), přežít selhání kroku (`on_error`) a číst
třídy chyb v `summary.md`.

Předpoklad: díly 1–3.

---

## Krok 1 — agent s jiným modelem

Popis fotky pro generátor obrázků napíše levnější a rychlejší model.
`workflows/agents/tutorial-ilustrator.md`:

```markdown
---
version: 1
name: tutorial-ilustrator
description: Píše anglický popis produktové fotky pro generátor obrázků (tutoriál, díl 4)
model: rychly
limits:
  budget_usd: 0.01
---
Jsi produktový fotograf. Z popisu produktu napíšeš popis fotky pro
generátor obrázků:

- anglicky, 30 až 60 slov,
- produkt na čistém pozadí, měkké světlo, pohled zepředu,
- bez textu, nápisů a log v obraze, bez lidí.
```

Jediná změna proti dosavadním agentům: `model: rychly` (Gemini Flash-Lite).

---

## Krok 2 — scénář s `parallel` a `image`

`workflows/scenarios/tutorial-04-paralelne.yaml`:

```yaml
version: 1
name: tutorial-04-paralelne
description: Souběžně vymyslí název se sloganem a vyfotí produkt (tutoriál, díl 4)

inputs:
  produkt:
    type: string
    required: true
    description: Jaký produkt pojmenováváme a fotíme

outputs:
  nazev:
    type: string
  slogan:
    type: string
  foto:
    type: file
    description: Produktová fotka 1:1

steps:
  # 1. Dvě větve běží souběžně. budget_usd u parallel = součet všeho uvnitř.
  - id: soucasne
    budget_usd: 0.15
    parallel:
      texty:
        - id: navrh
          ask:
            agent: tutorial-pojmenovavac
            prompt: "Vymysli 3 názvy pro tento produkt: {{ inputs.produkt }}."
            schema:
              nazvy: [string]
        - id: slogan
          ask:
            agent: tutorial-sloganista
            prompt: "Napiš slogan pro produkt {{ inputs.produkt }} s názvem {{ steps.navrh.nazvy[0] }}."
            schema:
              slogan: string
      vizual:
        - id: popis
          ask:
            agent: tutorial-ilustrator
            prompt: "Produkt: {{ inputs.produkt }}"
            schema:
              popis: string
        - id: fotka
          budget_usd: 0.10
          timeout: 2m
          retry: 1
          image:
            model: gemini-image
            prompt: "{{ steps.popis.popis }}"
            aspect_ratio: "1:1"

  # 2. Až doběhnou obě větve.
  - id: out
    output:
      nazev: "{{ steps.navrh.nazvy[0] }}"
      slogan: "{{ steps.slogan.slogan }}"
      foto: "{{ steps.fotka.file }}"
```

### `parallel`

- Pod `parallel` jsou **pojmenované větve** (`texty`, `vizual`). Každá je
  seznam kroků, které v ní běží jeden po druhém.
- Větve běží **souběžně**. Krok za `parallel` (`out`) začne, až doběhnou
  všechny.
- **Výstupy** kroků ve větvích čteš normálně přes jejich `id`
  (`steps.navrh…`, `steps.fotka…`). Jméno větve je jen pro čitelnost
  a záznam; `parallel` sám žádný výstup nemá.
- Krok ve větvi smí číst kroky **nad `parallel`** a kroky nad sebou **ve
  stejné větvi** (`slogan` čte `navrh`). Do jiné větve číst nesmí —
  nevíš, co doběhne dřív.

### `image`

- `model` — alias **obrazového** modelu z `config.yaml` (`gemini-image`).
- `prompt` — popis obrázku (šablona).
- `aspect_ratio` — poměr stran jako **text v uvozovkách** (`"1:1"`,
  `"4:5"`). Framework po uložení poměr zkontroluje; odchylka přes 2 % je
  chyba, nic se tiše neořízne.
- Výstup: `steps.fotka.file` — typ `file`. Ten vzniká **jen** z kroku
  `image`; napsat do `output` cestu jako text nejde.

### Nové vlastnosti kroků

| Vlastnost | Tady | Co dělá |
|---|---|---|
| `budget_usd` | `0.15` u `parallel`, `0.10` u `fotka` | kolik smí krok stát; u `parallel` součet všeho uvnitř |
| `timeout` | `2m` | nejdelší doba kroku (`s`, `m`, `h`) |
| `retry` | `1` | kolikrát se **jedno volání** zopakuje po chybě `transient` nebo `schema` (výchozí 2) |

Vedle toho platí limity celého běhu z `config.yaml` (mění je vlastník):

```bash
grep -A5 "^limits:" workflows/config.yaml
```

```
limits:
  run_budget_usd: 1.00
  run_image_budget_usd: 0.30
  run_timeout: 1h
  max_call_depth: 3
```

`run_image_budget_usd` hlídá obrázky zvlášť — jsou o dva řády dražší než
text. Výsledný limit kroku je vždy **nejmenší** z: limit kroku, limit
agenta, zbytek limitu běhu.

---

## Krok 3 — plán a falešný běh

```bash
agencast validate workflows/scenarios/tutorial-04-paralelne.yaml
agencast run workflows/scenarios/tutorial-04-paralelne.yaml -i produkt="veganská zmrzlina z ovesného mléka" --dry-run
```

```
v pořádku: tutorial-04-paralelne (6 kroků)
# Plán: tutorial-04-paralelne

Souběžně vymyslí název se sloganem a vyfotí produkt (tutoriál, díl 4)

Limity běhu: rozpočet 1.0 USD (z toho obrázky 0.3 USD), čas 1h. Jev: jev-1.13.

| # | Krok | Typ | Podmínka | Co udělá | Limity |
|---|---|---|---|---|---|
| 1 | soucasne | parallel |  | větve: texty, vizual | 0.15 USD |
| 2 | ↳ navrh | ask |  | agent tutorial-pojmenovavac → chytry (anthropic/claude-haiku-4.5); schema: nazvy (kaskáda od native_schema) | 0.01 USD, 2m |
| 3 | ↳ slogan | ask |  | agent tutorial-sloganista → chytry (anthropic/claude-haiku-4.5); schema: slogan (kaskáda od native_schema) | 0.01 USD, 2m |
| 4 | ↳ popis | ask |  | agent tutorial-ilustrator → rychly (google/gemini-3.5-flash-lite); schema: popis (kaskáda od tool_wrapper) | 0.01 USD, 2m |
| 5 | ↳ fotka | image |  | gemini-image (google/gemini-3.1-flash-image), poměr 1:1 | 0.1 USD, 2m, retry 1 |
| 6 | out | output |  | nazev, slogan, foto |  |
```

Fixtura `framework/tests/golden/tutorial-04-paralelne.yaml`:

```yaml
# Skriptované odpovědi pro tutorial-04-paralelne.
# Krok image nepotřebuje nic: falešný poskytovatel vyrobí šedé PNG v poměru aspect_ratio.
navrh:
  - json:
      nazvy: ["Ovesňák", "Mrazík Oves", "Zmrzlá Pláň"]
slogan:
  - json:
      slogan: "Zmrzlina, která roste na poli"
popis:
  - json:
      popis: "A pint of oat milk ice cream on a clean white background, soft light, front view, no text."
```

```bash
agencast run workflows/scenarios/tutorial-04-paralelne.yaml -i produkt="veganská zmrzlina z ovesného mléka" --fake framework/tests/golden/tutorial-04-paralelne.yaml
```

```
běh 20260925-151749-tutorial-04-paralelne-85a6: úspěch · 0,0 s · 0,0403 USD
```

Falešný obrázek „stojí" 0,04 USD, aby šlo zkoušet rozpočty (krok 6).
Placené to není.

---

## Krok 4 — ostrý běh s obrázkem

```bash
agencast run workflows/scenarios/tutorial-04-paralelne.yaml -i produkt="veganská zmrzlina z ovesného mléka"
```

```
běh 20260925-151755-tutorial-04-paralelne-8c76: úspěch · 10,5 s · 0,0683 USD
záznam: ~/orca/workspaces/multiagent-workflows/tutorials/runs/20260925-151755-tutorial-04-paralelne-8c76/summary.md
```

```
# tutorial-04-paralelne — úspěch

Souběžně vymyslí název se sloganem a vyfotí produkt (tutoriál, díl 4)
Běh `20260925-151755-tutorial-04-paralelne-8c76` · 25. 9. 2026 15:17:55 UTC · 10,5 s · 0,0683 USD (z toho obrázky 0,0672 USD)

## Vstupy
- produkt: veganská zmrzlina z ovesného mléka

## Kroky
| # | Krok | Typ | Stav | Čas | Cena | Poznámka |
|---|---|---|---|---|---|---|
| 1 | soucasne | parallel | ✓ | 10,5 s | 0,0683 |  |
| 2 | navrh | ask | ✓ | 2,1 s | 0,0005 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 3 | slogan | ask | ✓ | 1,6 s | 0,0004 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 4 | popis | ask | ✓ | 1,2 s | 0,0002 | rychly → google/gemini-3.5-flash-lite (tool_wrapper) |
| 5 | fotka | image | ✓ | 9,2 s | 0,0672 | image.png, 1024×1024 |
| 6 | out | output | ✓ | 0,0 s | 0 |  |
| | Celkem | | | 10,5 s | 0,0683 | z toho obrázky 0,0672 |

## Varování
žádná

## Výstup
- nazev: „Ovesový Raj"
- slogan: „Ovesový Raj - čistá vegan sladkost bez viny"
- foto: file://~/orca/workspaces/multiagent-workflows/tutorials/outputs/20260925-151755-tutorial-04-paralelne-8c76-6f88f7d39aeab16913150e899dfe8070/foto.png
```

Co z toho vyčteš:

- **Souběh funguje:** kroky ve větvích dohromady trvaly 2,1 + 1,6 + 1,2 +
  9,2 = 14,1 s, celý `parallel` jen 10,5 s. Větev `texty` doběhla, zatímco
  se fotka ještě generovala.
- **Obrázek je 98 % ceny** (0,0672 z 0,0683 USD). Proto má vlastní limit.
- **1024×1024** — poměr 1:1 sedí.
- **`foto`** je `file://` cesta, protože `config.yaml` má
  `storage.type: local` — soubor se zkopíroval do `outputs/`. Obrázek
  samotný je i ve složce běhu: `steps/05-fotka/image.png` (u nás: bílá
  miska se kopečkem zmrzliny na světle šedém pozadí).

Souběh je vidět i v `events.jsonl` (čas, událost, krok, větev):

```
15:17:55.402 step_started soucasne
15:17:55.402 step_started navrh texty
15:17:55.416 step_started popis vizual
15:17:56.655 step_finished popis
15:17:56.656 step_started fotka vizual
15:17:57.514 step_finished navrh
15:17:57.514 step_started slogan texty
15:17:59.097 step_finished slogan
15:18:05.886 step_finished fotka
15:18:05.886 step_finished soucasne
```

(Tenhle výpis jsem z `events.jsonl` vytáhl krátkým skriptem v Pythonu;
formátu `events.jsonl` se věnuje díl 5.)

---

## Krok 5 — třídy chyb

Každá chyba má **třídu**. Podle ní framework ví, jestli má smysl to
zkoušet znovu, a ty (nebo n8n) víš, co dělat:

| Třída | Co se stalo | Opakuje se? |
|---|---|---|
| `transient` | přetížení (HTTP 429), výpadek, 5xx, prázdná odpověď | ano (`retry`) |
| `schema` | JSON od modelu nesedí na `schema` (díl 2) | ano (`retry`) |
| `content` | model odmítl obsah | ne |
| `budget` | došly peníze kroku, agenta nebo běhu | ne |
| `timeout` | došel čas kroku nebo běhu | ne |
| `config` | chyba v souborech, nebo HTTP 400/401/404 | ne |
| `expression` | výraz selhal za běhu (díl 2, 3) | ne |
| `fail` | tvůj krok `fail` (díl 3) | ne |

Všechny následující ukázky jsou falešné běhy s fixturou uloženou
v `/tmp/` — nic nestojí.

### `transient` → opakování

`/tmp/pretizeni.yaml`:

```yaml
navrh:
  - status: 429
    error: "Rate limit exceeded"
  - json:
      nazvy: ["Ovesňák", "Mrazík Oves", "Zmrzlá Pláň"]
```

```bash
agencast run workflows/scenarios/tutorial-04-paralelne.yaml -i produkt="zmrzlina" --fake /tmp/pretizeni.yaml
```

```
běh 20260925-151818-tutorial-04-paralelne-42d6: úspěch · 0,0 s · 0,0403 USD
```

Běh prošel — první pokus dostal HTTP 429, druhý uspěl. V `events.jsonl`:

```
{"ts":"2026-09-25T15:18:18.099Z","type":"error","step":"navrh","class":"transient","message":"HTTP 429: Rate limit exceeded","attempt":1,"will_retry":true,"http_status":429}
```

V `summary.md` je u varování `žádná` — odmítnuté volání nic nestojí,
opakování po `transient` je normální provoz.

### `content` → konec

`/tmp/odmitnuti.yaml`:

```yaml
fotka:
  - refusal: "I can't generate this image."
```

```bash
agencast run workflows/scenarios/tutorial-04-paralelne.yaml -i produkt="zmrzlina" --fake /tmp/odmitnuti.yaml
```

```
content v kroku fotka: model odmítl: I can't generate this image.
běh 20260925-151818-tutorial-04-paralelne-b318: chyba · 0,0 s · 0,0403 USD
```

~~~
## Chyba
- třída: `content`
- krok: `fotka`
- zpráva:

```
model odmítl: I can't generate this image.
```

Běh skončil v kroku fotka.
…
| 1 | soucasne | parallel | chyba | 0,0 s | 0,0403 | viz Chyba |
| 2 | navrh | ask | ✓ | 0,0 s | 0,0001 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 3 | slogan | ask | ✓ | 0,0 s | 0,0001 | chytry → anthropic/claude-haiku-4.5 (native_schema) |
| 4 | popis | ask | ✓ | 0,0 s | 0,0001 | rychly → google/gemini-3.5-flash-lite (tool_wrapper) |
| 5 | fotka | image | chyba | 0,0 s | 0,0400 | viz Chyba |
~~~

Odmítnutí se neopakuje, i když má krok `retry: 1` — stejný prompt by
dopadl stejně. Pozor: generátor obrázků sám skoro nic neodmítá (ani
skutečné osoby). Pravidla obsahu proto hlídá scénář — Jevem nad popisem
fotky, jako to dělá `workflows/scenarios/ig-post.yaml`.

### Když selže jedna větev

`/tmp/zruseni.yaml` — `navrh` dostane HTTP 400 (chyba `config`, neopakuje
se), fotka zatím „generuje" (`sleep: 1`):

```yaml
navrh:
  - status: 400
    error: "Invalid request"
fotka:
  - sleep: 1
```

```bash
agencast run workflows/scenarios/tutorial-04-paralelne.yaml -i produkt="zmrzlina" --fake /tmp/zruseni.yaml
```

```
config v kroku navrh: HTTP 400: Invalid request
běh 20260925-151846-tutorial-04-paralelne-9332: chyba · 0,0 s · 0,0001 USD
```

```
| 1 | soucasne | parallel | chyba | 0,0 s | 0,0001 | viz Chyba |
| 2 | navrh | ask | chyba | 0,0 s | 0 | viz Chyba |
| 4 | popis | ask | ✓ | 0,0 s | 0,0001 | rychly → google/gemini-3.5-flash-lite (tool_wrapper) |
| 5 | fotka | image | zrušeno | 0,0 s | 0 |  |
| | Celkem | | | 0,0 s | 0,0001 |  |
```

Chyba v jedné větvi **zruší ostatní** (`zrušeno`) a běh končí. Krok 3
(`slogan`) v tabulce chybí — na něj běh nedošel, a takové kroky se
nezapisují.

---

## Krok 6 — `budget_usd` a `timeout` v akci

Zkusíme to s přísnějšími limity. **Dočasně** změň u kroku `fotka`
`budget_usd: 0.10` na `budget_usd: 0.03` (falešný obrázek stojí 0,04):

```bash
agencast run workflows/scenarios/tutorial-04-paralelne.yaml -i produkt="zmrzlina" --fake framework/tests/golden/tutorial-04-paralelne.yaml
```

```
běh 20260925-151828-tutorial-04-paralelne-3d22: úspěch · 0,0 s · 0,0403 USD
```

```
## Varování
- rozpočet kroku 'fotka' překročen o 0.0100 USD (krok fotka)
```

Běh prošel! Pravidlo: **rozpočet se kontroluje před každým voláním.**
Volání, které začalo pod limitem, se dokončí a platí (peníze jsou stejně
utracené) — a zapíše se varování. Další volání už ale nezačne. To uvidíš,
když první pokus selže a `retry` by chtěl zkusit druhý —
`/tmp/bez-obrazku.yaml`:

```yaml
fotka:
  - finish_reason: error
```

```bash
agencast run workflows/scenarios/tutorial-04-paralelne.yaml -i produkt="zmrzlina" --fake /tmp/bez-obrazku.yaml
```

```
budget v kroku fotka: rozpočet kroku 'fotka' vyčerpán (0.0400 z 0.03 USD)
běh 20260925-151828-tutorial-04-paralelne-13cb: chyba · 2,0 s · 0,0403 USD
```

V `events.jsonl` je celý příběh: první pokus skončil `transient`
(`will_retry: true`), po 2 s čekání se měl zkusit znovu, ale rozpočet
kroku už byl pryč → `budget`:

```
{"ts":"2026-09-25T15:18:28.324Z","type":"error","step":"fotka","class":"transient","message":"poskytovatel vrátil HTTP 200 s finish_reason: error","attempt":1,"will_retry":true,"http_status":null}
{"ts":"2026-09-25T15:18:30.326Z","type":"error","step":"fotka","class":"budget","message":"rozpočet kroku 'fotka' vyčerpán (0.0400 z 0.03 USD)","attempt":null,"will_retry":false,"http_status":null}
```

Vrať `budget_usd: 0.10`. Teď **dočasně** změň `timeout: 2m` na
`timeout: 2s` a nech falešný obrázek „generovat" 5 sekund —
`/tmp/pomaly.yaml`:

```yaml
fotka:
  - sleep: 5
```

```bash
agencast run workflows/scenarios/tutorial-04-paralelne.yaml -i produkt="zmrzlina" --fake /tmp/pomaly.yaml
```

```
timeout v kroku fotka: překročen časový limit kroku (2s)
běh 20260925-151839-tutorial-04-paralelne-a82b: chyba · 2,0 s · 0,0003 USD
```

Vrať `timeout: 2m`. Skutečné generování trvalo 9,2 s, 2 minuty jsou
bezpečná rezerva.

---

## Co sis zapamatoval

- `parallel`: pojmenované větve běží souběžně; výstupy čteš přes `id`
  kroků; do jiné větve nečteš; chyba jedné větve zruší ostatní.
- `image`: alias obrazového modelu, `aspect_ratio` v uvozovkách, výstup
  `steps.<id>.file`. Obrázek ≈ 0,07 USD.
- `budget_usd` se kontroluje **před** voláním; `timeout` utne krok;
  `retry` opakuje jen `transient` a `schema`.
- Třída chyby v `summary.md` ti řekne, co dělat: `transient` zkus
  později, `content` změň prompt, `budget`/`timeout` uprav limit,
  `config` oprav soubor.

---

## Cvičení

Obrázek je „bonus": když se nepovede (třeba ho model odmítne), chceš
aspoň název a slogan a běh má skončit **úspěchem** s varováním. Uprav
scénář tak, aby `foto` v takovém případě bylo `null`. Ulož jako
`workflows/scenarios/tutorial-04-cviceni.yaml` s fixturou a ověř falešným
během s odmítnutým obrázkem.

Nápověda: `on_error` a `default` ze [scenario.md §3](../spec/scenario.md#3-společné-vlastnosti-kroků).

<details>
<summary>Řešení</summary>

```bash
diff workflows/scenarios/tutorial-04-paralelne.yaml workflows/scenarios/tutorial-04-cviceni.yaml
```

```
2,3c2,3
< name: tutorial-04-paralelne
< description: Souběžně vymyslí název se sloganem a vyfotí produkt (tutoriál, díl 4)
---
> name: tutorial-04-cviceni
> description: Souběžně vymyslí název se sloganem a vyfotí produkt (tutoriál, díl 4 — řešení cvičení)
18c18
<     description: Produktová fotka 1:1
---
>     description: Produktová fotka 1:1 (null, když se nepovedla)
48a49,50
>           on_error: continue
>           default: { file: null }
```

- `on_error: continue` — chyba kroku neukončí běh.
- `default: { file: null }` — výstup kroku, když selže. Musí obsahovat
  všechna pole výstupu (`image` má jen `file`). `null` z výslovného
  `default` se do výstupu vložit smí — zvolil jsi ho vědomě.

Fixtura `framework/tests/golden/tutorial-04-cviceni.yaml` je stejná jako
u hlavního scénáře (zlatý test ověřuje úspěšnou cestu):

```yaml
# Skriptované odpovědi pro tutorial-04-cviceni (řešení cvičení z dílu 4).
# Krok image nepotřebuje nic: falešný poskytovatel vyrobí šedé PNG v poměru aspect_ratio.
navrh:
  - json:
      nazvy: ["Ovesňák", "Mrazík Oves", "Zmrzlá Pláň"]
slogan:
  - json:
      slogan: "Zmrzlina, která roste na poli"
popis:
  - json:
      popis: "A pint of oat milk ice cream on a clean white background, soft light, front view, no text."
```

Odmítnutý obrázek, `/tmp/odmitnuti-cviceni.yaml`:

```yaml
navrh:
  - json:
      nazvy: ["Ovesňák", "Mrazík Oves", "Zmrzlá Pláň"]
slogan:
  - json:
      slogan: "Zmrzlina, která roste na poli"
fotka:
  - refusal: "I can't generate this image."
```

```bash
agencast validate workflows/scenarios/tutorial-04-cviceni.yaml
agencast run workflows/scenarios/tutorial-04-cviceni.yaml -i produkt="zmrzlina" --fake /tmp/odmitnuti-cviceni.yaml
```

```
v pořádku: tutorial-04-cviceni (6 kroků)
běh 20260925-151900-tutorial-04-cviceni-77d9: úspěch · 0,0 s · 0,0403 USD
```

```
| 5 | fotka | image | chyba, pokračuje | 0,0 s | 0,0400 | selhal, použit default |
| 6 | out | output | ✓ | 0,0 s | 0 |  |
| | Celkem | | | 0,0 s | 0,0403 | z toho obrázky 0,0400 |

## Varování
- krok fotka selhal (content: model odmítl: I can't generate this image.) — běh pokračuje s default (on_error: continue)

## Výstup
- nazev: „Ovesňák"
- slogan: „Zmrzlina, která roste na poli"
- foto: null
```

A v `callback.json`: `"status": "succeeded"`, `"foto": null` a varování
v `"warnings"` — n8n tak pozná, že má příspěvek poslat bez obrázku nebo
ho vrátit k ruční práci.

</details>

**Další díl:** [Od hraní k provozu](05-od-hrani-k-provozu.md).
