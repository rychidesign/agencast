# multiagent-workflows — návrh

**Stav:** návrh v0.1, 2026-09-25. Zachycuje rozhodnutí z návrhové diskuse
mezi rychidesign a koordinátorem (FirstBuddy). Otevřené body jsou označené
**OTEVŘENO**. Dokument je závazný pro workery: co je zde rozhodnuto, se
neotvírá znovu bez souhlasu uživatele.

---

## 1. Cíl

Framework, ve kterém se workflowy s LLM agenty píší v dobře čitelných
souborech (scénáře v YAML, agenti v Markdownu). Uživatel je programátor
začátečník: musí ze souboru scénáře i ze záznamu běhu rozumět tomu, co se
děje. Vnitřek frameworku ho nezajímá. Modely a Jev jdou přes jednoho
poskytovatele (OpenRouter). Běh na vlastním serveru nebo na Modal.com,
spouštění webhookem (typicky z n8n).

Referenční případ: příspěvek na Instagram (copywriter → kontrola Jev →
obrázek → návrh ke schválení → publikace).

---

## 2. Požadavky

| # | Požadavek |
|---|---|
| R1 | Workflow (scénář) se píše v dobře čitelném souboru. |
| R2 | Uživatel rozumí tomu, co workflow dělá, ze souboru scénáře **a** ze záznamu běhu. Vnitřek frameworku ho nezajímá. |
| R3 | Agenti jsou definovaní centrálně, každý ve vlastním souboru (model, instrukce, MCP servery, skilly, nástroje, limity). Scénář je volá jménem. |
| R4 | Poskytovatel napevno OpenRouter: LLM, Jev (System One API), generování obrázků. |
| R5 | Běh na vlastním serveru nebo na Modal.com; spouštění webhookem. Cron, události a schvalování řeší n8n mimo framework. |
| R6 | Framework je nástroj, do kterého uživatel nesahá. Pokud je vlastní, ladí a rozvíjí ho agenti (workeři). |
| R7 | Aktualizace frameworku ani jeho závislostí nesmí vyžadovat změnu agentů a scénářů. Formáty jsou naše, verzované. |

---

## 3. Rozhodnutí

### D1 — Formáty

**D1a Agent = Markdown s frontmatter.** Konfigurace nahoře (YAML
frontmatter), instrukce jako tělo souboru. Ilustrativně:

```markdown
---
name: copywriter
description: Copywriter pro sociální sítě značky THTD
model: chytry                 # alias z config.yaml, ne konkrétní model
skills: [marketing-copy]
mcp: []
tools: {}
limits: { max_turns: 8, budget_usd: 0.5 }
---
Jsi copywriter značky … (instrukce)
```

Poznámka: tvar připomíná agenty Claude Code, ale **nejde o kompatibilní
formát** (jiná pole, jiné nástroje). Konvertor případně později.

**D1b Dva typy kroků pro agenta.** `ask` = jedno volání modelu s instrukcemi
agenta (žádná smyčka nástrojů). `task` = autonomní smyčka model ↔ nástroje
s limity tahů a peněz. Ve scénáři je hned vidět, kde se co děje.

**D1c Výrazy.** `{{ steps.copy.caption }}` slouží **jen na vkládání hodnot**
(prompty, parametry). Pro `when`, `switch` a `set` se převezme malý hotový
výrazový jazyk (kandidáti: CEL, expr, JSONata) — **OTEVŘENO**, rozhodne se
spolu s D4. Pevná pravidla viz §5.4.

**D1d Typy kroků.**

v1 (implementuje se):

| Krok | Co dělá |
|---|---|
| `ask` | jedno volání modelu přes agenta; `schema` vynutí JSON výstup |
| `task` | autonomní agent s nástroji/MCP/skilly, limity tahů a rozpočtu |
| `jev` | rozhodnutí přes Jev (`noul` / `choice` / `score`), vrací hodnoty i pravděpodobnosti |
| `image` | generování obrázku přes OpenRouter; výsledek je soubor ve složce běhu |
| `parallel` | souběžné větve uvnitř jednoho běhu, pojmenované výstupy |
| `switch` | větvení podle hodnoty; `default` je **povinný** |
| `call` | vnořené spuštění jiného scénáře (viz §5.3) |
| `set` | výpočet/přetvoření hodnot bez LLM |
| `fail` | záměrné ukončení běhu s chybou a zprávou |
| `output` | co běh vrací (JSON + soubory); soubory se nahrají do úložiště a callback nese URL |

Vlastnosti libovolného kroku: `id`, `when`, `retry`, `timeout`, `budget`,
`schema`, `on_error`.

