# Changelog frameworku

Semver podle DESIGN §5.9 bod 5: oprava = patch, přidání = minor, nová
verze formátu = major. Změny formátů jsou v `docs/spec/CHANGELOG.md`.

## 0.2.0 — 2026-09-25 (Fáze 3a: krok task, MCP, skilly, dedupe_key)

Formát beze změny: spec v1 (§5.9 — jen implementace existujících polí).

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
- Falešný poskytovatel: `tool_calls` ve skriptu. Testy: falešný MCP server
  `tests/fake_mcp_server.py`, `test_task.py`, zlatý scénář
  `workflows/scenarios/ukazka-task.yaml` (agent `knihovnik`, skill
  `katalog`, nový `workflows/mcp.yaml`).

Závislosti: přibylo jen `mcp==2.2.*` (zamčeno v `uv.lock`).

Není v 0.2.0: výpis nástrojů MCP serverů v `--dry-run`/`plan.md`
(ISSUES 22), opakování handshaku MCP (ISSUES 16).

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
