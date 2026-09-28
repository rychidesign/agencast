# AgenCast

[![CI](https://github.com/rychidesign/agencast/actions/workflows/ci.yml/badge.svg)](https://github.com/rychidesign/agencast/actions/workflows/ci.yml)

AgenCast is an open-source framework for defining and running LLM-agent workflows. Scenarios use YAML, agents use Markdown, and each run leaves a readable record.

AgenCast je framework pro vývojáře a týmy, které chtějí skládat opakovatelné úlohy s LLM agenty ze souborů, které lze číst, verzovat a kontrolovat. Scénář popisuje průběh práce, agent jeho roli a nástroje.

## English quick start

AgenCast runs LLM-agent workflows defined in YAML and Markdown.
Tested on Linux/WSL with Python 3.12 and `uv`; native Windows is unsupported, macOS untested.
GUI builds and example MCP servers need Node `^20.19.0 || >=22.12.0` (tested: 24).
```bash
uv tool install "git+https://github.com/rychidesign/agencast#subdirectory=framework"
agencast new project ~/demo --example showcase
cd ~/demo
agencast run ig-post -i tema="coffee" --fake fake/ig-post.yaml
```
This example needs no model key or payment; `--fake` still uses real MCP servers and callbacks.
Offline runs require no `task` steps (including called scenarios) and no `--callback-url`, as above.
Docs and GUI are in Czech; a multilingual GUI is planned. Deploy the GUI only on a private network.
The command above installs the CLI/API; build the GUI from a clone as described below.

## Co umí

- Scénáře v YAML, agenti a skilly v Markdownu.
- Deset typů kroků: `ask`, `task`, `jev`, `image`, `parallel`, `switch`, `call`, `set`, `fail` a `output`.
- `task` volá povolené nástroje MCP; `parallel`, `switch` a `call` skládají větve a scénáře.
- Falešný poskytovatel nahrazuje volání modelů bez ceny a bez klíče; MCP a callbacky zůstávají skutečné.
- Každý běh ukládá `summary.md`, `callback.json` a samostatný `report.html`.
- `agencast serve` přijímá webhooky a nabízí GUI pro registrované projekty.
- Skilly pro kódovací agenty pomáhají scénáře spouštět i vytvářet.

![Editor scénáře ig-post v GUI AgenCast](docs/ui/screenshots/editor.png)

## Instalace

Ověřeno na Linuxu a WSL s Pythonem 3.12; použijte `uv`.
Pro sestavení GUI a ukázkové MCP přes `npx` potřebujete Node.js
`^20.19.0 || >=22.12.0` (podle `ui/package.json`, ověřeno s Node 24).
Nativní Windows není podporován (`fcntl` v `projects.py` a `task.py`);
macOS není ověřen.

Z klonu repozitáře včetně GUI:

```bash
git clone https://github.com/rychidesign/agencast
cd agencast
(cd ui && npm install && npm run build)   # sestaví GUI do balíčku
uv tool install --editable framework
```

Přímo z GitHubu bez klonu se nainstaluje jen příkaz `agencast` a server
s API, bez GUI:

```bash
uv tool install "git+https://github.com/rychidesign/agencast#subdirectory=framework"
```

Příklady, tutoriály, dokumentace a skilly jsou přibalené i bez klonu.

## Rychlý start

Celý postup pro balíček i klon: [Začínáme s AgenCast](docs/getting-started.md).

`--fake` nahrazuje jen volání modelů: bez ceny za model a bez klíče OpenRouteru.
Krok `task` stále spouští skutečné MCP servery z `mcp.yaml`; ukázkový
`filesystem` používá `npx`, potřebuje Node.js a při prvním spuštění stahuje balíček.
`--callback-url` odesílá skutečný callback (a potřebuje jeho podpisové tajemství).
Zaručeně offline jsou jen scénáře bez `task` (i ve volaných scénářích)
a bez `--callback-url`, například `ig-post`.

Příklad `ig-post` z klonu spustíte offline (nemá `task`, nepřidávejte `--callback-url`):

```bash
agencast --project examples/showcase run ig-post -i tema="nová káva" --fake examples/showcase/fake/ig-post.yaml
```

Další ukázky najdete v [examples/](examples/). Pro vlastní práci vytvořte projekt, doplňte klíč OpenRouteru do `.env` a projděte nejprve kontroly bez ostrého volání:

```bash
agencast new project ~/muj-projekt
cd ~/muj-projekt
cp .env.example .env
# Do .env nastavte OPENROUTER_API_KEY.
agencast validate ukazka
agencast run ukazka --dry-run
agencast run ukazka --fake
agencast run ukazka
```

## Skilly pro kódovací agenty

`agencast skills install` nainstaluje skilly pro nalezené nástroje Claude Code,
Codex, OpenCode a OMP; `--to all` vybere všechny. Více: [skills/](skills/).

## Struktura repozitáře

| Cesta | Obsah |
|---|---|
| `framework/` | Python balík a příkaz `agencast` |
| `ui/` | Zdrojový kód GUI |
| `examples/` | Samostatné projekty showcase a tutorial |
| `docs/` | Specifikace, návrh a tutoriály |
| `skills/` | Skilly pro kódovací agenty |

## Dokumentace

- [Specifikace formátů](docs/spec/)
- [Tutoriály](docs/tutorials/)
- [Návrh frameworku](docs/DESIGN.md)
- [README frameworku](framework/README.md)
- [README GUI](ui/README.md)
- [Skilly pro kódovací agenty](skills/)

## GUI a server

`agencast serve` umí běžet v režimu registru projektů. Na hostu nastavte
`AGENCAST_TOKEN`, `AGENCAST_HOST` a `AGENCAST_PORT` v
`~/.config/agencast/serve.env` (systemd `EnvironmentFile`). GUI vystavujte
jen v privátní síti. Adresu zjistíte přečtením pouze hostu a portu:

```bash
grep -E '^AGENCAST_(HOST|PORT)=' ~/.config/agencast/serve.env
```

Hodnotu tokenu nikdy nevypisujte.

## Stav a licence

Aktuální verze frameworku je **0.17.0** (řada 0.17.x); historii změn najdete
v [changelogu](framework/CHANGELOG.md). Projekt je dostupný pod licencí
[WTFPL verze 2](LICENSE).

Plánováno: vícejazyčné GUI.

Software je poskytován bez jakékoli záruky. / This program comes without any warranty, to the extent permitted by applicable law.

[Přispívání / Contributing](CONTRIBUTING.md) · [Bezpečnost / Security](SECURITY.md)
