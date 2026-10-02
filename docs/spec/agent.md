# Agent format — specification v1

An agent is a single file `workflows/agents/<name>.md`: configuration at the
top (YAML frontmatter between two `---` lines), instructions in Markdown
below it (DESIGN D1a). A scenario calls the agent by name in an `ask` or
`task` step.

Machine-readable form: [`schema/agent.schema.json`](schema/agent.schema.json).
Examples: `examples/showcase/workflows/agents/copywriter.md`, `photographer.md`, `publisher.md`.

The frontmatter is read as **YAML 1.2 core** (booleans only `true`/`false`,
a duplicate key = `config` error with a line number; see
[scenario.md](scenario.md)). Only files directly in `workflows/agents/` are
read; subdirectories are ignored (useful e.g. for an archive).

Notation in the text: **proposal** = not covered by DESIGN.md; a proposed
default behavior awaiting approval.

## Full example

```markdown
---
version: 1
name: publisher
description: Publishes an approved post to Instagram
model: smart
skills: [ig-rules]
mcp: [instagram]
tools:
  instagram: [create_media, publish_media]
limits:
  max_turns: 6
  budget_usd: 0.20
  timeout: 5m
---
You manage the Instagram account of the Lumen brand. You receive the finished text and the image URL…
```

## Frontmatter fields

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `version` | yes | Version of the agent format. The framework uses it to know how to read the file (R7). Only `1` so far. | `validate` ends with a `config` error. | `version: 1` |
| `name` | yes | Name the scenario uses to call the agent. Must match the file name without `.md`. Lowercase letters, digits, hyphen. | `config` error. A mismatch with the file name too. | `name: copywriter` |
| `description` | yes | One sentence for humans: what the agent is for. It is **not sent** in the prompt. | `config` error. | `description: Copywriter for Lumen brand IG` |
| `model` | yes | Model **alias** from `config.yaml` (§5.5), never a concrete model id. | `config` error. An unknown alias too. | `model: smart` |
| `skills` | no | List of skills from `workflows/skills/<name>/SKILL.md` ([skill.md](skill.md)). How they reach the model, see below. | No skills. | `skills: [ig-rules]` |
| `mcp` | no | List of MCP servers from `mcp.yaml` the agent may connect to. Only the `task` step uses them. The server must list this agent in its `agents` in `mcp.yaml` (decided by the project owner). | The agent has no tools. | `mcp: [instagram]` |
| `tools` | for every server in `mcp` | **Explicit list** of tools the agent may call, for **every** server in `mcp` (DESIGN §5.8: allowlist by name — a new tool the server adds is not visible to the agent). The keys of `tools` = exactly the servers in `mcp`. A tool must also be in the server's `tools` in `mcp.yaml` if the project owner restricted them. | A server from `mcp` without an entry in `tools` is a `config` error; `agencast run <scenario> --dry-run` lists in `plan.md` what the server offers. A `tools` key for a server outside `mcp` is an error too. | `tools: { instagram: [publish_media] }` |
| `limits` | yes | Upper bounds for one use of the agent in a step. A step may only lower them. | `config` error. | see below |
| `limits.max_turns` | when the agent has `mcp` | How many turns may happen in one `task` step (§5.1 item 6). Turn = a model response processed by the loop; a retry after an error does not count. Meaningless for `ask` — `ask` is always a single call. | Agent with `mcp` without `max_turns` = `config` error. Agent without `mcp` used in `task` without `max_turns` = `config` error. | `max_turns: 6` |
| `limits.budget_usd` | yes | How many USD one step with this agent may cost (all calls including retries). | `config` error. | `budget_usd: 0.20` |
| `limits.timeout` | no | Maximum duration of one step with this agent. Format `<number>s`, `m` or `h`. | Default by step type (`ask` 2m, `task` 15m) — **proposal**. | `timeout: 5m` |

The frontmatter allows no other fields — a typo (`modle:`) is a `config`
error, not a silently ignored field.

The list of scenarios allowed to use the agent is **not** in the agent:
others write agents too, so these restrictions are held by the project
owner in `mcp.yaml` (`agents`, `scenarios`, `tools` on the server —
[config.md](config.md), DESIGN §5.2).

