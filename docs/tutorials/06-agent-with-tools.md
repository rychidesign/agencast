# Part 6 — An agent with tools: `task`, an MCP server and skills

Mentions of `maw` denote the historical name of AgenCast; the outputs and the limitations of the time are archival.

Run the commands from `examples/tutorial` (from the clone root: `cd examples/tutorial`).

**Time:** about 30 minutes · **Spend:** one live run for ~0.014 USD
(the others with `--fake` or without a model call)
**You will learn to:** allow an agent an MCP server (as the owner), write an
agent with tools and a skill (as the author), run a `task` step, read every
tool call in the run record, and know everywhere the framework stops you.

Prerequisite: parts 1–5 and **Node.js** (`npx` starts the MCP server; the
first time it downloads the package, so it needs internet).

> The outputs of `validate`, `--dry-run` and `--fake` come from the current CLI. The live run
> (step 7 and the record excerpts in step 8) is archival: a real run from 25 Sep 2026 against
> `maw` 0.2.1, with the names adapted to the English example project. Run the commands from the
> `examples/tutorial` project with the `agencast` shortcut from part 1.

---

## Step 1 — `ask` × `task`

Until now your agents only **answered**: an `ask` step = one model call,
text in, text (or JSON) out. A `task` step gives the agent **tools** and
lets it work in a loop:

```
model: "call list_allowed_directories"  → the framework runs the tool, returns the result to the model
model: "call write_file(...)"           → runs it, returns the result
model: "done, here is the answer"       → end of the step
```

Every model response that the loop processes is one **turn**. A turn can
contain several tool calls at once. A retry after an error
(`transient`, `schema`) does not count as a turn.

| | `ask` | `task` |
|---|---|---|
| Model calls | one (+ retries after an error) | a loop, at most `max_turns` turns |
| Tools | none | the allowed tools of MCP servers + `load_skill` |
| Skills | inserted into the prompt **in full** | only a list in the prompt, the model loads the body with a tool |
| Limits | `budget_usd`, `timeout` | `max_turns`, `budget_usd`, `timeout` |
| End | the model's response | the model answers without a tool call |

Tools are offered by an **MCP server** — a separate program the framework
talks to using the MCP protocol. We will use the official
`@modelcontextprotocol/server-filesystem`: it can read and write files, but
only in one folder, which it receives at startup.

---

## Step 2 — a skill

A skill is knowledge that an agent picks up when it needs it. Here: what a
file in the archive should look like.

Create `workflows/skills/tutorial-entry/SKILL.md`:

```markdown
---
name: tutorial-entry
description: Format of archive entries — use it whenever you write or check an entry or the archive index
---
The archive has two files, both directly in the allowed folder:

1. `<day>.md` — the entry for one day (`<day>` is the date from the prompt, e.g. `2026-09-25.md`):
   - first line `# Entry <day>`,
   - each sentence of the note on its own line starting with `- `,
   - nothing else (no blank lines, no comments).
2. `index.md` — the archive index:
   - first line `# Index`,
   - for each entry a line `- <day>: <first sentence of the note>`.
```

- `name` = the folder name.
- With `task`, `description` is **the only thing the model sees about a skill**
  until it loads it. That is why it must say *when* to use the skill — not just
  "archive format".

---

## Step 3 — an agent with tools (the author role)

`workflows/agents/tutorial-archivist.md`:

```markdown
---
version: 1
name: tutorial-archivist
description: Writes notes to an archive in the run workspace (tutorial, part 6)
model: smart
skills: [tutorial-entry]
mcp: [filesystem]
tools:
  filesystem: [list_allowed_directories, list_directory, read_text_file, write_file]
limits:
  max_turns: 6
  budget_usd: 0.03
  timeout: 3m
---
You are an archivist. You have access to a single folder — find it with the
`list_allowed_directories` tool. Always write full file paths (allowed
folder + file name).

Steps:
1. Find the allowed folder and load the `tutorial-entry` skill.
2. Write both files according to the skill with the `write_file` tool.
3. List the folder and read each file. If a file does not match the skill, fix it.
4. Only then reply: the names of the written files (without the folder) and the number
   of sentences in the day's entry. Never reply before you have actually written the files.

