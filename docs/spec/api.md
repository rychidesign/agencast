# API `agencast serve` — rodina `/projects/...` (čtení od frameworku 0.4.0, editace od 0.5.0, doplňky pro GUI od 0.6.0, 0.7.0, 0.8.0 a 0.9.0)

Pro GUI (DESIGN „Obálky“) a kohokoli, kdo chce číst a upravovat projekty
a číst běhy přes HTTP. Doplňuje [webhook.md](webhook.md) — `POST /runs`, `GET /runs/<id>`
a callbacky se nemění. Projekty: [projects.md](projects.md).

## Režimy serveru

| Spuštění | Režim | Token (`Authorization: Bearer …`) | `/runs` |
|---|---|---|---|
| `agencast serve` v projektu (složka s `workflows/` od cwd nahoru) nebo `--project <cesta>` | jeden projekt (jako do 0.3.x; Modal) | hodnota `webhook.token_env` projektu | ano, beze změny |
| `agencast serve` mimo projekt | registr | proměnná **`AGENCAST_TOKEN`** (povinná při startu, jinak `config`) | ne — 404, běh přes `POST /projects/<p>/runs` |

- V jednoprojektovém režimu je v `/projects` právě ten projekt; jméno má
  z registru, jinak výchozí (jméno složky, [projects.md](projects.md)).
- **Tajemství v režimu registru:** `serve` bere všechna tajemství
  z prostředí svého procesu (a z `.env` v aktuální složce); `.env`
  jednotlivých projektů se v registru nečtou. Jména proměnných
  (`openrouter.api_key_env`, `callback.secret_env`) se dál berou
  z `config.yaml` projektu, hodnoty z prostředí serveru. `callback.secret_env`
  se vyžaduje jen při běhu s `callback_url`; `webhook.token_env` se čte
  pouze v jednoprojektovém režimu.
- Registr se čte při každém požadavku. Každý projekt má vlastní frontu
  (`<runs>/_queue/`) a `--workers N` pracovních vláken; fronty dostupných
  projektů se obnoví při startu, projekt přidaný později při prvním `POST`.
