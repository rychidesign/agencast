# Changelog formátů

Každá změna formátu agenta, scénáře nebo konfigurace se zapisuje sem
(DESIGN §5.6). Formát se mění jen zvýšením `version`; framework umí číst
všechny vydané verze (R7).

Do 0.2.5 se balík a příkaz jmenovaly `maw`; starší záznamy tu to jméno nechávají.

## version 1 — 2026-09-25 (návrh ke schválení)

První specifikace. Obsahuje:

- [agent.md](agent.md) — agent jako Markdown s frontmatter (D1a).
- [scenario.md](scenario.md) — scénář, 10 typů kroků v1 (D1d), šablony
  a výrazy (D1c, §5.4), `call` (§5.3), chyby (§5.1).
- [config.md](config.md) — `config.yaml`, `mcp.yaml`, `commands.yaml`
  (jen struktura; krok `run` není ve v1).
- [run-record.md](run-record.md) — složka běhu, `events.jsonl`,
  `summary.md`, callback.
- [schema/](schema/) — JSON Schema draft 2020-12: `agent`, `scenario`,
  `config`, `mcp`, `skill`.

Odchylky od ilustrativní syntaxe v DESIGN (§3 D1a/D1d, §6) — ke
schválení v [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md):

- zadání pro model v `ask` se jmenuje `prompt` (v §6 `task`, což koliduje
  s typem kroku `task`),
- `schema` se píše uvnitř `ask`/`task` (jako v §6), ne na úrovni kroku,
- rozpočet kroku se píše `budget_usd` (jako `limits.budget_usd` u agenta),
- scénář deklaruje `outputs` v hlavičce; krok `output` je poslední,
- nové třídy chyb `fail` a `internal`.

Přidáno, protože to vyžaduje DESIGN, i když ne ve výčtu D1d: `default`
(§5.4), `dedupe_key` (§5.2). Přidáno kvůli referenčnímu scénáři: pole
`aspect_ratio` kroku `image` (IG 4:5) a `max_tokens` u aliasu modelu
(reasoning modely, `finish_reason: length`).

### Doplněno 2026-09-25 — jazyk výrazů (spike (c))

