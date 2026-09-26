# Audit ponytail — AgenCast, 2026-09-26

Rozsah: `framework/src`, `framework/tests`, `ui/src`, `ui/e2e`, `skills/`, `docs/` (jen struktura).
Výchozí stav `main` 211948d. Hledalo se jen přeinženýrování (mrtvý kód, zdvojené pomocné funkce,
obaly, které jen předávají, ručně psané věci ze stdlib/platformy, nepotřebné závislosti). Chyby
správnosti, bezpečnost a výkon sem nepatří (viz „Mimo rozsah“).

Značky: `delete` smazat · `shrink` stejná logika kratší · `stdlib` / `native` nahradit
stdlib / platformou · `yagni` abstrakce bez druhého použití.
Stav: **provedeno** (bez změny chování a formátů, sada zelená) · **odloženo** (mění chování nebo
smlouvu, jen odhad rozsahu) · rozsah XS < 1 h, S < ½ dne, M ~ 1 den.

## Nálezy (seřazeno podle dopadu)

| # | Značka | Co | Čím nahradit | Cesta | Stav |
|---|---|---|---|---|---|
| 1 | native | Dvě YAML knihovny: PyYAML (vlastní `Yaml12Loader` s resolvery YAML 1.2, `_int12`, kontrola duplicitních klíčů) a ruamel.yaml (editace, řádky chyb schématu). | Jen ruamel (`YAML(typ="safe")` je YAML 1.2 a hlídá duplicitní klíče — ověřeno v prostředí projektu, ruamel 0.19.1: `yes`/`on`/`4:5` jsou text, `0o17` = 15, duplicitní klíč = `DuplicateKeyError`). −1 závislost, ~−45 ř. | `framework/src/agencast/loader.py:22-78`, `pyproject.toml` | odloženo — M; mění text a řádky hlášek (spec B6, testy hlášek), nejdřív spike |
| 2 | yagni | 6 funkcí v `api`, které jen předávaly argumenty do `projects`. | Re-export z `projects` (`list_projects as projects`, `normalize_root as normalize_project_root`, `remove as remove_project`, …). −33 ř. | `framework/src/agencast/api.py` | provedeno |
| 3 | shrink | report.html znovu skládá kroky z událostí; totéž dělá `_step_rows` pro API. | `report_html` nad `_step_rows(run.rec.dir)`. ~−25 ř. | `framework/src/agencast/record.py:417-440`, `:303` | odloženo — M; jiné popisky stavů v reportu, report je součást záznamu běhu |
| 4 | shrink | `SaveStatus` byl doslovná kopie `SaveNote`, jen s tlačítkem na chyby. | `SaveNote` s volitelným `onJump`. −18 ř. | `ui/src/pages/Scenario.tsx`, `ui/src/pages/Agents.tsx:46` | provedeno |
| 5 | delete | Mrtvé komponenty `Field` a `Row` (0 použití; `Row` byl exportovaný jen kvůli `noUnusedLocals`). | nic. −19 ř. | `ui/src/components/ui.tsx`, `ui/src/pages/Agents.tsx` | provedeno |
| 6 | shrink | `load_config` + `if errs: raise ConfigErrors` ve 4 kopiích. | `validate.require_config(wf)`. −12 ř. | `api.py`, `cli.py`, `projects.py`, `server.py` | provedeno |
| 7 | shrink | Čtení `JSON` těla a kontrola objektu/polí ve 4 handlerech s různými těly 422. | `_json_object(raw, **navíc)` v `server.py`. ~−12 ř. | `framework/src/agencast/server.py` (`accept`, `create_project`, `add_project`, `edit`) | odloženo — S; musí zachovat přesná těla 422 (HTTP smlouva) |
| 8 | shrink | Atomický zápis (temp + `os.replace`) v 5 variantách. | Jedna `atomic_write(path, data)` v `loader`. ~−10 ř. | `task.py:78`, `edit.py:86`, `server.py:152`, `projects.py:204`, `providers.py:101` | odloženo — S; `mkstemp` dává práva 0600 místo umask a jiná jména dočasných souborů |
| 9 | native | `Collapsible` ručně (`useState` + šipka) místo `<details>/<summary>` (ten už je v `RunFiles.tsx`). | `<details>`. ~−10 ř. | `ui/src/components/ui.tsx:236` (3 použití ve `StepPanel.tsx`) | odloženo — S; jiný fokus a značka rozbalení, vizuální kontrola |
| 10 | native | `Modal` ručně (focus trap, Esc, klik na pozadí) místo `<dialog>.showModal()`. | `<dialog>` + `::backdrop` + `cancel`. ~−25 ř. | `ui/src/components/form.tsx:177` (12+ použití) | odloženo — M; chování fokusu a e2e selektory |
| 11 | shrink | Obnova fronty v `Webhook.execute` četla `events.jsonl` vlastní smyčkou. | `record._events`. −8 ř. | `framework/src/agencast/server.py:204` | provedeno |
| 12 | shrink | Strom kroků z textu scénáře ve 3 kopiích. | `projects.text_tree(text, where)`. −8 ř. | `edit.py` (`render`, `render_text`), `projects.py` (`_tree`) | provedeno |
| 13 | stdlib | Aritmetika a `< <= > >=` ve výrazech přes slovník lambd a `match`. | `operator.add/sub/…/lt/ge`. −6 ř. | `framework/src/agencast/expressions.py` | provedeno |
| 14 | shrink | `_Checker.walk`: pět větví `if/elif` volajících metodu stejného jména. | Jedno `getattr(self, k)`. −6 ř. | `framework/src/agencast/validate.py:485` | provedeno |
| 15 | delete | `engine._leaves` byl kopií `mcp_client._leaves` (engine už z `mcp_client` importuje). | Import. −6 ř. | `framework/src/agencast/engine.py` | provedeno |
| 16 | shrink | Testy: `registry_server`, `serve`, `TOKEN`, `SECRET` v testovacích modulech, 3 křížové importy a 9× `noqa: F811`. | `conftest.py`. −7 ř., −12 `noqa`/importů | `framework/tests/` | provedeno |
| 17 | delete | Mrtvé exporty: `RELIABILITY` (StepPanel má vlastní), typy `ScenarioDraft`, `TextFile`, `export { Arrow }`. | nic. −7 ř. | `ui/src/steps.ts`, `scenarioDraft.ts`, `textfile.ts`, `components/StepCards.tsx` | provedeno |
| 18 | shrink | Pořadí ve frontě pro `GET /runs/<id>` se počítá znovu, místo aby se použilo `api._queue`. | `api._queue(runs)`. ~−5 ř. | `framework/src/agencast/server.py:167` | odloženo — XS; starší endpoint n8n, ověřit shodu těla |
| 19 | shrink | `read_file` má vlastní regex frontmatteru („jako loader.read_frontmatter“). | `loader.split_frontmatter(text, where)` pro oba. ~−5 ř. | `edit.py:583`, `loader.py:85` | odloženo — XS; skupiny se liší koncovým `\n` → může se posunout řádek u chyby na konci |
| 20 | shrink | `schema_errors`: výpočet prefixu `soubor, řádek N:` dvakrát. | Lokální `at(p)`. −3 ř. | `framework/src/agencast/loader.py:232` | provedeno |
| 21 | delete | Nepoužité klíče `agent.limits`, `skill.text`, `editor.readonly` (ověřeno i proti dynamickým `t(\`…\`)`). | nic. −3 ř. | `ui/src/locales/cs.json` | provedeno |
| 22 | delete | Nepoužitý `conftest.fake_for`. | nic. −3 ř. | `framework/tests/conftest.py` | provedeno |
| 23 | delete | Nepoužitý import `dataclasses.field`; `usage` v `run_finished` skládaný ze slovníku s `None`, které hned přepíše `tokens()`. | `self.tokens() \| {"cost_usd": …}` (stejné pořadí klíčů). −2 ř. | `framework/src/agencast/engine.py` | provedeno |
| 24 | shrink | Dvě tabulky `IMAGE_EXT` (task má navíc gif). | Jedna tabulka. −1 ř. | `engine.py:46`, `task.py:27` | odloženo — XS; krok `image` by u gif ukládal `.gif` místo `.bin` |
| 25 | shrink | Regex jména projektu opsaný v serveru. | `projects.NAME`. 0 ř., jeden zdroj pravdy | `framework/src/agencast/server.py` | provedeno |

