# Díl 1 — První agent a první scénář

**Čas:** asi 15 minut · **Útrata:** jeden ostrý běh za ~0,0002 USD
**Co budeš umět:** napsat agenta, napsat scénář s jedním krokem, zkontrolovat
ho, vyzkoušet ho zadarmo a jednou pustit naostro.

Úkol dílu je schválně primitivní: agent **pojmenovávač** vymyslí tři názvy
pro produkt.

> Všechny příkazy spouštěj **z projektu `examples/tutorial`** (z kořene klonu
> nejprve `cd examples/tutorial`, z balíčku `cd ~/agencast-tutorial`). Výstupy v tomto dílu jsou skutečné — z běhů
> 25. 9. 2026. Tvoje `run_id`, časy a texty od modelu budou jiné.

---

## Krok 0 — zkratka pro příkaz

Po instalaci balíčku je `agencast` přímo v PATH. Pouze při práci z klonu
bez instalace nástroje si nastav zkratku (platí do zavření terminálu):

```bash
alias agencast="uv run --project ../../framework agencast"
agencast --help
```

```
usage: agencast [-h] {validate,run,runs} ...

AgenCast 0.3.0 — scénáře s LLM agenty

positional arguments:
  {validate,run,runs}
    validate           zkontroluje scénář, agenty, skilly a config
    run                spustí scénář
    runs               záznamy běhů
…
```

Tři příkazy — to je všechno, co budeš v dílech 1–5 potřebovat.

---

## Krok 1 — kam co patří

```
workflows/
  agents/       ← sem píšeš agenty (*.md)
  scenarios/    ← sem píšeš scénáře (*.yaml)
  skills/       ← skilly (v tomhle dílu nepotřebuješ)
  config.yaml   ← modely, limity, klíče — mění jen vlastník
```

`config.yaml` už existuje. **Neměníš ho** — patří vlastníkovi (to jsi sice
ty, ale v roli „správce", ne „autora scénáře"; k tomu se vrátíme v dílu 5).
Pro teď z něj potřebuješ vědět jen jedno: jaké **aliasy modelů** máš
k dispozici.

```bash
grep -A4 "^models:" workflows/config.yaml
```

```
models:
  chytry:       { id: anthropic/claude-haiku-4.5 }
  rychly:       { id: google/gemini-3.5-flash-lite, structured_output: tool_wrapper }
  gemini-image: { id: google/gemini-3.1-flash-image }
```

Agent nikdy neříká „chci Claude Haiku 4.5". Říká „chci `chytry`". Který
model se pod tím schovává, rozhoduje `config.yaml`.

---

## Krok 2 — první agent

Vytvoř soubor `workflows/agents/tutorial-pojmenovavac.md`:

```markdown
---
version: 1
name: tutorial-pojmenovavac
description: Vymýšlí krátké názvy pro produkty (tutoriál, díl 1)
model: chytry
limits:
  budget_usd: 0.01
---
Jsi zkušený tvůrce názvů produktů. Píšeš česky.

Pravidla:
- Každý název má nejvýš dvě slova a dá se snadno vyslovit.
- Nepoužívej existující známé značky.
- Odpovídej jen názvy, bez vysvětlování.
```

Soubor má dvě části:

1. **Frontmatter** — mezi dvěma řádky `---`. Konfigurace v YAML.
2. **Tělo** — pod druhým `---`. Instrukce pro model (system prompt), běžný
   Markdown. Nesmí být prázdné.

Pole ve frontmatteru, která jsou **povinná**:

| Pole | Co znamená |
|---|---|
| `version` | verze formátu, vždy `1` |
| `name` | jméno agenta — **stejné jako jméno souboru** bez `.md`; malá písmena, číslice, pomlčka |
| `description` | jedna věta pro tebe; modelu se neposílá |
| `model` | alias z `config.yaml` (tady `chytry`) |
| `limits.budget_usd` | kolik USD smí stát jeden krok s tímto agentem |

Nic jiného ve frontmatteru být nesmí — ani překlep. To je dobrá zpráva:
framework ti překlep neodpustí potichu, ale řekne ti ho (uvidíš v kroku 4).

