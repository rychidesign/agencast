# Changelog frameworku

Semver podle DESIGN §5.9 bod 5: oprava = patch, přidání = minor, nová
verze formátu = major. Změny formátů jsou v `docs/spec/CHANGELOG.md`.

Do 0.2.5 se balík a příkaz jmenovaly `maw`; starší záznamy tu to jméno nechávají.

## 0.16.1 (nevydáno)

- Věrnost: sidebar podle návrhu V3 (232 px, značka 25/22 px, „← Projekty“ jako řádek 44 px s
  oddělovačem, položky 44 px s mezerou 6, aktivní `surface-active`, pruh útraty na `track`).
- Věrnost: hlavička stránky s H1 32 px semibold, popisem 14 a meta řádkem mono 13; ⋯ v hlavičce jako
  ikonové tlačítko `bg-control` 48 × 48 (editor 40 × 40); obsah max. 1176 px, pod hlavičkou 24 px.
- Věrnost: Projekty mají popis, cestu registru pod ním a ikonové „Načíst znovu“; karta projektu radius 16,
  padding 24, název 20 px, čipy počtů a útrata „dnes 1,20 USD“ (dvě desetinná místa).
- Věrnost: Běhy s filtrační kartou (hledání podle scénáře a run_id, stav, scénář), záhlavím sloupců a řádky
  jako karty 80 px s run_id pod jménem, stavem v barvě a „Načíst další“ s ikonou; čip „N běží · M ve frontě“
  v hlavičce. Cena běhu a kroku vždy se čtyřmi desetinnými místy („0,0000 USD“, ne „0“ ani „0,000013128“).
- Věrnost: detail běhu s titulem mono 32 a ↗, run_id pod ním, čipem stavu, „32,4 s · 0,0812 USD“,
  tlačítkem „Otevřít scénář“, kartou VSTUPY a záložkami přes celou šířku se „sledovat běh“ vpravo.
- Věrnost: editor má Spustit jako primární a Uložit jako sekundární tlačítko s ikonou; token serveru a
  neexistující adresa (404) podle návrhu (karta 420 px, přepínač zobrazení tokenu; velké „404“).
- Věrnost: Agenti a Skilly mají seznam 200 px s kartami položek a editor v kartě; skilly a MCP
  servery agenta jsou řádky s checkboxy, instrukce mají delší Markdown pole a použití tvoří odkazy.
- Věrnost: Config má formulář v kartě, sekce ve dvojicích sloupců, vnořené karty aliasů,
  stavové řádky proměnných a MCP servery označené „Pouze čtení“.
- Věrnost: tokeny pro ovládací prvky, aktivní plochu a progress podle návrhu V3.
- Věrnost: tlačítka, pole, přepínač, záložky, čipy, menu, akordeon a prázdné stavy mají rozměry a barvy návrhu.
- Věrnost: YAML editor, čtecí bloky kódu a konfliktový pruh mají hlavičky, číslování a patičky podle návrhu.
- Věrnost: karta scénáře podle návrhu — rádius 16, padding 24, min. výška 290; typy kroků jako prosté ikony 16 px bez koleček a šipek (řetěz se už nezalamuje), název 20 px, popis na 2 řádky, meta mono „7 kroků · 3 agenti“ + čip „volatelný“, dole čip běhu a „Otevřít ↗“ (`docs/ui/redesign-fidelity.md` §5).
- Věrnost: karta kroku 96 px — číslo vlevo mimo kolečko, kolečko 40 px s ikonou typu, řádek „ask · navrh“ mono malými, titul 16 px (u ask/task/image úryvek promptu), třetí řádek mono s agentem / modelem · poměrem a podmínkou „když …“; ⋯ uvnitř pilulky; výběr `surface-active` + prstenec 1 px; v běhu vpravo „12,4 s · 0,0210 USD“ nad stavem (§6).
- Věrnost: hlavičková karta, kontejnery (obal r16 p16, sbalení vpravo, větve r12 s kartami 72 px), (+) na konektoru v `control`, „+ Přidat krok“ a „+ output“ jako sekundární tlačítka, TypePicker s položkami 40 px; sloupec 640, panel 420, mezera 32 (§6).
- Věrnost: panely — padding 24, eyebrow mono 11, titul 20, zavřít ghost 32; „Typ kroku“ ukazuje „ask · jedno volání agenta“; panel spuštění s kartami režimu 72 px, limity jako řádky s oddělovači, varováním v `warning/10` a tlačítky Zrušit + Spustit; panel kroku v běhu se stavovým čipem, podtrženými záložkami, blokem kódu (hlavička, čísla řádků, Kopírovat) a řádky souborů 44 px s ↗ (§7).

## 0.16.0 — 2026-09-28 (GUI podle návrhu V3: sidebar, jednotné hlavičky, tokeny)

Jen GUI; API, CLI, formáty souborů, routy a klávesové zkratky beze změny.

- QA (vlna D): ztlumené karty (nedošlo, přeskočeno, nedostupný projekt) mají čárkovaný obrys
  místo průhlednosti (kontrast ≥ 4,5:1, axe bez vážných nálezů); menu ⋯ karty leží nad dalšími
  kartami a menu hlavičky nad panelem; karta scénáře má stav dole a popis na 3 řádky; konfliktní
  pruh editoru je v přilepené hlavičce; neexistující projekt, scénář a běh bez ovládání navíc;
  dialog drží fokus i po odmítnutém smazání; ⋯ zavře Tab; výpadek serveru hlásí SaveNote česky;
  tmavé nativní selecty (`color-scheme: dark`), kurzor ruky na klikacích prvcích, viditelný fokus
  na (+); „Načíst znovu“ na Projektech v ⋯; duplicitní chyby projektu jen jednou.