Plánováno (implementuje se **až když ho potřebuje konkrétní scénář**):
`foreach`, `repeat`, `http`, `tool` (přímé volání MCP bez modelu), `file`,
`run` (jen pojmenované příkazy z `commands.yaml`), `state` (paměť mezi
běhy, atomické `claim`).

Zamítnuto: `race`, `approve`/`human`, `wait` (schvalování a čekání řeší
n8n), `embed`/`search`.

### D2 — Model běhu

- **Běhy jdou jeden za druhým** (fronta). Paralelní kroky *uvnitř* běhu
  (`parallel`) zůstávají. Návrh nesmí paralelním běhům bránit do budoucna:
  běhy si nesdílí soubory (kromě `state` a úložiště výstupů).
- **Webhook je asynchronní:** hned vrátí `run_id` a pozici ve frontě,
  výsledek přijde na **callback URL** (n8n). Callback se posílá **vždy**,
  při úspěchu i při chybě.
- Délka běhu minuty až hodina. Časový limit v n8n musí počítat i s čekáním
  ve frontě.
- **Schvalování člověkem není ve frameworku.** Workflow se dělí na části,
  n8n drží stav mezi nimi. Smlouva o předání: výstup = JSON + URL souborů.
- Oba režimy agenta: `ask` (jedno volání) i `task` (autonomní).
- **Záznam běhu** je složka: `events.jsonl` (strojově čitelný log),
  výstupy každého kroku (prompt, odpověď, model, tokeny, cena, čas),
  `summary.md` pro člověka a **jeden samostatný HTML soubor** nahraný do
  úložiště (odkaz v callbacku). GUI nad `events.jsonl` později.
- Scénáře píše uživatel, jeho agenti, případně další lidé a jejich agenti
  → přísné JSON Schema formátů, `validate` před během, výslovná oprávnění,
  tajné klíče nikdy v souborech workflow.

### D3 — Engine — **OTEVŘENO**

Rozhodne spike, ne debata. Z D2 plyne směr: **vlastní orchestrace** (pořadí,
paralelismus, podmínky, záznam běhu — je malá) + **hotová knihovna pro
agentní runtime** (smyčka model ↔ nástroje, MCP klient, strukturovaný
výstup — je těžká). Kandidáti na runtime: Vercel AI SDK (TS), PydanticAI
(Py); větší frameworky (Mastra, LangGraph, Google ADK, CrewAI, MS Agent
Framework) jen pokud spike ukáže, že jejich model běhu nekoliduje s D1/D2.
Kritérium navíc: stabilita a velikost toho, na co se napojujeme (semver,
1.0+, pravidla zastarávání).

### D4 — Jazyk — **OTEVŘENO**

TypeScript na Bunu, nebo Python. Rozhoduje se s D3. Modal je nativně
Pythonový, ale kroky jsou API volání, takže framework na Modalu poběží v
kontejneru bez ohledu na jazyk.

### D5 — Hosting

Vlastní server (CLI + webhook) a Modal (`max_containers=1`, fronta přes
`.spawn()`; název parametru ověří spike). Jeden společný Dockerfile pro
obě prostředí, aby se nerozjely nainstalované nástroje. Úložiště výstupů:
lokálně složka, v cloudu Cloudflare R2. Trigger, cron a schvalování: n8n.

---

## 4. Struktura repozitáře

```
multiagent-workflows/
  framework/        jádro (CLI, engine, adaptéry, webhook) — udržují workeři
  workflows/        vrstva uživatele
    agents/         *.md   — agenti (D1a)
    scenarios/      *.yaml — scénáře (D1d)
    skills/         <name>/SKILL.md
    config.yaml     OpenRouter, aliasy modelů, úložiště, limity   ← jen vlastník
    mcp.yaml        registr MCP serverů + odkazy na tajné klíče    ← jen vlastník
    commands.yaml   povolené příkazy pro `run`                     ← jen vlastník
  docs/             tento návrh, specifikace formátů, changelog
  spikes/           časově omezené experimenty, každý s REPORT.md
```

Soubory označené „jen vlastník" rozhodují, co je v systému vůbec povolené.
Všechno ostatní mohou psát ostatní lidé a agenti.

---

## 5. Pevná pravidla

### 5.1 Chyby — nic neselže potichu
1. Výchozí chování: chyba kroku ukončí běh se stavem `failed`.
2. Callback se posílá vždy: stav, který krok selhal, třída chyby, zpráva.
3. Třídy chyb a jejich chování: `transient` (429, 5xx, síť → opakovat
   s prodlevou), `schema` (výstup modelu nesedí → opakovat, model dostane
   chybu jako zpětnou vazbu), `content` (model odmítl obsah, např.
   obrázek → neopakovat), `budget` / `timeout` (ukončit), `config`
   (zachytí `validate` před během).