> Proč prefix `tutorial-`? Aby soubory z tutoriálu nepletly tvoje skutečné
> agenty. Ve vlastní práci pojmenuj agenta, jak chceš.

---

## Krok 3 — první scénář

Vytvoř `workflows/scenarios/tutorial-01-nazvy.yaml`:

```yaml
version: 1
name: tutorial-01-nazvy
description: Vymyslí tři názvy pro produkt (tutoriál, díl 1)

inputs:
  produkt:
    type: string
    required: true
    description: Jaký produkt pojmenováváme

outputs:
  nazvy:
    type: string
    description: Tři návrhy názvů, každý na vlastním řádku

steps:
  # 1. Agent vymyslí názvy.
  - id: navrh
    ask:
      agent: tutorial-pojmenovavac
      prompt: "Vymysli 3 názvy pro tento produkt: {{ inputs.produkt }}. Každý na vlastní řádek."

  # 2. Výsledek běhu.
  - id: out
    output:
      nazvy: "{{ steps.navrh.text }}"
```

Čti ho shora dolů:

- **Hlavička** — `version`, `name` (opět = jméno souboru bez `.yaml`),
  `description`.
- **`inputs`** — co scénář dostane zvenku. Každý vstup má `type` a buď
  `required: true`, **nebo** `default` (nikdy obojí, nikdy nic).
- **`outputs`** — co scénář vrátí. Je to „smlouva": n8n (nebo kdokoli, kdo
  scénář spustí) se může spolehnout, že dostane právě tato pole.
- **`steps`** — kroky, běží shora dolů, jeden po druhém.
  - `ask` = jedno volání modelu přes agenta. Bez `schema` vrátí text,
    který je pak vidět jako `steps.navrh.text`.
  - `output` = poslední krok; plní pole z `outputs`.
- **`{{ … }}`** je **šablona**: jen vloží hodnotu. `{{ inputs.produkt }}`
  vloží vstup, `{{ steps.navrh.text }}` vloží odpověď kroku `navrh`.

---

## Krok 4 — `agencast validate`

Než cokoli spustíš, nech si scénář zkontrolovat:

```bash
agencast validate workflows/scenarios/tutorial-01-nazvy.yaml
```

```
v pořádku: tutorial-01-nazvy (2 kroky)
```

`validate` ověří scénář, agenta, `config.yaml` a navíc se zeptá
OpenRouteru, jestli model `anthropic/claude-haiku-4.5` opravdu existuje.
(Bez sítě přidej `--offline`, pak tuhle poslední kontrolu vynechá.)

Teď schválně něco rozbij, ať víš, jak vypadá chyba. Smaž z agenta dva řádky
`limits:` a `budget_usd: 0.01` a spusť `validate` znovu:

```
config: agents/tutorial-pojmenovavac.md: chybí povinné pole 'limits'
```

Vrať je zpátky. Přepiš `model:` na `modle:`:

```
config: agents/tutorial-pojmenovavac.md: neznámé pole 'modle' (překlep?)
config: agents/tutorial-pojmenovavac.md: chybí povinné pole 'model'
```

Oprav a napiš alias s překlepem, `model: chytrej`:

```
config: agents/tutorial-pojmenovavac.md: model 'chytrej' není alias v config.yaml (aliasy: chytry, rychly, gemini-image)
```

A ve scénáři `agent: pojmenovavac` (bez prefixu):

```
config: tutorial-01-nazvy.yaml: krok "navrh": agent 'pojmenovavac' neexistuje (agents/pojmenovavac.md)
```

Jak hlášku číst: **třída chyby** (`config` = chyba v souborech), **soubor**,
případně **krok**, a co je špatně. Všechno oprav, ať `validate` zase píše
`v pořádku`.

---

## Krok 5 — `--dry-run`: co by se stalo

```bash
agencast run workflows/scenarios/tutorial-01-nazvy.yaml -i produkt="veganská zmrzlina z ovesného mléka" --dry-run
```

