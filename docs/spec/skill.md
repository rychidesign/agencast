# Formát skillu — specifikace v1

Skill je znalost nebo postup, který agent použije, když ho potřebuje
(DESIGN §5.8). Jedna složka `workflows/skills/<name>/` se souborem
`SKILL.md`: nahoře YAML frontmatter, pod ním text v Markdownu. Agent skill
uvádí ve `skills` ([agent.md](agent.md)).

Strojová podoba: [`schema/skill.schema.json`](schema/skill.schema.json).
Ukázka: `workflows/skills/thtd-hlas/SKILL.md`.

```markdown
---
name: thtd-hlas
description: Tón a slovník značky THTD pro texty na sociální sítě
---
Tykáme. Krátké věty. …
```

| Pole | Povinné | Co dělá | Když chybí | Příklad |
|---|---|---|---|---|
| `name` | ano | Jméno skillu = jméno složky. Malá písmena, číslice, pomlčka. | Chyba `config`; nesoulad se jménem složky také. | `name: thtd-hlas` |
| `description` | ano | Jedna věta: kdy skill použít. U `task` je to jediné, co model o skillu vidí, dokud ho nenačte — proto musí říct, k čemu skill je. | Chyba `config`. | `description: Tón a slovník značky THTD` |

Jiná pole nejsou povolená. Tělo pod frontmatterem musí být neprázdné.
Soubor se čte jako YAML 1.2 core (viz [scenario.md](scenario.md)).

Jak se skill dostane k modelu:

- **`task`:** system prompt nese jen řádek `- <name>: <description>`; tělo
  si model načte nástrojem `load_skill(name)`.
- **`ask`:** tělo se vloží do system promptu celé (ask nemá nástroje).

Podrobnosti v [agent.md](agent.md#jak-vznikne-system-prompt). Skill
nevynucuje tvar výstupu — to dělá `schema` kroku. Tajné hodnoty do skillu
nepatří (stejně jako do agenta).