- [scenario.md §5](scenario.md#výrazy) popisuje jazyk výrazů přesně: co v
  něm je (seznamový literál, `in`, `%`, záporný index, `["klíč"]`) a co
  ne (podmínka `if/else`, řezy, `**`, metody, přiřazení, `lambda`,
  comprehension, atributy, `import`); tečka = čtení klíče; přísné typy
  (porovnání napříč typy je chyba kromě `== null` / `!= null`, `boolean`
  není číslo, text + číslo je chyba, `/` je vždy desetinné); 8 funkcí
  s typovou kontrolou; `round` půlku od nuly; `str(null)` = `"null"`;
  limity 2000 znaků / hloubka 100; příklady hlášek.
- Rozhodnuto: literály `true` / `false` / `null` (OPEN-QUESTIONS 7).
- Nová třída chyby `expression` (chyba výrazu nebo šablony za běhu; chová
  se jako `fail` kroku, neopakuje se). Statická kontrola výrazů ve
  `validate` zůstává třída `config`. Třída doplněna i do výčtu v
  [run-record.md](run-record.md).
- `null` v šabloně je chyba, výjimkou je výslovný `default`.
- Nové otevřené otázky 8–10 (rozhodnutí koordinátora s výchozí volbou).
- JSON Schema beze změny (výrazy jsou řetězce).

### Opravy po nezávislé kontrole — 2026-09-25

Podle [REVIEW.md](REVIEW.md) (41 nálezů) a rozhodnutí koordinátora; stav
každého nálezu je na konci REVIEW.md.

- **Ověřování:** ukázky i úryvky se ověřují [`tools/check.py`](tools/check.py)
  — **stejným loaderem, jaký použije framework** (PyYAML `SafeLoader` bez
  resolverů YAML 1.1, kontrola duplicitních klíčů, `jsonschema` Draft
  2020-12). Dřívější ověření přes `check-jsonschema` (ruamel) chybu
  PyYAML s `4:5`, `yes`/`on` a duplicitními klíči skrylo. Spuštění:
  `uv run docs/spec/tools/check.py`.
- **YAML 1.2 core** pro všechny soubory: booleany jen `true`/`false`,
  `4:5` a `yes` jsou text, duplicitní klíč = chyba `config`.
- **Skilly:** nový [skill.md](skill.md) a `schema/skill.schema.json`; u
  `task` seznam + nástroj `load_skill`, u `ask` celé (OPEN-QUESTIONS 11).
  Ukázka `workflows/skills/thtd-hlas/`.
- **Oprávnění:** každý server z `mcp` agenta má povinný seznam `tools`;
  vlastník v `mcp.yaml` určuje `agents` (povinné), `scenarios` a `tools`
  serveru; scénář má `callable` (výchozí `false`) a `call` smí jen na
  volatelný scénář.
- **Nové:** [webhook.md](webhook.md) (`POST /runs`, 202/200/401/422);
  kaskáda strukturovaného výstupu (`models.<alias>.structured_output`,
  `_submit_output`); `dedupe` jako samostatné soubory `_dedupe/` se stavem
  `started`/`succeeded` (OPEN-QUESTIONS 12); `runs_dir`; `transport` a
  `timeouts` u MCP serveru; `{run_dir}` v `args`; vstup typu `file` přes
  `call`.
- **Záznam běhu:** klíč v úložišti `<run_id>-<32 hex>/<jméno>`; tajné
  hodnoty se v záznamu i callbacku nahrazují `<tajné: JMENO>`; události
  `mcp_server`, `callback_failed`; `step_finished.status: cancelled`;
  `tool_call.invalid_args`; `<nn>` = pořadí v souboru.
- **Upřesnění:** rozpočet (kontrola před voláním, chybějící cena), `max_turns`
  vs. `retry`, `image` bez obrázku a kontrola `aspect_ratio`, úplný
  `default`, `switch` nad `null`, uzavřený seznam polí se šablonami,
  typy operátorů a `in`, čísla (`int`, `round`, `nan`), typ `file`,
  kontrola `validate` proti `/models` s cache.
- **Schémata:** kořen `schema` u `ask`/`task` je mapa; `outputs` aspoň
  jedna položka; `limits.max_turns` povinné jen s `mcp`; `base_url` jen
  OpenRouter nebo localhost; `env` serveru bez `PATH`, `LD_PRELOAD`, ….
- **Přejmenováno v ukázce:** výstup fotografa `prompt` → `popis_fotky`.
- OPEN-QUESTIONS: 6 vyřešeno podle DESIGN §5.8; nové 11–14.

## version 1 — zpětně kompatibilní doplnění (framework 0.2.1)

- [run-record.md](run-record.md): pole `timeout_s` v událostech
  `model_call` a `jev_call` (timeout HTTP volání, ISSUES 34). Starší
  záznamy ho nemají; čtenář ho smí ignorovat.

## version 1 — zpětně kompatibilní uvolnění (framework 0.2.3)

- [agent.md](agent.md), [scenario.md](scenario.md): podsložky ve
  `workflows/agents/` a `workflows/scenarios/` už nejsou chyba `config`,
  ale tiše se ignorují (hodí se třeba na archiv). Čtou se dál jen soubory
  přímo ve složce. Co dřív prošlo, projde dál (ISSUES 37, REVIEW M9).

## version 1 — zpětně kompatibilní zpřesnění (framework 0.2.4)

- [run-record.md](run-record.md): ceny volání se ukládají přesně tak, jak
  je vrátil poskytovatel, součty se zaokrouhlují jen na 10 desetinných
  míst (dřív 8). Tvar polí se nemění, jen přesnost. `summary.md` a
  `report.html` ukazují celou cenu (`0,000004482` místo `0,0000`) a na
  konci tabulky kroků řádek **Celkem** (ISSUES 38).

## version 1 — zpětně kompatibilní zpřesnění (framework 0.2.5)

- [run-record.md](run-record.md): řádek **Celkem** v `summary.md` a
  `report.html` má ve sloupci Čas čas celého běhu (`duration_s`
  z `run_finished`), ne součet kroků (ISSUES 38).

## version 1 — beze změny formátu (framework 0.3.0)

- Framework se jmenuje AgenCast, příkaz `maw` → `agencast` (v textu
  [run-record.md](run-record.md) a ISSUES). Žádný formát jméno
  neobsahoval: záznam běhu, callback (`X-Run-Id`, `X-Signature`) ani fake
  skripty se nemění.
- [webhook.md](webhook.md): `agencast serve --workers N` (výchozí 1) —
  N běhů najednou nad jednou frontou; `queue_position` počítá čekající
  i běžící, pořadí dokončení s N > 1 není zaručené (ISSUES 39). Tvar
  požadavku, odpovědí ani callbacku se nemění.
- Kolize `run_id` (ISSUES 35) řeší nový suffix; formát id se nemění.

## version 1 — zpětně kompatibilní doplnění (framework 0.3.1)

- [config.md](config.md), [schema/config.schema.json](schema/config.schema.json):
  volitelné `limits.max_parallel_runs` (celé číslo ≥ 1, strop souběžných
  běhů napříč procesy, čekání nejdéle `run_timeout`, pak `timeout`) a
  `limits.daily_budget_usd` (číslo > 0, denní strop útraty v UTC, kontrola
  jen na startu, pak `budget`). Bez nich se chování nemění; co dřív
  prošlo, projde dál (ISSUES 40).
- [run-record.md](run-record.md): vedle složek běhů `_slots/<n>.lock`
  a denní kniha `_ledger/<RRRR-MM-DD>.jsonl` (`_ledger-fake/` u `--fake`);
  nová událost `run_waiting` (`waited_s`, `max_parallel_runs`). Starší
  záznamy ji nemají; čtenář neznámé události smí ignorovat.
- [webhook.md](webhook.md): čekání na slot a třídy `timeout`/`budget`
  u běhu, který nezačal. Tvar požadavku, odpovědí ani callbacku se nemění.

## version 1 — beze změny formátu (framework 0.4.0)

- Nové [projects.md](projects.md): registr projektů
  `~/.config/agencast/projects.yaml` a šablony `agencast new` (ISSUES 41).
- Nové [api.md](api.md): čtecí API `serve` (`/projects/...`), režim
  registru s `AGENCAST_TOKEN`, `POST /projects/<p>/runs` (ISSUES 42).
  [webhook.md](webhook.md) na něj odkazuje; `POST /runs`, `GET /runs/<id>`
  a callback se nemění.
- Formáty `agent`, `scenario`, `config`, `mcp`, záznam běhu ani JSON Schema
  se nemění.

## version 1 — beze změny formátu (framework 0.5.0)

- [api.md](api.md) „Editace“: editační operace `serve` pro GUI —
  hlavička scénáře a kroky (přidat, upravit, přesunout, smazat), agent,
  skill, `config.yaml`, surový text souborů ve `workflows/` a `new`
  přes HTTP. Adresa kroku (`address` v `GET …/scenarios/<s>`), otisk
  `etag` (sha256 obsahu) a v `GET /projects/<p>` pole `etag` u scénářů,
  agentů a skillů — nová pole v odpovědích, stávající se nemění
  (ISSUES 43).
- Zápis zachovává komentáře, pořadí klíčů, prázdné řádky a uvozovky;
  soubory zůstávají ve formátu v1, JSON Schema se nemění.

## version 1 — zpětně kompatibilní doplnění (framework 0.6.0)

- [api.md](api.md) „Doplňky pro GUI“ (ISSUES 44): `POST
  /projects/<p>/validate` (validace bez zápisu), `env` v `GET
  /projects/<p>` (jen příznak nastavené proměnné, nikdy hodnota), v
  seznamu a detailu běhu `scenario`, `started_at`, `finished_at`,
  `current_step`, `steps_total`; `POST /projects/<p>/runs` s volitelnou
  `callback_url` a `dry_run`; `serve` podává GUI (`GET /`, `/assets/…`
  bez tokenu) a má `--cors <origin>`.
- **Změna tvaru API (0.5.0 → 0.6.0):** položky polí `errors` jsou objekty
  `{message, file?, step?, field?, line?}` místo textů; `message` =
  dřívější text. Týká se `GET /projects/<p>` (projekt, scénáře, agenti,
  skilly), `GET …/scenarios/<s>`, `GET …/files/<cesta>` a odpovědí 200/422
  editačních operací. Jediný klient těch polí je GUI; `details`, CLI
  a Python API zůstávají texty.
- [run-record.md](run-record.md): `run_started` má nová pole `steps_total`
  a `callback_url` (bez query, `null` = bez callbacku). Starší záznamy je
  nemají; čtenář bere chybějící pole jako `null`.
- [webhook.md](webhook.md) jen odkaz; smlouva `POST /runs` se nemění.
  Formáty `agent`, `scenario`, `config`, `mcp` ani JSON Schema se nemění.