```
# Plán: tutorial-01-nazvy

Vymyslí tři názvy pro produkt (tutoriál, díl 1)

Limity běhu: rozpočet 1.0 USD (z toho obrázky 0.3 USD), čas 1h. Jev: jev-1.13.

| # | Krok | Typ | Podmínka | Co udělá | Limity |
|---|---|---|---|---|---|
| 1 | navrh | ask |  | agent tutorial-pojmenovavac → chytry (anthropic/claude-haiku-4.5); text | 0.01 USD, 2m |
| 2 | out | output |  | nazvy |  |


plán: runs/20260925-150947-tutorial-01-nazvy-3c6f/plan.md
```

- `-i klíč=hodnota` předá vstup. Více vstupů = více `-i`.
- `--dry-run` nic nevolá a nic nestojí. Uloží jen `plan.md` (a
  `inputs.json`) do nové složky v `runs/`.
- V plánu vidíš, na jaký **skutečný model** se alias přeložil a jaké
  limity platí: 0,01 USD z agenta, 2 minuty je výchozí časový limit kroku
  `ask`.

Zkus vynechat `-i`:

```
config: chybí povinný vstup 'produkt' (string)
```

Běh vůbec nezačne.

---

## Krok 6 — `--fake`: běh zadarmo a bez sítě

```bash
agencast run workflows/scenarios/tutorial-01-nazvy.yaml -i produkt="veganská zmrzlina z ovesného mléka" --fake
```

```
běh 20260925-150949-tutorial-01-nazvy-b761: úspěch · 0,0 s · 0,0001 USD
záznam: runs/20260925-150949-tutorial-01-nazvy-b761/summary.md
```

`--fake` místo OpenRouteru použije **falešného poskytovatele**: běží celý
framework (šablony, kroky, záznam), jen odpověď modelu je vymyšlená. Cena
0,0001 USD je taky vymyšlená — nic se neplatí.

Podívej se, co „model" odpověděl:

```bash
cat runs/20260925-150949-tutorial-01-nazvy-b761/steps/01-navrh/output.json
```

```
{
  "text": "Falešná odpověď."
}
```

Na zkoušení, že scénář **jde projít**, to stačí. Jenže „Falešná odpověď."
nevypadá jako tři názvy. Chceš-li, aby falešný model odpovídal
realisticky, napíšeš mu **fixturu** — soubor s předem danými odpověďmi.

### Fixtura

Vytvoř `fake/tutorial-01-nazvy.yaml`:

```yaml
# Skriptované odpovědi falešného poskytovatele pro tutorial-01-nazvy.
# Klíč = id kroku, pod ním seznam odpovědí (každé volání vezme další).
navrh:
  - text: "Ovesňák\nMrazík Oves\nZmrzlá Pláň"
```

a spusť s ní:

```bash
agencast run workflows/scenarios/tutorial-01-nazvy.yaml -i produkt="veganská zmrzlina z ovesného mléka" --fake fake/tutorial-01-nazvy.yaml
```

```
běh 20260925-150957-tutorial-01-nazvy-c3a6: úspěch · 0,0 s · 0,0001 USD
záznam: runs/20260925-150957-tutorial-01-nazvy-c3a6/summary.md
```

Proč zrovna do `fake/` a proč stejné jméno jako scénář?
Protože **každý scénář v příkladech klonu ve `workflows/scenarios/` je zároveň test
frameworku** (tzv. zlatý scénář). Testy ho spustí s `--fake` a když
k němu najdou fixturu se stejným jménem, použijí ji a čekají úspěch. Díky
tomu, až někdo framework vylepší, hned uvidí, jestli tvůj scénář pořád
běží. Víc v dílu 5.

Pravidla fixtury, která zatím potřebuješ:

- klíč = `id` kroku,
- `text: "…"` = textová odpověď (pro `ask` bez `schema`),
- seznam = odpověď na 1., 2., … volání kroku; poslední se opakuje.

---

## Krok 7 — složka běhu a `summary.md`

Každý běh (i falešný) má vlastní složku v `runs/`:

```bash
find runs/20260925-150949-tutorial-01-nazvy-b761 -type f | sort
```