If a tool returns an error, do not try paths outside the allowed folder:
reply with a description of the error.
```

New fields:

| Field | What it does |
|---|---|
| `skills` | skills from `workflows/skills/` |
| `mcp` | which servers from `mcp.yaml` the agent may connect to |
| `tools` | an **explicit list** of tools for every server in `mcp` — what is not here, the model will not see. When a server adds a tool in a new version (say `delete_file`), the agent does not get it. |
| `limits.max_turns` | at most this many turns in one `task` step; required for an agent with `mcp` |
| `limits.budget_usd` | how much the **whole step** may cost — all turns together |

Why `list_allowed_directories` and "full paths": the agent does not know in
advance where its folder is (every run has a different one). It asks the
server.

---

## Step 4 — a scenario with a `task` step

`workflows/scenarios/tutorial-06-archive.yaml`:

```yaml
version: 1
name: tutorial-06-archive
description: The archivist writes a note to the run workspace and reads it back (tutorial, part 6)

inputs:
  day:
    type: string
    required: true
    description: Date of the entry, e.g. 2026-09-25
  text:
    type: string
    required: true
    description: The note as free text

outputs:
  message:
    type: string
    description: What the archivist wrote and checked (its final reply)

steps:
  # 1. An agent with tools: it finds the folder itself, loads the skill, writes two files,
  #    lists the folder and reads the files. Tools are allowed by mcp.yaml (owner)
  #    and the agent; the step may only narrow them — here it only lowers max_turns.
  #    No schema: with it, Haiku in maw 0.2.1 often replies at once, without tools
  #    (part 6, "Watch out for schema in task"; BUGS.md, maw 0.2.1).
  - id: write
    task:
      agent: tutorial-archivist
      prompt: |
        Day: {{ inputs.day }}
        Note: {{ inputs.text }}
        Write the note to the archive and check it.
      max_turns: 5

  # 2. Result.
  - id: out
    output:
      message: "{{ steps.write.text }}"
```

`task` has the same fields as `ask` (`agent`, `prompt`, optionally `schema`)
and may additionally narrow `max_turns`, `mcp` and `tools`. Without `schema`
the step output is `steps.write.text` — the agent's final answer. Why there
is deliberately no `schema` here, you will see in step 7.

Validate it. The finished project in `examples/tutorial` already has the
permissions set. If you were writing it from scratch and the owner's `mcp.yaml`
(step 5) did not list the agent yet — say it listed only `tutorial-namer` —
the check would look like this:

```bash
agencast validate tutorial-06-archive
```

```
config: agents/tutorial-archivist.md: the project owner has not allowed server 'filesystem' for agent 'tutorial-archivist' (mcp.yaml → servers.filesystem.agents: tutorial-namer)
```

(To try it yourself, use the copy from step 9 and change `agents` in its
`mcp.yaml` to `[tutorial-namer]`.) The agent says "I want filesystem", but
that is not enough.

---

## Step 5 — `mcp.yaml` (the owner role)

Which agent may do what is decided by the **owner** in `workflows/mcp.yaml`:

```yaml
# mcp.yaml — MCP server registry. Changed by the owner only (DESIGN §4, §5.2).
# Created in Phase 3a from mcp.example.yaml. This is where it is decided who may
# use what: agents (required), scenarios and tools (optional).
# Tokens only by environment variable name. Specification: docs/spec/config.md
version: 1

servers:
  # Run workspace: the server sees only runs/<run>/work, nothing else.
  # The package version is pinned (R7); preinstall it on Modal (D5).
  filesystem:
    description: Reading and writing in the workspace of the current run
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem@2026.8.31", "{run_dir}/work"]
    agents: [tutorial-archivist]
    tools: [list_allowed_directories, list_directory, read_text_file, write_file]