- Tokeny: barvy, písma a rádiusy V3 v `ui/src/index.css`; Inter Variable a
  JetBrains Mono se bundlují lokálně (bez CDN). V `ui/src` nezůstaly třídy
  `zinc-*` ani napevno zapsané barvy (výjimka: bílé pozadí iframe reportu).
  `fg-muted` je `#8497B0`, aby i na `surface-hover` měl kontrast ≥ 4,5:1.
- Shell: levý sidebar (značka, „← Projekty“, jméno projektu, navigace
  Scénáře · Agenti · Běhy · Skilly · Config, dole dnešní útrata s pruhem);
  pod 1024 px horní lišta. Výpadek serveru hlásí dole v sidebaru.
- Hlavičky: každá stránka má jednu hlavičku (`PageHeader`): titul, popis,
  nejvýš dvě tlačítka a menu ⋯ s ostatními akcemi (nebezpečné červeně a
  poslední); přepínač Form | YAML / Markdown a stav uložení jsou v jejím
  druhém řádku. Sekce projektu v ní nesou „+ Nový scénář“, „+ Nový agent“,
  „+ Nový skill“ a Uložit; „Načíst znovu“ je v ⋯. Config má cestu projektu
  jako popis. Neexistující adresa má stejnou hlavičku.
- Projekty a projekt: karta projektu bez štítku „dostupný“, přidání projektu
  je tlačítko v hlavičce (čárkovaná karta jen u prázdného seznamu); hlavička
  projektu neukazuje cestu, limity ani útratu.
- Karty: kroky, konektory, nabídka typů a karty scénářů v tokenech V3; karta
  scénáře ukazuje jméno, popis, „N kroků · agenti“ a jediný čas v čipu
  posledního běhu.
- Panely: panel kroku, hlavičky, spuštění a kroku v běhu v tokenech V3
  (eyebrow „KROK n · typ“, typ kroku jako první pole, režim běhu kartou).
  V editoru scénáře je panel vedle sloupce karet od 1280 px, užší obrazovka
  ho ukáže jako list dole se zavíracím křížkem.
- Běhy: seznam bez sloupce run_id a bez řádku útraty, stav se v poznámce
  neopakuje; detail běhu s „← Běhy“, vstupy na jeden řádek a „Běh skončil“
  jen pro čtečku.
- Formuláře: editor agenta a skillu i Config mají jedno Uložit; sekce bez
  karet a technických štítků; alias modelu má meta „používá …“ /
  „nepoužívá se“ a na úzké obrazovce se zalomí. Prvky (tlačítka, pole,
  menu, modály, editory) v tokenech V3.

## 0.15.1 — 2026-09-27 (registr snese nedostupný kořen; validate bez zápisu do registru)

- `GET /projects` už nespadne (500), když některý zapsaný kořen nemá
  `workflows/`; položka je jen `available: false` s důvodem, jako když
  chybí `config.yaml`. GUI ji nabídne k odebrání.
- `agencast validate` už projekt do registru nepřidává, dělá to jen úspěšný
  `run`. Validace z kopií projektu (testy, worktree workerů) tak
  nezanechávají v registru cizí položky.

## 0.15.0 — 2026-09-27 (přejmenování scénáře a agenta)

- Veřejné API, HTTP API, CLI i GUI umí přejmenovat scénář nebo agenta a
  přepsat jejich odkazy. Běhy zůstávají se jménem platným v době spuštění.

## 0.14.0 — 2026-09-27 (parametry obrázku jako šablony)

- `image`: šablony poměru stran, kvality a rozlišení, kontrola dosazených
  hodnot a výchozích vstupů; kvalita kroku přebíjí alias.
- GUI nabízí proměnné pro všechny tři parametry; chat API ignorované
  parametry zaznamená jako varování. Volatelný příklad `obrazek.yaml`.

## 0.12.0 — 2026-09-27 (krok image přes Images API OpenRouteru)

- Aliasy modelů volí `chat` (výchozí) nebo dedikované Images API; podpora
  kvality, validace modelů a `--fake` pro nové endpointy.

## 0.11.0 — 2026-09-27 (nabídka proměnných v editoru)

- GUI: do polí výrazů a šablon přibyla nabídka dostupných proměnných, která
  je vkládá na pozici kurzoru; dosavadní našeptávač při psaní zůstává.

## 0.10.3 — 2026-09-26 (alias modelu z GUI)

- GUI: alias modelu v Configu jde přejmenovat i s pomlčkou (`gpt-image`,
  jako jméno agenta). Pole bralo jen jména výrazů bez pomlčky, takže se
  přejmenování při opuštění pole tiše vracelo na `model-1`. Neplatné jméno
  má teď pravidlo v nápovědě pole a pod seznamem aliasů.
- Editace: nová mapa vedle map v řádkovém stylu `{ … }` (aliasy v
  `config.yaml`) se zapíše stejným stylem, ne blokem; soubor tak po úpravě
  z GUI vypadá jednotně.

## 0.10.2 — 2026-09-26 (opravy souběhu a odchodu z editoru)

- Editace znovu ověří SHA-256 souboru po validaci a těsně před zápisem; změna
  během validace vrátí 409 a zůstane zachována.
- Zápisy do registru projektů zamykají čtení, úpravu i zápis přes
  `projects.yaml.lock`, takže souběžná přidání neztratí záznam.
- Neuložený editor potvrzuje odchod i při změně hashe či tlačítku Zpět;
  odmítnutí vrátí původní hash.

## 0.10.1 — 2026-09-26 (úklid podle ponytail auditu, bez změny chování)

Patch: úklid podle ponytail auditu, bez změny chování; formáty v1, záznam
běhu a HTTP smlouvy se nemění. Audit: `docs/audit-ponytail-2026-09-26.md`.