```
runs/20260925-150949-tutorial-01-nazvy-b761/callback.json
runs/20260925-150949-tutorial-01-nazvy-b761/events.jsonl
runs/20260925-150949-tutorial-01-nazvy-b761/inputs.json
runs/20260925-150949-tutorial-01-nazvy-b761/plan.md
runs/20260925-150949-tutorial-01-nazvy-b761/steps/01-navrh/calls/01.request.json
runs/20260925-150949-tutorial-01-nazvy-b761/steps/01-navrh/calls/01.response.json
runs/20260925-150949-tutorial-01-nazvy-b761/steps/01-navrh/output.json
runs/20260925-150949-tutorial-01-nazvy-b761/steps/01-navrh/prompt.md
runs/20260925-150949-tutorial-01-nazvy-b761/steps/02-out/output.json
runs/20260925-150949-tutorial-01-nazvy-b761/summary.md
```

Pro teď stačí tři soubory:

| Soubor | K čemu |
|---|---|
| `summary.md` | souhrn pro člověka — čti vždy jako první |
| `steps/01-navrh/prompt.md` | **přesně** to, co dostal model: system prompt (tělo agenta) + zpráva (prompt kroku po dosazení) |
| `steps/01-navrh/output.json` | výstup kroku — to, co vidíš jako `steps.navrh` |

`01` je pořadí kroku v souboru scénáře. Zbytek (`events.jsonl`, `calls/`,
`callback.json`) rozebereme v dílu 5.

```bash
cat runs/20260925-150949-tutorial-01-nazvy-b761/steps/01-navrh/prompt.md
```

```
# System prompt

Jsi zkušený tvůrce názvů produktů. Píšeš česky.

Pravidla:
- Každý název má nejvýš dvě slova a dá se snadno vyslovit.
- Nepoužívej existující známé značky.
- Odpovídej jen názvy, bez vysvětlování.

# Zpráva

Vymysli 3 názvy pro tento produkt: veganská zmrzlina z ovesného mléka. Každý na vlastní řádek.
```

Když model odpoví divně, **tady** hledáš proč: co přesně dostal.

---

## Krok 8 — jeden ostrý běh

Klíč `OPENROUTER_API_KEY` je v souboru `.env` v projektu `examples/tutorial`;
framework si ho načte sám (a nikam ho nevypisuje). Spusť bez `--fake`:

```bash
agencast run workflows/scenarios/tutorial-01-nazvy.yaml -i produkt="veganská zmrzlina z ovesného mléka"
```

```
běh 20260925-151000-tutorial-01-nazvy-8d6a: úspěch · 1,6 s · 0,0002 USD
záznam: runs/20260925-151000-tutorial-01-nazvy-8d6a/summary.md
```

```bash
agencast runs show 20260925-151000-tutorial-01-nazvy-8d6a
```

```
# tutorial-01-nazvy — úspěch

Vymyslí tři názvy pro produkt (tutoriál, díl 1)
Běh `20260925-151000-tutorial-01-nazvy-8d6a` · 25. 9. 2026 15:10:00 UTC · 1,6 s · 0,0002 USD

## Vstupy
- produkt: veganská zmrzlina z ovesného mléka

## Kroky
| # | Krok | Typ | Stav | Čas | Cena | Poznámka |
|---|---|---|---|---|---|---|
| 1 | navrh | ask | ✓ | 1,6 s | 0,0002 | chytry → anthropic/claude-haiku-4.5 |
| 2 | out | output | ✓ | 0,0 s | 0 |  |
| | Celkem | | | 1,6 s | 0,0002 |  |

## Varování
žádná

## Výstup
- nazvy: „Ovesanka
Mlékový led
Zrníčko"
```

**Kde vidíš cenu:**

- v prvním řádku po běhu (`0,0002 USD`),
- v `summary.md` — celkem v záhlaví, po krocích ve sloupci **Cena**,
- v přehledu všech běhů:

```bash
agencast runs list
```