**Celkem 25 nálezů: 16 provedeno, 9 odloženo.** Provedeno: kód −128 ř. (jádro −71,
testy −7, ui −50), 0 závislostí. Odloženo: ~−140 ř. a −1 závislost (PyYAML).

### Vědomě ponecháno (neprovádět)

- `DedupeStore`, `SlotStore`, `Ledger`, `local_*` — rozhraní s jednou implementací, ale DESIGN
  „Obálky“ je drží kvůli Modalu. Totéž fasáda `api` nad `edit`/`projects`.
- `fake.py` v `src` — funkce CLI (`--fake`), ne testovací kód.
- Vlastní evaluátor výrazů (`expressions.py`) — whitelist AST podle spiku (c), bezpečnostní hranice.
- `i18n.ts` — vlastní plurály, přiměřené (Intl.MessageFormat v cílovém runtime není).
- `Webhook.authorized` × `Projects.authorized`, `engine` řádek kroku ve `start()` a `skip()`,
  testové pomocné funkce (`errors` ×3, čtení `events.jsonl` ×5, fixture `proj` ×2, `json()` v testech
  ui ×3) — zisk ≤ 8 ř., cenou nového souboru nebo horší čitelnosti.
- `edit.set_header` / `add_step` / … kontrolují tělo před `_save` i v operaci — určuje, že špatné
  tělo dá 422 dřív než 409.
