# Skilly pro kódovací agenty

`agencast-run` pomáhá spouštět scénáře a číst výsledky; `agencast-create`
vytvářet agenty a scénáře. Jsou přibalené i v instalaci bez klonu.

```bash
agencast skills list
agencast skills install                # nalezené nástroje
agencast skills install --to all       # Claude Code, Codex, OpenCode, OMP
agencast skills path
```

Výchozí instalace vytvoří symlinky v `~/.claude/skills`, `~/.codex/skills`,
`~/.config/opencode/skills` a `~/.omp/agent/managed-skills`. `--copy` vytvoří
kopie, `--force` dovolí přepsat existující složky, `--prefix DIR` změní domovskou
složku. Konkrétní nástroje vyberete např. `--to claude,codex`.

Skilly v `examples/*/workflows/skills/` jsou naopak pro agenty uvnitř scénářů.
