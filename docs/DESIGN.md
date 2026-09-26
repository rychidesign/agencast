# multiagent-workflows — návrh

**Stav:** v0.4, 2026-09-25 — **v1 implementována**: AgenCast (`agencast`, do 0.2.5 `maw`) 0.3.0 v `framework/`
(všech 10 typů kroků, MCP a skilly, `call`, webhook `agencast serve`, `report.html`;
391 hermetických testů, zlaté scénáře pro každý soubor ve `workflows/`),
tutoriály 1–7 v `docs/tutorials/`. Spec v1 (`docs/spec/`) schválena uživatelem
včetně otázek 1–14; výklady při implementaci v `docs/spec/ISSUES.md` (39 bodů).
Nehotovo: D5 nasazení na Modal + úložiště R2 (Fáze 3c, čeká na klíče R2).
Dokument je závazný pro workery: co je zde rozhodnuto, se neotvírá znovu bez
souhlasu uživatele.

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
| R8 | **Stávající scénáře a agenti se při vylepšování frameworku nesmí rozsypat.** Pravidla kompatibility viz §5.9. (Přidáno 2026-09-25 při schválení spec v1.) |

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

**D1c Výrazy — rozhodnuto 2026-09-25.** `{{ steps.copy.caption }}` slouží
**jen na vkládání hodnot** (prompty, parametry). Pro `when`, `switch` a
`set` se používají **bezpečně vyhodnocované výrazy v pythonovském stylu**,
např. `steps.kontrola.on_brand < 0.7 and inputs.jazyk == "cs"`:
tečkový přístup k `inputs`, `steps`, `item`; porovnání, `and`/`or`/`not`,
aritmetika, indexování, malá sada povolených funkcí (`len`, `min`, `max`,
`round`, `str`, `int`, `float`, `join`). Žádný přístup k systému, žádné
volání metod, žádný import. Pevná pravidla viz §5.4.

Spike (c) 2026-09-25 (`spikes/expressions/REPORT.md`): rozhodnuto **vlastní
evaluátor nad `ast`**, žádná knihovna. Z 8 konfigurací (simpleeval, asteval,
evalidate, RestrictedPython, cel-python, cel-rust, vlastní) splnil D1c + §5.4
jen vlastní prototyp (207 řádků; odhad s validací 350–500). Knihovny
v pythonovské syntaxi rozbíjí tečkový přístup u kroku jménem `copy`
(vrátí `dict.copy`) a tiše vrací `False` u `3 == "3"`; asteval přečte
soubor přes `open()`; CEL má jinou syntaxi. Z toho pevně: **tečka = čtení
klíče, ne atribut**; limit délky výrazu **před** parserem; `and/or/not`
jen nad bool; `round` půlku od nuly; `str(None)` = `"null"`; bez ternáru,
řezů, `**` a volání metod. Chyba výrazu za běhu = třída `expression`.

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

Vlastnosti kroků: `id`, `when` (každý krok); `retry`, `timeout`,
`budget_usd`, `on_error` (jen kroky, kde mají smysl — určuje spec);
`schema` uvnitř `ask`/`task`. (Upřesněno specifikací v1, viz
`docs/spec/OPEN-QUESTIONS.md`.)

Plánováno (implementuje se **až když ho potřebuje konkrétní scénář**):
`foreach`, `repeat`, `http`, `tool` (přímé volání MCP bez modelu), `file`,
`run` (jen pojmenované příkazy z `commands.yaml`), `state` (paměť mezi
běhy, atomické `claim`).

Zamítnuto: `race`, `approve`/`human`, `wait` (schvalování a čekání řeší
n8n), `embed`/`search`.

### D2 — Model běhu

