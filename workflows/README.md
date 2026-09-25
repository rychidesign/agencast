# workflows — vrstva uživatele

Tady žije všechno, co píše uživatel (nebo jeho agenti), ne framework.

```
agents/        *.md   — agenti: YAML frontmatter (model alias, skilly, MCP,
                        nástroje, limity) + instrukce v těle
scenarios/     *.yaml — scénáře: inputs, steps, output; volají agenty jménem
skills/        <name>/SKILL.md
config.yaml    OpenRouter, aliasy modelů, úložiště výstupů, limity   ← jen vlastník
mcp.yaml       registr MCP serverů + odkazy na tajné klíče           ← jen vlastník
commands.yaml  povolené příkazy pro krok `run`                       ← jen vlastník
```

Přesné formáty definuje specifikace v `docs/spec/` (v1, schválena
2026-09-25; změny jen podle pravidel kompatibility v `docs/DESIGN.md` §5.9). Referenční ukázky: `agents/*.md`, `scenarios/ig-post.yaml`, `scenarios/ukazka-call.yaml` (volá `kontrola-tonu.yaml` krokem `call`), `scenarios/ukazka-task.yaml` (krok task s MCP serverem),
`*.example.yaml` (skutečné `config.yaml`, `mcp.yaml`, `commands.yaml`
vytváří jen vlastník).

Tajné klíče do těchto souborů nepatří — odkazuje se na proměnné prostředí.