```

| Field | What it means |
|---|---|
| `command`, `args` | how to start the server. `{run_dir}` = the folder of the current run — so the server sees only `runs/<run>/work`, no other run and none of the rest of the disk. The package version is pinned. |
| `agents` | which agents may use the server (at least one; an empty list is not a valid file) |
| `tools` | the upper bound of tools — the agent may pick from them, no more |
| `scenarios` (not here) | which scenarios an agent with this server may run in — e.g. publishing only from an approval scenario |

The `agents` line is what the owner adds for the agent (in the finished
project it is already there). With it the check passes:

```bash
agencast validate tutorial-06-archive
```

```
valid: tutorial-06-archive (2 steps)
```

**Why it cannot come from the agent:** agents and scenarios are also written
by others — a colleague, or another agent. If an agent could write the
permission into its own frontmatter, it would not be a permission but a wish.
So there are three layers, each of which may only **narrow** the previous one:

```
owner (mcp.yaml)  →  agent (mcp, tools, limits)  →  task step (tools, max_turns, …)
```

A step never adds a server or a tool and never raises a limit (you will try
that in step 9).

### `--dry-run` shows what the server offers

```bash
agencast run tutorial-06-archive -i day=2026-09-25 -i text="It rained in the morning. In the afternoon we finished part 6." --dry-run
```

```
| 1 | write | task |  | agent tutorial-archivist → smart (anthropic/claude-haiku-4.5); tools: filesystem: list_allowed_directories, list_directory, read_text_file, write_file; skills: tutorial-entry; max_turns 5; text | 0.03 USD, 3m |
| 2 | out | output |  | message |  |

## MCP servers

- **filesystem** (Reading and writing in the workspace of the current run): offers create_directory, directory_tree, edit_file, get_file_info, list_allowed_directories, list_directory, list_directory_with_sizes, move_file, read_file, read_media_file, read_multiple_files, read_text_file, search_files, write_file
```

`--dry-run` really starts the server and asks it for its tools — this is how
you find out the names for `tools` without reading the server's
documentation. The server offers 14, the owner allowed 4, the agent wants
those 4. The model will see only them (and `load_skill`). The step limits:
`max_turns 5` (the agent allows 6), `0.03 USD` and `3m` from the agent.

---

## Step 6 — `--fake`: turns in the fixture

With `task`, a model response is a **list of turns**. A turn is either tool
calls (`tool_calls`) or a final answer (`text`, with `schema` `json`).
`fake/tutorial-06-archive.yaml`:

```yaml
# Scripted responses for tutorial-06-archive. A task step = a list of turns:
# each turn is either tool calls (tool_calls) or the final reply (text).
# Tool name = <server>__<tool>; load_skill is a framework tool.
# In tests a fake server (tests/fake_mcp_server.py) runs instead of server-filesystem;
# paths are relative to its root.
write:
  - tool_calls:
      - { name: filesystem__list_allowed_directories, arguments: {} }
      - { name: load_skill, arguments: { name: tutorial-entry } }
  - tool_calls:
      - name: filesystem__write_file
        arguments: { path: 2026-09-25.md, content: "# Entry 2026-09-25\n- It rained in the morning.\n- In the afternoon we finished part 6.\n" }
      - name: filesystem__write_file
        arguments: { path: index.md, content: "# Index\n- 2026-09-25: It rained in the morning.\n" }
  - tool_calls:
      - { name: filesystem__list_directory, arguments: { path: . } }
      - { name: filesystem__read_text_file, arguments: { path: 2026-09-25.md } }
      - { name: filesystem__read_text_file, arguments: { path: index.md } }
  - text: "Written: 2026-09-25.md and index.md. The entry has 2 sentences."