4. `on_error: continue` jde jen výslovně a v souhrnu běhu je vidět jako
   varování.
5. Každý přeskočený krok má v záznamu uvedený důvod.
6. `repeat` a `task` mají limit iterací/tahů **povinný**.
7. Pojistka mimo framework: časový limit v n8n („když do X minut nepřijde
   callback → upozorni") a limit útraty přímo na klíči OpenRouter.

### 5.2 Bezpečnost
- Tajné klíče existují jen v `config.yaml` / `mcp.yaml` (odkazem na
  proměnné prostředí), nikdy ve scénářích, agentech ani promptech.
  Framework je do promptu nemá odkud dát.
- `run` spouští jen pojmenované příkazy z `commands.yaml`, bez shellu,
  s prázdným prostředím, validovanými argumenty.
- Agent definuje **maximum** oprávnění (nástroje, MCP, limity); krok ve
  scénáři je může jen **zúžit**, nikdy rozšířit.
- Příchozí webhook chce token; callback je podepsaný (HMAC), n8n ho ověří.
- Idempotence: klíč požadavku na webhooku (opakované volání nespustí druhý
  běh) a `dedupe_key` na krocích s vedlejším účinkem (publikace).

### 5.3 `call`
- `call` je vnořený krok **uvnitř stejného běhu**: stejný rozpočet,
  podsložka v záznamu běhu. Nevytváří nový běh, fronta o něm neví.
- Volaný scénář deklaruje `inputs` (typy, povinnost, výchozí hodnoty) a
  `outputs`. `validate` kontroluje volající místa staticky.
- Cykly validace odmítne; hloubka vnoření má limit.
- Každý scénář je zároveň spustitelný samostatně i volatelný. Jeden
  soubor, jeden formát.
- **Scénář nikdy nesmí spustit nový běh frameworku a čekat na něj**
  (se sekvenční frontou = zablokování). Spuštění nového běhu je dovoleno
  jen stylem „pošli a nečekej" (přes n8n / webhook).

### 5.4 Výrazy a šablony
- `{{ }}` v odpovědi modelu se **nikdy znovu nevyhodnocuje**.
- Odkaz na výstup přeskočeného kroku je chyba validace, pokud krok nemá
  `default`.
- Vkládání textu do JSON (např. `state` pro Jev) je vždy JSON-bezpečné;
  scénář neskládá JSON ručně.
- Typy: číslo vs. text vs. bool vs. null jsou rozlišené; porovnání
  napříč typy je chyba validace.

### 5.5 Modely
- Scénáře a agenti odkazují na **aliasy** (`chytry`, `rychly`,
  `gemini-image`), `config.yaml` je mapuje na konkrétní modely OpenRouteru.
  Výměna modelu = jeden řádek.
- Ke každému aliasu patří **konformační scénář** (umí nástroj + JSON
  schema), který se spustí při změně aliasu. Podpora nástrojů deklarovaná
  OpenRouterem není záruka kvality.
- Strukturovaný výstup: kaskáda nativní JSON schema → nástroj jako obal →
  prompt + validace + opakování. Použitá úroveň se zapíše do záznamu.

### 5.6 Verzování a testy — specifikace je produkt
- `version: 1` ve scénářích i agentech od prvního dne; changelog formátů.
- **Konformační scénáře** s falešným poskytovatelem (bez sítě, zdarma)
  běží před každou změnou frameworku. Bez nich R6 nefunguje.
- Závislosti zamčené v lockfile; update je vědomé rozhodnutí ve větvi
  s proběhlými konformačními testy.

### 5.7 Obrázky a soubory
- `image` vrací base64 → framework uloží soubor do složky běhu → krok
  vrátí cestu. Soubory v `output` se na konci běhu nahrají do úložiště
  z `config.yaml`; callback nese URL. Instagram Graph API vyžaduje
  veřejnou URL a Business/Creator účet napojený na Facebook stránku
  (mimo framework).

---

## 6. Referenční scénář (ilustrativně, syntaxe se upřesní ve specifikaci)

```yaml
version: 1
name: ig-post
description: Návrh IG příspěvku ke schválení (část 1; publikace v části 2 přes n8n)

inputs:
  tema: { type: string, required: true }

steps:
  - id: copy
    ask:
      agent: copywriter
      task: "Napiš IG příspěvek na téma: {{ inputs.tema }}"
      schema: { caption: string, hashtags: [string], image_prompt: string }

  - id: kontrola
    jev:
      state: "{{ steps.copy.caption }}"
      questions:
        on_brand: { type: noul, instructions: "Odpovídá text tónu značky?" }

  - id: stop
    when: steps.kontrola.on_brand < 0.7
    fail: "Text neodpovídá značce (on_brand = {{ steps.kontrola.on_brand }})"

  - id: foto
    image:
      model: gemini-image
      prompt: "{{ steps.copy.image_prompt }}"

  - id: out
    output:
      caption: "{{ steps.copy.caption }}"
      hashtags: "{{ steps.copy.hashtags }}"
      image: "{{ steps.foto.file }}"     # → nahraje se, callback nese URL
```

Očekávaný záznam běhu: složka s plánem (`--dry-run`), výstupem každého
kroku, důvodem přeskočení, cenou a časem, `summary.md` a HTML.

---

## 7. Známá rizika (ze zpětného pohledu 2026-09-25)

1. Rozsah v1 — hlídat, nepřidávat kroky bez scénáře, který je potřebuje.
2. `task` je nejtěžší část; heterogenita modelů za OpenRouterem.
3. Neověřené předpoklady: Jev přes OpenRouter je beta; MCP servery
   (stdio, `npx`) na Modalu; přístup k záznamům běhu na Modalu.
4. Výrazový jazyk zatím nerozhodnutý (D1c).
5. Pozorovatelnost na Modalu (proto HTML záznam běhu v úložišti).
6. Údržba: bez konformačních testů se regrese vkradou do měsíce.

---

## 8. Spiky (před dokončením specifikace)

Každý spike: jeden worker, jasná otázka, časový limit ~1 den, výstup
`spikes/<name>/REPORT.md` s verdiktem *funguje / nefunguje / funguje
s výhradou* a naměřenými fakty (ne dojmy).

**(a) OpenRouter** — otázky: (1) `ask` se JSON schématem a jedním
nástrojem na 3 modelech (Claude, Kimi/GLM, Gemini) — spolehlivost,
která úroveň kaskády se použila; (2) Jev přes
`https://openrouter.ai/api/v1/systemone` — tvar odpovědi, chyby, latence;
(3) generování obrázku (`google/gemini-3.1-flash-image` nebo obdobný) —
tvar odpovědi, uložení souboru, cena. Výchozí materiál:
`~/workspace/jev-labs` (existující experimenty s Jev přímo přes TypeSafe
API, `docs/findings.md`). Potřebuje `OPENROUTER_API_KEY` v prostředí;
náklady v centech.

**(b) Modal** — otázky: (1) kontejner s jedním stdio MCP serverem
(`npx`), studený start; (2) webhook → `.spawn()` → callback na testovací
URL, `max_containers=1` (ověřit název parametru), fronta; (3) Volume pro
záznam běhu a nahrání jednoho souboru do R2 s veřejnou URL. Potřebuje
token Modalu a přístup k R2.

Výsledky spiků rozhodnou D3, D4 a D1c.

---

## 9. Výchozí materiál (co si bereme z existujících nástrojů)

Průzkum GitHubu 2026-09-25 (4× Haiku, 5× Sonnet xhigh, ověřeno přes
`gh api`): nic nesplňuje R1–R7 najednou. Inspirace:

- **foxzi/baton** (Go, MIT): scénáře v YAML, `validate` + `--dry-run`,
  složka běhu, třídy chyb, `dedupe_key`, kaskáda strukturovaného výstupu,
  „agent smí jen to, co mu povolíš". Nemá centrální agenty; `agent:` krok =
  Claude Code/Codex CLI, ne API model.
- **zendev-sh/zenflow** (Go, Apache-2.0): blok `agents:` v YAML,
  `dependsOn`, `forEach`, `condition`, `include`. Skrytý LLM koordinátor.
- **johnlindquist/mdflow** (TS, MIT): workflow jako Markdown s `_steps` ve
  frontmatter — nejčitelnější formát; kroky = CLI agenti.
- **IBM/prompt-declaration-language** (Apache-2.0): `base_url` u volání,
  LiteLLM; spíš programovací jazyk v YAML.
- OpenRouter: 460 modelů, 11 s výstupem obrázku, ~390 deklaruje `tools`
  a `structured_outputs` (stav 2026-09-25). Jev: `/api/v1/systemone`,
  odpověď `{ answers: { id: { type, noul|choice|score… } }, usage.cost }`.
- **`~/workspace/jev-labs`** (vlastní, 2026-09-21): Python CLI a měření Jev
  přímo přes TypeSafe API (`docs/findings.md`). Poznatky: čeština funguje
  (34/34 správné `choice`, termín `noul` 15/15), latence medián 0,63 s,
  `score` u věcných popisů závad nadhodnocuje nespokojenost, `confidence`
  není pravděpodobnost správnosti, `noul=0.5` = nejistota; chyby API 401,
  422, 429, 529; limity 1 200 req/min. Prahy pro automatizaci nebyly
  stanoveny — ve scénářích je proto prah vždy výslovný (`< 0.7`), ne
  implicitní.