- **Běhy jdou jeden za druhým** (fronta). Paralelní kroky *uvnitř* běhu
  (`parallel`) zůstávají. Návrh nesmí paralelním běhům bránit do budoucna:
  běhy si nesdílí soubory (kromě `state`, úložiště výstupů a `_dedupe` —
  klíčů vedlejších účinků, které jsou samostatné atomicky vytvářené
  soubory, nikdy jeden sdílený log; jediná ohraničená výjimka je denní
  kniha útraty `_ledger/` od 0.3.1 — jeden řádek na dokončený běh pod
  `flock`, viz ISSUES 40). Výchozí zůstává jeden za druhým;
  `agencast serve --workers N` (od 0.3.0) volitelně pouští N běhů nad
  jednou frontou — kolize `run_id` řeší nový suffix, cache `/models` se
  zapisuje atomicky, `_dedupe` je za rozhraním `DedupeStore` (ISSUES 39).
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

### D3 — Engine — rozhodnuto 2026-09-25 (po spicích)

**Vlastní malý framework.** Orchestraci (pořadí kroků, `parallel`,
`switch`, `call`, záznam běhu) i tenký runtime agenta (smyčka model ↔
nástroje, kaskáda strukturovaného výstupu, MCP klient) píšeme sami nad
**protokoly a malými stabilními knihovnami**. Žádný agentní framework
(Mastra, LangGraph, Google ADK, CrewAI, MS Agent Framework) a žádný fork
batonu/zenflow.

Důvody: (1) spiky ukázaly, že OpenRouter i Modal zvládne holý HTTP/SDK a
že těžká místa — kontrola `finish_reason`, kaskáda výstupu podle modelu,
vracení `reasoning_details`, normalizace `usage` — velké frameworky za nás
neřeší; (2) jejich hlavní přínosy (pauza na člověka, trvalý stav grafu)
nepotřebujeme, protože schvalování dělá n8n a frontu Modal (D2);
(3) R7 — závislost jen na věcech, které se mění pomalu.

Cena: údržba je naše → konformační testy (§5.6) jsou povinnost, ne
přání. Odhad jádra v1: 3–5 tisíc řádků, píší a udržují workeři.

### D4 — Jazyk — rozhodnuto 2026-09-25: Python 3.12 + uv

Důvody: Modal je nativně Pythonový — webhook, fronta, Volume a secrets ze
spiku (b) se stanou přímo součástí frameworku (v TypeScriptu by byly dva
jazyky na údržbu); spiky i `jev-labs` jsou v Pythonu; výhoda AI SDK v TS
je malá, když kaskádu a kontroly píšeme vlastní.

Výchozí sada knihoven (změna jen s důvodem v changelogu): `httpx` (HTTP),
`mcp` (oficiální MCP SDK), `pydantic` (validace formátů, JSON Schema),
`pyyaml`, `modal` (jen v nasazení), CLI přes `typer` nebo `argparse`,
evaluátor výrazů dle D1c. Distribuce `uv run`/`uvx` na serveru i v Modal
image; závislosti zamčené v `uv.lock`.

**Doplněk 2026-09-26 (framework 0.5.0): `ruamel.yaml`** jen pro editační
operace GUI (`agencast/edit.py`, ISSUES 43). Důvod: GUI zapisuje do
souborů, které píše i člověk, a zápis musí zachovat komentáře, pořadí
klíčů, prázdné řádky a styl uvozovek (`"{{ … }}"`) — PyYAML komentáře
zahodí. Čtení a validace zůstávají na PyYAML (YAML 1.2 core, `loader.py`);
po úpravě se výsledek čte zase jím. ruamel přepisuje mezery ve flow
mapách (`{ a: 1 }`) a zarovnání, proto se nezměněné řádky berou doslova
z původního souboru.

### D5 — Hosting

Vlastní server (CLI + webhook) a Modal. Trigger, cron a schvalování: n8n.
Ověřeno spikem (b), Modal SDK 1.5.5:

- **Fronta:** `@app.function(max_containers=1)` + `.spawn()` z endpointu
  = běhy striktně jeden za druhým (3 běhy bez překryvu), webhook odpovídá
  < 1 s. Pozici ve frontě Modal spolehlivě nedává
  (`get_current_stats().backlog` je opožděný) — drží ji framework nebo n8n.