## Body = instructions

Everything below the second `---` is the agent's instructions in Markdown.
It must not be empty. `{{ }}` is **not evaluated** in the body — the agent
is a fixed role description; the step passes values from a specific run
to it through `prompt`.

### How the system prompt is built

The framework always builds the system prompt the same way and adds
nothing else to it.

**For `task`** (DESIGN §5.8):

1. the agent body,
2. a `## Skills` section with a line `- <name>: <description>` for each skill.

The model gets the tool `load_skill(name)`, where `name` is an enumeration
(`enum`) of the agent's skills. The tool returns the body of `SKILL.md`. An
unknown name returns an error with a list of available skills. A
`load_skill` call counts as a turn and the record has a `tool_call` with
`server: "_skills"`. `load_skill` is never sent to an MCP server.

**For `ask`** (a single call, no tools — D1b): `load_skill` cannot be used,
so skills are inserted **in full**:

1. the agent body,
2. for each skill in the order of `skills`: a line `## Skill: <name>` and
   the body of `SKILL.md` without frontmatter.

(The alternative "forbid skills in `ask`" is OPEN-QUESTIONS 11.)

The user message (`user`) is the step's `prompt`. Exactly what the model
received is in the run record in `steps/<nn>-<id>/prompt.md` (see
[run-record.md](run-record.md)).

When the step asks for JSON (`schema`) and the cascade (§5.5) is at the
`prompt` level, the framework appends a description of the required JSON
to the end of the system prompt. This is also visible in `prompt.md`. The
step output is enforced by `schema`, not by a skill.

## `ask` vs. `task` — what happens to the agent

| | `ask` | `task` |
|---|---|---|
| Model calls | one (plus retries on a `transient`/`schema` error) | model ↔ tools loop, at most `max_turns` turns |
| System prompt | body + full skills | body + list of skills |
| Tools | **none** (MCP is not connected) | allowed MCP tools, `load_skill` (if it has skills), `_submit_output` (cascade) |
| Limits | `budget_usd`, `timeout` | `max_turns`, `budget_usd`, `timeout` |
| End | model response | the model responds without a tool call, or calls `_submit_output` |

## Permissions: project owner → agent → step (§5.2, §5.8)

Three layers, each may only narrow the previous one:

1. The **project owner** in `mcp.yaml` decides for each server which agents
   may use it (`agents`), which scenarios may run an agent with this server
   (`scenarios`) and the upper list of tools (`tools`).
2. The **agent** states what is allowed for it **at most** (`mcp`, `tools`,
   `limits`).
3. A **`task` step** may select a subset of `mcp` and `tools` and lower
   `max_turns`, `budget_usd`, `timeout`.

A step can never add a server or a tool, or raise a limit. An attempt to do
so is a `config` error in `validate`, e.g.:

```
config: ig-publish.yaml: step "publish", task.tools: step requests tool instagram.delete_media, which agent 'publisher' does not allow (tools.instagram)
```

The effective limit of a step is always the smallest of: the agent's limit,
the step's limit, the remaining budget and time of the whole run
(`config.yaml` → `limits`). Only allowed tools go into `tools` for the model
(DESIGN §5.8).

At run time:

- When the model calls a tool that is not allowed, the framework does not
  run it, returns an error to the model ("Error: tool … is not allowed")
  and writes it to the record (`tool_call` with `allowed: false`). The run
  does not fail because of it.
- **Arguments from the model are validated before the call** against the
  tool schema sent by the server (the original, not the one simplified for
  the provider — Gemini silently ignores parts of the schema, DESIGN §5.8).
  When they do not match, the tool is not run and the model gets the
  validation error as the tool result (the turn counts; the record has
  `invalid_args: true`).

## What must not be in an agent

- Secret keys, tokens, passwords — not even in the instructions. Keys exist
  only in `config.yaml` / `mcp.yaml` as a reference to an environment
  variable (§5.2).
- A concrete model id (`anthropic/claude-haiku-4.5`) — only an alias.