- Zdvojené pomocné funkce na jednom místě: `validate.require_config`
  (config nebo `ConfigErrors`, dřív 4 kopie v api, cli, projects, server),
  `projects.text_tree` (strom kroků z textu, dřív 3 kopie v edit a
  projects), `record._events` i při obnově fronty v `server`,
  `mcp_client._leaves` i v `engine`, `projects.NAME` i v `server`.
- `api` re-exportuje funkce registru z `projects` místo obalů, které jen
  předávaly argumenty (`projects`, `new_project`, `projects_root`,
  `normalize_project_root`, `registry_writable`, `remove_project`).
- Výrazy počítají aritmetiku a `< <= > >=` přes `operator`; `validate`
  volá kontroly kroků jedním `getattr`; kratší `schema_errors`.
- Testy: společný `registry_server`, `serve`, `TOKEN` a `SECRET`
  v `conftest.py` (bez křížových importů a `noqa`), smazán nepoužitý
  `fake_for`.

## 0.10.0 — 2026-09-26 (doplňky API podle nálezů GUI 21–28)

Minor: pouze aditivní HTTP API a oprava obnovy běhů; formáty v1, smlouva
`POST /runs` a callback se nemění. ISSUES 48.

- Restart `serve` zachová původní `run_started`, doplní chybu `internal`
  s posledním začatým krokem a API vrací `state: interrupted`; nedokončený
  krok má `status: interrupted`.
- Chyby schématu `config.yaml` vrací YAML řádek. `GET /projects` vrací
  počty scénářů/agentů a dnešní útratu; seznam běhů podporuje `before` a
  `next_before`, `last_run` přidává `started_at`.
- `render` přijímá text scénáře; `validate` přidává strom textového
  scénáře. Chyby dávky obsahují `step` a dostupné `field`.
- Callback tajemství je nutné jen při odesílání callbacku; token projektu
  se čte jen v jednoprojektovém režimu.

## 0.9.0 — 2026-09-26 (projekty z GUI)

Minor: aditivní API pro založení, registraci a odebrání projektu; formáty
v1 se nemění. ISSUES 47.

- **Projekty přes HTTP:** `POST /projects/new` založí projekt ze stejných
  šablon jako `api.new_project`, `POST /projects` zaregistruje existující
  projekt s `workflows/config.yaml`, `DELETE /projects/<p>` odebere jen
  položku registru. Zápis v jednoprojektovém režimu vrací 405.
- **Kořen projektů:** volitelný `projects_root` v registru (výchozí
  `~/workspace`); `GET /projects` vrací `projects_root` a `writable`.
- `agencast projects add|rm` a `new project` nadále používají veřejné
  funkce `agencast.api`, stejně jako nové HTTP zápisy.

## 0.8.0 — 2026-09-26 (API podle nálezů z GUI, část 2)

Minor: nové endpointy a pole, formáty v1 i záznam běhu beze změny.
Zadání `docs/ui/nalezy-api.md` body 10–20, ISSUES 46.

- **Dávka:** `POST …/scenarios/<s>/batch` `{etag, ops}` — operace
  `set_header`, `add_step`, `update_step`, `replace_step`, `move_step`,
  `delete_step`, `rename_step` (s `rename_refs`), `add_branch` po sobě
  nad jednou kopií, jedna validace, jeden zápis; chyba operace = 422
  s `op` (`api.batch`, `api.OpError`).
- **Náhled:** `POST …/scenarios/<s>/render` → `{text, tree, errors}` bez
  zápisu (`api.render`).
- **Celý krok:** `PUT …/steps/<adresa>` (`api.replace_step`), umí `null`.
- **Stav čerstvého běhu:** složka ze záznamu fronty `serve` bez zámku je
  `queued`, ne `interrupted`/`dry_run`; `dry_run` jen bez `run.lock`.
- **Soubory:** `HEAD …/files/<cesta>` (hlavička `ETag`),
  `?etag_only=1` (`api.file_etag`); `errors` v `GET …/files/<cesta>` =
  chyby `validate` souboru jako v `GET /projects/<p>`.
- **Nové soubory:** `description` v `POST …/scenarios` a `…/agents`,
  u agenta `model` (`api.new_scenario(…, description)`,
  `api.new_agent(…, description, model)`).
- **Projekt:** `links.scenario_model`, `models_used`.
- **Config:** `PUT …/config` povoluje `runs_dir` a `openrouter.jev_model`.
- CORS: preflight povoluje `HEAD`, odpovědi `Access-Control-Expose-Headers: ETag`.

## 0.7.0 — 2026-09-26 (API podle nálezů z GUI)

Minor: nová pole a endpoint, formáty v1 beze změny, v záznamu běhu nové
soubory a pole (aditivně). Zadání `docs/ui/nalezy-api.md`, ISSUES 45.

- **Běží × přerušen:** běh drží `flock` na `<run>/run.lock`
  (`task.hold_run_lock`, `task.run_locked`); `runs list` a API mají
  strojové `state` (`queued|running|interrupted|succeeded|failed|
  cancelled|dry_run`) a text `běží` / `přerušen` místo „běží nebo
  přerušen“ (i v CLI `runs list`).
- **Podrobnosti kroků:** `steps` v `GET …/runs/<id>` mají `nn`, `dir`,
  `error`, `continued`, `default_used`, `calls`, u `task` `turns`
  a `tool_calls`, u `jev` `answers`; nový `GET …/runs/<id>/steps/<cesta>`
  (události, `output`, soubory kroku). `step_started` nese `nn` a `dir`,
  `step_skipped` `nn`, `step_finished` s `continued` `default_used`.
