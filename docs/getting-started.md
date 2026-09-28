# Začínáme s AgenCast

Ověřeno na Linuxu a WSL s Pythonem 3.12; použijte `uv`.
Pro sestavení GUI a ukázkové MCP přes `npx` potřebujete Node.js
`^20.19.0 || >=22.12.0` (podle `ui/package.json`, ověřeno s Node 24).
Nativní Windows není podporován (`fcntl` v `projects.py` a `task.py`);
macOS není ověřen.

Balíček obsahuje CLI, API, dokumentaci, skilly i příklady.
Instalace přímo z GitHubu (bez GUI):

```bash
uv tool install "git+https://github.com/rychidesign/agencast#subdirectory=framework"
```

Pro GUI naklonujte repozitář a sestavte frontend pomocí Node.js:

```bash
git clone https://github.com/rychidesign/agencast
cd agencast
(cd ui && npm install && npm run build)
uv tool install --editable framework
```

Vlastní projekt vytvoříte příkazem `agencast new project ~/muj-projekt`.
Dostanete kostru s agentem `pisatel` a scénářem `ukazka`.
Pro hotový příklad včetně deterministických odpovědí použijte:

```bash
agencast new project ~/agencast-demo --example showcase
cd ~/agencast-demo
agencast validate ig-post --offline
agencast run ig-post -i tema="nová káva" --dry-run --fake fake/ig-post.yaml
agencast run ig-post -i tema="nová káva" --fake fake/ig-post.yaml
```

`--dry-run` vytvoří plán; přidané `--fake` vynechá i síťovou kontrolu modelů.
Bez fixtury lze použít samotné `--fake`, ale vymyšlené odpovědi nemusí projít
podmínkami scénáře. Kostru vyzkoušíte přes `agencast run ukazka --fake`.

`--fake` nahrazuje jen volání modelů: bez ceny za model a bez klíče OpenRouteru.
Krok `task` stále spouští skutečné MCP servery z `mcp.yaml`; ukázkový
`filesystem` používá `npx`, potřebuje Node.js a při prvním spuštění stahuje balíček.
`--callback-url` odesílá skutečný callback (a potřebuje jeho podpisové tajemství).
Zaručeně offline jsou jen scénáře bez `task` (i ve volaných scénářích)
a bez `--callback-url`, například `ig-post`.

Teprve pro ostrý běh zkopírujte `.env.example` do `.env` a doplňte
`OPENROUTER_API_KEY`. Klíče nikdy necommitujte ani nevypisujte.
Po kontrole plánu a výsledku falešného běhu spusťte:

```bash
agencast run ig-post -i tema="nová káva"
```

Záznam je v `runs/<run_id>/summary.md`, strojový výsledek v `callback.json`,
report v `report.html`; exporty jsou v `outputs/`. CLI vypíše přesné cesty.
`agencast runs list` a `agencast runs show <run_id>` zobrazí historii.

Skilly pro Claude Code, Codex, OpenCode a OMP nainstalujete takto:

```bash
agencast skills list
agencast skills install                 # nástroje s existující základní složkou
agencast skills install --to all        # všechny čtyři
```

Výchozí jsou symlinky; `--copy` vytvoří kopie, `--prefix DIR` změní domovskou
složku a `--force` dovolí přepsat existující kopie. `agencast skills path`
vypíše zdrojovou složku. Po aktualizaci balíčku obnovte instalované kopie.

```bash
agencast docs
agencast docs show spec/scenario.md
agencast new project ~/agencast-tutorial --example tutorial
agencast docs show tutorials/01-prvni-agent-a-scenar.md
```

[Tutoriály](tutorials/README.md) mají sedm dílů; formáty popisuje
[specifikace scénáře](spec/scenario.md), [agenta](spec/agent.md) a
[konfigurace](spec/config.md). Zdrojový kód: [GitHub](https://github.com/rychidesign/agencast).

`agencast serve` spustí API a případné sestavené GUI. Nové projekty se zapisují
do registru pro GUI automaticky. Server a GUI vystavujte jen v privátní síti;
pro režim registru nastavte `AGENCAST_TOKEN`, pro jeden projekt `WEBHOOK_TOKEN`
podle `.env.example`. Podrobnosti: `agencast docs show spec/webhook.md`.
