# multiagent-workflows

Framework pro workflowy s LLM agenty psané v čitelných souborech
(scénáře v YAML, agenti v Markdownu), s modely a Jev přes OpenRouter,
běžící na vlastním serveru nebo na Modal.com a spouštěný webhookem.

Stav: **návrh** — viz [`docs/DESIGN.md`](docs/DESIGN.md). Kód zatím žádný;
nejdřív běží spiky (`spikes/`), které rozhodnou engine a jazyk.

```
framework/    jádro (CLI, engine, adaptéry, webhook)
workflows/    vrstva uživatele: agents/, scenarios/, skills/, config
docs/         návrh, specifikace formátů, changelog
spikes/       časově omezené experimenty s REPORT.md
```