- `skills/`, `docs/` — bez nálezů; každý soubor v `docs/` má aspoň jeden odkaz.

### Mimo rozsah (pro běžné review)

- `ui/src/textfile.ts:270` — tabulka LCS v `Uint16Array` přeteče nad 65 535 řádků → tichý
  špatný diff (ceiling v markeru uvádí jen paměť).
- `skills/install.sh` — natvrdo cesta `src=~/workspace/...`.

## Dluhový deník

Všechny komentáře `ponytail:` (včetně jednoho v docstringu). Formát: co bylo odloženo → strop →
návrh → kdy řešit. `bez spouštěče` = komentář nenese podmínku, kdy se k němu vrátit.

### framework/src/agencast

| Soubor:řádek | Co bylo odloženo (strop) | Návrh | Kdy řešit |
|---|---|---|---|
| `loader.py:17` | Schémata se čtou z `docs/spec/schema` vedle frameworku; wheel bez repa je nemá. | Přibalit `docs/spec/schema` do wheelu (`[tool.hatch.build.targets.wheel] force-include`), `SPEC_SCHEMAS` přes `importlib.resources`. | Před nasazením na Modal nebo instalací z wheelu. |
| `edit.py:45` | Jeden zámek na všechny zápisy v procesu; ruční úprava souboru mezi čtením a `os.replace` se nepozná. **bez spouštěče** | Těsně před `os.replace` soubor znovu přečíst a porovnat otisk (okno se zúží z doby validace na µs), případně `flock` na souboru. | **Hned** — okno trvá celou validaci kopie projektu (viz `edit.py:103`) a roste s projektem; DESIGN slibuje „souběžná ruční úprava se nepřepíše potichu“. |
| `edit.py:103` | Kopie celé `workflows/` při každé změně (ms u běžného projektu). | Kopírovat jen `*.yaml`/`*.md` a `SKILL.md`, ne ostatní soubory skillů. | Až bude skill s velkými soubory nebo úprava přes GUI > 200 ms. |
| `server.py:63` | Jeden zámek na přijetí požadavku i `validate` v pracovních vláknech. **bez spouštěče** | Zámek jen kolem `request_key` + zápisu fronty; `validate` mimo zámek. | Až `workers` > 1 a `POST /runs` začne čekat (měřit latenci 202). |
| `server.py:212` | Přerušený běh po restartu se neopakuje, jen se nahlásí (může i doběhnout bez callbacku). **bez spouštěče** | Nechat — rozhodnutí (vedlejší účinky kroků). Případně volitelné `resume` jen pro scénáře bez `task`. | Jen na žádost uživatele (nové pole = rozšíření spec). |
| `mcp_client.py:107` | `allOf` se slučuje mělce (stačí na Pydantic: jeden `$ref`). | Hluboké sloučení `properties`/`required` napříč částmi. | S prvním MCP serverem, jehož schéma má `allOf` s víc objekty. |
| `projects.py:201` | Registr: dva souběžné zápisy (add ze dvou terminálů) → vyhraje poslední. | `flock` na `projects.yaml.lock` kolem čtení+zápisu v `_save`. | Až GUI a CLI zapisují registr souběžně (režim registru v `serve`). |
| `projects.py:393` | `error_fields` čte pole ze začátku hlášky; hláška jiného tvaru má jen `message`. **bez spouštěče** | Strukturované chyby už v `validate` (objekt místo textu), text z nich skládat. | Až GUI potřebuje `field`/`step` u hlášek, které ho teď nemají (hlásit z GUI). |
| `projects.py:399` | Scénář pojmenovaný `config` nebo `mcp` se splete s `config.yaml`/`mcp.yaml`. **bez spouštěče** | Hlásit scénáře cestou `scenarios/<jméno>.yaml`, nebo jména `config`/`mcp` zakázat ve `validate` (varování). | Při příští úpravě hlášek `validate`; rozšíření spec → koordinátor. |