- **Endpoint:** `@modal.fastapi_endpoint(method="POST")`; HTTP požadavek
  má limit 150 s, proto submit jen spawne a vrátí `run_id`. Timeout funkce
  1 s – 24 h (`timeout=`), čekání ve frontě se nepočítá. Hlavičky číst
  přes `Header()`. Endpointy jsou veřejné → vlastní token v hlavičce ze
  `modal.Secret`.
- **Callback** z funkce na HTTPS endpoint funguje bez omezení.
- **MCP servery:** stdio `npx` server v kontejneru funguje; balíčky
  **předinstalovat do image** (cold handshake 0,7 s vs. 3,8 s přes
  `npx -y`). Cold start kontejneru 4–7 s, studený web endpoint +4–5 s.
- **Soubory:** `modal.Volume` (`commit()` po zápisu, `reload()` před
  čtením); čtení lokálně přes `modal volume get` i veřejný GET přes
  endpoint. URL je ale Modal-specifická → pro Instagram a trvalé odkazy
  zůstává Cloudflare R2 (S3 token + r2.dev/custom doména, `boto3`).
- **Secrets:** `modal.Secret.from_name` (rotace bez redeploye).
- **Nasazení:** `modal deploy` nad běžící aplikací nemusí vyměnit warm
  kontejnery → nasazovat jako `app stop` + `deploy`, nebo ověřit verzi.
- Jeden společný Dockerfile pro server i Modal (`Image.from_dockerfile`,
  nezkoušeno), aby se nerozjely nainstalované nástroje.

### Obálky (od 0.3.0)

CLI (`agencast`), webhook (`agencast serve`), později Modal a MCP server
jsou **tenké obálky nad `agencast.api`** (`load`, `run`, `dry_run`,
`runs_list`, `run_status`):

- Obálka neobsahuje logiku — jen převádí vstup (argumenty, HTTP, volání
  nástroje) na volání `api` a výsledek zpět. Cokoli s logikou jde do jádra
  a má hermetický test.
- Tajné klíče jen z prostředí (`.env` jen lokálně, na Modalu
  `modal.Secret`), nikdy v souborech workflow ani v argumentech.
- Sdílený stav mezi běhy je za rozhraním: `dedupe_key` přes `DedupeStore`
  (`get`, `claim` — výhradně a atomicky, `finish`) v `agencast/task.py`.
  Lokální implementace drží soubory `<runs>/_dedupe/<sha256>.json`
  (`_dedupe-fake/` u `--fake`); **tady Modal později dosadí vlastní
  úložiště** (`modal.Dict` apod.) přes `Run.dedupe`. Stejně od 0.3.1
  sloty `limits.max_parallel_runs` (`SlotStore`: `acquire`, `release`;
  lokálně `flock` na `<runs>/_slots/<n>.lock`) a denní kniha útraty pro
  `limits.daily_budget_usd` (`Ledger`: `total`, `add`; lokálně
  `<runs>/_ledger/<den>.jsonl`, `_ledger-fake/` u `--fake`) — ISSUES 40.
  Od 0.7.0 i zámek živého běhu (`hold_run_lock`, `run_locked`; lokálně
  `flock` na `<run>/run.lock`), podle kterého API rozliší běžící
  a přerušený běh — ISSUES 45.
- MCP nástroje budou „spusť a vrať ID“, „stav“ a „počkej“ — běh trvá
  minuty a web endpoint Modalu má limit 150 s (D5), takže nástroj nesmí
  čekat na konec běhu v jednom volání.

**GUI — rozhodnuto 2026-09-26 (uživatel + koordinátor):**

- GUI je samostatná obálka `ui/` v tomto repu (React). Servíruje ji
  `agencast serve`; Skynet Soul ji jen vloží do záložky (iframe).
- GUI mluví s jádrem **jen přes HTTP API `serve`** (`/projects/...`,
  [spec/api.md](spec/api.md)) — žádný přímý přístup k souborům ani vlastní
  parser formátů.