- **Snímek scénáře:** `<run>/scenario/<jméno>.yaml` (spouštěný i volané
  přes `call`); detail běhu vrací `tree`, `callees`, `tree_source`.
- **Seznam běhů:** `fake`, `queue_position`, `current_nn`, `steps_done`,
  u dry-runu `scenario` a `started_at` z `run_id`; `?scenario=&limit=`
  (`api.runs_list(root, scenario, limit)`); `api.last_run` a `last_run`
  ve `scenarios` a v `GET /projects`.
- **Projekt:** `types` ve `scenarios`, `links.scenario_step_agent`
  (trojice), v `GET /projects` `reason` u nedostupného a `registry`.
- **Rozbitý config:** `files/config.yaml` a `mcp.yaml` hlásí i chyby
  schématu a proměnných; 422 z `GET /projects/<p>` má i `errors`
  objekty; čtení běhů a `spend` potřebují jen `runs_dir` (jinak
  `./runs`).
- **Oprava:** duplicitní klíč ve frontmatteru `.md` — „poprvé na řádku
  N“ teď ukazuje řádek v souboru (chyběl posun o řádek `---`).

## 0.6.0 — 2026-09-26 (doplňky API pro GUI)

Minor: nové endpointy a pole, formáty v1 beze změny (R8), v záznamu běhu
dvě nová pole. **Jediná změna tvaru:** `errors` v HTTP API jsou objekty
(GUI je jediný klient). ISSUES 44.

- **Chyby jako objekty** `{message, file?, step?, field?, line?}` ve všech
  `errors` HTTP API (`GET /projects/<p>`, `…/scenarios/<s>`, `…/files/`,
  odpovědi editačních operací, `validate`); `message` = dřívější text.
  CLI a Python API beze změny (`projects.error_fields`).
- **`POST /projects/<p>/validate`** bez zápisu: prázdné tělo = projekt na
  disku, `{path, text}` = s jedním souborem nahrazeným (`edit.validate_text`,
  re-export v `agencast.api`; stejná kopie `workflows/` jako editace).
- **`env`** v `GET /projects/<p>`: `{JMÉNO: true|false}` pro všechny
  proměnné z `config.yaml` (`*_env`) a `mcp.yaml` (`env`,
  `bearer_token_env`); nikdy hodnota.
- **Běhy pro GUI:** `runs list` / `GET …/runs[/<id>]` mají `scenario`,
  `started_at`, `finished_at`, `current_step`, `steps_total`;
  `run_started` nese `steps_total` a `callback_url` (bez query, `null`
  = bez callbacku). `run_status` snese rozepsaný poslední řádek.
- **Spuštění z GUI:** v `POST /projects/<p>/runs` je `callback_url`
  volitelná a `dry_run: true` vrátí hned `{run_id, dry_run: true}` (jen
  `plan.md` a `inputs.json`). `POST /runs` beze změny.
- **GUI v `serve`:** statické soubory z `agencast/ui/` (`GET /`,
  `/assets/…`, bez tokenu, cesta bez přípony → `index.html`; bez
  sestaveného GUI 404 s návodem). `--cors <origin>` pro `vite dev`.
  `pyproject.toml`: `[tool.hatch.build.targets.wheel] artifacts` pro
  `agencast/ui/**` (složka je v `.gitignore`).

## 0.5.0 — 2026-09-26 (editační operace pro GUI)

Minor: nové operace a endpointy, formáty v1 beze změny (R8). ISSUES 43.

- **Editační operace v jádru** (`agencast/edit.py`, re-export v
  `agencast.api`): `set_header`, `add_step`, `update_step`, `move_step`,
  `delete_step`, `delete_scenario`, `set_agent`, `delete_agent`,
  `set_skill`, `delete_skill`, `set_config`, `read_file`, `write_file`.
  Každá ověří otisk (sha256 obsahu → `Conflict`), validuje kopii
  `workflows/` se změnou (nová chyba → `ConfigErrors`, nic se nezapíše)
  a zapíše atomicky. Mazání použitého agenta/skillu/volaného scénáře
  odmítne.
- **Round-trip YAML** přes `ruamel.yaml` (nová závislost, DESIGN D4):
  komentáře, pořadí klíčů, prázdné řádky a uvozovky zůstávají, nezměněné
  řádky doslova. Každý scénář a agent z `workflows/` projde no-op úpravou
  bajtově beze změny (test).
- **Adresa kroku** `["steps", 2, "parallel", "a", 0]` v poli `address`
  odpovědi `GET …/scenarios/<s>`; `etag` u scénářů, agentů a skillů.
- **HTTP v `serve`** (docs/spec/api.md „Editace“): `PUT/DELETE
  …/scenarios/<s>`, `POST …/scenarios/<s>/steps`, `PATCH/DELETE
  …/steps/<adresa>`, `POST …/steps/<adresa>/move`, `PUT/DELETE
  …/agents/<a>`, `PUT …/config`, `PUT/DELETE …/skills/<n>`, `GET/PUT
  …/files/<cesta>`, `POST …/scenarios` a `…/agents` (= `new`). 409 při
  neshodě otisku, 422 s `errors`, 404 mimo povolené soubory; stejný token
  jako čtení.

## 0.4.0 — 2026-09-26 (agencast new, registr projektů, čtecí API serve)

Minor: nové příkazy a endpointy, formáty v1 beze změny (R8).

- **`agencast new project <cesta> [--name N]`** — kostra projektu:
  `workflows/config.yaml` (OpenRouter, aliasy `chytry`/`rychly`/
  `gemini-image`, `storage.type: local`), agent `pisatel`, scénář `ukazka`
  (projdou `validate --offline` i `--fake`), `.env.example`, `.gitignore`.
  **`new agent|scenario <jméno>`** přidá minimální soubor. Nic nepřepisuje.
  API `new_project`, `new_agent`, `new_scenario` (vrací vytvořené cesty).