```

The tool name for the model is `<server>__<tool>` (two underscores) — that is
how the framework names it so that the tools of two servers do not clash.

```bash
agencast run tutorial-06-archive -i day=2026-09-25 -i text="It rained in the morning. In the afternoon we finished part 6." --fake fake/tutorial-06-archive.yaml
```

```
run 20260929-190051-tutorial-06-archive-ad02: succeeded · 0.8 s · 0.0004 USD
```

```
| 1 | write | task | ✓ | 0.8 s | 0.0004 | smart → anthropic/claude-haiku-4.5, turns 4, tools 7 |
…
## Output
- message: “Written: 2026-09-25.md and index.md. The entry has 2 sentences.”
```

One thing to watch out for: `--fake` fakes **only the model**. The MCP server
is real — `npx` started it and the files were really created:

```bash
ls runs/20260929-190051-tutorial-06-archive-ad02/work
```

```
2026-09-25.md  index.md
```

In the golden tests (`cd ../../framework && uv run pytest`) a fake server from
`../../framework/tests/fake_mcp_server.py` runs instead — no Node and no
network, with the same tools. The fixture is the same.

---

## Step 7 — a live run

```bash
agencast run tutorial-06-archive -i day=2026-09-25 -i text="It rained in the morning and the train was late. In the afternoon we finished the sixth part of the tutorial. In the evening we launched it for real."
```

```
run 20260925-161501-tutorial-06-archive-dfec: succeeded · 9.9 s · 0.0135 USD
```

```
| 1 | write | task | ✓ | 9.9 s | 0.0135 | smart → anthropic/claude-haiku-4.5, turns 4, tools 7 |
| 2 | out | output | ✓ | 0.0 s | 0 |  |
| | Total | | | 9.9 s | 0.0135 |  |
…
## Output
- message: “Perfect! Both files match the skill:

✅ **2026-09-25.md** — correct: header `# Entry 2026-09-25`, three sentences on their own lines with `-`
✅ **index.md** — correct: header `# Index`, one line with the date and the first sentence

**Answer:**
- **Written files:** `2026-09-25.md`, `index.md`
- **Number of sentences in the day's entry:** 3”
```

And in the workspace:

```
--- work/2026-09-25.md
# Entry 2026-09-25
- It rained in the morning and the train was late.
- In the afternoon we finished the sixth part of the tutorial.
- In the evening we launched it for real.
--- work/index.md
# Index
- 2026-09-25: It rained in the morning and the train was late.
```

Exactly according to the skill. The turns in order (from `events.jsonl`):

```
mcp_server started (0.75 s — server start and handshake)
turn 1: list_allowed_directories, load_skill tutorial-entry    1.8 s   0.0020 USD
turn 2: write_file 2026-09-25.md, write_file index.md          2.3 s   0.0037 USD
turn 3: list_directory, read_text_file ×2                      2.1 s   0.0040 USD
turn 4: final answer (finish_reason stop)                      2.8 s   0.0038 USD
mcp_server stopped
```

The tools themselves took 2–9 ms; the time is spent in the model. The turns get
more and more expensive: in every turn the model receives the **entire
conversation so far**, including the tool results (1,522 → 2,982 input tokens).
That is why `max_turns` and `budget_usd` exist — an agent that goes in circles
would otherwise pay more and more.

### Watch out for `schema` in `task`

The first version of the scenario had a `schema` on the step
(`files: [string]`, `lines: integer`), like `ask` in part 2. Three live runs
in a row ended like this:

```
| 1 | write | task | ✓ | 24.0 s | 0.0046 | smart → anthropic/claude-haiku-4.5, turns 2, tools 2 (native_schema) |
…
- files:  /home/…/runs/20260925-161001-tutorial-06-archive-9a8f/work/2026-09-25.md
- lines: 4
```

"Success" — but the `work/` folder **does not exist**. The model found the
folder, loaded the skill and in the second turn answered straight away with
JSON, as if it had written the file. The second and third attempts (with
stricter instructions) ended the same way, the third one even without a single
tool (`turns 1, tools 0`). The same scenario **without `schema`** passed the
first time.

What is going on: with a `schema` and an alias at the `native_schema` level, the
framework sends the model the required shape of the JSON answer in **every**
turn — and Haiku takes it as an instruction "answer with JSON right now". The
framework behaved according to the specification: the model answered without a
tool call, and that ends the loop. It is recorded in `docs/tutorials/BUGS.md`
(the maw 0.2.1 section) together with what helped (an alias with
`structured_output: tool_wrapper` — that is the owner's decision in
`config.yaml`).

**Since `maw` 0.2.2** the framework does not send the required JSON shape in the
turns of a `task`: with a `schema` it always starts at the `tool_wrapper` level —
the model submits the result with the `_submit_output` tool when it is done
(`docs/spec/ISSUES.md`, item 36). The alias's `structured_output` now applies
only to `ask`. Exactly this variant wrote both files correctly in the control
run (BUGS.md, item 7). In the step's note you will then see `(tool_wrapper)`, or
`(prompt)` when the model did not submit the result with the tool and the
cascade went one level down.

Two rules follow from this, and they hold even after the fix:

1. **Do not trust an agent with tools; check the record.** You can tell from
   `summary.md` (`tools 2`, yet writing needs at least two `write_file`) and
   from `events.jsonl` (no `tool_call` with `write_file`).
2. With `task` in `maw` 0.2.1 and Haiku, prefer a text answer; when you need
   data, extract it in the next step (an `ask` with `schema` over
   `steps.write.text`) — JSON does not get in the way there.

---

## Step 8 — the record of a `task` step

```
runs/20260925-161501-tutorial-06-archive-dfec/
  mcp/filesystem.stderr.log     what the server printed to stderr
  work/                         the workspace = what the server sees
  steps/01-write/
    prompt.md                   the system prompt with the list of skills
    calls/01.request.json       turn 1 — the request to the model
    calls/01.response.json      turn 1 — the response (tool calls)
    calls/02.tool.json          the list_allowed_directories tool
    calls/03.tool.json          the load_skill tool
    calls/04.request.json       turn 2 …
    …
