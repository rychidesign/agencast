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

Přesné formáty definuje specifikace v `docs/` (vznikne po spicích). Do té
doby jsou zde jen tyto složky; ukázkový scénář je v `docs/DESIGN.md` §6.

Tajné klíče do těchto souborů nepatří — odkazuje se na proměnné prostředí.
