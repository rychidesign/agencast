# skills

Skills for coding agents (Claude Code, Codex, OpenCode and OMP) that work *on* AgenCast:
`agencast-run` (validate, dry-run, run, read results) and `agencast-create`
(write agents and scenarios). Install with `bash skills/install.sh`; it creates
symlinks in `~/.claude/skills`, `~/.codex/skills`,
`~/.config/opencode/skills` and `~/.omp/agent/managed-skills`.

Not to be confused with `examples/*/workflows/skills/` — those are skills for the agents
*inside* scenarios (loaded by the `skills:` field of an agent).