```

The numbers in `calls/` run in order across model calls and tool calls.

### `prompt.md` — skills as a list

```
# System prompt

You are an archivist. You have access to a single folder — find it with the
…
## Skills

- tutorial-entry: Format of archive entries — use it whenever you write or check an entry or the archive index

# Message

Day: 2026-09-25
…
```

The skill body is **not** in the prompt — only the name and the `description`.
For it the model got the `load_skill` tool (from `calls/01.request.json`):

```
{"type": "function", "function": {"name": "load_skill", "description": "Load the full instructions for a skill from the Skills list. When a skill is relevant to the task, load it before starting.", "parameters": {"type": "object", "properties": {"name": {"type": "string", "enum": ["tutorial-entry"]}}, "required": ["name"], "additionalProperties": false}}}
```

### `tool_call` in `events.jsonl`

Every tool call is one event. `load_skill` has `server: "_skills"` — it never
goes to an MCP server, the framework handles it itself:

```
{"ts":"2026-09-25T16:15:03.685Z","type":"tool_call","step":"write","turn":1,"server":"_skills","tool":"load_skill","allowed":true,"invalid_args":false,"is_error":false,"duration_s":0.0,"call_file":"steps/01-write/calls/03.tool.json"}
{"ts":"2026-09-25T16:15:06.009Z","type":"tool_call","step":"write","turn":2,"server":"filesystem","tool":"write_file","allowed":true,"invalid_args":false,"is_error":false,"duration_s":0.008,"call_file":"steps/01-write/calls/05.tool.json"}
```

| Field | What it says |
|---|---|
| `turn` | in which turn the model called the tool |
| `allowed` | `false` = the tool was not allowed, it did not run |
| `invalid_args` | `true` = the arguments do not match the tool's schema, it did not run |
| `is_error` | the tool ran but returned an error (the model received it) |

The arguments and the result are in `call_file` (`calls/05.tool.json`):

```
{
  "turn": 2,
  "name": "filesystem__write_file",
  "server": "filesystem",
  "tool": "write_file",
  "arguments": {
    "path": "/home/…/runs/20260925-161501-tutorial-06-archive-dfec/work/2026-09-25.md",
    "content": "# Entry 2026-09-25\n- It rained in the morning and the train was late.\n- In the afternoon we finished the sixth part of the tutorial.\n- In the evening we launched it for real.\n"
  },
  "allowed": true,
  "invalid_args": false,
  "is_error": false,
  "result": "Successfully wrote to /home/…/work/2026-09-25.md",
  "files": []
}
```

### `mcp_server` and `mcp/filesystem.stderr.log`

The server starts **once per run**, at the first `task` that needs it, and ends
with the run:

```
{"ts":"2026-09-25T16:15:01.869Z","type":"mcp_server","server":"filesystem","action":"started","duration_s":0.753,"stderr_file":"mcp/filesystem.stderr.log"}
{"ts":"2026-09-25T16:15:11.007Z","type":"mcp_server","server":"filesystem","action":"stopped","stderr_file":"mcp/filesystem.stderr.log"}
```

What the server printed is in `mcp/filesystem.stderr.log` — look here when the
server does not start:

```
Secure MCP Filesystem Server running on stdio
Client does not support MCP Roots, using allowed directories set from server args: [
  '/home/…/runs/20260925-161501-tutorial-06-archive-dfec/work'
]
```

The second line confirms that the server sees only the `work/` of this run.

---

## Step 9 — where the framework stops you

To experiment, work in a copy so you do not break your files:

```bash
rm -rf /tmp/experiment && mkdir -p /tmp/experiment && cp -r workflows /tmp/experiment/
```

### Before the run: `validate`

The step wants a tool the agent does not have — in the copy of the scenario add
the line `tools: { filesystem: [write_file, move_file] }` to the `write` step:

```
config: tutorial-06-archive.yaml: step "write", task.tools: step requests tool filesystem.move_file, which agent 'tutorial-archivist' does not allow (tools.filesystem)
```

The agent wants a tool the owner has not allowed — in the copy of the agent add
`edit_file` to `tools.filesystem`:

```
config: agents/tutorial-archivist.md: the project owner has not allowed tools edit_file on server 'filesystem' (mcp.yaml → servers.filesystem.tools: list_allowed_directories, list_directory, read_text_file, write_file)
```

The step wants more turns than the agent allows (`max_turns: 10`):

```
config: tutorial-06-archive.yaml: step "write", task.max_turns: 10 exceeds limits.max_turns of agent 'tutorial-archivist' (6) — steps may only lower limits
```

An agent with `mcp` but without `tools`, or without `limits.max_turns`:

```
config: agents/tutorial-archivist.md: field 'mcp' requires 'tools' — an explicit list of tools for each server: tools: { filesystem: [tool, …] }; plan.md from agencast run <scenario> --dry-run lists the tools offered by each server
config: agents/tutorial-archivist.md: limits: missing required field 'max_turns'
```

(After each experiment, restore the file in the copy from `workflows/`.)

### At run time: fixtures in `/tmp`

What if the model calls a tool it does not have? The server can do `move_file`,
but the agent has not allowed it. `/tmp/not-allowed.yaml`:

```yaml
write:
  - tool_calls:
      - { name: filesystem__move_file, arguments: { source: a.md, destination: b.md } }
      - { name: filesystem__write_file, arguments: { path: a.md } }
  - text: "I wrote nothing."