- Čtení i zápis používají stejný token. Chybějící/nesedící token → 401.
- Token chrání jen `/projects…` a `/runs…`; GUI (`GET /`, `/assets/…`,
  oddíl [GUI](#gui-a-cors-od-060)) je bez tokenu.

## Endpointy

Odpovědi jsou JSON (kromě `runs/<id>/files/`). Chyby `{"error": "…"}`, u 422
navíc `"details": [...]` (u editačních operací `"errors": [...]`, oddíl
[Editace](#editace-od-050)). Pole `errors` obsahuje od 0.6.0 **objekty**
`{message, file?, step?, field?, line?}` ([Chyby jako objekty](#chyby-jako-objekty-od-060));
`details` zůstávají texty.

| Metoda a cesta | Odpověď |
|---|---|
| `GET /projects` | `{"projects": [{"name", "root", "available"}]}`; od 0.7.0 `reason` u `available: false`, `last_run` a `registry`; od 0.9.0 `projects_root` a `writable`; od 0.10.0 `counts` a `spend_today_usd` |
| `POST /projects/new` | `{name, root?}` — založí projekt a registruje ho; 201 `{name, root, created}` |
| `POST /projects` | `{root, name?}` — zaregistruje existující projekt s `workflows/config.yaml`; 201 `{name, root}` |
| `DELETE /projects/<p>` | Odebere projekt z registru; 200 `{name, removed: true, files_deleted: false, message}`; soubory zůstávají |
| `GET /projects/<p>` | popis projektu (níže) |
| `GET /projects/<p>/scenarios/<s>` | scénář se stromem kroků (níže) |
| `GET /projects/<p>/files/<cesta>` | soubor z `workflows/` jako text s otiskem (oddíl [Editace](#editace-od-050)); od 0.8.0 `errors` = chyby `validate` souboru a `?etag_only=1` → jen `{"etag"}` ([Doplňky 0.8.0](#dávka-náhled-a-doplňky-podle-nálezů-gui-část-2-od-080)) |
| `HEAD /projects/<p>/files/<cesta>` | od 0.8.0: jen otisk v hlavičce `ETag` ([Doplňky 0.8.0](#dávka-náhled-a-doplňky-podle-nálezů-gui-část-2-od-080)) |
| `GET /projects/<p>/runs` | `{"runs": [...]}` — položky jako `agencast runs list`: čekající `{"run_id", "status": "queued"}`, pak `{"run_id", "status", "cost_usd", "duration_s", "callback", "scenario", "started_at", "finished_at", "current_step", "steps_total"}` (pole od `scenario` dál od 0.6.0, [Běhy pro GUI](#běhy-pro-gui-od-060)), nejnovější první; od 0.7.0 `state`, `fake`, `current_nn`, `steps_done`, `queue_position` a `?scenario=&limit=`; od 0.10.0 `before` a `next_before` |
| `GET /projects/<p>/runs/<id>` | stav běhu + kroky + soubory (níže); čekající ve frontě `{"run_id", "status": "queued"}` (od 0.7.0 i `state`, `scenario`, `queue_position`); od 0.7.0 strom kroků `tree` |
| `GET /projects/<p>/runs/<id>/steps/<cesta>` | jeden krok běhu: jeho události, výstup a soubory (od 0.7.0, [níže](#get-projectspruns-idstepscesta-od-070)) |
| `GET /projects/<p>/runs/<id>/files/<cesta>` | obsah souboru ze složky běhu (`summary.md`, `report.html`, `events.jsonl`, `steps/…`), `Content-Type` podle přípony |
| `GET /projects/<p>/spend?day=RRRR-MM-DD` | denní kniha útraty ostrých běhů: `{"day", "total_usd", "runs": [{"run_id", "cost_usd", "finished_at"}]}`; bez `day` dnešek (UTC); jiný tvar `day` → 422 |
| `POST /projects/<p>/runs` | jako `POST /runs` ([webhook.md](webhook.md)) v projektu `<p>` — stejné tělo, odpovědi 202/200/401/422 i callback; od 0.6.0 `callback_url` volitelná a `dry_run` ([Spuštění z GUI](#spuštění-z-gui-od-060)) |
| `POST /projects/<p>/validate` | validace bez zápisu (od 0.6.0, [níže](#post-projectspvalidate-od-060)) |

- **404** s JSON chybou: neznámý projekt, nedostupný projekt
  (`available: false`), neznámý scénář, běh, soubor nebo adresa. Cesta
  souboru mimo složku běhu (`..`, absolutní cesta, symlink ven) = 404.
- **422**: `config.yaml` projektu neprošel kontrolou (`details` = chyby,
  od 0.7.0 u `GET` i `errors` jako objekty); u `POST` i chybějící
  proměnná prostředí projektu. `…/runs`, `…/runs/<id>…` a `spend`
  fungují od 0.7.0 i s neplatným `config.yaml` (stačí jim `runs_dir`).
- Zápis projektu je dostupný jen v režimu registru. V jednoprojektovém
  režimu vrací `POST /projects/new`, `POST /projects` a
  `DELETE /projects/<p>` kód **405** s vysvětlením.
- `POST /projects/new` potřebuje `name` a volitelně `root`; bez `root` se
  použije `<projects_root>/<name>`. Existující `workflows/` a jméno v
  registru → **409**; u existující složky odpověď radí přidat ji přes
  `POST /projects`. `created` je seznam cest vytvořených na disku.
- `POST /projects` přijímá kořen projektu s `workflows/config.yaml`.
  `root` se rozbalí a normalizuje: `~` se expanduje, absolutní cesta může
  mířit kamkoli a relativní cesta se vztahuje k `projects_root`. Jakékoli
  `..` nebo relativní cesta vedoucí ven přes symlink → **422**. Kolize
  názvu nebo kořene → **409**.
- Zápis mimo domovský adresář `serve` je povolený, pokud ho dovolí práva
  souborového systému. GUI má práva uživatele, pod kterým `agencast serve`
  běží.
- `spend` čte jen knihu ostrých běhů (`_ledger/`); falešné běhy
  (`--fake`) mají vlastní `_ledger-fake/` a v `spend` nejsou.

### `GET /projects/<p>`

```json
{
  "name": "lumen", "root": "~/projekty/lumen",
  "models": {"chytry": "anthropic/claude-haiku-4.5"},
  "limits": {"run_budget_usd": 1.0, "run_timeout": "1h", "max_call_depth": 3},
  "scenarios": [{"name": "ig-post", "etag": "9f2c…", "description": "…", "inputs": {…}, "outputs": {…},
                 "callable": false, "steps_count": 8, "errors": [],
                 "types": ["ask", "jev", "fail", "jev", "image", "output"],
                 "last_run": {"run_id": "20260926-120000-ig-post-ab12", "state": "succeeded",
                              "finished_at": "2026-09-26T12:01:10.500Z", "cost_usd": 0.0123}}],
  "agents": [{"name": "copywriter", "etag": "…", "description": "…", "model": "chytry",
              "model_id": "anthropic/claude-haiku-4.5", "skills": ["lumen-hlas"], "mcp": [], "tools": {},
              "errors": []}],
  "skills": [{"name": "lumen-hlas", "etag": "…", "description": "…", "errors": []}],
  "mcp_servers": [{"name": "filesystem", "type": "stdio", "agents": ["knihovnik"],
                   "tools": ["read_text_file"], "scenarios": null}],
  "links": {"scenario_agent": [["ig-post", "copywriter"]], "scenario_step_agent": [["ig-post", "copy", "copywriter"]],
            "scenario_scenario": [["ukazka-call", "kontrola-tonu"]],
            "agent_skill": [["copywriter", "lumen-hlas"]], "agent_server": [["knihovnik", "filesystem"]]},
  "env": {"CALLBACK_SECRET": true, "OPENROUTER_API_KEY": true, "WEBHOOK_TOKEN": false},
  "errors": []
}
```

- Čte se loaderem a `validate` (bez kontroly modelů proti `GET /models`).
  `errors` = hlášky `validate` daného souboru; rozbitý soubor se přesto
  zobrazí, co z něj jde přečíst. `errors` projektu = chyby `mcp.yaml`.
- `steps_count` = všechny kroky včetně vnořených ve větvích.
- `etag` (od 0.5.0) = otisk souboru scénáře, agenta, skillu (`SKILL.md`)
  pro editační operace.
- MCP servery bez tajemství: jen jméno, `type` (`stdio`/`http`) a povolení
  z `mcp.yaml` (`agents`, `tools`, `scenarios`) — žádné `command`, `args`,
  `url`, `env` ani `bearer_token_env`.
- `links` = seřazené dvojice [odkud, kam]: krok `ask`/`task` → agent,
  krok `call` → scénář, agent → skill, agent → MCP server. Od 0.7.0
  `scenario_step_agent` = trojice [scénář, id kroku, agent] (i kroky ve
  větvích); `scenario_agent` zůstává. Od 0.8.0 `scenario_model` =
  [scénář, alias] z kroků `image` a pole `models_used`
  ([Doplňky 0.8.0](#dávka-náhled-a-doplňky-podle-nálezů-gui-část-2-od-080)).
- `types` (od 0.7.0) = typy kroků hlavního seznamu v pořadí souboru
  (`null`, když soubor typ neurčuje); `last_run` (od 0.7.0) = nejnovější
  běh scénáře (tvar [níže](#doplňky-podle-nálezů-gui-od-070)), `null` bez běhů.
- `env` (od 0.6.0) = všechny proměnné prostředí, na které projekt
  odkazuje (pole `*_env` v `config.yaml` — `openrouter.api_key_env`,
  `webhook.token_env`, `callback.secret_env`, proměnné úložiště — a
  `env`/`bearer_token_env` serverů v `mcp.yaml`), seřazené podle jména:
  `true` = v prostředí procesu `serve` je neprázdná (v jednoprojektovém
  režimu po načtení `.env` projektu, v registru jen prostředí serveru a
  `.env` v cwd). **Hodnota se nikdy nevrací.**

### `GET /projects/<p>/scenarios/<s>`

Hlavička jako v `scenarios` výše (včetně `etag`) a `steps` — strom kroků
pro karty:

```json
{"nn": 3, "address": ["steps", 2], "id": "stop", "type": "fail", "when": "steps.kontrola.on_brand < 0.7",
 "fields": {"fail": "Text neodpovídá značce (on_brand = {{ steps.kontrola.on_brand }})"},
 "refs": ["steps.kontrola.on_brand"]}
```

| Pole | Co to je |
|---|---|
| `nn` | pořadí v souboru hloubkově — stejné číslo jako složka kroku `steps/<nn>-<id>` v záznamu běhu |
| `address` | adresa kroku pro editační operace (od 0.5.0, níže) |
| `id`, `type`, `when` | id, typ kroku (`null`, když soubor typ neurčuje), podmínka (`null` bez `when`) |
| `fields` | všechna ostatní pole kroku tak, jak jsou v souboru, bez vnořených seznamů kroků (u `switch` jen `value`) |
| `refs` | odkazy `steps.<id>.<pole>` z výrazů a šablon tohoto kroku (bez vnořených kroků) |
| `agent` | u `ask` a `task` |
| `call` | u `call`: jméno volaného scénáře |
| `branches` | u `parallel`: `{větev: [kroky]}` |
| `cases`, `default` | u `switch`: `{hodnota: [kroky]}` a `[kroky]` |

### `GET /projects/<p>/runs/<id>`

Pole `agencast runs list` (`run_id`, `status`, `cost_usd`, `duration_s`,
`callback`) a navíc:

- `steps` — kroky v pořadí první události z `events.jsonl`:
  `{"step", "kind", "status", "branch", "started_at", "finished_at",
  "duration_s", "cost_usd"}`; `status` = `running`, `succeeded`,
  `failed`, `cancelled`, nebo `skipped` (pak `reason_code`, `reason`).
  `step` je cesta jako v `events.jsonl` (u `call` `navrh/copy`). Od 0.7.0
  další pole ([níže](#podrobnosti-kroků-od-070)).
- `files` — relativní cesty všech souborů ve složce běhu (pro `files/`).
- od 0.7.0 `tree`, `callees`, `tree_source` — strom kroků, jak platil
  při běhu ([níže](#strom-kroků-běhu-od-070)).

## Editace (od 0.5.0)

GUI mění soubory jen přes tyto operace; **soubor je pravda** (DESIGN
„Obálky“). Každá operace:

1. přečte soubor a porovná **otisk** `etag` z těla požadavku s otiskem
   souboru — `etag` = sha256 (hex) bajtů souboru, který klient načetl
   (`GET …/scenarios/<s>`, `GET /projects/<p>`, `GET …/files/<cesta>`);
   nový soubor má `etag: null`. Nesedí → **409** a nic se nezapíše;
2. soubor upraví se zachováním komentářů, pořadí klíčů, prázdných řádků
   a stylu uvozovek (nezměněné řádky zůstanou doslova; přepsaný řádek
   může dostat jiné mezery, např. `{a: 1}` místo `{ a: 1 }`);
3. ověří kopii `workflows/` se změnou stejně jako `agencast validate`
   (bez kontroly modelů proti `GET /models`). Změna nesmí do projektu
   přidat **novou** chybu — chyby, které v projektu už byly, ji
   neblokují (dva rozbité soubory jdou opravit jeden po druhém).
   Nová chyba → **422** a nic se nezapíše;
4. zapíše atomicky (dočasný soubor + přejmenování).

Tělo požadavku je JSON objekt s polem `etag`. Odpovědi:

| Kód | Tělo |
|---|---|
| 200 | `{"etag": "<nový otisk>" \| null po smazání, "errors": [chyby, které v projektu zůstávají]}` (objekty, [níže](#chyby-jako-objekty-od-060)) |
| 409 | `{"error", "etag": "<aktuální otisk>" \| null}` — soubor se mezitím změnil; načti ho znovu |
| 422 | `{"error", "errors": [...]}` — hlášky jako z `agencast validate` (třída `config`) jako objekty, nic se nezapsalo |
| 404 | `{"error"}` — neznámý projekt, soubor, adresa kroku nebo cesta mimo povolené soubory |
| 401 | chybí/nesedí token (stejný jako pro čtení) |

Přejmenování vrací navíc `name` a `changed`: nové jméno a seřazené cesty
změněných souborů relativně k `workflows/`; `errors` obsahuje chyby, které
v projektu zůstaly. Přejmenování neupravuje `runs/`: starší běhy dál nesou
jméno scénáře platné při spuštění.

### Adresa kroku

Cesta ke kroku v dokumentu scénáře, jako JSON pole. Vrací ji
`GET …/scenarios/<s>` v poli `address` každého kroku:

| Adresa | Co to je |
|---|---|
| `["steps", 2]` | třetí krok hlavního seznamu |
| `["steps", 2, "parallel", "a", 0]` | první krok větve `a` kroku `parallel` |
| `["steps", 4, "switch", "cases", "hravy", 1]` | druhý krok případu `hravy` |
| `["steps", 4, "switch", "default", 0]` | první krok `default` |
| bez posledního indexu, např. `["steps", 2, "parallel", "a"]` nebo `["steps"]` | seznam kroků (začátek větve) |

Vnořuje se do libovolné hloubky, kterou dovoluje scénář. V URL je adresa
cesta po `steps/` (každá položka jeden segment, `/` ve jménu případu jako
`%2F`): `["steps", 2, "parallel", "a", 0]` → `…/steps/2/parallel/a/0`.

### Operace

`<p>` projekt, `<s>` scénář, `<a>` agent, `<n>` skill. Změny polí jsou
**merge patch** (RFC 7396): mapa se slučuje, `null` klíč smaže, jiná
hodnota nahradí. Text s `{{ }}` se zapíše v dvojitých uvozovkách, víc
řádků jako blok `|`; nahrazený text v uvozovkách si styl nechá.

| Metoda a cesta | Tělo (kromě `etag`) | Co udělá |
|---|---|---|
| `POST /projects/<p>/scenarios` | `{"name", "description"?}` | nový scénář ze šablony (`agencast new scenario`); 200 `{"name", "etag"}`, existující → 422; `description` od 0.8.0 |
| `POST /projects/<p>/agents` | `{"name", "description"?, "model"?}` | nový agent ze šablony (`agencast new agent`); 200 `{"name", "etag"}`; od 0.8.0 `description` a `model` (alias z `config.yaml`, jiný → 422) |
| `POST /projects/<p>/scenarios/<s>/rename` | `{"name"}` | přejmenuje scénář, soubor i odkazy `call.scenario`; 200 `{"name", "etag", "changed", "errors"}` |
| `POST /projects/<p>/agents/<a>/rename` | `{"name"}` | přejmenuje agenta, soubor i odkazy v krocích `ask`/`task` a seznamech `agents` v `mcp.yaml`; 200 `{"name", "etag", "changed", "errors"}` |
| `PUT /projects/<p>/scenarios/<s>` | `{"fields": {…}}` | hlavička: jen `description`, `inputs`, `outputs`, `callable` (jiné pole → 422) |
| `DELETE /projects/<p>/scenarios/<s>` | — | smaže scénář; když ho jiný volá přes `call` → 422 |
| `POST /projects/<p>/scenarios/<s>/steps` | `{"after": adresa, "step": {…}}` | vloží krok (celý, jako v souboru) za krok `after`; adresa seznamu = na jeho začátek; bez `after` na začátek `steps` |
| `PATCH /projects/<p>/scenarios/<s>/steps/<adresa>` | `{"fields": {…}}` | pole kroku (i `id`, `when`, větve `parallel` a případy `switch`) |
| `POST /projects/<p>/scenarios/<s>/steps/<adresa>/move` | `{"to": adresa}` | přesune krok za krok `to`, nebo na začátek seznamu `to`; do vlastní větve → 422 |
| `DELETE /projects/<p>/scenarios/<s>/steps/<adresa>` | — | smaže krok |
| `PUT /projects/<p>/scenarios/<s>/steps/<adresa>` | `{"step": {…}}` | od 0.8.0: nahradí celý krok (umí `null`) |
| `POST /projects/<p>/scenarios/<s>/batch` | `{"ops": [...]}` | od 0.8.0: dávka operací, jedna validace, jeden zápis ([níže](#dávka-post-scenariossbatch)) |
| `POST /projects/<p>/scenarios/<s>/render` | `{"ops": [...]}`, `etag` nepovinný | od 0.8.0: výsledek dávky bez zápisu `{text, tree, errors}` ([níže](#náhled-post-scenariossrender)) |
| `PUT /projects/<p>/agents/<a>` | `{"frontmatter": {…}, "body": "…"}` | frontmatter jako merge patch, tělo celé; chybějící = beze změny; nový agent potřebuje obojí |
| `DELETE /projects/<p>/agents/<a>` | — | smaže agenta; když ho používá scénář (`ask`/`task`) → 422 |
| `PUT /projects/<p>/skills/<n>` | `{"text"}` | celý `SKILL.md`; nový skill založí |
| `DELETE /projects/<p>/skills/<n>` | — | smaže `SKILL.md` (a složku, je-li prázdná); když ho agent používá → 422 |
| `PUT /projects/<p>/config` | `{"fields": {…}}` | `config.yaml`: jen `models`, `limits`, `storage`, `webhook`, `callback` a `openrouter.api_key_env`; od 0.8.0 i `runs_dir` a `openrouter.jev_model` ([proč ne víc](#put-config-od-080)) |
| `GET /projects/<p>/files/<cesta>` | — | `{"path", "etag", "text", "errors"}` a rozparsovaný obsah: u `.yaml` `data`, u `.md` `frontmatter` a `body` (GUI neparsuje samo) |
| `PUT /projects/<p>/files/<cesta>` | `{"text"}` | celý text souboru (záložní textový editor); nový soubor s `etag: null` |

- Po operaci nad kroky `output` zůstává posledním krokem hlavního
  seznamu — jinak 422 (`config`). Když z větve `parallel` nebo případu
  `switch` odejde poslední krok, větev/případ zmizí (prázdný seznam
  schéma nepovoluje).
- Merge patch neumí zapsat hodnotu `null` (smaže klíč); krok s `null`
  (např. `default: { file: null }`) jde vložit celý přes `POST …/steps`,
  od 0.8.0 nahradit celý přes `PUT …/steps/<adresa>`, nebo upravit jako
  text přes `files/`.
- **`files/<cesta>`** (jiná rodina než `…/runs/<id>/files/`) pouští jen
  `agents/<jméno>.md`, `scenarios/<jméno>.yaml`, `skills/<jméno>/SKILL.md`,
  `config.yaml` a `mcp.yaml` uvnitř `workflows/` projektu; cokoli jiného
  (`..`, absolutní cesta, symlink ven, `.env`, `commands.yaml`, podsložky)
  = 404. **`.env` se nikdy nečte ani nezapisuje.**
- **Tajemství:** `config.yaml` a `mcp.yaml` obsahují jen jména proměnných
  (`*_env`, `env`), hodnoty jsou v prostředí/`.env`. Hodnota místo jména
  (třeba klíč `sk-or-…` v `api_key_env`) neprojde schématem → 422 a
  hláška hodnotu nevypíše.
- Operace v jednom procesu `serve` jdou po jedné (zámek). Ruční úprava
  souboru mimo `serve` se pozná podle otisku při další operaci.
- Veřejné API (`agencast.api`): `set_header`, `add_step`, `update_step`,
  `move_step`, `delete_step`, `delete_scenario`, `rename_scenario`, `set_agent`,
  `delete_agent`, `rename_agent`, `set_skill`, `delete_skill`, `set_config`, `read_file`,
  `write_file`, od 0.6.0 `validate_text`, od 0.8.0 `replace_step`,
  `batch`, `render`, `file_etag`; výjimky `Conflict` (`.etag`),
  `NotFound`, `ConfigErrors`, od 0.8.0 `OpError` (podtřída
  `ConfigErrors`, `.op` = index operace dávky). Python API vrací chyby jako texty (jako
  `agencast validate`); objekty z nich dělá až HTTP vrstva.

## Doplňky pro GUI (od 0.6.0)

Podle návrhu GUI (`docs/ui/navrh-gui.md` §7, §8). Aditivní kromě tvaru
`errors` — jediným klientem těch polí je GUI.

### Chyby jako objekty (od 0.6.0)

Všude, kde API vrací pole `errors` (`GET /projects/<p>` — projekt,
scénáře, agenti, skilly —, `GET …/scenarios/<s>`, `GET …/files/<cesta>`,
odpovědi 200 a 422 editačních operací, `POST …/validate`), je položka
objekt:

```json
{"message": "ukazka.yaml: krok \"vystup\", output.text: krok 'nic' neexistuje (dostupné: napis)\n  {{ steps.nic.text }}\n           ^",
 "file": "scenarios/ukazka.yaml", "step": "vystup", "field": "output.text"}
```

| Pole | Co to je |
|---|---|
| `message` | hláška přesně jako z `agencast validate` (CLI ji tiskne beze změny) |
| `file` | relativní cesta ve `workflows/` (`scenarios/ig-post.yaml`, `agents/copy.md`, `skills/hlas/SKILL.md`, `config.yaml`, `mcp.yaml`) |
| `step` | id kroku, kterého se chyba týká |
| `field` | pole (cesta s tečkami, např. `ask.prompt`, `inputs.tema.default`, `openrouter`) |
| `line` | číslo řádku — syntaxe YAML, duplicitní klíč a od 0.10.0 chyby schématu `config.yaml` podle klíče |

Pole kromě `message` chybí, když je hláška neuvádí (např. chyba těla
požadavku `fields: má být JSON objekt`). Změna tvaru proti 0.4.0/0.5.0
(dřív texty): `message` = dřívější text. `details` (odmítnutý `POST`,
chyba `config.yaml` u čtení) zůstávají texty.

### `POST /projects/<p>/validate` (od 0.6.0)

Validace bez zápisu, stejná mechanika jako krok 3 editačních operací
(kopie `workflows/` + `validate` bez kontroly modelů).

| Tělo | Co ověří |
|---|---|
| prázdné nebo `{}` | projekt, jak je na disku |
| `{"path": "scenarios/ig-post.yaml", "text": "…"}` | projekt s tímto souborem nahrazeným textem `text` (nový soubor jde taky); `path` jen z povolených souborů `files/` |

Odpověď **200** `{"errors": [...]}` = **všechny** chyby projektu (i ty,
které tam už byly; objekty jako výše). U `path: "scenarios/<jméno>.yaml"`
vrátí text scénáře navíc `tree` ve stejném tvaru jako
`GET …/scenarios/<s>`; nic se nezapisuje. Soubor mimo povolené → 404,
`text` není text → 422. Otisk se nekontroluje, nic se nezapisuje.

### Běhy pro GUI (od 0.6.0)

`GET /projects/<p>/runs` a `GET /projects/<p>/runs/<id>` mají navíc
(zdroj `events.jsonl`):

| Pole | Co to je |
|---|---|
| `scenario` | jméno scénáře z `run_started` |
| `started_at`, `finished_at` | `ts` z `run_started` a `run_finished`; `finished_at: null` u běžícího (nebo přerušeného) běhu |
| `current_step` | u běhu bez `run_finished`: `step` posledního `step_started` bez `step_finished`; jinak `null` |
| `steps_total` | počet kroků scénáře včetně vnořených ve větvích (bez kroků volaných scénářů) z `run_started.steps_total`; `null` u běhů před 0.6.0 |

`status` zůstává jako v `agencast runs list` (`succeeded`, `failed
(<třída> v <krok>)`, `běží nebo přerušen` — od 0.7.0 rozdělený na `běží`
a `přerušen` —, `dry-run`); dry-run a běhy bez `events.jsonl` mají nová
pole `null` (od 0.7.0 dry-run `scenario` a `started_at` z `run_id`).

```json
{"run_id": "20260926-120000-ukazka-ab12", "status": "běží", "state": "running", "cost_usd": null,
 "duration_s": null, "callback": "", "scenario": "ukazka", "started_at": "2026-09-26T12:00:00.004Z",
 "finished_at": null, "current_step": "vystup", "steps_total": 2, "fake": false, "current_nn": 2, "steps_done": 1}
```

### Spuštění z GUI (od 0.6.0)

`POST /projects/<p>/runs` přijímá navíc proti `POST /runs`:

- `callback_url` je **volitelná** — bez ní se callback neposílá;
  v záznamu je `run_started.callback_url: null` a žádné `callback_sent`
  ([run-record.md](run-record.md)). Když je, platí pravidla webhook.md.
- `"dry_run": true` → běh se nespustí, vznikne jen složka s `plan.md`
  a `inputs.json` (jako `agencast run --dry-run`); odpověď **200**
  `{"run_id": "…", "dry_run": true}`. Vstupy a scénář se kontrolují
  stejně (422). S `callback_url` nebo `request_key` → 422.

Smlouva `POST /runs` ([webhook.md](webhook.md)) se nemění: `callback_url`
povinná, pole `dry_run` neznámé (422).

### GUI a CORS (od 0.6.0)

- `serve` podává statické soubory ze složky `agencast/ui/` balíku
  (`framework/src/agencast/ui/`, sestavené GUI z `ui/` přes `npm run
  build`): `GET /` → `index.html`, `GET /assets/…` soubory. **Bez
  tokenu.** Cesta bez přípony, která není soubor, vrátí `index.html`
  (GUI používá hash routing); neznámý soubor s příponou → 404. Cesta
  mimo složku GUI → 404.
- Když GUI sestavené není, `GET /` vrátí **404** `{"error"}` s návodem
  (`ui/` → `npm install` a `npm run build`).
- `agencast serve --cors <origin>` (vývoj GUI z `vite dev`, např.
  `http://localhost:5173`): každá odpověď má
  `Access-Control-Allow-Origin: <origin>` a `OPTIONS` (preflight) vrátí
  204 s `Access-Control-Allow-Methods` a `Access-Control-Allow-Headers:
  Authorization, Content-Type`. Bez přepínače žádné CORS hlavičky
  a `OPTIONS` → 404 (zdroj: MDN, *Cross-Origin Resource Sharing (CORS)*,
  https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).

## Doplňky podle nálezů GUI (od 0.7.0)

Podle `docs/ui/nalezy-api.md` (co GUI při stavbě čtecí verze postrádalo).
Vše aditivní; smlouva `POST /runs`, `GET /runs/<id>` a callback beze
změny.

### Stav běhu: `state`

Běh drží po celou dobu svého procesu zámek `flock` na `<run>/run.lock`
([run-record.md](run-record.md)); zámek pustí i pád procesu. Seznam
i detail běhu mají strojové pole `state`:

| `state` | Kdy | `status` (text jako v `runs list`) |
|---|---|---|
| `queued` | požadavek ve frontě `serve`, složka běhu ještě není; od 0.8.0 i složka ze záznamu fronty, jejíž zámek nikdo nedrží a která nemá `run_finished` | `queued` |
| `running` | zámek `run.lock` drží živý proces | `běží` |
| `interrupted` | bez drženého zámku, bez `run_finished` nebo `run_finished` obnovený po restartu `serve` (od 0.10.0) | `přerušen` nebo `failed (internal v <krok>)` po obnově |
| `succeeded`, `failed` | `run_finished.status` | `succeeded`, `failed (<třída> v <krok>)` |
| `cancelled` | rezervováno — běh v1 tak nekončí | — |
| `dry_run` | jen `plan.md` (`--dry-run`, `dry_run: true`); od 0.8.0 navíc bez `run.lock` — ostrý běh ho má dřív než `plan.md` | `dry-run` |

Pozor: běh spuštěný frameworkem před 0.7.0, který ještě běží, je
`interrupted` (zámek nedrží).

### Seznam běhů

`GET /projects/<p>/runs?scenario=<s>&limit=<n>&before=<run_id>`:
`scenario` filtruje podle jména v `run_id`; `limit` = nejvýš `n` položek
(kladné celé číslo, jinak 422; bez něj všechny). Výsledky řadí jméno
složky sestupně. `before` je výlučný kurzor podle jména složky; musí mít
tvar `run_id`, jinak 422. S `limit` vrátí API `next_before` jen tehdy, když
existují starší výsledky; hodnota je `run_id` poslední položky stránky.
Limit se uplatní před čtením záznamů. Nová pole položky:

| Pole | Co to je |
|---|---|
| `state` | strojový stav (výše) |
| `fake` | `run_started.fake`; `null` bez `events.jsonl` |
| `queue_position` | jen u `queued`: pořadí jako v `GET /runs/<id>` (čekající + běžící přede mnou, včetně mě) |
| `scenario` | u `queued` z fronty, u dry-runu z `run_id` |
| `started_at` | u dry-runu čas z `run_id` (`RRRR-MM-DDTHH:MM:SS.000Z`) |
| `current_nn` | jen u `running`: `nn` právě běžícího kroku hlavního scénáře (u kroku volaného přes `call` číslo kroku `call`); `null` u záznamů bez `nn` |
| `steps_done` | jen u `running`: počet dokončených nebo přeskočených kroků — počítá se jako `steps_total` (bez kroků volaných scénářů) |

`last_run` (`GET /projects` u dostupného projektu, `GET /projects/<p>`
u scénáře) = první položka seznamu (`limit=1`) zúžená na
`{"run_id", "state", "started_at", "finished_at", "cost_usd"}`, `null` bez běhů —
může to být i čekající běh nebo dry-run.

### Podrobnosti kroků (od 0.7.0)

Položky `steps` v `GET …/runs/<id>` mají navíc:

| Pole | Co to je |
|---|---|
| `nn` | číslo kroku v jeho scénáři (u `call` vnořený krok má číslo ve volaném scénáři) — z `step_started`/`step_skipped.nn`, u běhů před 0.7.0 z cesty souboru |
| `dir` | složka kroku ve složce běhu (`steps/02-ton/steps/01-kontrola`); `null` u přeskočeného kroku a u kroku bez souborů v běhu před 0.7.0 |
| `error` | `{class, message}` poslední chyby kroku, po které se už neopakovalo; jinak `null`. Chyba vnořeného kroku (větev, `call`) je u něj, ne u nadřazeného |
| `continued` | `true` = selhal s `on_error: continue` |
| `default_used` | `true` = jako výstup se použil `default` (přeskočený krok nebo `continued`) |
| `calls` | volání modelu a Jev: `[{attempt, alias, model, input_tokens, output_tokens, cost_usd, finish_reason, structured_output, duration_s}]` (u Jev `alias`, `finish_reason` a `structured_output` `null`) |
| `turns`, `tool_calls` | jen u `task`: počet tahů a zavolaných nástrojů |
| `answers` | jen u `jev`: odpovědi posledního volání |

### `GET /projects/<p>/runs/<id>/steps/<cesta>` (od 0.7.0)

`<cesta>` = `step` (u `call` `navrh/copy` → `…/steps/navrh/copy`).
Odpověď = položka `steps` (výše) a navíc:

- `events` — všechny události kroku z `events.jsonl` (`step` = cesta)
  v pořadí zápisu, beze změny;
- `output` — obsah `output.json` kroku, `null` když není;
- `files` — soubory složky kroku (relativně ke složce běhu, pro
  `…/files/`), bez složek vnořených kroků `call`.

Neznámý krok nebo běh → 404.

### Strom kroků běhu (od 0.7.0)

Při startu běh uloží kopii spouštěného scénáře a všech scénářů volaných
přes `call` do `<run>/scenario/<jméno>.yaml`
([run-record.md](run-record.md)). `GET …/runs/<id>` vrací:

| Pole | Co to je |
|---|---|
| `tree` | strom kroků spouštěného scénáře, stejný tvar jako `steps` v `GET …/scenarios/<s>` |
| `callees` | `{jméno: strom}` volaných scénářů ze snímku; bez snímku `{}` |
| `tree_source` | `snapshot` = ze snímku; `current` = běh bez snímku (před 0.7.0, dry-run, běh, který nezačal) — strom ze současného souboru scénáře, který se od běhu mohl změnit (neexistující soubor → `[]`) |

### Chyby `config.yaml` a `mcp.yaml`

- `GET …/files/config.yaml` a `…/files/mcp.yaml` vrací v `errors` všechny
  chyby souboru (syntaxe, schéma, proměnné), ne jen syntaxi; `line` tam,
  kde ho zná loader (syntaxe YAML, duplicitní klíč).
- 422 z `GET /projects/<p>` nese vedle `details` (texty) i `errors`
  (objekty).
- `…/runs`, `…/runs/<id>…` a `spend` potřebují z `config.yaml` jen
  `runs_dir`; když ani to nejde přečíst, platí výchozí `./runs`.

### `GET /projects`

`{"projects": [...], "registry": "/home/…/.config/agencast/projects.yaml",
 "projects_root": "/home/…/workspace", "writable": true}`
— `registry` = cesta k souboru registru (i když neexistuje, i v režimu
jednoho projektu). `projects_root` = nastavená výchozí cesta, jinak
`~/workspace`. `writable` je `true` jen v režimu registru, když proces může
registr atomicky zapsat; v jednoprojektovém režimu je `false`. Nedostupný
projekt má `reason` (`chybí <root>/workflows/config.yaml`). Od 0.10.0
každá položka projektu navíc obsahuje `counts: {scenarios, agents}`
(počet souborů ve složkách projektu) a `spend_today_usd` z denní knihy
v UTC. Počty a útrata se načítají bez validace projektu.

## Dávka, náhled a doplňky podle nálezů GUI, část 2 (od 0.8.0)

Podle `docs/ui/nalezy-api.md` body 10–20. Vše aditivní; dosavadní
endpointy a jejich odpovědi se nemění.

### Dávka: `POST …/scenarios/<s>/batch`

```json
{"etag": "9f2c…", "ops": [
  {"op": "rename_step", "address": ["steps", 0], "new_id": "navrh"},
  {"op": "add_step", "after": ["steps", 0], "step": {"id": "novy", "ask": {}}},
  {"op": "update_step", "address": ["steps", 1], "fields": {"ask": {"agent": "copy", "prompt": "…"}}}]}
```

Všechny operace jdou po sobě nad **jednou** kopií dokumentu v paměti;
adresa každé operace platí pro stav **po** předchozích (po smazání
`["steps", 1]` je bývalý `["steps", 2]` na `["steps", 1]`). Pak jedna
validace výsledku (pravidlo „nesmí přidat novou chybu“ jako u jedné
operace) a jeden atomický zápis — nebo nic.

| Operace | Pole (kromě `op`) | Jako |
|---|---|---|
| `set_header` | `fields` | `PUT …/scenarios/<s>` |
| `add_step` | `step`, `after`? (bez = začátek `steps`) | `POST …/steps` |
| `update_step` | `address`, `fields` | `PATCH …/steps/<adresa>` |
| `replace_step` | `address`, `step` | `PUT …/steps/<adresa>` (celý krok, umí `null`) |
| `move_step` | `address`, `to` | `POST …/steps/<adresa>/move` |
| `delete_step` | `address` | `DELETE …/steps/<adresa>` |
| `rename_step` | `address`, `new_id`, `rename_refs`? (výchozí `true`) | nové `id`; s `rename_refs` přepíše `steps.<staré>.` → `steps.<nové>.` ve všech výrazech a šablonách kroků scénáře — celé pole `when`, `switch.value` a hodnoty `set`, jinde jen uvnitř `{{ }}`. Komentáře a text mimo `{{ }}` zůstanou |
| `add_branch` | `address` (krok `parallel`/`switch`), `name`, `steps`? (výchozí `[]`) | nová větev `parallel` nebo nový případ `switch` (`cases`); existující jméno → chyba operace. Prázdnou větev doplní další `add_step` s `after` = adresa větve |

| Kód | Tělo |
|---|---|
| 200 | `{"etag", "errors"}` jako u jedné operace |
| 409 | otisk nesedí (nic se nezapsalo) |
| 422 operace | `{"error", "op": <index od 0>, "errors": [...]}` — operaci nešlo provést (neznámá `op`, chybějící/neznámé pole, adresa, která v tu chvíli není, větev, která už je, …); hlášky začínají `ops[<index>] <op>: ` |
| 422 výsledek | `{"error", "errors": [...]}` bez `op` — operace prošly, ale výsledek přidal chybu projektu |
| 404 | neznámý projekt nebo scénář |

**Neúplný nový krok a prázdná větev** (nález 13): validace se nemění —
prázdný `ask` nebo větev bez kroků jsou dál chyba. Dávka je řeší tak,
že krok vloží a pole doplní (nebo větev přidá a naplní) v jedné dávce;
rozpracovaný stav bez zápisu ukáže `render`.

### Náhled: `POST …/scenarios/<s>/render`

Tělo `{"etag"?, "ops": [...]}` (operace jako u `batch`, prázdné `ops` =
soubor, jak je). **Nic se nezapisuje.** `etag` je nepovinný; když je
a nesedí → 409.

```json
{"text": "version: 1\n…", "tree": [{"nn": 1, "address": ["steps", 0], "id": "navrh", …}],
 "errors": [{"message": "…", "file": "scenarios/ig-post.yaml", "step": "novy", "field": "ask"}]}
```

- `text` = výsledný YAML se zachovanými komentáři (stejný, jaký by
  zapsal `batch`);
- `tree` = strom kroků výsledku, tvar `steps` z `GET …/scenarios/<s>`
  (adresy platí pro výsledek);
- `errors` = **všechny** chyby projektu s tímto textem (jako
  `POST …/validate`), i nové — rozpracovaný stav smí být neplatný, 200.

Chyba operace → 422 s `op` jako u `batch`. GUI tím validuje Form režim
průběžně a převádí Form ↔ YAML i s neuloženými změnami.

Od 0.10.0 přijímá `render` také `{"text": "…"}` místo `ops` a vrací
`{"tree": [...], "errors": [...]}` podle rozpracovaného scénáře; text se
nezapisuje. `text` a `ops` v jednom těle → 422. Stejný tvar stromu přidává
`POST …/validate` pro text scénáře.

### Celý krok: `PUT …/scenarios/<s>/steps/<adresa>`

Tělo `{"etag", "step": {…}}` — krok se nahradí celý (komentáře uvnitř
kroku zmizí), `null` se zapíše jako `null` (`default: { file: null }`).
Odpovědi jako u ostatních operací.

### Lehké zjištění změny souboru

- `HEAD /projects/<p>/files/<cesta>` → 200 bez těla s hlavičkou
  `ETag: "<otisk>"` (otisk v uvozovkách podle RFC 9110 §8.8.3, hodnota
  = `etag` z `GET …/files/<cesta>`); neznámý soubor nebo cesta mimo
  povolené → 404, bez tokenu 401. S `--cors` odpovědi nesou
  `Access-Control-Expose-Headers: ETag` (jinak ji prohlížeč skriptu
  nepustí) a preflight povoluje `HEAD` (zdroje: RFC 9110 §8.8.3,
  https://www.rfc-editor.org/rfc/rfc9110#section-8.8.3; MDN
  *Access-Control-Expose-Headers*,
  https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Expose-Headers;
  ověřeno 2026-09-26).
- `GET /projects/<p>/files/<cesta>?etag_only=1` → `{"etag"}`.

Soubor se nečte loaderem ani nevaliduje — jen sha256 bajtů. Push změn
(SSE) není.

### `errors` v `GET …/files/<cesta>`

U scénáře, agenta a skillu = chyby `validate` toho souboru, **stejné**
jako `errors` u položky v `GET /projects/<p>` (dřív jen chyby
loaderu). Když soubor nejde přečíst, zůstávají chyby loaderu (s
`line`). S neplatným `config.yaml` (projekt nejde validovat) jsou
v `errors` chyby `config.yaml`. `config.yaml` a `mcp.yaml` beze změny
(od 0.7.0 všechny chyby souboru).

### Stav čerstvého běhu

Od `202` na `POST /projects/<p>/runs` do konce běhu vrací
`GET …/runs/<id>` i seznam jen `queued` → `running` → výsledek:
záznam ve frontě `serve` (`<runs>/_queue/<run_id>.json`, zmizí až po
callbacku) přebije `interrupted` i `dry_run` na `queued` (s
`queue_position`), dokud běh nedrží zámek (`running`) nebo neskončí.
`dry_run` = složka s `plan.md` bez `events.jsonl` **a bez `run.lock`**
(dry-run zámek nemá, ostrý běh ho vytvoří před `plan.md` —
[run-record.md](run-record.md)); formát záznamu se nemění. Ostrý běh,
který spadl mezi `plan.md` a první událostí, je `interrupted`. Záznam
fronty zůstává i po pádu `serve` — do restartu (kdy se běh nahlásí jako
přerušený) je takový běh `queued`.

### `POST …/scenarios` a `POST …/agents`

Volitelné `description` (text, zapíše se v uvozovkách), u agenta
`model` = alias z `config.yaml` (jiný → 422, výchozí první alias).
Bez nich šablona jako dřív (`TODO`).

### Použití aliasů: `links.scenario_model` a `models_used`

`links.scenario_model` = seřazené dvojice [scénář, alias] z `image.model`
kroků (i ve větvích). `models_used` = `{alias: [soubory, které ho
používají]}` — `agents/<a>.md` (pole `model`) a `scenarios/<s>.yaml`
(krok `image`), cesty jako v `files/` a v `errors[].file`. Klíče = všechny
aliasy z `config.yaml` (`[]` = nepoužitý, jde smazat) a navíc aliasy, na
které se odkazuje, ale v configu nejsou (to je zároveň chyba `validate`).

```json
"models_used": {"chytry": ["agents/copywriter.md"], "gemini-image": ["scenarios/ig-post.yaml"], "rychly": []}
```

### `PUT …/config` (od 0.8.0)

Povolená pole: `models`, `limits`, `storage`, `webhook`, `callback`,
`runs_dir`, `openrouter.api_key_env` a `openrouter.jev_model`. Zůstává
zakázané (422):

- `version` — verze formátu, mění se jen s novým formátem (DESIGN §5.6);
- `openrouter.base_url` — kam odchází API klíč; přesměrování z GUI by
  klíč poslalo jinam (config.md ho povoluje jen pro konformační testy).
  Mění se v YAML režimu (`PUT …/files/config.yaml`), vědomě.

`runs_dir` platí pro nové běhy a čtení běhů hned; běžící `serve` má ale
frontu `_queue/` ve složce ze startu projektu — po změně `runs_dir`
restartuj `serve`, jinak čekající běhy ze staré složky GUI neuvidí.

## Doplňky podle nálezů GUI (od 0.10.0)

- Obnovený rozběhnutý záznam zachová původní `run_started`; doplní
  `run_finished.status: failed` s chybou `internal`, posledním začatým
  krokem a zprávou `běh přerušen restartem serveru`. API `state` zůstává
  `interrupted`; krok bez `step_finished` má `status: interrupted`.
- Chyby schématu `config.yaml` nesou `line` podle klíče YAML v odpovědi
  `GET …/files/config.yaml` i `GET /projects/<p>`.
- `GET /projects` vrací v každé položce `counts: {scenarios, agents}` a
  `spend_today_usd`; počty jsou výpisy souborů a útrata denní kniha,
  bez plné validace.
- `GET …/runs` přijímá `before=<run_id>` a při další stránce vrací
  `next_before`; `last_run` přidává `started_at`.
- Chyby dávkové operace nesou `step` (adresa před operací, nebo id
  vloženého kroku u `add_step`) a `field`, je-li známé.
- U `POST /projects/<p>/runs` se `callback.secret_env` vyžaduje jen s
  `callback_url`. `webhook.token_env` se čte jen v jednoprojektovém
  režimu; režim registru ověřuje token serveru.

Smlouva `POST /runs`, callback a formáty v1 se nemění.