### ui/src

| Soubor:řádek | Co bylo odloženo (strop) | Návrh | Kdy řešit |
|---|---|---|---|
| `textfile.ts:62` | Varování před odchodem jen při kliknutí na odkaz; tlačítko Zpět (`hashchange`) se neptá. **bez spouštěče** | Posluchač `hashchange`: při neuloženém stavu `confirm`, při odmítnutí vrátit `location.hash`. | Až uživatel přijde o rozpracovanou změnu tlačítkem Zpět (stav zůstává v localStorage, riziko je malé). |
| `textfile.ts:270` | LCS má paměť O(n·m); pro soubory nad ~5000 řádků. | Myersův diff (O((n+m)·d)). Pozor: `Uint16Array` navíc přeteče nad 65 535 řádků. | Až bude soubor ve `workflows/` nad 2000 řádků. |
| `edit.ts:334` | Kontejner (`parallel`/`switch`) s hodnotou `null` nejde uložit formulářem, jen v YAML. **bez spouštěče** | `replace_step` s celým krokem včetně vnořených větví. | Až to uživatel ve formuláři potřebuje (zatím hláška „uprav v YAML“). |

### spikes/ (kód se do frameworku nepřenáší, neřešit)

| Soubor:řádek | Co bylo odloženo | Poznámka |
|---|---|---|
| `spikes/expressions/custom_eval.py:14` | Stříška předpokládá jednořádkový výraz. | Ve frameworku vyřešeno (`expressions._src`, `_fragment_error`). |
| `spikes/mcp-python/common.py:108` | Mělké sloučení `allOf`. | Přeneseno jako `mcp_client.py:107`. |

**15 markerů, 7 bez spouštěče** (`edit.py:45`, `server.py:63`, `server.py:212`, `projects.py:393`,
`projects.py:399`, `textfile.ts:62`, `edit.ts:334`).

## Celkový verdikt

Repo je čisté: 25 nálezů na ~20 tis. řádků, žádná nepoužitá závislost, žádná zbytečná vrstva nad
rámec toho, co předepisuje DESIGN. Přeinženýrování se tu skoro nevyskytuje, dluh vzniká spíš
opisováním (4× načtení configu, 5× atomický zápis, 3× strom scénáře) mezi workery, kteří nevěděli
o funkci o dva soubory vedle. Největší riziko není ve velikosti kódu, ale v dluhu `edit.py:45`
+ `edit.py:103`: ruční úprava souboru během validace kopie projektu se přepíše potichu, a to okno
roste s projektem. Příště bych zadal (1) opravu `edit.py:45` (znovu ověřit otisk před
`os.replace`, s testem), (2) spike „jen ruamel“, který změří dopad na hlášky spec B6 a rozhodne
o odebrání PyYAML, (3) do zadání workerů větu „před novou pomocnou funkcí grepni `framework/src`“.