```

```bash
agencast run /tmp/experiment/workflows/scenarios/tutorial-06-archive.yaml -i day=2026-09-25 -i text="It rained." --fake /tmp/not-allowed.yaml
```

The run finishes (`succeeded`) and both attempts are in `events.jsonl`:

```
{"type":"tool_call","step":"write","turn":1,"server":"filesystem","tool":"move_file","allowed":false,"invalid_args":false,"is_error":false,…}
{"type":"tool_call","step":"write","turn":1,"server":"filesystem","tool":"write_file","allowed":true,"invalid_args":true,"is_error":false,…}
```

Instead of a result, the model received an error (from `calls/02.tool.json` and
`03.tool.json`):

```
Error: tool filesystem__move_file is not allowed. Allowed: filesystem__list_allowed_directories, filesystem__list_directory, filesystem__read_text_file, filesystem__write_file, load_skill
Error: arguments did not match the tool schema: root: missing required field 'content'
```

Neither tool ran. The run does not fail because of it — the model can correct
itself.

An agent that goes in circles. `/tmp/looping.yaml` (the last response repeats,
so the model keeps calling tools):

```yaml
write:
  - tool_calls:
      - { name: filesystem__list_directory, arguments: { path: . } }
```

```
budget in step write: max_turns 5 exhausted without a final answer (model keeps calling tools)
run 20260929-190106-tutorial-06-archive-4044: failed · 0.8 s · 0.0005 USD
```

The tools ran in 4 turns, the fifth model response wanted another one — end,
class `budget`.

An expensive agent. `/tmp/expensive.yaml` — every turn costs 0.02 USD (`cost`
is supported only by the fake provider):

```yaml
write:
  - cost: 0.02
    tool_calls:
      - { name: filesystem__list_allowed_directories, arguments: {} }