- **Registr projektů** `~/.config/agencast/projects.yaml`
  (`AGENCAST_CONFIG_DIR`): `agencast projects list|add|rm`; plní ho
  `new project` a úspěšný `validate`/`run` (hláška jednou na stderr).
  API `projects()` (s `available`), `add_project`, `remove_project`.
- **`serve` mimo projekt = režim registru** s tokenem `AGENCAST_TOKEN`,
  tajemství z prostředí serveru; v projektu nebo s `--project` beze změny.
- **Čtecí API** (docs/spec/api.md): `GET /projects`, `/projects/<p>`
  (scénáře, agenti, skilly, MCP servery bez tajemství, aliasy, limity,
  vazby), `/scenarios/<s>` (strom kroků pro karty s `refs`), `/runs`,
  `/runs/<id>` (kroky se stavem, cenou a časem), `/runs/<id>/files/<cesta>`
  (jen uvnitř složky běhu), `/spend?day=`; `POST /projects/<p>/runs`.
  API `describe_project`, `describe_scenario`, `run_detail`, `run_file`,
  `spend`; `Ledger.rows`.

## 0.3.1 — 2026-09-26 (strop souběžných běhů, denní limit útraty)

Patch: dva volitelné klíče, bez nich se chování nemění (R8).
Formát: spec v1, zpětně kompatibilní doplnění (ISSUES 40).

- **`limits.max_parallel_runs: N`** — nejvýš N běhů naráz nad jedním
  `runs/`, napříč procesy (CLI, n8n, cron, `serve --workers`): `flock` na
  `<runs>/_slots/<n>.lock`, slot se bere před složkou běhu a uvolní se
  vždy. Plno → stderr „čekám na volný slot (max_parallel_runs=N)“,
  polling po 0,5 s nejdéle `run_timeout`, pak `timeout`. Čekání je
  v záznamu jako událost `run_waiting` (`waited_s`). Falešné běhy se
  slotů účastní.
- **`limits.daily_budget_usd: X`** — denní kniha útraty
  `<runs>/_ledger/<RRRR-MM-DD>.jsonl` (UTC, řádek `{run_id, cost_usd,
  finished_at}` na každý dokončený běh; `--fake` do `_ledger-fake/`).
  Součet dneška ≥ X → nový běh skončí `budget` ještě před prvním
  voláním. Kontrola jen na startu; kniha se píše vždy, od 0.3.1.
- Běh, který kvůli slotu nebo dennímu limitu nezačal, má záznam jako běh
  nespuštěný webhookem (`run_scenario(error=…)`): `run_finished` s `error`,
  `callback.json`, `summary.md`, bez `plan.md`/`inputs.json`.
- `SlotStore` a `Ledger` v `task.py` vedle `DedupeStore` (místo pro Modal).
- `agencast run`: chyba bez kroku se vypíše `<třída>: <hláška>` (dřív
  „… v kroku None: …“).

## 0.3.0 — 2026-09-26 (AgenCast, souběžné běhy, API pro obálky)

Minor: přejmenování a nové funkce, vše zpětně kompatibilní. Formát: spec
v1 beze změny (jen doplněné `--workers` ve webhook.md).

- **Přejmenování:** framework se jmenuje AgenCast — balík `agencast`
  (dřív `maw`), příkaz `agencast` (dřív `maw`), výjimka `AgencastError`
  (dřív `MawError`). Žádný formát (záznam běhu, callback, hlavičky
  webhooku, fake skripty) jméno neobsahoval, takže staré záznamy i skripty
  platí beze změny. Alias z tutoriálu:
  `alias agencast="uv run --project framework agencast"`.
- **`agencast serve --workers N`** (výchozí 1): N pracovních vláken nad
  jednou frontou; obnova fronty a `request_key` pod zámkem, pořadí
  dokončení s N > 1 není zaručené (ISSUES 39).
- **Kolize `run_id`** (ISSUES 35): nový suffix, nejvýš 5×, pak `internal`;
  webhook při přijetí přeskočí id s existujícím záznamem fronty.
- **Cache `/models`** se zapisuje atomicky (dočasný soubor + `os.replace`),
  poškozená cache = cache není.
- **`DedupeStore`** (`task.py`): `dedupe_key` za rozhraním `get` / `claim` /
  `finish`, lokálně beze změny souborů `<runs>/_dedupe/` a `_dedupe-fake/`;
  `Run.dedupe` je místo, kam Modal dosadí vlastní úložiště.
- **`agencast.api`**: `load`, `run`, `dry_run`, `runs_list`, `run_status`
  (+ `find_root`) — tenké funkce nad validate, engine a record; `cli.py`
  i `server.py` volají přes ně (DESIGN „Obálky“).

## 0.2.5 — 2026-09-25 (čas v řádku Celkem)

Formát: spec v1, jen zpřesnění (ISSUES 38):

- **Řádek Celkem** v `summary.md` i `report.html` má ve sloupci Čas čas
  celého běhu (`duration_s` z `run_finished`, stejné číslo jako
  v hlavičce), ne součet kroků — větve `parallel` běží současně a vnořené
  kroky jsou už v čase nadřazeného `parallel`/`switch`/`call`.

## 0.2.4 — 2026-09-25 (celá cena, řádek Celkem)

Formát: spec v1, jen zpřesnění (ISSUES 38):

- **Cena bez zaokrouhlení:** cena volání jde do `events.jsonl`,
  `calls/*.json`, `step_finished`, `run_finished` i `callback.json`
  přesně tak, jak ji vrátil OpenRouter. Součty (krok, běh, obrázky,
  `budget_exceeded_usd`) se zaokrouhlují na 10 desetinných míst (dřív 8,
  takže callback ukázal 4.48e-06 místo 4.482e-06).
