---
name: agencast-create
description: Write or edit AgenCast agents (workflows/agents/<name>.md) and scenarios (workflows/scenarios/<name>.yaml). AgenCast is a CLI framework for LLM-agent scenarios written in YAML/Markdown (`agencast` command) — NOT the Claude Code Workflow tool. Use when asked to create/change an AgenCast (formerly maw) agent, scenario, step, prompt, Jev check or branching.
---

# Creating AgenCast agents and scenarios

Files go **directly** in `workflows/agents/` and `workflows/scenarios/` of the
project; subfolders are ignored. `name` must equal the file name without
extension (lowercase, digits, `-`). Unknown fields are errors, not ignored.
Never edit `config.yaml`, `mcp.yaml`, `commands.yaml` — owner only; ask.

## New project, registration, rename, migrate

```bash
agencast new project <dir>                  # skeleton with a sample agent + scenario, registers it
agencast new agent <name>                   # workflows/agents/<name>.md from a template (never overwrites)
agencast new scenario <name>                # workflows/scenarios/<name>.yaml
agencast projects add <root> [--name jmeno] # register an existing folder (name = folder name)
agencast projects rm <jmeno>                # registry only, files stay
agencast rename scenario|agent <old> <new>  # rewrites references
agencast migrate <file>                     # scenario, config or agent .md → current format version
```

Registry = `~/.config/agencast/projects.yaml` (`agencast projects list`). Only
`new project`, `projects add` and a successful `run` register; `validate` does not.
The web GUI (`agencast serve` in registry mode, systemd user service
`agencast.service`, only over Tailscale at `http://<tailscale-host>:8090`) shows
**registered projects only**, sees a new registration on the next request (no
restart) and edits the same files as the CLI — files are the single source of
truth. Never expose it publicly; the token is in `~/.config/agencast/serve.env`
(do not print it).

Never rename by moving files: `name` must equal the file name and `call`/`agent`
references would break. When `validate` reports an old format version, run `migrate`.

## Minimal agent — `workflows/agents/greeter.md`

```markdown
---
version: 1
name: greeter
description: Writes short friendly greetings   # for humans, not sent to the model
model: chytry            # alias from workflows/config.yaml `models`, never a model id
limits:
  budget_usd: 0.02       # required; optional: timeout: 2m, max_turns (required with mcp or in task)
# optional: skills: [name] (workflows/skills/<name>/SKILL.md), mcp: [server], tools: {server: [tool]}
---
You write one-sentence greetings. Plain text, no emoji.
```

Body = system prompt; `{{ }}` is not evaluated here, run data comes via the step `prompt`.
## Minimal scenario — `workflows/scenarios/greet.yaml`

```yaml
version: 1
name: greet
description: Writes a greeting for a name and returns it
inputs:            # each input: required: true OR a default, never both/neither
  who: { type: string, required: true, description: Who to greet }
outputs:
  text: { type: string }
steps:
  - id: write
    ask:
      agent: greeter
      prompt: "Greet {{ inputs.who }}."
  - id: out
    output:
      text: "{{ steps.write.text }}"
```

Types: `string number integer boolean list object file`. Steps run top to
bottom; a step sees only steps above it as `steps.<id>.<field>`.
## Step types (exactly one per step, plus `id`)

- `ask` — one model call via an agent, no tools; output `.text`, or the fields of `schema: {a: string, b: [string]}`.
- `task` — agent loop with MCP tools (`max_turns`, `tools` subset); same outputs as `ask`.
- `jev` — cheap classifier: `state` + `questions` (`type: noul` → 0–1, `choice` with `criteria`); output `steps.<id>.<question>`.
- `image` — `model` (pevný alias), `prompt`; `aspect_ratio`, `quality` a `resolution` mohou být šablony, kvalita kroku přebíjí alias; chat API kvalitu/rozlišení ignoruje s varováním; výstup `.file`.
- `call` — run another scenario (`callable: true`) in the same run; output = its `outputs`.
- `parallel` — named branches (lists of steps) run concurrently; no cross-branch refs.
- `switch` — `value` (string expr), `cases: {v: [steps]}`, `default:` required (`[]` = nothing).
- `set` — compute values without LLM: `set: {n: len(steps.write.text)}`.
- `fail` — stop the run on purpose with a message (usually with `when`).
- `output` — last step, keys exactly = `outputs`; required iff `outputs` exists.

Common step keys: `when`, `timeout`, `budget_usd`, `retry`, `on_error: continue` + `default`.
## Values

`{{ path }}` templates only insert a value (no operators) in prompts, `jev.state`,
`fail`, `output`, `call.inputs`. Expressions (`when`, `switch.value`, `set`) are
bare Python-style: `steps.check.on_brand < 0.7 and inputs.lang in ["cs", "sk"]`,
literals `true/false/null`, functions `len min max round str int float join`.
A step skipped by `when`/`switch` needs `default:` if a later step reads it.
Quote YAML values starting with `{{`; wrap expressions starting with `"`, `[`, `{`
in single quotes.

## Finish — always

```bash
agencast validate greet                    # --offline to skip the model check
agencast run greet -i who=Ada --dry-run    # plan, no calls
agencast run greet -i who=Ada --fake       # fake provider, no cost
```

Fix every `config:` message (names file, step, position) before a live run;
running and reading results: skill `agencast-run`.

Examples: `~/workspace/multiagent-workflows/workflows/agents/*.md`,
`…/workflows/scenarios/ig-post.yaml` (ask + jev + fail + image + output).
Full format: `~/workspace/multiagent-workflows/docs/spec/agent.md`,
`…/docs/spec/scenario.md`, `…/docs/spec/config.md`.
