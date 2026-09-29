# Skill format — specification v1

A skill is knowledge or a procedure that an agent uses when it needs it
(DESIGN §5.8). It is one directory `workflows/skills/<name>/` with a
`SKILL.md` file: YAML frontmatter at the top, Markdown text below. An agent
lists its skills in `skills` ([agent.md](agent.md)).

Machine-readable form: [`schema/skill.schema.json`](schema/skill.schema.json).
Example: `examples/showcase/workflows/skills/lumen-voice/SKILL.md`.

```markdown
---
name: lumen-voice
description: Lumen brand tone and vocabulary for social media copy
---
Informal "you". Short sentences. …
```

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `name` | yes | Skill name = directory name. Lowercase letters, digits, hyphen. | `config` error; a mismatch with the directory name too. | `name: lumen-voice` |
| `description` | yes | One sentence: when to use the skill. In `task` it is the only thing the model sees about the skill until it loads it — so it must say what the skill is for. | `config` error. | `description: Lumen brand tone and vocabulary` |

No other fields are allowed. The body below the frontmatter must not be
empty. The file is read as YAML 1.2 core (see [scenario.md](scenario.md)).

How a skill reaches the model:

- **`task`:** the system prompt carries only the line `- <name>: <description>`;
  the model loads the body with the `load_skill(name)` tool.
- **`ask`:** the whole body is inserted into the system prompt (ask has no tools).

Details in [agent.md](agent.md#how-the-system-prompt-is-built). A skill
does not enforce the shape of the output — the step's `schema` does that.
Secret values do not belong in a skill (same as in an agent).
