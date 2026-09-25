# Changelog formátů

Každá změna formátu agenta, scénáře nebo konfigurace se zapisuje sem
(DESIGN §5.6). Formát se mění jen zvýšením `version`; framework umí číst
všechny vydané verze (R7).

## version 1 — 2026-09-25 (návrh ke schválení)

První specifikace. Obsahuje:

- [agent.md](agent.md) — agent jako Markdown s frontmatter (D1a).
- [scenario.md](scenario.md) — scénář, 10 typů kroků v1 (D1d), šablony
  a výrazy (D1c, §5.4), `call` (§5.3), chyby (§5.1).
- [config.md](config.md) — `config.yaml`, `mcp.yaml`, `commands.yaml`
  (jen struktura; krok `run` není ve v1).
- [run-record.md](run-record.md) — složka běhu, `events.jsonl`,
  `summary.md`, callback.
- [schema/](schema/) — JSON Schema draft 2020-12: `agent`, `scenario`,
  `config`, `mcp`. Ověřeno `uvx check-jsonschema` na ukázkách ve
  `workflows/` a na úryvcích ze `scenario.md`.

Odchylky od ilustrativní syntaxe v DESIGN (§3 D1a/D1d, §6) — ke
schválení v [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md):

- zadání pro model v `ask` se jmenuje `prompt` (v §6 `task`, což koliduje
  s typem kroku `task`),
- `schema` se píše uvnitř `ask`/`task` (jako v §6), ne na úrovni kroku,
- rozpočet kroku se píše `budget_usd` (jako `limits.budget_usd` u agenta),
- scénář deklaruje `outputs` v hlavičce; krok `output` je poslední,
- nové třídy chyb `fail` a `internal`,
- ve výrazech `true` / `false` / `null`, ne pythonovské `True` / `None`.

Přidáno, protože to vyžaduje DESIGN, i když ne ve výčtu D1d: `default`
(§5.4), `dedupe_key` (§5.2). Přidáno kvůli referenčnímu scénáři: pole
`aspect_ratio` kroku `image` (IG 4:5) a `max_tokens` u aliasu modelu
(reasoning modely, `finish_reason: length`).
