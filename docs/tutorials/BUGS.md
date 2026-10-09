# Framework bugs found while writing the tutorials (maw 0.1.0)

An archive of development findings: up to 0.2.5 the package and the command were called `maw`; older records here keep the historical name and commands.

All six are fixed in maw 0.2.1 (branch `fix-tutorial-bugs`, see
`../../framework/CHANGELOG.md`); each item has the fixing commit and a test.
The original description stays below. The commands are run
from the `examples/tutorial` project, `maw` = `uv run --project ../../framework maw`. The
fixtures from `/tmp` are given with each item.

## 1. A false "no cost returned" warning after an HTTP error (medium)

**Fixed in 0.2.1 (commit 7dd0d00).** The warning only for a successful response without `usage.cost`; test `test_http_error_without_usage_no_cost_warning` (429 and 400).

A call that ends with an HTTP error (429, 400) has no `usage` — and costs
nothing. The framework nevertheless writes a warning, as if the cost were
missing from a successful response. Live, OpenRouter returns a body without
`usage` for 429 too, so the warning shows up in live runs after every overload.

Reproduction — `/tmp/overload.yaml`:

```yaml
propose:
  - status: 429
    error: "Rate limit exceeded"
  - json:
      names: ["Oatsy", "Frost Oat", "Frozen Field"]
```

```bash
maw run workflows/scenarios/tutorial-04-parallel.yaml -i product="ice cream" --fake /tmp/overload.yaml
```

Expected: the run `succeeded`, no warnings (a retry after `transient` is
normal). Actual (`summary.md`):

```
## Warnings
- step propose: provider returned no cost (usage.cost) — budget cannot be tracked precisely
```

Likewise after HTTP 400 (fixture `propose: [{status: 400, error: "Invalid request"}]`).
The spec (scenario.md §6 Budget, run-record.md `usage`) talks about a missing
cost in a response, not in an error status.

## 2. The second message reveals Python internals (minor)

**Fixed in 0.2.1 (commit d5bf1bb).** Only the first message, now with a caret; test `test_template_in_expression_one_error`.

`{{ }}` in an expression (`set`, `when`) gives two messages; the second talks
about a Python AST node that a beginner does not understand:

```bash
# in tutorial-02-name-and-slogan.yaml in the step summary: count: "{{ steps.propose.names }}"
maw validate workflows/scenarios/tutorial-02-name-and-slogan.yaml
```

```
config: tutorial-02-name-and-slogan.yaml: step "summary", set.count: template {{ }} is not allowed here — allowed only in prompt, jev.state, jev.questions (instructions, criteria), fail, output values, call.inputs and dedupe_key
config: tutorial-02-name-and-slogan.yaml: step "summary", set.count: construct 'Set' is not allowed in expressions
  {{ steps.propose.names }}
  ^
```

Expected: only the first message (with a caret). In Python `{` is read as a set
(`Set`), hence the second one.

## 3. The message about a model id in an agent does not say "alias" (minor)

**Fixed in 0.2.1 (commit b1dcbc1).** A message about an alias instead of a regex, schema unchanged; test `test_agent_model_id_instead_of_alias`.

```bash
# in workflows/agents/tutorial-namer.md: model: anthropic/claude-haiku-4.5
maw validate workflows/scenarios/tutorial-01-names.yaml
```

```
config: agents/tutorial-namer.md: model: value does not match the pattern ^[a-z][a-z0-9-]*$
```

Expected (agent.md: "never a concrete model id"): a message like the one for
an unknown alias, e.g. `model 'anthropic/claude-haiku-4.5' is not an alias in
config.yaml (aliases: smart, fast, gemini-image)`. A regex is
incomprehensible to a beginner, and this is the most common mistake of a new
agent.

## 4. A YAML error without a hint (minor)

**Fixed in 0.2.1 (commit 2447fd4).** A sentence with a hint and the line, the parser message on the second line; test `test_yaml_syntax_error_english_hint`.

```bash
# in tutorial-03-decisions.yaml: when: {{ steps.check.memorable }} < 0.5
maw validate workflows/scenarios/tutorial-03-decisions.yaml
```

```
config: tutorial-03-decisions.yaml, line 56: expected <block end>, but found '<scalar>'
```