- **Zobrazení:** `summary.md`, `report.html`, závěrečný řádek `maw run`,
  `maw runs list/show` a hlášky rozpočtu ukazují cenu desetinně
  (`0,000004482`, dřív `0,0000`), aspoň na 4 místa; krok bez volání
  modelu má cenu `0`. Hlášky rozpočtu mají nově desetinnou čárku.
- **Řádek Celkem** na konci tabulky kroků v `summary.md` i `report.html`
  (i u neúspěšného běhu): cena běhu, u obrázků „z toho obrázky …".

## 0.2.3 — 2026-09-25 (podsložky se ignorují)

Formát: spec v1, jen zpětně kompatibilní uvolnění (ISSUES 37):

- **Podsložky v `workflows/agents/` a `workflows/scenarios/`** (třeba
  `archiv/`) už nezastaví validate ani běh chybou `config` — tiše se
  ignorují. Agenti, cíle `call`, webhook i `maw runs`/`serve` čtou dál
  jen soubory přímo ve složce.
- Když agent nebo cíl `call` neexistuje, ale stejnojmenný soubor leží
  v podsložce, hláška dodá „(soubor je v podsložce agents/archiv/,
  podsložky se nečtou)".
- Srozumitelnější hláška, když se spouští scénář mimo
  `workflows/scenarios/` (třeba z `archiv/`).

## 0.2.2 — 2026-09-25 (opravy z tutoriálů 6 a 7)

Formát: spec v1, jen zpětně kompatibilní doplňky. Opravy z
`docs/tutorials/BUGS.md` (sekce maw 0.2.1):

- **Dedupe a `--fake` (BUGS 8, vysoká):** falešný běh zapisuje dedupe do
  `<runs>/_dedupe-fake/` (stejná struktura), ostrý do `<runs>/_dedupe/`;
  nikdy se nečtou křížem. Dřív ostrý běh po zkoušce s `--fake` krok
  přeskočil a vrátil vymyšlený výstup. `run_started` má nové pole
  `fake` (run-record.md), `summary.md` a `report.html` falešný běh
  označí. Záznamy v `_dedupe/` z falešných běhů 0.2.1 oprava nepozná
  a nesmaže — po zkouškách s `--fake` je najdi (`grep -l <scénář>
  runs/_dedupe/*.json`) a smaž ručně jen ty, o kterých víš, že patří
  zkouškám.
