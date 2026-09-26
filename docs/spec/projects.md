# Projekty — registr a `agencast new` (od frameworku 0.4.0)

Projekt = složka s `workflows/` (kořen projektu). Framework projekty na
disku **neskenuje**; které zná, drží registr. Formáty v1 se tím nemění.

## Registr

`~/.config/agencast/projects.yaml` (složku přepíše proměnná
`AGENCAST_CONFIG_DIR`, hlavně pro testy):

```yaml
projects_root: ~/workspace   # výchozí místo pro nové projekty z GUI
projects:
  - name: thtd              # jméno projektu v registru a v URL /projects/<name>
    root: ~/thtd  # absolutní cesta ke kořeni (složka s workflows/)
```

| Pole | Co dělá |
|---|---|
| `projects_root` | Výchozí kořen pro `POST /projects/new`; výchozí `~/workspace`. Cesty se rozbalí a normalizují. |
| `name` | Unikátní, tvar jako jména scénářů (malá písmena, číslice, pomlčka, začíná písmenem). Výchozí = jméno složky převedené na tento tvar (`Muj Projekt` → `muj-projekt`). |
| `root` | Absolutní cesta ke kořeni projektu; jeden kořen je v registru nejvýš jednou. |

- V registru nejsou klíče ani tajemství, jen jména a cesty.
- Projekt, kterému chybí `workflows/config.yaml` (smazaný, odpojený
  disk), v registru **zůstává** s příznakem `available: false`
  (`agencast projects list`, `GET /projects`).
- Zápis je atomický (dočasný soubor + přejmenování); `serve` čte
  registr při každém požadavku.
- GUI může projekt založit přes `POST /projects/new` (viz [api.md](api.md));
  `root` bez hodnoty míří do `<projects_root>/<name>`. Cesta `~` se rozbalí,
  relativní cesta se vztahuje k `projects_root` a nesmí obsahovat `..` ani
  přes symlink utéct mimo tento kořen. Absolutní cesty jsou povolené i mimo
  domovský adresář serveru; GUI má stejná práva k souborům jako uživatel,
  pod kterým běží `agencast serve`.
- Nový projekt nepřepisuje existující `workflows/`; složku s projektem lze
  místo toho zaregistrovat přes `POST /projects`, pokud obsahuje
  `workflows/config.yaml`. Odregistrování přes `DELETE /projects/<name>`
  nemaže žádné soubory.

### Kdy se registr mění

| Příkaz | Co udělá |
|---|---|
| `agencast new project <cesta> [--name N]` | Založí projekt a hned ho zapíše. |
| `agencast projects add <cesta> [--name N]` | Zapíše existující projekt. |
| `agencast projects rm <jméno>` | Odebere položku; soubory projektu zůstávají. |
| úspěšný `agencast validate` / `run` | Projekt, který v registru není, přidá pod výchozím jménem a jednou vypíše na stderr `projekt <name> přidán do registru (<cesta k projects.yaml>)`. |

Kolize jména → chyba `config` s nápovědou `agencast projects add <cesta>
--name <jméno>`. U `validate`/`run` se chyba registru jen vypíše na
stderr a příkaz doběhne s vlastním výsledkem.

## `agencast new`

Šablony jsou součástí frameworku (ne kopie `workflows/`). Nic se
nepřepisuje: existující soubor nebo `workflows/` = chyba `config`.

- **`new project <cesta>`** vytvoří
  - `workflows/config.yaml` — OpenRouter (`OPENROUTER_API_KEY`), aliasy
    `chytry`, `rychly`, `gemini-image`, `runs_dir: ./runs`,
    `storage.type: local` (`./outputs`), limity běhu, `webhook` a `callback`,
  - `workflows/agents/pisatel.md` a `workflows/scenarios/ukazka.yaml`
    (vstup `tema` s výchozí hodnotou → `ask` → `output`); projdou
    `validate --offline` i `run ukazka --fake`,
  - `.env.example` (`OPENROUTER_API_KEY=`, pro `serve` `WEBHOOK_TOKEN=`,
    `CALLBACK_SECRET=`) a `.gitignore` (`.env`, `runs/`, `outputs/`),
    pokud tam ještě není.
- **`new agent <jméno>`** — `workflows/agents/<jméno>.md`: `model` = první
  alias z `config.yaml` projektu (ostatní v komentáři), `budget_usd: 0.02`,
  tělo a `description` k doplnění.
- **`new scenario <jméno>`** — `workflows/scenarios/<jméno>.yaml`: vstup →
  `ask` s prvním agentem projektu (podle abecedy) → `output`. Projekt bez
  agenta = chyba `config`.

Projekt se hledá jako u ostatních příkazů (aktuální složka nahoru nebo
`--project`). Veřejné API: `agencast.api.new_project(root, name=None)`,
`new_agent(project_root, name)`, `new_scenario(project_root, name)` vrací
seznam vytvořených cest; `projects()`, `add_project(path, name=None)`,
`remove_project(name)`, `projects_root()`.
