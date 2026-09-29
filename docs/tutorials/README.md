# `agencast` tutorials

Seven parts, from the first agent to running behind a webhook. Each part builds
on the previous ones, has real outputs from runs and ends with an exercise with
a solution. Run the commands in the parts from `examples/tutorial` (`cd examples/tutorial` from the clone root).

From an installed package (without a clone), start like this:

```bash
agencast new project ~/agencast-tutorial --example tutorial
cd ~/agencast-tutorial
agencast docs show tutorials/01-first-agent-and-scenario.md
```

Then run the commands from that folder; the fixtures are in `fake/`.
The framework tests via `uv run pytest` require a clone; individual fake runs do not.

The solutions are the `tutorial-0N-*` files in `examples/tutorial/workflows/` and
the fixtures in `examples/tutorial/fake/` — they are also golden tests
(`cd framework && uv run pytest`).

| Part | Time | Spend | What you will learn |
|---|---|---|---|
| [1 — First agent and first scenario](01-first-agent-and-scenario.md) | 15 min | ~0.0002 USD | agent, one-step scenario, `validate`, `--dry-run`, `--fake`, the run folder, first live run |
| [2 — Chaining steps](02-chaining-steps.md) | 15 min | ~0.0008 USD | `{{ steps.… }}`, `schema`, `set`, `output`, what if the model breaks the JSON, `validate` messages |
| [3 — Decisions](03-decisions.md) | 20 min | ~0.0007 USD | Jev, `when` + `fail`, `switch`, `default`, expression rules |
| [4 — Parallel steps and an image](04-parallel-and-image.md) | 20 min | ~0.07 USD | `parallel`, the `image` step, error classes, `budget_usd` and `timeout` |
| [5 — From playground to production](05-from-playground-to-production.md) | 20 min | 0 USD | swapping a model in `config.yaml`, golden tests, the record in depth, `--callback-url` and the signature |
| [6 — An agent with tools](06-agent-with-tools.md) | 30 min | ~0.014 USD | the `task` step, turns and `max_turns`, `mcp.yaml` (owner) × agent (author), skills and `load_skill`, the `tool_call` record |
| [7 — Composition and operations](07-composition-and-operations.md) | 35 min | 0 USD (+ optionally ~0.001) | `call` and building blocks, `agencast serve`, 401/422/202, `request_key`, callback, `report.html`, `dedupe_key`, what n8n needs |

Parts 1–5 were written with `maw` 0.1.0, parts 6 and 7 with `maw` 0.2.1 (up to
0.2.5 the package and the command were called `maw`, from 0.3.0 `agencast`; the
commands in the text already use the new name). The outputs of the commands were
later checked against the current CLI (`validate --offline`, `--dry-run` and
`--fake` re-run in a scratch copy of `examples/tutorial`) and rewritten in its
current format: English status texts, decimal points, ISO dates and the model
aliases `smart` and `fast`. The `run_id`s and timestamps come from the original
runs of 25 Sep 2026. The times are an estimate for a first pass;
the spend is for the live runs in the part (OpenRouter prices from 25 Sep 2026).

More files:

- [`callback-receiver.py`](callback-receiver.py) — a local callback receiver
  with signature verification (part 7).
- [`BUGS.md`](BUGS.md) — framework bugs found while writing the tutorials.