- Scénář je svislý seznam karet kroků (strom podle `parallel`/`switch`),
  žádný canvas; GUI je zároveň prohlížeč běhů (stav kroků, cena, soubory
  běhu, denní útrata).
- **Soubor je pravda:** scénáře a agenti zůstávají YAML/Markdown ve
  `workflows/`; GUI je čte a od 0.5.0 mění jen editačními operacemi
  jádra (`agencast/edit.py`, [spec/api.md](spec/api.md) „Editace“), které
  zapisují do stejných souborů (ISSUES 43):
  - **otisk** = sha256 obsahu souboru, který klient načetl (ne mtime);
    nesedí → 409 a nic se nezapíše — souběžná ruční úprava v editoru se
    nepřepíše potichu;
  - **validace před zápisem**: kopie `workflows/` se změnou projde
    `validate` (bez kontroly modelů); změna nesmí přidat novou chybu,
    dřívější chyby ji neblokují; pak atomický zápis (temp + `os.replace`);
  - zápis zachovává komentáře, pořadí klíčů, prázdné řádky a uvozovky
    (`ruamel.yaml`, D4); nezměněné řádky zůstávají doslova;
  - pravidla vlastníka platí: `config.yaml` a `mcp.yaml` jen jako
    formulář bez tajemství (jména proměnných), `.env` se nikdy nečte ani
    nezapisuje; surový text jen pro soubory formátů uvnitř `workflows/`.
- Projekty se **neskenují**, vede se registr
  `~/.config/agencast/projects.yaml` ([spec/projects.md](spec/projects.md));
  `agencast serve` mimo projekt obsluhuje všechny projekty z registru
  s tokenem serveru `AGENCAST_TOKEN`, v projektu nebo s `--project` jeden
  projekt jako dosud (n8n, Modal). ISSUES 41, 42.

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
8. **HTTP 200 není úspěch.** Krok s modelem je úspěšný až po kontrole
   `finish_reason`, parsování a validace schématu. Spike (a): Gemini
   vrátilo 200 s `finish_reason: "error"`, `completion_tokens: 0` a
   useknutým JSON. Odmítnutí obsahu se může projevit také jako 200 bez
   obsahu (`refusal`, `finish_reason` ≠ `stop`).

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
  běh) a `dedupe_key` na krocích s vedlejším účinkem (publikace). Záznam
  `started` vzniká před prvním voláním nástroje; `started` bez `succeeded`
  při dalším běhu = chyba `config` „ověř ručně", ne tiché opakování.
- **Kdo smí co použít, určuje vlastník** v `mcp.yaml`: u každého serveru
  `agents:` (kteří agenti ho smí použít), volitelně `scenarios:` (které
  scénáře smí spustit agenta s tímto serverem) a `tools:` (horní allowlist).
  Agenti i scénáře jsou soubory, které píší ostatní, proto tam tahle
  omezení být nemohou. Scénář je volatelný přes `call` jen s
  `callable: true` (výchozí `false`), aby část 1 nemohla obejít schválení
  v n8n voláním části 2.
- Tajné hodnoty (proměnné z `*_env` a `env`) framework před zápisem každého
  souboru záznamu i callbacku nahradí textem `<tajné: JMENO>` — nástroj
  MCP je může vrátit ve výsledku (spike (d): `get-env`).
- Klíč souboru v úložišti výstupů = `<run_id>-<32 hex náhodných>/<jméno>`;
  bucket je veřejný kvůli Instagramu, `run_id` je uhodnutelný, náhodná část
  je jen v callbacku a záznamu.
- Soubory se čtou jako **YAML 1.2 core**: jen `true`/`false` jsou booleany
  (`yes`/`on` je text), `4:5` je text, duplicitní klíč = chyba `config`
  s číslem řádku. PyYAML to ve výchozím stavu nedělá (spec REVIEW B6) →
  vlastní `SafeLoader` a ověřování ukázek stejným loaderem.

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
  Spike (a): Claude Haiku 4.5 a Kimi K3 nativně 10/10; Gemini 3.5
  Flash-Lite samotné schéma 5/5, **schéma + nástroj 4/5 nativně, 5/5 přes
  nástroj-obal**. Konformační scénář proto testuje **kombinaci** schéma +
  nástroj, ne každé zvlášť.
