# Skills for coding agents

Let your coding agent turn a recurring task into a workflow, check its flow, run it with new inputs and
read the results. AgenCast skills guide this work through the CLI or a connected MCP server, using the
project's configured models, permissions and limits.

`agencast-run` helps run scenarios and read results — from the CLI or through a connected `agencast mcp`
server, including copying the user's images to the server's `--input-dir`; `agencast-create`
helps create agents and scenarios. The MCP server serves both as `get_guide("run")` and `get_guide("create")`. They are bundled with the installation even without a clone.

```bash
agencast skills list
agencast skills install                # detected tools
agencast skills install --to all       # Claude Code, Codex, OpenCode, OMP
agencast skills path
```

The default installation creates symlinks in `~/.claude/skills`, `~/.codex/skills`,
`~/.config/opencode/skills` and `~/.omp/agent/managed-skills`. `--copy` creates
copies, `--force` allows overwriting existing folders, `--prefix DIR` changes the home
folder. Pick specific tools with e.g. `--to claude,codex`.

The skills in `examples/*/workflows/skills/` provide instructions for the agents executing workflow steps.
Those agents use the project's OpenRouter models; the coding agent operates AgenCast itself.