- **`task` se `schema` vždy od `tool_wrapper` (BUGS 7, ISSUES 36):**
  strukturovaný výstup se v kroku `task` vynucuje nástrojem
  `_submit_output` bez ohledu na `models.<alias>.structured_output`;
  `response_format` se v tazích neposílá (Haiku s ním končilo smyčku
  bez volání nástrojů). Kaskáda dál na `prompt`. Nastavení aliasu platí
  jen pro `ask`. Úroveň je v `model_call.structured_output`, v poznámce
  kroku a v `plan.md` („kaskáda od tool_wrapper"). Falešný poskytovatel
  na úrovni `tool_wrapper` respektuje `text` ze skriptu (model nezavolal
  `_submit_output`).
- Agent s `mcp` bez `tools`: hláška jmenuje servery, ukáže tvar
  `tools: { server: [nástroj, …] }` a radí `maw run … --dry-run` (BUGS 9).
- `POST /runs`: 422 vrací chyby těla (neznámé pole, …) spolu s chybami
  scénáře a vstupů, ne až na druhý pokus (BUGS 9).
- Tutoriály: díl 5 `report_url` (od 0.2.0 adresa `report.html`, ne
  `null`), díl 6 poznámka k `schema` u `task`, díl 7 `_dedupe-fake/`.

## 0.2.1 — 2026-09-25 (opravy z tutoriálů)

Formát: spec v1 beze změny. Opravy chyb z `docs/tutorials/BUGS.md`:

- Varování „poskytovatel nevrátil cenu" jen u úspěšné odpovědi bez
  `usage.cost`; chybová odpověď (HTTP 429, 400, `error` v těle) nic
  nestojí a varování nedá (BUGS 1).
- `{{ }}` ve výrazu (`set`, `when`, `switch.value`): jen hláška „šablona
  tu není povolená", nově se stříškou; druhá hláška o AST uzlu `Set`
  zmizela (BUGS 2).
- Konkrétní id modelu v agentovi (`model: anthropic/claude-haiku-4.5`):
  hláška „model '…' není alias v config.yaml (aliasy: …)" místo regexu
  ze schématu; schéma beze změny (BUGS 3).
- Chyba syntaxe YAML: česká věta s radou (hodnota s `{`, `[`, `: ` nebo
  ` #` do uvozovek, scenario.md §5 „Pozor na YAML") a řádkem, původní
  hláška parseru jako druhý řádek. Duplicitní klíč beze změny (BUGS 4).
- Skloňování počtů: `validate` „(1 krok / 2 kroky / 9 kroků)", `serve`
  „ve frontě 2 běhy", poznámka kroku `call` v `summary.md` (BUGS 5).
- Testy: testovací config přebírá aliasy ze skutečného
  `workflows/config.yaml` (klíče, limity a úložiště zůstávají testovací),
  falešné `GET /models` zná jejich id — nový alias vlastníka nerozbije
  zlaté testy (BUGS 6).
- Čtecí timeout HTTP volání poskytovatele (ISSUES 34): u každého volání
  min(zbývající čas kroku, 120 s chat/obrázek/tah `task`, 30 s Jev);
  vypršení = `transient`, opakuje se podle `retry`. `model_call`
  a `jev_call` mají nové pole `timeout_s` (run-record.md, zpětně
  kompatibilně). Dřív zaseknuté spojení čekalo až na timeout kroku.
- Nestabilní test `test_webhook.py::test_202_and_signed_callback`
  (pod zátěží 1 selhání z 8 běhů): test četl `events.jsonl`, jakmile
  přijímač dostal callback, ale `callback_sent` framework zapíše až po
  odpovědi přijímače. Webhook testy teď čekají na konec běhu (smazání
  záznamu fronty) a pořadí ve frontě drží závorou místo `sleep` —
  totéž se týkalo restartu v `test_request_key_is_idempotent_across_restart`.
  Marker `live` (síť, skutečný npx server) registrovaný v pyproject,
  běžný `uv run pytest` ho přeskočí; žádný test ho zatím nepotřebuje —
  celá sada prošla i bez sítě. Testy: +9 (369 celkem).

## 0.2.0 — 2026-09-25 (Fáze 3)

Formát: spec v1 beze změny.

### 3b — call, webhook server, report.html, CLI

- Krok `call` (scenario.md call, DESIGN §5.3): vnořený scénář ve stejném
  běhu — stejný `events.jsonl`, rozpočet i časový limit, kroky mají cestu
  `navrh/copy`, záznam ve `steps/<nn>-<id>/steps/…` (+ `inputs.json`
  volání). `validate`: `callable: true`, vstupy (povinné, žádné navíc,
  typy; `file` jen ze souboru), čtou se jen deklarované `outputs`, cykly
  a `limits.max_call_depth`; chyby volaného scénáře s jeho jménem souboru.
  Za běhu: typ vstupu, který nešel ověřit předem → `expression`; chyba
  uvnitř = chyba kroku `call` (`step` je cesta); `on_error: continue`
  kroku `call` ji pokryje, včetně jeho vlastního `budget_usd`/`timeout`.
  Soubory z volaného scénáře se nenahrávají.
- Webhook server `maw serve --host --port [--fake]` (webhook.md):
  `POST /runs` (Bearer token, 401/422 synchronně bez `run_id`, 202,
  200 pro opakovaný `request_key`), `GET /runs/<run_id>`, fronta jeden
  běh po druhém, trvalá fronta a `request_key` v `<runs>/_queue/`,
  callback vždy od přidělení `run_id` (i když `validate` selže až po
  vyzvednutí z fronty → `config`; přerušený běh po restartu → `internal`).
  Stdlib `http.server.ThreadingHTTPServer` — žádná nová závislost.
- `report.html` u každého běhu: jeden soubor bez externích zdrojů,
  hlavička, chyba, varování, vstupy, tabulka kroků (i vnořených), prompty
  a odpovědi v `<details>` (zkrácené na 4000 znaků), výstupy; maskování
  tajných hodnot, bez base64. Nahraje se do úložiště, `report_url`
  v callbacku (dřív `null`, ISSUES 5).
- CLI: scénář jménem nebo cestou; kořen projektu podle `workflows/` od
  cwd nahoru nebo `--project` (u všech příkazů; nahrazuje `runs
  --workflows`); `runs list` ukazuje i požadavky ve frontě; `maw migrate
  <soubor>` (kostra: v1 → „nic k převodu", neznámá verze → `config`).
  Vlastní hlášky česky; hlášky samotného `argparse` (usage, chybějící
  argument) zůstávají anglicky.
- `callback_url` smí být i `http://127.0.0.1` (testy, lokální přijímač) —
  ISSUES 14.
- Testy: +44 (call, webhook s lokálním přijímačem callbacku, report, CLI);
  zlaté scénáře `kontrola-tonu` (`callable: true`) a `ukazka-call`.

### 3a — krok task, MCP servery, skilly, dedupe_key

- **Krok `task`** (`task.py`): smyčka model ↔ nástroje přes OpenRouter
  chat; nástroje jen z efektivní sady krok ⊆ agent ⊆ `mcp.yaml`;
  `max_turns` (opakování po `transient`/`schema` se nepočítá; vyčerpání =
  `budget`), `budget_usd`, `timeout`; `isError` a chyby validace
  argumentů jdou modelu jako výsledek nástroje; obrázky z nástrojů jako
  soubor `steps/<nn>-<id>/tool-<NN>-<k>.png` + následná user zpráva;
  `reasoning_details` zpět; kaskáda výstupu (`native_schema` →
  `tool_wrapper` s `_submit_output`, který nikdy nejde na server →
  `prompt`); události `tool_call`, `calls/NN.tool.json`.
- **MCP klient** (`mcp_client.py`) nad oficiálním SDK `mcp==2.2.*`: stdio,
  Streamable HTTP, SSE; `mode="legacy"`; timeouty handshaku i volání +
  vnější pojistka; rozbalení `ExceptionGroup` do tříd `timeout` /
  `config` / `transient`; stderr serveru do `mcp/<server>.stderr.log`
  (maskovaný); server startuje při prvním `task` v běhu, sdílí ho větve
  `parallel`, na konci běhu se ukončí (test: 0 zbylých procesů);
  události `mcp_server`.
- **Normalizace schémat nástrojů:** `server__tool` (`[a-zA-Z0-9_-]`, max
  64), vložení `$ref`, `allOf`/`oneOf`, `const` → `enum`, ne-řetězcový
  `enum` do `description`; argumenty se validují proti původnímu schématu
  (`invalid_args`). Kolize jmen po normalizaci = `config`.
- **`mcp.yaml`:** načtení a validace proti `mcp.schema.json`, jen
  `{run_dir}`; oprávnění vlastníka ve `validate` (`agents`, `scenarios`,
  `tools` serveru; krok nesmí rozšířit server, nástroj ani `max_turns`);
  proměnné serverů se maskují a nesmí být stejné jako `*_env` z
  `config.yaml`; chybějící proměnná = `config` před během.
- **Skilly:** u `task` oddíl `## Skilly` se seznamem `- jméno: description`
  a nástroj `load_skill` (`enum` jmen, chyba se seznamem, tah, server
  `_skills`); u `ask` beze změny celá těla.
- **`dedupe_key`:** atomické soubory `<runs>/_dedupe/<sha256>.json`;
  `started` před prvním voláním MCP nástroje, `succeeded` s výstupem;
  další běh krok přeskočí (`step_skipped`, `dedupe`), `started` bez
  `succeeded` = `config` „ověř ručně a smaž <soubor>".
- `validate`: alias agenta v `task` musí mít `tools` v `GET /models`.
- Falešný poskytovatel: `tool_calls` ve skriptu. Testy (+30, z toho 2 po
  sloučení s 3b: `--dry-run` s nástroji serverů, `task` s `dedupe_key`
  uvnitř `call`): falešný MCP server
  `tests/fake_mcp_server.py`, `test_task.py`, zlatý scénář
  `workflows/scenarios/ukazka-task.yaml` (agent `knihovnik`, skill
  `katalog`, nový `workflows/mcp.yaml`).

Závislosti: přibylo jen `mcp==2.2.*` (zamčeno v `uv.lock`).

- `--dry-run`: `plan.md` u kroku `task` ukazuje agenta, výslednou sadu
  nástrojů, skilly, `max_turns` a `dedupe_key`; servery, které běh může
  spustit, se kvůli `tools/list` spustí v dočasné složce a plán vypíše,
  co nabízejí (nebo proč se nespustily) — scenario.md §7.

Není v 0.2.0: opakování handshaku MCP (ISSUES 26), čtecí timeout HTTP
volání poskytovatele (ISSUES 34, otevřeno).

## 0.1.0 — 2026-09-25 (Fáze 2: jádro)

Formát: spec v1 (`version: 1` scénáře, agenta, configu).

- CLI `maw`: `validate`, `run` (`-i`, `--dry-run`, `--fake [SKRIPT]`,
  `--callback-url`, `--request-key`), `runs list|show`.
- Loader: YAML 1.2 core (jen `true`/`false`, `4:5` a `yes` jsou text,
  duplicitní klíč = `config` s řádkem), frontmatter, `.env` s CRLF.
  JSON Schema se čtou z `docs/spec/schema/` (jediný zdroj pravdy);
  kroky se ověřují každý proti schématu svého typu → české hlášky
  bez vypsání hodnot `*_env`.
- Validate (scenario.md §7): verze, schéma, jméno = soubor, podsložky,
  unikátní `id`, odkazy jen nahoru a ne do jiné větve `parallel`, krok,
  který nemusí proběhnout, bez `default`, úplný `default`, agent / skill /
  alias existuje, limity kroku ⊆ agent, šablony jen v povolených polích,
  výrazy (syntaxe, zakázané konstrukce, typy známé předem), `output`
  poslední a sedí na `outputs`, nedosažitelné kroky za `fail`, `cases`
  ⊆ `criteria`, aliasy proti `GET /models` (cache 24 h, výstup obrázku,
  structured_outputs/tools).
- Výrazy a šablony (§5, D1c): vlastní evaluátor nad `ast`, tečka = klíč,
  přísné typy, `and/or/not` jen bool, `round` půlku od nuly, limity
  2000 znaků / hloubka 100 / výsledek 100 000, hlášky česky se stříškou.
- Engine: pořadí kroků, `when`, `parallel` (TaskGroup, zrušení ostatních
  větví → `cancelled`), `switch` s `default`, `set`, `fail`, `output`;
  `retry` (2 s, 4 s, 8 s nebo `Retry-After`), `timeout` (krok, parallel,
  běh), `budget_usd` (krok, agent, parallel, běh, obrázky), `on_error:
  continue`; třídy chyb §6; HTTP 200 není úspěch.
- Poskytovatelé: OpenRouter chat (kaskáda `native_schema` → `tool_wrapper`
  → `prompt`, zpětná vazba modelu, `reasoning_details` zpět), Jev
  (`/systemone`), obrázek (chat completions s `modalities`, base64 →
  soubor, kontrola `aspect_ratio` ±2 %), normalizace `usage`. Falešný
  poskytovatel = `httpx.MockTransport` (stejná cesta kódu jako ostrá).
- Záznam běhu (run-record.md): složka, `events.jsonl`, `steps/<nn>-<id>/`,
  `summary.md`, `plan.md`, `callback.json`, maskování tajných hodnot,
  bez base64 a `reasoning_details`; callback POST (https, HMAC-SHA256,
  3 pokusy).
- Konformační sada `uv run pytest` (výrazy ze spiku (c), loader, validate,
  engine, zlaté scénáře z `workflows/` a ukázky z `docs/spec/`).

Závislosti: `pyyaml`, `jsonschema`, `httpx`; vývoj `pytest`. Oproti
výchozí sadě D4 **bez** `pydantic` (formáty jsou JSON Schema ze spec, ty
ověřuje `jsonschema` přímo — druhý popis v pydantic by byl duplicita) a
**bez** `typer` (stačí `argparse` ze stdlib). `hatchling` je jen build
backend pro instalaci příkazu `maw` (za běhu se nepoužívá). `mcp` a `modal`
přijdou s krokem `task` a nasazením.

Není v 0.1.0 (místa v kódu připravená): `task` (MCP, skilly přes
`load_skill`, `dedupe_key`), `call`, webhook server, Modal, `report.html`,
úložiště R2 — `validate` je odmítne srozumitelnou chybou `config`.
