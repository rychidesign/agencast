---
name: agencast-create
description: Write or edit AgenCast agents (workflows/agents/<name>.md), scenarios (workflows/scenarios/<name>.yaml) and agent skills, or start a new AgenCast project. AgenCast is a CLI framework for LLM-agent scenarios written in YAML/Markdown (`agencast` command) — NOT the Claude Code Workflow tool. Use when asked to create/change an AgenCast (formerly maw) project, agent, scenario, step, prompt, Jev check or branching.
---

# Creating AgenCast agents and scenarios

Command: `agencast` (on this host `~/.local/bin/agencast`; fallback
`uv run --project ~/workspace/multiagent-workflows/framework agencast`).

## Before writing anything

1. **Find the project** — a folder with `workflows/` (`config.yaml`, `agents/`,
   `scenarios/`, optional `skills/`, `mcp.yaml`). Every command walks up from the
   current directory or takes `agencast --project <root> …`. Registered projects
   and their paths: `agencast projects list`. No project yet:
   `agencast new project <dir>` (skeleton with config, agent `pisatel`, scenario
   `ukazka`, `.env.example`; it is registered for the GUI right away).
2. **Read `workflows/config.yaml`** and note the keys under `models:` — agents
   reference a model only by such an alias, never by a model id. Read only:
   `config.yaml`, `mcp.yaml` and `commands.yaml` are owner-only; if a new alias
   or MCP server is needed, ask.
3. **Look at the existing `agents/*.md` and `scenarios/*.yaml`** and match
   their language (prompts here are usually Czech) and naming.
4. **Scaffold or write by hand.** `agencast new agent <name>` /
   `agencast new scenario <name>` create a minimal valid file (agent gets a real
   alias from `config.yaml`); nothing is ever overwritten. Hand-written files
   follow the examples below.

## File rules

Files go **directly** in `workflows/agents/` and `workflows/scenarios/`;
subfolders are ignored. `name` must equal the file name without extension
(lowercase, digits, `-`). Unknown fields are errors, not ignored. Never rename by
moving files — use `agencast rename scenario|agent <old> <new>`, it rewrites
`call`/`agent` references. `agencast migrate <file>` when `validate` reports an
old format version.

## Minimal agent — `workflows/agents/greeter.md`

```markdown
---
version: 1
name: greeter
description: Writes short friendly greetings   # for humans, not sent to the model
model: chytry            # alias from workflows/config.yaml `models`, never a model id
limits:
  budget_usd: 0.02       # required: cap per step using this agent
  # timeout: 2m          # optional; default ask 2m, task 15m
  # max_turns: 8         # required when the agent has `mcp`
# skills: [name]         # workflows/skills/<name>/SKILL.md; `ask` gets the whole text, `task` loads on demand
# mcp: [server]          # only servers in mcp.yaml that list this agent in `agents`; used by `task` steps
# tools: {server: [tool]}  # required allowlist for every server in `mcp`
---
You write one-sentence greetings. Plain text, no emoji.
```

Body = system prompt; `{{ }}` is not evaluated here, run data comes via the
step `prompt`. A skill is `workflows/skills/<name>/SKILL.md` with frontmatter
`name` (= folder) and `description` (one sentence; in `task` it is all the model
sees until it loads the skill) followed by the instructions.

## Minimal scenario — `workflows/scenarios/greet.yaml`

```yaml
version: 1
name: greet
description: Writes a greeting for a name and returns it
inputs:            # names lowercase/digits/_; each has required: true OR a default, never both/neither
  who: { type: string, required: true, description: Who to greet }
outputs:           # optional; if present, at least one item and a final `output` step
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

Input types: `string number integer boolean list object` (`file` only via
`call`). Steps run top to bottom; a step sees only steps above it as
`steps.<id>.<field>`. Step `id`: lowercase, digits, `_`, starts with a letter,
unique in the file, not a Python keyword (`in`, `is`, `if`, …).

## Step types (exactly one per step, plus `id`)

- `ask` — one model call via an agent, no tools; output `.text`, or the fields of
  `schema: {a: string, b: [string], c: {x: number}}` (root is a map, all fields required).
- `task` — agent loop with MCP tools (`max_turns`, `mcp`, `tools` subsets of the agent's); same outputs as `ask`.
- `jev` — cheap classifier: `state` + `questions.<q>` with `type: noul` (0–1), `choice` (`criteria: {key: description}` → key) or `score` (`criteria:` list of levels → number); output `steps.<id>.<q>`.
- `image` — `model` (image alias), `prompt`; optional `aspect_ratio`, `quality`, `resolution` (may be templates); output `.file`.
- `call` — run another scenario (it needs `callable: true`) in the same run with `inputs:`; output = its `outputs`.
- `parallel` — named branches (lists of steps) run concurrently; no cross-branch refs.
- `switch` — `value` (string expr), `cases: {v: [steps]}`, `default:` required (`[]` = nothing).
- `set` — compute values without LLM: `set: {n: len(steps.write.text)}`.
- `fail` — stop the run on purpose with a message template (usually with `when`).
- `output` — last step, keys exactly = `outputs`; required iff `outputs` exists.

Common step keys: `when`, `timeout`, `budget_usd`, `retry` (repeats one API
call on `transient`/`schema`), `on_error: continue` + `default`,
`dedupe_key` (template; the step runs once per key, bound to scenario + step).

## Values

`{{ path }}` templates only insert a value (no operators) in prompts, `jev.state`,
`fail`, `output`, `call.inputs`; a `null` in a template is a runtime error unless
it comes from an explicit `default`. Expressions (`when`, `switch.value`, `set`)
are bare Python-style: `steps.check.on_brand < 0.7 and inputs.lang in ["cs", "sk"]`,
literals `true/false/null`, functions `len min max round str int float join`.
A step skipped by `when`/`switch`/`on_error` needs `default:` if a later step
reads it. YAML: quote values starting with `{{`; wrap an expression that starts
with `"`, `[`, `{` or contains `: ` or ` #` in single quotes.

## Finish — always

```bash
agencast validate greet                    # --offline to skip the model check (needs network otherwise)
agencast run greet -i who=Ada --dry-run    # plan, no calls
agencast run greet -i who=Ada --fake       # fake provider, no cost
```

`validate` prints `v pořádku: greet (2 kroky)` or `config: …` lines that name
the file, step and field — fix every one before a live run. `--fake` without a
fixture invents values (Jev answers 0.5), so a threshold `fail` is expected.
Then tell the user the files, the inputs and the exact `run` command; a live
run and reading results: skill `agencast-run`.

## GUI and registry

The web GUI (`agencast serve` in registry mode, systemd user service
`agencast.service`, only over Tailscale at `http://<tailscale-host>:8090`) edits
the same files and shows **registered projects only**
(`~/.config/agencast/projects.yaml`, `agencast projects list`). `new project`
registers; an existing folder: `agencast projects add <root> [--name jmeno]`;
`projects rm <jmeno>` removes from the registry only. `validate` never
registers; a successful `run` does as a fallback. The GUI picks up a new
registration on the next request. Never expose it publicly; the token is in
`~/.config/agencast/serve.env` (do not print it).

Examples: `~/workspace/multiagent-workflows/workflows/agents/*.md`,
`…/workflows/scenarios/ig-post.yaml` (ask + jev + fail + image + output),
`…/ukazka-task.yaml` (task with MCP), `…/ukazka-call.yaml` (call).
Full format: `~/workspace/multiagent-workflows/docs/spec/agent.md`,
`…/docs/spec/scenario.md`, `…/docs/spec/skill.md`, `…/docs/spec/config.md`.
