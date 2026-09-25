# multiagent-workflows

Framework pro workflowy s LLM agenty psané v čitelných souborech
(scénáře v YAML, agenti v Markdownu), s modely a Jev přes OpenRouter,
běžící na vlastním serveru nebo na Modal.com a spouštěný webhookem.

Stav: spec v1 schválená ([`docs/spec/`](docs/spec/)), návrh
[`docs/DESIGN.md`](docs/DESIGN.md); jádro frameworku 0.1.0 v
[`framework/`](framework/README.md) (Fáze 2: `ask`, `jev`, `image`,
`parallel`, `switch`, `set`, `fail`, `output`).

```
framework/    jádro (CLI, engine, adaptéry, webhook)
workflows/    vrstva uživatele: agents/, scenarios/, skills/, config
docs/         návrh, specifikace formátů, changelog
spikes/       časově omezené experimenty s REPORT.md
```
