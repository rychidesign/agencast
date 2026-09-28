# AgenCast

AgenCast is an open-source framework for defining and running LLM-agent workflows. Scenarios use YAML, agents use Markdown, and each run leaves a readable record.

AgenCast je framework pro vývojáře a týmy, které chtějí skládat opakovatelné úlohy s LLM agenty ze souborů, které lze číst, verzovat a kontrolovat. Scénář popisuje průběh práce, agent jeho roli a nástroje.

## Co umí

- Scénáře v YAML, agenti a skilly v Markdownu.
- Deset typů kroků: `ask`, `task`, `jev`, `image`, `parallel`, `switch`, `call`, `set`, `fail` a `output`.
- `task` volá povolené nástroje MCP; `parallel`, `switch` a `call` skládají větve a scénáře.
- Falešný poskytovatel spustí scénář bez sítě a bez ceny.
- Každý běh ukládá `summary.md`, `callback.json` a samostatný `report.html`.
- `agencast serve` přijímá webhooky a nabízí GUI pro registrované projekty.
- Skilly pro kódovací agenty pomáhají scénáře spouštět i vytvářet.

## Instalace

Vyžaduje Python 3.12. S `uv` nainstalujte nástroj z klonu repozitáře:

```bash
uv tool install --editable framework
```

Nebo přímo z GitHubu:

```bash
uv tool install "git+https://github.com/rychidesign/agencast#subdirectory=framework"
```

## Rychlý start

Vytvořte projekt, doplňte klíč OpenRouteru do `.env` a projděte nejprve kontroly bez ostrého volání:

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

## Struktura repozitáře

| Cesta | Obsah |
|---|---|
| `framework/` | Python balík a příkaz `agencast` |
| `ui/` | Zdrojový kód GUI |
| `workflows/` | Příklady agentů, scénářů, skillů a konfigurace |
| `docs/` | Specifikace, návrh a tutoriály |
| `spikes/` | Časově omezené experimenty s nezpracovanými výsledky |
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

Aktuální verze frameworku je **0.16.3** (řada 0.16.x); historii změn najdete
v [changelogu](framework/CHANGELOG.md). Projekt je dostupný pod licencí
[WTFPL verze 2](LICENSE).
