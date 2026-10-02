# Open questions on the v1 specification

A historical record of decisions; it is not a list waiting for new approval.
The v1 spec is approved and frozen per [DESIGN, R8 and §5.9](../DESIGN.md)
and the [contributor guidelines](../../CLAUDE.md). All 14 choices below are part of the
valid v1; the original recommendations and alternatives stay as context.
A separate record of user consent for each item is not documented here;
the status follows from the approval of the whole v1, not from votes worked out after the fact.
[Independent review, Status of fixes](REVIEW.md#status-of-fixes) documents how the findings were incorporated.

### 1. `prompt` instead of `task` inside the `ask` step

**Status: part of the approved v1** ([DESIGN §5.9](../DESIGN.md)); current wording: [scenario.md §4, `prompt`](scenario.md).

DESIGN §6 writes `ask: { agent, task: "…" }`. But the word `task` is also a
step type, so in a scenario it would mean two different things.
**Recommendation:** `prompt` (the same for `ask`, `task` and `image`).

### 2. `schema` inside `ask`/`task`, not as a property of every step

**Status: part of the approved v1** ([DESIGN §5.9](../DESIGN.md)); current wording: [scenario.md §4, `schema`](scenario.md).

D1d lists `schema` among the properties of any step, §6 writes it inside
`ask`. It only makes sense for steps with a model that returns text.
**Recommendation:** inside `ask`/`task` (as in §6).

### 3. `budget_usd` instead of `budget`

**Status: part of the approved v1** ([DESIGN §5.9](../DESIGN.md)); current wording: [scenario.md §3, `budget_usd`](scenario.md).

D1d names the step property `budget`, D1a `limits.budget_usd` on an agent.
One word for one thing.
**Recommendation:** `budget_usd` everywhere (the unit is visible in the name).

### 4. Scenario output: `outputs` in the header + `output` as the last step

**Status: part of the approved v1** ([DESIGN §5.9](../DESIGN.md)); current wording: [scenario.md, the header and `output`](scenario.md).

§5.3 wants a scenario to declare `outputs`. The spec solves this with a header
(types) and an `output` step (values), which may appear only once and only at
the end — not inside `switch`/`parallel` branches. Different results depending on the branch are
handled with `default` and `set`.
**Recommendation:** yes, like this. A scenario then reads “at the top what it returns, at the bottom
where it takes it from”.

### 5. New error classes `fail` and `internal`

**Status: part of the approved v1** ([DESIGN §5.9](../DESIGN.md)); current wording: [scenario.md §6, error classes](scenario.md).

§5.1 knows `transient`, `schema`, `content`, `budget`, `timeout`, `config`.
A deliberate `fail` step and an error of the framework itself belong to none of them, and
the callback could not otherwise tell them apart from a provider failure.
**Recommendation:** add both.

### 6. A server in `mcp` without an entry in `tools` — **resolved**

**Status: part of the approved v1** ([DESIGN §5.9](../DESIGN.md)); current wording: [DESIGN §5.8](../DESIGN.md) and [REVIEW, B2](REVIEW.md#status-of-fixes).

The original recommendation (“all tools”) contradicted DESIGN §5.8 (an allowlist
by name; a new tool that the server adds must not be seen by the agent).
**Decided per DESIGN §5.8 (coordinator, 2026-09-25):** every server
from an agent's `mcp` must have an explicit list in `tools`; a server without an entry is
a `config` error; `run --dry-run` prints the tools the server
offers. In addition the owner in `mcp.yaml` determines `agents`, `scenarios` and the upper
`tools` of the server.

### 7. Literals in expressions: `true` / `false` / `null`

**Status: part of the approved v1** ([DESIGN §5.9](../DESIGN.md)); current wording: [scenario.md §5, literals](scenario.md).

D1c says “Python-style expressions”, but Python writes `True`, `False`,
`None`. The user, however, sees the same values in YAML, JSON and the run record
as `true` / `false` / `null`.
**Decided (coordinator, 2026-09-25):** `true` / `false` / `null`.
So `x == null` and `str(null)` = `"null"` apply.

---

Questions 8–10 came from spike (c) (the report on the `spike-expressions` branch; the spike was removed from the tree,
its outputs are in the repository history up to commit fe90e05). The coordinator decided them and the spec is written accordingly;
their current status is part of the frozen v1.

### 8. `and` / `or` / `not` only over `true` / `false`

**Status: part of the approved v1** ([DESIGN §5.9](../DESIGN.md)); current wording: [scenario.md §5, operators](scenario.md).

Python also accepts the “truthiness” of other values (empty text or list =
false, `0` = false). The spec forbids this: `steps.copy.hashtags and …`
is an error with the advice to write `len(steps.copy.hashtags) > 0`. In a scenario
it is thus always visible what a condition asks about.
**Default choice:** only `true`/`false`. Alternative: Python truthiness.

### 9. `round` rounds half away from zero

**Status: part of the approved v1** ([DESIGN §5.9](../DESIGN.md)); current wording: [scenario.md §5, the `round` function](scenario.md).

Python rounds half to even (`round(2.5)` = `2`, `round(3.5)` = `4`).
The spec defines school rounding: `round(2.5)` = `3`, `round(-2.5)` =
`-3` — an explicit deviation from Python.
**Default choice:** half away from zero. Alternative: like Python.

### 10. `null` in a template is an error

**Status: part of the approved v1** ([DESIGN §5.9](../DESIGN.md)); current wording: [scenario.md §5, templates](scenario.md).

`{{ x }}` where `x` is `null` is not inserted silently: an error in `validate`
(`config`) when it can be detected in advance, otherwise at run time (`expression`).
Exception: `null` from a step's explicit `default` is inserted as `null` (in text
as `null`).
**Default choice:** an error, with an exception for an explicit `default`.
Alternative: always insert the text `null` (nothing fails, but a missing value
may silently make its way into the prompt or the callback).

---

Questions 11–14 came from the independent review (`REVIEW.md`, findings B1, B4,
M10). The recommendations are incorporated in the frozen v1.

### 11. Skills in `ask` are inserted whole

**Status: part of the approved v1** ([DESIGN §5.9](../DESIGN.md)); current wording: [agent.md, system prompt](agent.md) and [REVIEW, B1](REVIEW.md#status-of-fixes).

For `task` the system prompt carries only a list of skills and the model loads the body
with the `load_skill` tool (DESIGN §5.8). `ask` is a single call without tools,
so `load_skill` cannot be used in it. The spec therefore inserts the skill bodies
whole into the system prompt for `ask`.
**Recommendation:** insert them whole. Alternative: forbid agents with skills in `ask`
(a `config` error).

### 12. `dedupe` as state shared between runs

**Status: part of the approved v1** ([DESIGN §5.9](../DESIGN.md)); current wording: [DESIGN D2 and §5.2](../DESIGN.md) and [REVIEW, B4](REVIEW.md#status-of-fixes).

D2: runs do not share files (except `state` and storage). But `dedupe_key`
must survive a run, otherwise it does not protect against double publishing. The spec therefore makes it
an exception like `state`: each key is a separate atomically created file
in `<runs>/_dedupe/`, never one shared log (concurrent writes thus
are not lost). A `started` state without `succeeded` stops the next run with a
“verify manually” prompt.
**Recommendation:** keep it (the main DESIGN already states this in D2 and §5.2).

### 13. `retry`, `timeout`, `on_error` only on some steps

**Status: part of the approved v1** ([DESIGN §5.9](../DESIGN.md)); current wording: [scenario.md §3, the property table](scenario.md) and [REVIEW, M10](REVIEW.md#status-of-fixes).

D1d gives `retry`, `timeout`, `budget`, `on_error` to “any step”.
The spec allows them only where they make sense (the table in scenario.md §3):
e.g. `retry` on `set` or `on_error` on `fail` means nothing, so
writing them is a `config` error, not a silently ignored field.
**Recommendation:** keep it (the main DESIGN already refines this in D1d with a reference to the
spec).

### 14. Comparison across types for unknown types only at run time

**Status: part of the approved v1** ([DESIGN §5.9](../DESIGN.md)); current wording: [scenario.md §5, type checking](scenario.md) and [REVIEW, M10](REVIEW.md#status-of-fixes).

§5.4 says that comparing across types is a **validation** error. But when the type
of a value cannot be known in advance (e.g. an element of Jev's `details` object), the spec
reports the error only at run time as class `expression`. Types known in advance
(`inputs`, `schema`, `jev`, `set`) are checked by `validate`.
**Recommendation:** keep it.
