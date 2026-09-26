# multiagent-workflows

Framework **AgenCast** (balík i příkaz `agencast`, do 0.2.5 `maw`) pro
workflowy s LLM agenty psané v čitelných souborech (scénáře v YAML, agenti
v Markdownu), s modely a Jev přes OpenRouter, běžící na vlastním serveru
nebo na Modal.com a spouštěný webhookem.

Stav: spec v1 schválená ([`docs/spec/`](docs/spec/)), návrh
[`docs/DESIGN.md`](docs/DESIGN.md); jádro frameworku 0.3.0 v
[`framework/`](framework/README.md) (všech 10 typů kroků v1, MCP,
webhook `agencast serve`), tutoriály v [`docs/tutorials/`](docs/tutorials/).

```
framework/    jádro (CLI, engine, adaptéry, webhook)
workflows/    vrstva uživatele: agents/, scenarios/, skills/, config
docs/         návrh, specifikace formátů, changelog
spikes/       časově omezené experimenty s REPORT.md
skills/       skilly pro kódovací agenty (agencast-run, agencast-create)
```

Skilly [`skills/`](skills/README.md) naučí Claude Code, Codex a OMP
AgenCast spouštět a psát; na hostu je nainstaluje `skills/install.sh`.