The line number is fine; the rest is the raw parser message. The same for
`mapping values are not allowed here` in a `description` with `: ` inside.
Proposal: add a hint ("a value with `{`, `[`, `: ` or ` #` belongs in
quotes", scenario.md §5 "YAML pitfalls").

## 5. Wrong plural form of the step count in `validate` (cosmetic)

**Fixed in 0.2.1 (commit 1c28c4d; outputs in the tutorials 31b1d5e).** The count now goes through one helper with a singular and a plural form (`1 step`, `2 steps`); it is also used by `serve` ("2 runs queued") and by the note of a `call` step in `summary.md`; test `test_step_count_english_plural`.

```bash
maw validate workflows/scenarios/tutorial-01-names.yaml
```

At the time the message was written in Czech, and the step count of a scenario with two steps was printed with the plural form meant for five or more steps. Czech has three plural forms (one, two to four, five or more), and the code used the last one for every count above one. The message is English now, so the bug can no longer be reproduced; the current output is `valid: tutorial-01-names (2 steps)`. `../../framework/src/maw/cli.py`, `cmd_validate`.

## 6. Golden tests do not read `workflows/config.yaml` (medium, verified by reading the code)

**Fixed in 0.2.1 (commit f04a099).** The test config takes the aliases from the real `config.yaml`; test `test_owner_alias_reaches_golden_tests` (a temporary alias `cheap` only in the test).

`../../framework/tests/conftest.py` has a fixed test `CONFIG` with the aliases
`smart`, `fast`, `gemini-image`, and the `wf` fixture writes it instead of
the real `config.yaml`. When the owner adds a new alias to `workflows/config.yaml`
(e.g. `cheap`) and an agent uses it, `maw validate` passes, but
`test_workflow_agent_valid` and `test_workflow_scenario_runs_with_fake`
fail with "model 'cheap' is not an alias in config.yaml".

Not run — it would require a change of `config.yaml`, which only the owner may
make. Reproduction for the owner: add an alias to `config.yaml`, an agent using
it to `workflows/agents/`, `cd ../../framework && uv run pytest -k
<agent>`. Proposal: derive the test config from `workflows/config.yaml`
(take the aliases, override `base_url`/limits for testing).

---

# maw 0.2.1 — findings from parts 6 and 7

Found on 2026-09-25 while writing parts 6 and 7 against `maw` 0.2.1 (branch
`tutorials-6-7`). `../../framework/src` unchanged; the numbering continues.
`maw` = `uv run --project ../../framework maw`, commands from the `examples/tutorial` project.

All three points are fixed in maw 0.2.2 (branch `fix-0.2.2`, see
`../../framework/CHANGELOG.md`); each item has the fixing commit and a test.

## 7. `task` with `schema` and `native_schema`: Haiku ends the loop without tools (medium)

**Fixed in 0.2.2 (commit 26e0d29).** Coordinator's decision: in `task`, structured output is always enforced by `_submit_output` (level `tool_wrapper`), `response_format` is not sent; the alias `structured_output` applies only to `ask`; interpretation ISSUES 36. Test `test_schema_always_tool_wrapper_and_cascade_to_prompt`. Not verified live (no live runs) — it relies on the control run with `tool_wrapper` in the table below.

With a `schema` on a `task` step and an alias at the level `native_schema` (`smart`
= `anthropic/claude-haiku-4.5`), the framework sends `response_format`
(`json_schema`, `strict`) in **every** turn together with `tools`
(`task.py` → `task_body`). Haiku then often answers directly with JSON
matching the schema instead of calling tools — with invented content. The loop
ends in "success" (spec: a response without a tool call = the end), the side
effect does not happen and nothing reports it.

Three live runs of the scenario `tutorial-06-archive` in a version with
`schema: {files: [string], lines: integer}` (agent `tutorial-archivist`):

| Run | Instructions | Result | Cost |
|---|---|---|---|
| `runs/20260925-161001-tutorial-06-archive-9a8f` | the first version of the agent | turn 1 `load_skill` + `list_allowed_directories` (provider Anthropic), turn 2 JSON (`stop`, Amazon Bedrock); `work/` does not exist, output `files: [" /…/work/2026-09-25.md"], lines: 4` | 0.0046 USD |
| `runs/20260925-161101-tutorial-06-archive-fee2` | an agent with a numbered procedure "never reply before you have written" | turn 1 `list_allowed_directories`, turn 2 JSON `files: ["2026-09-25.txt"]`; nothing written | 0.0040 USD |
| `runs/20260925-161129-tutorial-06-archive-67a6` | plus the procedure in the step's `prompt` | turn 1 straight JSON (0 tools, 1,818 output tokens for 58 characters, 75.8 s) | 0.0108 USD |

A control in a copy of the project (`/tmp/exp`, the owner's files in
`workflows/` unchanged), same input:

| Variant | Result | Cost |
|---|---|---|
| the same scenario **without `schema`** | 5 turns, 7 tools, both files correct | 0.0171 USD |
| with `schema`, alias `smart` with `structured_output: tool_wrapper` | 5 turns, 8 tools, both files correct; the final turn returned text instead of `_submit_output` → error `schema` → cascade to `prompt`, the 2nd attempt valid | 0.0215 USD |

`demo-task` (librarian, the same mechanism) passed in Phase 3a, so it is
a probability, not a certainty — but 3 out of 3 is enough for a beginner to run
into it. The tutorial therefore does not use `schema` with `task` and explains
why (part 6, "Watch out for schema in task").

Reproduction (~0.005 USD): in the step `write` in a copy of
`tutorial-06-archive.yaml` add `schema: {files: [string], lines:
integer}` and point `output` at these fields, `maw run … -i day=2026-09-25 -i
text="It rained in the morning and the train was late. In the afternoon we finished the sixth part
of the tutorial. In the evening we took it live."`, and in `summary.md` watch
`tools N` and whether `work/` exists.

Options (a decision for the coordinator/owner, not for the tutorial):
in `task`, start the cascade at `tool_wrapper` (the result via `_submit_output`,
in turns without `response_format`); or do not send `response_format` in
`task` and enforce the schema only by checking the final response; or just a
recommendation to the owner (`structured_output: tool_wrapper` on the alias for
agents with tools — but it changes `ask` too). The spec (scenario.md, cascade)
does not address this combination.

## 8. `--fake` writes to the same `runs/_dedupe/` as live runs (high)

**Fixed in 0.2.2 (commit cf5c31d).** A fake run has its own `<runs>/_dedupe-fake/`, the modes are not read crosswise; `run_started.fake`, a "Fake run" line in `summary.md` and `report.html`. Test `test_dedupe_fake_and_live_do_not_share_state` (fake → live → fake over the same `runs/`). Old fake records in `_dedupe/` from 0.2.1 are not deleted by the fix.

A fake run of a step with a `dedupe_key` creates `_dedupe/<sha>.json` with
`state: succeeded` and a **fake** output. The next live run with the same key
skips the step and returns the fake output as a real one — `succeeded`, 0 model
calls, and neither the callback nor `summary.md` shows that the output comes
from a fake run. For publishing (`ig-publish`) this would mean: after a
rehearsal with `--fake`, the post is never published live and the caller receives an
invented `post_url`.

```bash
maw serve --fake fake/tutorial-07-archive.yaml     # or maw run … --fake
# POST /runs: {"scenario": "tutorial-07-archive", "inputs": {"day": "2026-09-25", "text": "…"}, …}
maw run tutorial-07-archive -i day=2026-09-25 -i text="Live entry."   # without --fake
```

```
run 20260925-161909-tutorial-07-archive-1c51: succeeded · 0.0 s · 0 USD
…
{"type":"step_skipped","step":"write","kind":"task","reason_code":"dedupe","reason":"dedupe_key 'archive-2026-09-25': step already ran in run 20260925-161842-tutorial-07-archive-5637","default_used":false}
- message: “Written: 2026-09-25.md and index.md. The entry has 2 sentences.”
```

(The run `…-5637` was fake, through `maw serve --fake`; verified in a copy of
the project `/tmp/t7`.) Expected: a fake run does not affect the live dedupe
(its own `_dedupe`, or a record with a `fake` flag that the live run
ignores). The spec (scenario.md §3 dedupe) does not mention a fake run.
The tutorial warns about it (part 7, step 8).

## 9. Small things (cosmetic)

**Fixed in 0.2.2 (commit 0459c67).** Tests `test_agent_without_tools_list_and_without_max_turns` and `test_422_all_errors_at_once`.

- `validate` for an agent with `mcp` and without `tools` reports only
  `config: agents/tutorial-archivist.md: with the field 'mcp', 'tools' is required too`.
  agent.md promises that `validate --dry-run` lists the offered tools;
  the message could name the server and advise `--dry-run`.
- `POST /runs` with an unknown field **and** a wrong input type returns 422 with
  only the first group of errors (`unknown field 'priority' …`); the input error
  (`input 'product' must be string, got number`) arrives only on the second
  attempt. The spec does not require it, but it would save the caller a round.