- U reasoning modelů (Gemini, Kimi) se `reasoning_details` z odpovědi
  posílají v dalším tahu beze změny zpět (doporučení OpenRouteru).
- `usage` má u chat completions (`prompt_tokens`/`completion_tokens`) a
  u Jev (`input_tokens`/`output_tokens`) jiný tvar; `cost` v USD je u obou.
  Framework `usage` normalizuje na jednu podobu v záznamu běhu.
- Model id se ověřuje proti `GET /api/v1/models` (např.
  `anthropic/claude-haiku-4.5`, ne `-4-5`). Jev v tom seznamu **není**.

### 5.6 Verzování a testy — specifikace je produkt
- Po schválení uživatelem je závazná i `docs/spec/` (formáty v1). Rozpor
  spec × DESIGN hlásí worker koordinátorovi, nerozhoduje ho sám.
- `version: 1` ve scénářích i agentech od prvního dne; changelog formátů.
- **Konformační scénáře** s falešným poskytovatelem (bez sítě, zdarma)
  běží před každou změnou frameworku. Bez nich R6 nefunguje.
- Závislosti zamčené v lockfile; update je vědomé rozhodnutí ve větvi
  s proběhlými konformačními testy.

### 5.9 Kompatibilita (R8) — schválená spec v1 je zmražená
1. **Formát `version: 1` se po schválení jen rozšiřuje:** nová volitelná
   pole a nové typy kroků ano; přejmenování, odstranění nebo změna významu
   existujícího pole ne. Nové pole má vždy výchozí hodnotu, která zachová
   dosavadní chování.
2. **Zlomová změna = `version: 2`.** Framework podporuje předchozí verzi
   formátu souběžně a má příkaz `migrate`, který soubory převede a změny
   vypíše. Starý soubor běží beze změny, dokud ho uživatel sám nepřevede.
3. **Zlaté scénáře:** každý schválený scénář, agent a skill ve `workflows/`
   a každá ukázka v `docs/spec/` je součástí konformační sady: musí projít
   `validate` a doběhnout s falešným poskytovatelem při každé změně
   frameworku. Přidání scénáře do `workflows/` = přidání testu.
4. **Zastarávání s varováním:** nedoporučená konstrukce nejdřív vyvolá
   varování ve `validate` (běh pokračuje), odstranit ji smí až další verze
   formátu.
5. **Verze frameworku (semver):** oprava = patch, přidání = minor, nová
   verze formátu = major. `CHANGELOG.md` frameworku i formátů.
6. Framework odmítne soubor s verzí formátu, kterou nezná (`config`), nikdy
   ho tiše neinterpretuje po svém.

### 5.7 Obrázky a soubory
- Od 0.14.0 přijímá krok `image` šablony v `aspect_ratio`, `quality` a `resolution`; kvalita kroku přebíjí alias, chat API kvalitu a rozlišení ignoruje s varováním (aditivně, version 1).
- `image` vrací base64 → framework uloží soubor do složky běhu → krok
  vrátí cestu. Soubory v `output` se na konci běhu nahrají do úložiště
  z `config.yaml`; callback nese URL. Instagram Graph API vyžaduje
  veřejnou URL a Business/Creator účet napojený na Facebook stránku
  (mimo framework).
- Spike (a), `google/gemini-3.1-flash-image` přes chat completions
  s `modalities: ["image","text"]`: obrázek je v
  `choices[0].message.images[].image_url.url` jako **data URL base64**
  (~1,5 MB PNG), nikdy URL. Do `events.jsonl` ani do výstupů kroku se
  base64 **nevkládá**, jen cesta k souboru.
