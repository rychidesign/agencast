# Changelog formátů

Každá změna formátu agenta, scénáře nebo konfigurace se zapisuje sem
(DESIGN §5.6). Formát se mění jen zvýšením `version`; framework umí číst
všechny vydané verze (R7).

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
