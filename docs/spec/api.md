# API `agencast serve` — rodina `/projects/...` (čtení od frameworku 0.4.0, editace od 0.5.0, doplňky pro GUI od 0.6.0)

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
  z `config.yaml` projektu, hodnoty z prostředí serveru.
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
| `GET /projects` | `{"projects": [{"name", "root", "available"}]}` |
| `GET /projects/<p>` | popis projektu (níže) |
| `GET /projects/<p>/scenarios/<s>` | scénář se stromem kroků (níže) |
| `GET /projects/<p>/files/<cesta>` | soubor z `workflows/` jako text s otiskem (oddíl [Editace](#editace-od-050)) |
| `GET /projects/<p>/runs` | `{"runs": [...]}` — položky jako `agencast runs list`: čekající `{"run_id", "status": "queued"}`, pak `{"run_id", "status", "cost_usd", "duration_s", "callback", "scenario", "started_at", "finished_at", "current_step", "steps_total"}` (pole od `scenario` dál od 0.6.0, [Běhy pro GUI](#běhy-pro-gui-od-060)), nejnovější první |
| `GET /projects/<p>/runs/<id>` | stav běhu + kroky + soubory (níže); čekající ve frontě `{"run_id", "status": "queued"}` |
| `GET /projects/<p>/runs/<id>/files/<cesta>` | obsah souboru ze složky běhu (`summary.md`, `report.html`, `events.jsonl`, `steps/…`), `Content-Type` podle přípony |
| `GET /projects/<p>/spend?day=RRRR-MM-DD` | denní kniha útraty ostrých běhů: `{"day", "total_usd", "runs": [{"run_id", "cost_usd", "finished_at"}]}`; bez `day` dnešek (UTC); jiný tvar `day` → 422 |
| `POST /projects/<p>/runs` | jako `POST /runs` ([webhook.md](webhook.md)) v projektu `<p>` — stejné tělo, odpovědi 202/200/401/422 i callback; od 0.6.0 `callback_url` volitelná a `dry_run` ([Spuštění z GUI](#spuštění-z-gui-od-060)) |
| `POST /projects/<p>/validate` | validace bez zápisu (od 0.6.0, [níže](#post-projectspvalidate-od-060)) |

- **404** s JSON chybou: neznámý projekt, nedostupný projekt
  (`available: false`), neznámý scénář, běh, soubor nebo adresa. Cesta
  souboru mimo složku běhu (`..`, absolutní cesta, symlink ven) = 404.
- **422**: `config.yaml` projektu neprošel kontrolou (`details` = chyby);
  u `POST` i chybějící proměnná prostředí projektu.
- `spend` čte jen knihu ostrých běhů (`_ledger/`); falešné běhy
  (`--fake`) mají vlastní `_ledger-fake/` a v `spend` nejsou.

### `GET /projects/<p>`

```json
{
  "name": "thtd", "root": "~/thtd",
  "models": {"chytry": "anthropic/claude-haiku-4.5"},
  "limits": {"run_budget_usd": 1.0, "run_timeout": "1h", "max_call_depth": 3},
  "scenarios": [{"name": "ig-post", "etag": "9f2c…", "description": "…", "inputs": {…}, "outputs": {…},
                 "callable": false, "steps_count": 8, "errors": []}],
  "agents": [{"name": "copywriter", "etag": "…", "description": "…", "model": "chytry",
              "model_id": "anthropic/claude-haiku-4.5", "skills": ["thtd-hlas"], "mcp": [], "tools": {},
              "errors": []}],
  "skills": [{"name": "thtd-hlas", "etag": "…", "description": "…", "errors": []}],
  "mcp_servers": [{"name": "filesystem", "type": "stdio", "agents": ["knihovnik"],
                   "tools": ["read_text_file"], "scenarios": null}],
  "links": {"scenario_agent": [["ig-post", "copywriter"]], "scenario_scenario": [["ukazka-call", "kontrola-tonu"]],
            "agent_skill": [["copywriter", "thtd-hlas"]], "agent_server": [["knihovnik", "filesystem"]]},
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
  krok `call` → scénář, agent → skill, agent → MCP server.
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
  `step` je cesta jako v `events.jsonl` (u `call` `navrh/copy`).
- `files` — relativní cesty všech souborů ve složce běhu (pro `files/`).

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
| `POST /projects/<p>/scenarios` | `{"name"}` | nový scénář ze šablony (`agencast new scenario`); 200 `{"name", "etag"}`, existující → 422 |
| `POST /projects/<p>/agents` | `{"name"}` | nový agent ze šablony (`agencast new agent`); 200 `{"name", "etag"}` |
| `PUT /projects/<p>/scenarios/<s>` | `{"fields": {…}}` | hlavička: jen `description`, `inputs`, `outputs`, `callable` (jiné pole → 422) |
| `DELETE /projects/<p>/scenarios/<s>` | — | smaže scénář; když ho jiný volá přes `call` → 422 |
| `POST /projects/<p>/scenarios/<s>/steps` | `{"after": adresa, "step": {…}}` | vloží krok (celý, jako v souboru) za krok `after`; adresa seznamu = na jeho začátek; bez `after` na začátek `steps` |
| `PATCH /projects/<p>/scenarios/<s>/steps/<adresa>` | `{"fields": {…}}` | pole kroku (i `id`, `when`, větve `parallel` a případy `switch`) |
| `POST /projects/<p>/scenarios/<s>/steps/<adresa>/move` | `{"to": adresa}` | přesune krok za krok `to`, nebo na začátek seznamu `to`; do vlastní větve → 422 |
| `DELETE /projects/<p>/scenarios/<s>/steps/<adresa>` | — | smaže krok |
| `PUT /projects/<p>/agents/<a>` | `{"frontmatter": {…}, "body": "…"}` | frontmatter jako merge patch, tělo celé; chybějící = beze změny; nový agent potřebuje obojí |
| `DELETE /projects/<p>/agents/<a>` | — | smaže agenta; když ho používá scénář (`ask`/`task`) → 422 |
| `PUT /projects/<p>/skills/<n>` | `{"text"}` | celý `SKILL.md`; nový skill založí |
| `DELETE /projects/<p>/skills/<n>` | — | smaže `SKILL.md` (a složku, je-li prázdná); když ho agent používá → 422 |
| `PUT /projects/<p>/config` | `{"fields": {…}}` | `config.yaml`: jen `models`, `limits`, `storage`, `webhook`, `callback` a `openrouter.api_key_env` |
| `GET /projects/<p>/files/<cesta>` | — | `{"path", "etag", "text", "errors"}` a rozparsovaný obsah: u `.yaml` `data`, u `.md` `frontmatter` a `body` (GUI neparsuje samo) |
| `PUT /projects/<p>/files/<cesta>` | `{"text"}` | celý text souboru (záložní textový editor); nový soubor s `etag: null` |

- Po operaci nad kroky `output` zůstává posledním krokem hlavního
  seznamu — jinak 422 (`config`). Když z větve `parallel` nebo případu
  `switch` odejde poslední krok, větev/případ zmizí (prázdný seznam
  schéma nepovoluje).
- Merge patch neumí zapsat hodnotu `null` (smaže klíč); krok s `null`
  (např. `default: { file: null }`) jde vložit celý přes `POST …/steps`,
  nebo upravit jako text přes `files/`.
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
  `move_step`, `delete_step`, `delete_scenario`, `set_agent`,
  `delete_agent`, `set_skill`, `delete_skill`, `set_config`, `read_file`,
  `write_file`, od 0.6.0 `validate_text`; výjimky `Conflict` (`.etag`),
  `NotFound`, `ConfigErrors`. Python API vrací chyby jako texty (jako
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
| `line` | číslo řádku — jen tam, kde ho hlásí loader (syntaxe YAML, duplicitní klíč) |

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
které tam už byly; objekty jako výše). Soubor mimo povolené → 404,
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
(<třída> v <krok>)`, `běží nebo přerušen`, `dry-run`); dry-run a běhy
bez `events.jsonl` mají nová pole `null`.

```json
{"run_id": "20260926-120000-ukazka-ab12", "status": "běží nebo přerušen", "cost_usd": null, "duration_s": null,
 "callback": "", "scenario": "ukazka", "started_at": "2026-09-26T12:00:00.004Z", "finished_at": null,
 "current_step": "vystup", "steps_total": 2}
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