- Cena **0,04–0,07 USD a 6–11 s na obrázek** — o dva řády víc než textový
  krok (0,0005–0,01 USD). Obrázkové kroky se počítají do rozpočtu a
  časového limitu běhu zvlášť. Výchozí rozměr 1408×768; poměr stran pro
  IG (1:1, 4:5) přes `image_config` — **neověřeno**.
- **Provider odmítnutí obsahu nedělá:** podobizna skutečného veřejného
  činitele se vygenerovala na obou modelech (HTTP 200). Politiku obsahu
  (osoby, cizí značky) musí vynutit framework sám — typicky `jev`
  kontrola promptu před `image` krokem (levné, 0,3 s).
- Model bez obrazového výstupu s `modalities: ["image"]` → HTTP 404
  `No endpoints found that support the requested output modalities`
  (třída `config`, zachytí `validate` proti `/models`).
- `models.<alias>.api` vybírá pro `image` chat completions (výchozí, dosavadní chování) nebo dedikované Images API; volitelná `quality` platí jen pro Images API.

### 5.8 MCP servery, nástroje a skilly (spike (d), `mcp` SDK 2.2)
- Klient = oficiální `mcp` SDK (zamknout `2.2.*`); stdio, Streamable HTTP
  i SSE. Stdio server se spouští **per běh** (start ~140 ms lokální
  balíček, ~300 ms `npx -y`), balíčky předinstalované (sedí s D5).
- **Timeouty vždy výslovně:** `read_timeout_seconds` u handshaku i
  `call_tool` + vnější pojistka (`fail_after`); bez nich SDK čeká
  neomezeně. Výchozí `mode="auto"` přidá u mrtvého serveru pevných 10 s
  (`server/discover`) → pro servery z `mcp.yaml` `mode="legacy"`, dokud
  nebudou na protokolu 2026-07-28. Chyby handshaku přicházejí ve dvou
  vrstvách `ExceptionGroup` — framework je rozbalí do tříd §5.1.
- **Mapování chyb:** `isError: true` z nástroje = zpětná vazba modelu (krok
  pokračuje); `timed out` = třída `timeout`; selhání handshaku =
  `config`/`transient`.
- **Schémata nástrojů → OpenRouter `tools`** se normalizují (~50 řádků):
  jméno `server__tool` (jen `[a-zA-Z0-9_-]`, max 64, Claude jinak vrátí
  400), vložení `$ref`, `allOf`/`oneOf` → `anyOf`, `const` → `enum`,
  ne-řetězcový `enum` → do `description`. Gemini části schématu **tiše
  ignoruje** (HTTP 200 a špatné argumenty) → **argumenty se validují na
  klientovi proti původnímu schématu**, chyba jde modelu jako výsledek
  nástroje. Konformační scénář aliasu (§5.5) obsahuje `$ref`, `const`
  a číselný `enum`.
- **Obrázky z nástrojů** se posílají v následné user zprávě (funguje u
  Claude i Gemini); v tool zprávě je Gemini odmítne (400). Ukládají se jako
  soubor, ne base64 do záznamu.
- **Skilly:** `skills/<name>/SKILL.md` s `name` + `description`; system
  prompt nese jen seznam `jméno: description`, tělo načte nástroj
  `load_skill(name)` (`enum` jmen, neznámé jméno → chyba se seznamem).
  Výstup kroku vynucuje `schema`, ne skill.
- **Oprávnění (§5.2 konkrétně):** allowlist nástrojů podle jména;
  efektivní sada = krok ⊆ agent, jinak chyba `validate`; do `tools` i do
  dispatch jdou jen povolené nástroje (vedlejší efekt −66 až −81 %
  prompt tokenů). Druhá vrstva = argumenty serveru v `mcp.yaml` (např.
  povolený kořen filesystemu). Stdio server dědí jen 6 bezpečných
  proměnných prostředí; klíče pro servery se předávají výslovně přes
  `env` v `mcp.yaml`. `stderr` serverů jde do záznamu běhu.

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
2. `task` je nejtěžší část; heterogenita modelů za OpenRouterem —
   **potvrzeno** spikem (a) (Gemini: nástroj + schéma 4/5, 200 s chybou).
