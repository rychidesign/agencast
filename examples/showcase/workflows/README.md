# Showcase — sample workflows

Curated examples for Lumen, a fictional café and coffee roastery, and a book catalog.
Run the project from the repository root with `agencast --project examples/showcase`.

```
agents/        *.md   — agents: YAML frontmatter (model alias, skills, MCP,
                        tools, limits) + instructions in the body
scenarios/     *.yaml — scenarios: inputs, steps, output; call agents by name
skills/        <name>/SKILL.md
config.yaml    OpenRouter, model aliases, output storage, limits     ← owner only
mcp.yaml       MCP server registry + references to secret keys       ← owner only
commands.example.yaml  draft commands for a future `run` step        ← owner only
```

The exact formats are defined by the specification in [`docs/spec/`](../../../docs/spec/) (v1, approved
2026-09-25; changes only under the compatibility rules in [`docs/DESIGN.md`](../../../docs/DESIGN.md) §5.9). Reference examples: `agents/*.md`, `scenarios/ig-post.yaml`, `scenarios/demo-call.yaml` (calls `tone-check.yaml` with a `call` step), `scenarios/demo-task.yaml` (a task step with an MCP server),
`*.example.yaml` (the real `config.yaml`, `mcp.yaml` and `commands.yaml`
are created by the owner only). The `run` step is not part of v1;
`commands.example.yaml` is only a draft for a future extension.

Subfolders in `agents/` and `scenarios/` (such as `archive/`) are ignored — only
files directly in the folder are read.

Secret keys do not belong in these files — they are referenced through environment variables.