```

```
budget in step write: budget for step 'write' exhausted (0.0400 of 0.03 USD)
```

and in `summary.md`:

```
## Warnings
- budget for step 'write' exceeded by 0.0100 USD (step write)
```

Turn 1 cost 0.02 (under the 0.03 limit), so turn 2 was started. That one
exceeded the limit — it completes and is paid for (a warning), but no further
turn starts. `budget_usd` is therefore a boundary that can be crossed by at
most one turn.

---

## Step 10 — the same agent in `ask`

An agent with tools can also be used in `ask` — then it has no tools and the MCP
server does not start at all. But the model needs the skill, and it cannot call
`load_skill`. So the framework inserts it **in full**.
`/tmp/experiment/workflows/scenarios/tutorial-06-ask.yaml`:

```yaml
version: 1
name: tutorial-06-ask
description: The same agent in an ask step (no tools)
steps:
  - id: advice
    ask:
      agent: tutorial-archivist
      prompt: "What will the entry for 2026-09-25 look like with the note: It rained in the morning."
```

```bash
agencast run /tmp/experiment/workflows/scenarios/tutorial-06-ask.yaml --fake
```

`steps/01-advice/prompt.md`:

```
# System prompt

You are an archivist. You have access to a single folder — find it with the
…
## Skill: tutorial-entry

The archive has two files, both directly in the allowed folder:

1. `<day>.md` — the entry for one day (`<day>` is the date from the prompt, e.g. `2026-09-25.md`):
…
```

Instead of the line `- tutorial-entry: …` under `## Skills` there is the whole
body under `## Skill: tutorial-entry`. There is no `mcp_server` in
`events.jsonl`. (The model receives the instructions about tools here too, but
it has no tools — an agent written for `task` belongs in `ask` only for
experiments.) The consequence: with `ask` you pay for every skill in full,
every time; with `task` only for those the model actually loads.

---

## What you have learned

- `ask` = one answer; `task` = a loop of turns with tools, at most
  `max_turns`, all within `budget_usd`.
- Permissions: owner (`mcp.yaml`: `agents`, `tools`, `scenarios`) →
  agent (`mcp`, `tools`, `limits`) → step (narrowing only). You cannot write
  yourself a permission from the agent.
- `--dry-run` starts the server and prints what it offers.
- The record: `tool_call` (`allowed`, `invalid_args`, `is_error`),
  `calls/NN.tool.json`, `mcp_server`, `mcp/<server>.stderr.log`, `work/`.
- A skill in `task` = a line in the prompt + `load_skill` (`server: "_skills"`);
  in `ask` the whole body.
- Do not take an agent with tools at its word — the record shows what it really did.

---

## Exercise

Split the work into two `task` steps with the same agent: `write` may only
find the folder and write (`list_allowed_directories`, `write_file`),
`check` may only read (`list_allowed_directories`, `list_directory`,
`read_text_file`) and reports whether the files match the skill. Save the
scenario as `workflows/scenarios/tutorial-06-exercise.yaml`, write a fixture
and verify that the check really does not have `write_file`.

<details>
<summary>Solution</summary>

`workflows/scenarios/tutorial-06-exercise.yaml`:

```yaml
version: 1
name: tutorial-06-exercise
description: The archivist writes a note, a second step checks it read-only (tutorial, part 6 — exercise solution)

inputs:
  day:
    type: string
    required: true
    description: Date of the entry, e.g. 2026-09-25
  text:
    type: string
    required: true
    description: The note as free text

outputs:
  write:
    type: string
    description: What the write step reports
  check:
    type: string
    description: What the check step reports

steps:
  # 1. Writing: the step narrows the tools — there is no need to read or list the folder here.
  - id: write
    task:
      agent: tutorial-archivist
      prompt: |
        Day: {{ inputs.day }}
        Note: {{ inputs.text }}
        Write the note to the archive. Do not read or check anything, a colleague will do that.
      max_turns: 3
      tools:
        filesystem: [list_allowed_directories, write_file]

  # 2. Read-only check: the same agent, the same server (it runs once per run),
  #    but without write_file — it cannot fix anything, only report.
  - id: check
    task:
      agent: tutorial-archivist
      prompt: |
        Your colleague reports: {{ steps.write.text }}
        Read the entry for {{ inputs.day }} and the archive index. Do NOT write or fix anything.
        Say how many sentences the entry has and whether both files match the skill.
      max_turns: 4
      tools:
        filesystem: [list_allowed_directories, list_directory, read_text_file]

  - id: out
    output:
      write: "{{ steps.write.text }}"
      check: "{{ steps.check.text }}"
```

`fake/tutorial-06-exercise.yaml`:

```yaml
# Scripted responses for tutorial-06-exercise (exercise solution from part 6).
# Two task steps, each with its own list of turns. The check step reads the files
# written by the write step — the MCP server (fake in tests) runs once per run.
write:
  - tool_calls:
      - { name: filesystem__list_allowed_directories, arguments: {} }
      - { name: load_skill, arguments: { name: tutorial-entry } }
  - tool_calls:
      - name: filesystem__write_file
        arguments: { path: 2026-09-25.md, content: "# Entry 2026-09-25\n- It rained in the morning.\n- In the afternoon we finished part 6.\n" }
      - name: filesystem__write_file
        arguments: { path: index.md, content: "# Index\n- 2026-09-25: It rained in the morning.\n" }
  - text: "Written: 2026-09-25.md and index.md."
check:
  - tool_calls:
      - { name: load_skill, arguments: { name: tutorial-entry } }
      - { name: filesystem__read_text_file, arguments: { path: 2026-09-25.md } }
      - { name: filesystem__read_text_file, arguments: { path: index.md } }
  - text: "The entry has 2 sentences, both files match the skill."
```

```bash
agencast run tutorial-06-exercise -i day=2026-09-25 -i text="It rained in the morning. In the afternoon we finished part 6." --fake fake/tutorial-06-exercise.yaml
```

```
| 1 | write | task | ✓ | 0.9 s | 0.0003 | smart → anthropic/claude-haiku-4.5, turns 3, tools 4 |
| 2 | check | task | ✓ | 0.0 s | 0.0002 | smart → anthropic/claude-haiku-4.5, turns 2, tools 3 |
| 3 | out | output | ✓ | 0.0 s | 0 |  |
| | Total | | | 0.9 s | 0.0005 |  |
```

The check took 0.0 s even with the server: it has been running since the first
step (`mcp_server started` is in `events.jsonl` only once, with 0.9 s for the
start). The tools the model received in the `check` step
(`steps/02-check/calls/01.request.json`):

```
['filesystem__list_allowed_directories', 'filesystem__list_directory', 'filesystem__read_text_file', 'load_skill']
```

`write_file` is not there — if the model called it anyway, it would get
"tool is not allowed" (step 9).

```bash
cd ../../framework && uv run pytest -k tutorial-06 -v; cd ../examples/tutorial
```

```
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-06-archive] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-06-exercise] PASSED
```

</details>

---

## What comes next

**[Part 7 — Composition and operations](07-composition-and-operations.md):** a scenario
calls a scenario (`call`), `agencast serve` for n8n (token, `request_key`, a
callback with a signature), `report.html` and `dedupe_key` for steps that may
run only once.