```
20260925-151000-tutorial-01-nazvy-8d6a        succeeded                         1,6 s   0,0002 USD 
20260925-150957-tutorial-01-nazvy-c3a6        succeeded                         0,0 s   0,0001 USD 
20260925-150949-tutorial-01-nazvy-b761        succeeded                         0,0 s   0,0001 USD 
20260925-150947-tutorial-01-nazvy-3c6f        dry-run
```

Cenu počítá OpenRouter, framework ji jen přečte z odpovědi (přesně:
0,000234 USD, 134 tokenů dovnitř, 20 ven). Nikdy ji neodhaduje.

---

## Co sis zapamatoval

- Agent = `workflows/agents/<jméno>.md`: frontmatter (`version`, `name`,
  `description`, `model`, `limits.budget_usd`) + instrukce.
- Scénář = `workflows/scenarios/<jméno>.yaml`: hlavička, `inputs`,
  `outputs`, `steps`; `ask` bez `schema` dává `steps.<id>.text`.
- Postup vždy: **`validate` → `--dry-run` → `--fake` → ostrý běh.**
- První, co po běhu čteš: `summary.md`. Když něco nesedí: `prompt.md`.

---

## Cvičení

Přidej do scénáře druhý vstup **`styl`** (text), který **nemusí** přijít —
když nepřijde, platí `hravý`. Vlož ho do promptu. Scénář ulož jako
`workflows/scenarios/tutorial-01-cviceni.yaml` a udělej k němu fixturu.
Ověř falešným během, že bez `-i styl=…` model dostal „hravý" a s
`-i styl="luxusní"` dostal „luxusní".

<details>
<summary>Řešení</summary>

`workflows/scenarios/tutorial-01-cviceni.yaml`:

```yaml
version: 1
name: tutorial-01-cviceni
description: Vymyslí tři názvy pro produkt v zadaném stylu (tutoriál, díl 1 — řešení cvičení)

inputs:
  produkt:
    type: string
    required: true
    description: Jaký produkt pojmenováváme
  styl:
    type: string
    default: hravý
    description: Jaký styl názvů chceme

outputs:
  nazvy:
    type: string
    description: Tři návrhy názvů, každý na vlastním řádku

steps:
  - id: navrh
    ask:
      agent: tutorial-pojmenovavac
      prompt: "Vymysli 3 názvy ve stylu „{{ inputs.styl }}“ pro tento produkt: {{ inputs.produkt }}. Každý na vlastní řádek."

  - id: out
    output:
      nazvy: "{{ steps.navrh.text }}"
```

Pozor: `name` se musí změnit spolu se jménem souboru. Vstup `styl` má
`default`, proto **nemá** `required`.

`fake/tutorial-01-cviceni.yaml`:

```yaml
# Skriptované odpovědi pro tutorial-01-cviceni (řešení cvičení z dílu 1).
navrh:
  - text: "Ovesňáček\nMrazíček\nKopeček Oves"
```

Ověření:

```bash
agencast validate workflows/scenarios/tutorial-01-cviceni.yaml
agencast run workflows/scenarios/tutorial-01-cviceni.yaml -i produkt="veganská zmrzlina" --fake fake/tutorial-01-cviceni.yaml
```

```
v pořádku: tutorial-01-cviceni (2 kroky)
běh 20260925-151019-tutorial-01-cviceni-6b59: úspěch · 0,0 s · 0,0001 USD
záznam: runs/20260925-151019-tutorial-01-cviceni-6b59/summary.md
```

```bash
cat runs/20260925-151019-tutorial-01-cviceni-6b59/inputs.json
```

```
{
  "produkt": "veganská zmrzlina",
  "styl": "hravý"
}
```

a v `steps/01-navrh/prompt.md` pod `# Zpráva`:

```
Vymysli 3 názvy ve stylu „hravý“ pro tento produkt: veganská zmrzlina. Každý na vlastní řádek.
```

S `-i styl="luxusní"` je ve zprávě `ve stylu „luxusní“`.

</details>

**Další díl:** [Navazování kroků](02-navazovani-kroku.md) — druhý krok
čte výstup prvního a `schema` z odpovědi udělá data.