3. ~~Neověřené předpoklady~~ → ověřeno spiky 2026-09-25: Jev přes
   OpenRouter funguje (slovo „beta" v dokumentaci není, 6/6 OK); MCP
   servery na Modalu fungují; záznam běhu na Modalu je dostupný přes
   Volume i endpoint.
4. Výrazový jazyk zatím nerozhodnutý (D1c).
5. Pozorovatelnost na Modalu (proto HTML záznam běhu v úložišti).
6. Údržba: bez konformačních testů se regrese vkradou do měsíce.
7. **Nové:** třída chyby `content` (odmítnutí obsahu) se nepodařilo
   naměřit — provider nic neodmítl. Tvar odmítnutí neznáme.
8. **Nové:** `.env` s CRLF konci řádků rozbíjí tokeny (Modal: „Invalid
   metadata value"); načítání `.env` musí CRLF tolerovat.
9. **Nové:** R2 zatím bez klíčů — veřejná URL pro Instagram neověřena.

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

### Výsledky (2026-09-25, oba spiky hotové)

| Spike | Verdikt | Report |
|---|---|---|
| (a) OpenRouter — schéma + nástroj | funguje s výhradou (Gemini potřebuje nástroj-obal) | `spikes/openrouter/REPORT.md` |
| (a) OpenRouter — Jev | funguje (5/5, 0,30 s, ~0,00003 USD) | tamtéž |
| (a) OpenRouter — obrázek | funguje s výhradou (0,067 USD, odmítnutí nevyvoláno) | tamtéž |
| (b) Modal — MCP v kontejneru | funguje (předinstalovat balíčky) | `spikes/modal/REPORT.md` |
| (b) Modal — webhook + fronta | funguje (výhrada: redeploy = stop + deploy) | tamtéž |
| (b) Modal — Volume + veřejná URL | funguje; R2 neimplementováno (chybí klíče) | tamtéž |
| (b) Modal — Secrets | funguje | tamtéž |
| (c) výrazy pro D1c (2026-09-25, větev `spike-expressions`) | funguje: vlastní evaluátor 24/24 + 14/14 + 20/20; žádná knihovna nesplní §5.4 | `spikes/expressions/REPORT.md` |
| (d) MCP klient + skilly v Pythonu (2026-09-25, větev `spike-mcp-python`) | funguje: `mcp` 2.2 stdio/HTTP/SSE, schémata po normalizaci 18/18, `load_skill` 12/12, allowlist drží; 0,136 USD | `spikes/mcp-python/REPORT.md` |

Útrata: (a) 0,30 USD, (b) řádově centy. Fakta z obou spiků jsou
zapracována v §5.1 (bod 8), §5.5, §5.7, D5 a §7.

**Fakta relevantní pro D3/D4** (bez volby): všechna tři API OpenRouteru
i Modal šly ovládat holým HTTP/SDK bez agentního frameworku; těžká místa
jsou kaskáda strukturovaného výstupu, kontrola `finish_reason`, vracení
`reasoning_details`, normalizace `usage` a MCP handshake — přesně
runtime agenta, ne orchestrace. Rozhodnutí D3, D4 a D1c: **přijato
uživatelem 2026-09-25**, viz §3.

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
- **Jev přes OpenRouter** (spike (a)): `POST /api/v1/systemone`, tělo
  `{model: "jev-1.13", state, questions}`; odpověď `model` je datovaná
  verze (`typesafe/jev-1.13-20260917`, `jev-latest` → totéž; logovat),
  `answers.<id>` = `{type, choice|score|noul, probabilities?, confidence?,
  legend?}`, `usage: {input_tokens, output_tokens, cost}`. Chybný požadavek
  → HTTP 400, `error.message` je řetězec s JSON polem od validátoru, tělo
  obsahuje `user_id`. Neexistující model → 400.
