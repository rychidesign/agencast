# Independent review of the v1 specification

A historical independent audit from 2026-09-25; the author did not write the specification.
Checked against `docs/DESIGN.md` from the main branch (v0.2 with §5.8 and the facts from
spikes (c) and (d)). Citations `DESIGN.md:<line>` refer to that
version of the time. The copy of `docs/DESIGN.md` in the reviewed snapshot did not have §5.8; that is where most of the
contradictions about skills, tools and MCP come from (B1, B2, D16–D19).
The findings capture the state of the specification at that time and are not a current list of defects.

Summary: **6 BLOCKING, 23 IMPORTANT, 12 MINOR**.

## How it was verified

- The examples against the schemas (`uvx check-jsonschema` 0.38.2): `ig-post.yaml`,
  the frontmatter of three agents, `config.example.yaml`, `mcp.example.yaml` → all `ok`.
- 27 deliberately faulty scenarios + 3 agents + 4 `mcp.yaml` + 2 `config.yaml`
  (in `/tmp/rv`, not part of the repository). The schema **lets through** even what the text
  forbids or does not define: a duplicate `id` (that is handled by `validate`, fine),
  `schema: string` and `schema: [string]` in `ask`, `outputs: {}`, `retry: 1000`,
  `tools` for a server that is not in `mcp`, `env: {LD_PRELOAD: …}` in `mcp.yaml`,
  `base_url: http://evil.example.com`, the same variable for the webhook token,
  the callback secret and the OpenRouter key.
- The same files loaded with **PyYAML** (the library from D4) + `jsonschema` — the results
  differ from `check-jsonschema` (ruamel, YAML 1.2), see B6.

---

## BLOCKING

### B1. Per the spec skills are inserted whole, DESIGN wants a list + `load_skill`
- **Where:** `agent.md:41`, `agent.md:58-75` vs. `DESIGN.md:347-350`; `DESIGN.md:61-63` (D1b).
- **What:** The spec builds the system prompt as “body + the whole text of every SKILL.md”
  and postpones loading on demand until later. Per §5.8 the system prompt carries only
  `name: description` and the body is loaded with the tool `load_skill(name)`. The format of
  `SKILL.md` (`name` + `description` in the frontmatter) is not defined by the spec and
  the schema for it is missing. Moreover per D1b `ask` has no tool loop, so
  `load_skill` cannot work in it, and the spec does not say what happens then.
- **Why:** It violates the binding §5.8. The behavior of `ask` with skills would be
  decided at random in code.
- **Proposal:** Write into `agent.md`: “For `task` the system prompt contains the body of the
  agent and a section `## Skills` with lines `- <name>: <description>`. The model gets the
  tool `load_skill(name)`, where `name` is an `enum` of the agent's skills. An unknown
  name returns an error with a list. The call counts as a turn and in the record there is
  a `tool_call` with `server: "_skills"`. For `ask` the skills are inserted whole (ask has no
  tools).” Add the last sentence to OPEN-QUESTIONS as question 11
  (alternative: forbid skills for `ask`). Add `docs/spec/skill.md` and
  `schema/skill.schema.json`: frontmatter `name` (= the folder name, kebab-case),
  `description` (required), nothing else; a non-empty body.

### B2. A server in `mcp` without `tools` = all tools, which contradicts an allowlist by name
- **Where:** `agent.md:43`, `OPEN-QUESTIONS.md:38-43`, `agent.schema.json:15-25` vs. `DESIGN.md:351-354`.
- **What:** The spec (and the recommendation for question 6) gives a server without an entry in `tools`
  all tools. §5.8 wants an allowlist by name. Spike (d) justifies it
  by “a new tool that the server adds (`list_changed`) is not seen by the agent”
  (the mcp-python spike report, line 171; the spike was removed from the tree,
  its outputs are in the repository history up to commit fe90e05). With the default “all”
  the agent will see a new tool, say `delete_media` after a server update.
- **Why:** It violates DESIGN §5.8. Question 6 was asked before §5.8 existed.
- **Proposal:** In `agent.md:43` write: “Every server from `mcp` must have an explicit
  list of tools in `tools`. A server without an entry is a `config` error.
  `validate --dry-run` prints the tools the server offers so that the list can be
  written.” Add `dependentRequired: {"mcp": ["tools"]}` to `agent.schema.json`.
  `validate` checks that the keys of `tools` = `mcp`. Mark question 6 as
  resolved per §5.8.

### B3. The structured-output cascade contradicts the step success rule
- **Where:** `scenario.md:207`, `scenario.md:221-223`, `scenario.md:253-254`, `scenario.md:702` vs. `DESIGN.md:279-284`, `DESIGN.md:136-138`.
- **What:** `ask` succeeds only with `finish_reason: stop` and `task` ends when the
  model answers without a tool call. But at level L2 (a tool as a wrapper) the
  correct answer is precisely a tool call (`finish_reason: tool_calls`). `ask`
  at L2 would therefore always fail and `task` would send the wrapper call to dispatch
  (which would reject it as a disallowed tool). The spec also does not say **when**
  the framework moves from L1 to L2/L3: in advance by alias, or after a `schema` error?
  And does the transition consume an attempt from `retry`?
- **Why:** The cascade is required by DESIGN (D3, §5.5). Per the text of the spec it cannot
  be programmed.
- **Proposal:** Add to `scenario.md` (after `:223`): “The cascade level starts at
  `models.<alias>.structured_output` from `config.yaml` (`native_schema` |
  `tool_wrapper` | `prompt`, default `native_schema`; set by the conformance
  scenario). After a `schema` error the next attempt goes one level down. An attempt counts toward
  `retry`. At the `tool_wrapper` level success is a call to the `_submit_output` tool
  with arguments that match `schema` (`finish_reason: tool_calls`). For `task`
  this call ends the loop. `_submit_output` is never dispatched to MCP and
  is not subject to the allowlist.” Add the `structured_output` field to `config.md` and
  `config.schema.json`.

### B4. `dedupe.jsonl` is a file shared between runs
- **Where:** `scenario.md:180-182` vs. `DESIGN.md:115-117` (D2).
- **What:** D2: “runs do not share files (except `state` and the output storage)”,
  so that parallel runs are possible. The spec introduces a single `<runs>/dedupe.jsonl` for all
  runs. A Modal Volume is at the last `commit()` (`DESIGN.md:184`), so two
  concurrent writes are lost.
- **Why:** It violates D2. At the same time it is the “once and only once” feature for publishing,
  where a lost write means a double post.
- **Proposal:** Add to OPEN-QUESTIONS the question “dedupe is shared state, an exception
  to D2 like `state`” and write in the spec: “Each key is a separate file
  `<runs>/_dedupe/<sha256(scenario + '/' + step_id + '/' + key)>.json`,
  created atomically (create only if it does not exist). Contents: the state
  (`started` | `succeeded`), `run_id`, the output.” For the `started` state see D7.

### B5. The webhook contract is missing: request, response, token, idempotency, queue position
- **Where:** `config.md:126-135`, `scenario.md:89-90`, `run-record.md:104` vs. `DESIGN.md:118-120`, `DESIGN.md:171-179`, `DESIGN.md:247-249`.
- **What:** The spec defines the callback but not the request to start a run: the URL,
  the header with the token, the body (`scenario`, `inputs`, `callback_url`,
  `request_key`) and the response (`run_id`, queue position per D2) are missing. Also missing is
  what a repeated `request_key` does (§5.2) and when validation happens. `scenario.md:89-90`
  returns an input error “immediately”, but D2 wants a callback **always**. When `validate`
  runs only after pick-up from the queue on Modal, the spec does not say whether
  a callback arrives.
- **Why:** Per the spec n8n cannot be connected. D2 and §5.2 both remain
  unfulfilled.
- **Proposal:** A new section `run-record.md#webhook` (or `webhook.md`):
  “`POST /runs`, header `Authorization: Bearer <token from webhook.token_env>`,
  body `{scenario, inputs, callback_url (https only), request_key?}`.
  Synchronously: 401 = token; 422 = an unknown scenario, inputs that do not match `inputs`
  or that failed `validate`. Then no `run_id` and no callback is created. Otherwise 202
  `{run_id, queue_position}`, where `queue_position` is computed by the framework
  (D5: Modal does not provide it) and may be `null`. A repeated `request_key` returns 200
  with the original `run_id` and no new run is created. From the assignment of `run_id` the callback
  is always sent, even when `validate` fails only after pick-up from the queue.”

### B6. PyYAML (D4) silently changes the meaning of a scenario, verification via check-jsonschema hid it
- **Where:** `scenario.md:62-63` (“a typo is an error”), `scenario.md:316`, `scenario.md:391-393`; `CHANGELOG.md:97-98`; `DESIGN.md:161` (pyyaml), `DESIGN.md:219` (§5.1).
- **What:** Measured (`yaml.safe_load`, PyYAML):
  `a: 4:5` → `245`; `on: x` and `yes: y` in one map → `{True: 'y'}` (the value
  of `on` silently vanished); a duplicate `when:` in a step → the last one wins, without an error
  (ruamel in check-jsonschema reports `DuplicateKeyError`). `cases: {yes: …}`
  passes the schema (`cases` has no `propertyNames`), the key is `True` and that branch
  never matches `value`, so the run silently ends in `default`. The spec solves this only
  with the advice “write it in quotes”.
- **Why:** The spec promises that a typo is an error and §5.1 says “nothing fails
  silently”. The schemas were verified with a different parser than the one the framework will use.
- **Proposal:** Add to `scenario.md` §1 (and similarly to `agent.md`, `config.md`):
  “Files are read as YAML 1.2 core schema: `true`/`false` are the
  only booleans (`yes`, `no`, `on`, `off` are text), `4:5` is text,
  a duplicate key in a map is a `config` error with a line number.” For the implementation
  (PyYAML stays) write a custom `SafeLoader` without the YAML 1.1 bool and
  sexagesimal resolvers and with a duplicate check. Add `"propertyNames": {"type": "string"}` to
  `scenario.schema.json:277-281`. Change `CHANGELOG.md:97-98`:
  verification must run with the same loader that the framework uses.

---

## IMPORTANT

### D1. An MCP server from `mcp.yaml` can be used by anyone who writes an agent
- **Where:** `config.md:141`, `agent.md:87-95` vs. `DESIGN.md:212-213`, `DESIGN.md:130-132`.
- **What:** Agents are written, per DESIGN §4, by “other people and agents”. Anyone can thus
  create an agent with `mcp: [instagram]` and publish. The owner in `mcp.yaml`
  determines only that the server exists, not who may use it.
  The rule “agent = maximum” protects only against the scenario author, not against the author
  of the agent.
- **Proposal:** Add a mandatory `agents: [publisher]` to `mcp.yaml` (which agents
  may use the server) and an optional `tools: [...]` (the owner's upper allowlist).
  `validate`: an agent with a server outside `agents` or with a tool outside the server's `tools`
  = a `config` error.

### D2. `call` and `task` with the `publisher` agent bypass human approval
- **Where:** `scenario.md:400-432`, `ig-post.yaml:3` vs. `DESIGN.md:123-124`.
- **What:** Approval takes place in n8n between the parts of a workflow. But nothing prevents a scenario
  from part 1 from calling the scenario of part 2 (`call: {scenario: ig-publish}`) or
  directly a `task` with the `publisher` agent. The post would then be published without
  approval.
- **Proposal:** Add `callable: false|true` to the scenario header, default
  `false`: `call` may target only a scenario with `callable: true`. Add to the agent
  `scenarios: [ig-publish]`, i.e. a list of scenarios that may use
  an agent with a side effect; when missing, anyone may. `validate` checks both.

### D3. A `file` value can come from text, can be `null` and the upload can fail
- **Where:** `scenario.md:103-108`, `scenario.md:151`, `scenario.md:480-486`, `config.md:106`.
- **What:** (a) `output` admits “fixed values”. For an output of type `file` one
  can thus write `image: "~/.env"` or `../../x` and the spec does not say that this
  is an error, so a file outside the run folder could go to public storage.
  (b) `default: { file: null }` (the example at `:151`) → `output.image` is
  `null`: is something uploaded, is `null` returned, or is it an error? (c) A failed upload
  of an image to R2 has no class or run state (`report_url` has a defined behavior,
  `outputs` do not).
- **Proposal:** To `scenario.md` §5 Types: “`file` arises only from an `image` step
  (and from tool images, D18). It cannot be created from text. Text in the place of
  `file` is a `validate` error. The path is always inside the run folder and the framework verifies it
  before uploading (`realpath`).” For `outputs`: “`file: null` from an explicit
  `default` goes to the callback as `null`.” For the upload: “A failed upload of a file
  from `output` = `transient` with retrying, then the run is `failed`, class `transient`,
  the `output` step.”

### D4. The filesystem server in the example sees the folders of all runs
- **Where:** `mcp.example.yaml:6-9`, `config.md:149-152` vs. `DESIGN.md:115-117`, `DESIGN.md:355`.
- **What:** The description says “in the run folder”, but the root is `/runs`, i.e. all runs
  including `_dedupe`, `inputs.json` and `callback.json` of other runs, and also for
  writing. §5.8 builds on the filesystem root as the second layer of permissions. The spec
  has no way to put the folder of the **current** run into `args`.
- **Proposal:** Add to `config.md` (`args`): “The only permitted substitution in
  `args` is `{run_dir}` (the absolute path of the current run's folder), any other `{…}`
  is a `config` error.” In the example write `args: ["@modelcontextprotocol/server-filesystem", "{run_dir}/work"]`.

### D5. A public `report.html` at a guessable address
- **Where:** `run-record.md:43-44`, `config.md:104-108` vs. `DESIGN.md:128-129`.
- **What:** The storage key is `<run_id>/…` and `run_id` is time + scenario name +
  4 hex characters (65,536 possibilities). The bucket is public (because of Instagram), so
  `report.html` with all prompts, answers and tool results can be found
  by trying. The same applies to unapproved images.
- **Proposal:** Change `config.md:106` to: “The key = `<run_id>-<32 random hex
  characters>/<name>.<extension>`. The random part is created at run start and is only
  in the callback and in the record.” (Alternative: `report.html` to a non-public
  prefix and a presigned URL in the callback.)

### D6. Secret values can get into the record through a tool result
- **Where:** `run-record.md:57-66` vs. `DESIGN.md:240-242`; spike (d) `REPORT.md:94-96` (the `get-env` tool returns the server environment).
- **What:** An MCP server gets a key through `env` and its tool can return it
  (debug, an error message). The value then ends up in the model's context,
  in `calls/NN.tool.json` and in the public `report.html`. The spec forbids only
  request headers.
- **Proposal:** Add to `run-record.md` §“What never belongs in the record”: “Before
  writing every record file and the callback, the framework replaces every occurrence
  of the value of any variable from the `*_env` and `env` fields (length ≥ 8 characters) with the text
  `<secret: NAME>` and writes a warning.”

### D7. `dedupe_key` does not protect when a step fails only after the side effect, and keys get mixed between scenarios
- **Where:** `scenario.md:166` vs. `DESIGN.md:248-249`.
- **What:** A record is created only after a **successful** step. When `publish_media`
  runs and the step then fails (budget, timeout, `schema` of the final answer),
  n8n repeats the run and the post goes out twice. The key is also not bound to the
  scenario and step, so the same key text in another scenario returns the foreign output
  of a different shape.
- **Proposal:** “A `started` record is created before the first call of the step's tool.
  When on the next run a `started` exists without `succeeded`, the step does not start:
  an error of class `config` with the message ‘step may have run only partially; verify
  manually and delete <file>’. The key is stored together with the scenario name and the `id`
  of the step.”

### D8. Budget: the last call, concurrent branches and a missing cost
- **Where:** `scenario.md:162`, `scenario.md:705-706`, `run-record.md:93-94`, `config.md:118-119` vs. `DESIGN.md:311-313`.
- **What:** (a) A check after the call means that the call that exceeds the budget
  has already happened. Is a step that got a valid answer from this call
  `succeeded`, or `budget`? (b) `parallel` branches check the
  budget concurrently, so the overrun can be up to N calls. (c) A missing
  `usage.cost` gives only a warning, the budget then does not apply, and yet
  `config.md:118` claims that “a run without a spend cap does not exist”. Point 4 on
  `:705` is worded as a success condition, but it is only a warning.
  (d) §5.7 wants images counted separately also toward the **time** limit. The spec has only
  `run_image_budget_usd`.
- **Proposal:** “Before every call: when spend ≥ budget, the call is not
  started → `budget`. A call that exceeds the budget completes and its
  result counts (warning ‘budget exceeded by X USD’). In `parallel` the same
  applies, the overrun being at most one call per branch. A missing `cost` =
  retry as `transient`; after `retry` is exhausted class `budget` with the message
  ‘cost unknown’.” Move point 4 at `:705` out of the list of conditions.
  Add `run_finished.image_duration_s`, or state in the changelog that
  a separate time limit for images is not in v1.

### D9. Do retries count toward `max_turns`?
- **Where:** `scenario.md:163`, `scenario.md:248`, `agent.md:45`, `agent.md:81`.
- **What:** `max_turns` = “at most this many model calls”. `retry` applies “to each
  call in the loop separately”. With `max_turns: 4` and `retry: 2` there can be 4
  or 12 calls.
- **Proposal:** “`max_turns` counts turns (model answers that the loop
  processed). A retry of one turn after `transient`/`schema` does not count toward
  `max_turns`, only toward `budget_usd`.”

### D10. `image` without an image: `transient`, or `content`? And a silently ignored `aspect_ratio`
- **Where:** `scenario.md:681` vs. `scenario.md:683`; `scenario.md:316`, `scenario.md:325-329` vs. `DESIGN.md:313-314`, `DESIGN.md:417-418`.
- **What:** HTTP 200 without content and without a refusal is `transient`, but “`image`
  without an image” is `content`. For a 200 without `images`, without `refusal` and
  with `finish_reason: stop` both apply. Nobody measured the shape of a refusal
  (DESIGN §7 point 7). For `aspect_ratio` it is missing what happens when the chosen
  endpoint ignores it (the spike did not verify it for chat completions). The image then
  silently comes out as 1408×768.
- **Proposal:** “`image` without an image: when `refusal` is non-empty or
  `finish_reason: content_filter` → `content`. Otherwise `transient` and after
  `retry` is exhausted `content` with the message ‘model returned no image’.” Further:
  “After saving, the framework compares the aspect ratio from the file header with
  `aspect_ratio`. A deviation > 2 % = a `config` error (‘model does not support
  aspect_ratio’).”

### D11. `parallel`: cancelling a running step, `budget_usd` and `timeout` on `parallel`/`call`
- **Where:** `scenario.md:171-175`, `scenario.md:361-362`, `run-record.md:122` vs. `DESIGN.md:229`.
- **What:** A cancelled step that had already started has `step_started`, but the spec knows
  only `step_skipped` with `cancelled` for it. We do not know whether its cost counts and
  whether it has a `step_finished`. The table allows `budget_usd`/`timeout` on
  `parallel` and `call`, but the meaning is described only for steps with a model.
  Also unclear is what steps the run never got to (after a failure,
  inside a skipped `parallel`) receive, given §5.1 point 5.
- **Proposal:** “A started step cancelled because of another branch gets
  `step_finished` with `status: cancelled` and the cost of the calls so far.
  One that had not started gets `step_skipped` with `cancelled`. `budget_usd`/`timeout`
  on `parallel` and `call` = the sum of all steps inside / the time from start to
  the end of the last. Steps inside a skipped `parallel`/`switch` each get
  a `step_skipped` with the same reason. Steps after a run failure are
  not written, the summary states ‘run ended at step X’.”

### D12. Must `default` be complete?
- **Where:** `scenario.md:165` (the example `default: { on_brand: 0 }`), `scenario.md:294`.
- **What:** “The shape must match the step output.” We do not know whether a partial
  `default` is enough when only `on_brand` is read, and whether a `jev` default must
  also have `details`. If not, `steps.x.details.on_brand` after skipping ends in
  a runtime error.
- **Proposal:** “`default` must contain all fields of the step output (for `jev`
  all questions; `details` is filled in as `{}` automatically). A missing field
  = a `validate` error.”

### D13. `switch`/`when` over `null` and over a wrong type; does `on_error` apply to a condition error?
- **Where:** `scenario.md:160`, `scenario.md:387`, `scenario.md:598`, `scenario.md:631`.
- **What:** `value` “must be `string`”, but the spec does not say what happens at run time
  with `null` (typically `default: { kind: null }` on a `jev`): an `expression` error,
  or the `default` branch? Equally unclear is whether a step's `on_error: continue` covers
  an error in its own `when`.
- **Proposal:** “A `switch` with `value` `null` or of a type other than `string` =
  an `expression` error (not the `default` branch). When the type is known in advance, a
  `validate` error. An error in a step's `when` is a step error and `on_error` covers
  it.” Optionally: `validate` checks that the keys of `cases` ⊆ the keys of `criteria`
  when `value` is a `choice` from a `jev`.

### D14. There is no complete list of fields where templates are evaluated
- **Where:** `scenario.md:494-500`.
- **What:** “Everywhere else where there is a value” + an enumeration. Missing are
  `jev.questions.<q>.instructions`, `criteria`, `image.aspect_ratio`,
  `task.max_turns`, the keys of `cases`. The author has no idea whether
  `instructions: "Does it fit {{ inputs.brand }}?"` inserts the value or
  sends the literal text.
- **Proposal:** Replace with a closed list: “A template is evaluated **only**
  in: `ask.prompt`, `task.prompt`, `image.prompt`, `jev.state`,
  `jev.questions.*.instructions`, `jev.questions.*.criteria` (values),
  `fail`, the values of `output`, `call.inputs`, `dedupe_key`. `{{` anywhere else
  = a `validate` error.”

### D15. Expressions: `*` over text bypasses the length limit, `in` across types
- **Where:** `scenario.md:553-556`, `scenario.md:620-624`; spike (c) `REPORT.md:27` (`"a"*10**9` → 1 GB in 0.33 s), `REPORT.md:201-202`.
- **What:** The spec lists the arithmetic `+ - * / %` and explicitly allows only
  `+` for texts. We do not know whether `"a" * 999999999` (24 characters, passes the limit of
  2000) is an error. `3 in ["3"]`: is it a comparison across types (an error), or
  `false`? `in` over an object (a key) the prototype supports, the spec does not mention it.
- **Proposal:** “`*`, `/`, `%`, `-` only number with number. `+` number+number,
  text+text, list+list. A resulting text or list longer than 100,000
  characters/items = an `expression` error. `x in y`: `y` is a list (items must have
  the type of `x`, otherwise an error), a text (`x` text) or an object (`x` text = a key).”

### D16. MCP: timeouts, `mode="legacy"`, handshake errors, `stderr` and server start are missing from the spec
- **Where:** `config.md:139-171`, `mcp.schema.json:14-41`, `scenario.md:255-256`, `run-record.md` (no MCP event) vs. `DESIGN.md:325-335`, `DESIGN.md:357`.
- **What:** §5.8 wants timeouts “always explicit” (handshake and `call_tool`),
  `mode="legacy"`, `timed out` = class `timeout`, a handshake failure =
  `config`/`transient` and the servers' `stderr` in the record. The spec has no field for a
  timeout or an event for start/stderr. It only says that a tool error goes
  to the model, which does not hold for a timeout. We also do not know whether a server starts per
  run (§5.8), or per step (`agent.md:83` “connects”). For `parallel` this
  means either a shared or a separate server state.
- **Proposal:** Add `timeouts: {handshake: 10s, call: 60s}` to `mcp.yaml`
  (optional, with these defaults). Add to `scenario.md:255`:
  “`isError` → to the model, the step continues. A tool call timeout → the step fails,
  class `timeout` (the tool may have run, see D7). A handshake failure →
  `transient` (network, 5xx) or `config` (the process is not running, 401).” Add to
  `run-record.md` the event `mcp_server` (`server`, `action:
  started|stopped|failed`, `duration_s`, `stderr_file:
  mcp/<server>.stderr.log`) and the sentence “stdio servers start once per run at the
  first `task` that needs them, and `parallel` branches share them”.

### D17. Client-side argument validation and tool name normalization are missing from the spec
- **Where:** `agent.md:105-107`, `run-record.md:152-161` vs. `DESIGN.md:336-343`.
- **What:** §5.8 makes validating arguments against the **original** schema mandatory
  (Gemini silently sends wrong arguments). The spec does not mention it and `tool_call` has no state
  for it. The name `server__tool` has after normalization at most 64 characters
  `[a-zA-Z0-9_-]`, so two tools may get the same name and the spec
  does not say what then.
- **Proposal:** Add to `agent.md` after `:107`: “Arguments from the model are validated
  before the call against the tool schema from the server. When they do not match, the tool
  is not run and the model gets the validation error as the tool result (the turn
  counts).” Add `invalid_args: true` to `tool_call`. Add to `validate`:
  “two allowed tools with the same name after normalization = a `config`
  error”.

### D18. Images from tools, `reasoning_details` and base64 in `request.json`
- **Where:** `run-record.md:22-24`, `run-record.md:49-51`, `run-record.md:59-65` vs. `DESIGN.md:285-286`, `DESIGN.md:309-310`, `DESIGN.md:344-346`.
- **What:** The spec replaces base64 and `reasoning_details` only in `response.json`.
  But `request.json` (“body only”) of the next turn contains (a) the returned
  `reasoning_details` (~1.4 MB) and (b) an image from a tool, which §5.8 sends
  as a data URL in the following user message. The same applies to `calls/NN.tool.json`.
  The spec does not determine where an image from a tool is stored, nor that it goes in a user message,
  not in a tool message.
- **Proposal:** “The replacement of base64 and `reasoning_details` applies to **all**
  files in `calls/` including `request.json` and `NN.tool.json`. An image
  from a tool result is stored as `steps/<nn>-<id>/tool-<NN>-<k>.png`. It goes to
  the model in a user message right after the tool message. In the tool message there is only the text
  ‘image in the next message: tool-<NN>-<k>.png’.”

### D19. The stdio server environment: the spec promises something the SDK does not do
- **Where:** `config.md:167` vs. `DESIGN.md:355-357`; spike (d) `REPORT.md:94-96`.
- **What:** The spec: the server gets “nothing other than these variables and `PATH`”.
  The official SDK (D4) always adds `HOME, LOGNAME, PATH, SHELL, TERM, USER`.
  `npx` without `HOME` also has nowhere to keep its cache.
- **Proposal:** Rewrite `config.md:167`: “The server gets the variables `HOME`,
  `LOGNAME`, `PATH`, `SHELL`, `TERM`, `USER` (the default set of the `mcp` SDK) and
  the variables from `env`. Nothing else.” Add to `mcp.schema.json` in `env.propertyNames`
  `not: {enum: [PATH, HOME, LD_PRELOAD, LD_LIBRARY_PATH, NODE_OPTIONS,
  PYTHONPATH]}` (the schema currently lets them through).

### D20. A callback that cannot be delivered
- **Where:** `run-record.md:210-217`, `run-record.md:19` vs. `DESIGN.md:119-120`, `DESIGN.md:231-232`.
- **What:** Three attempts, and after that nothing is defined: does the run state change? Where
  is it visible? `callback_sent` is supposed to be “the last line of the file”, but with
  attempts there are up to three lines.
- **Proposal:** “Each attempt = one `callback_sent` event. After the third
  failure `callback_failed` (the last line). The run state does not change,
  `callback.json` stays. When run from the CLI and in `summary.md` ‘callback not
  delivered’ is shown. Recovery is handled by the time limit in n8n (§5.1 point 7).”

### D21. `validate` against `/models`: the need for a network and a missing check of alias capabilities
- **Where:** `scenario.md:738-739`, `scenario.md:723` vs. `DESIGN.md:276-278`, `DESIGN.md:295-296`.
- **What:** `validate` “before every run” calls `GET /models`. We do not know what the error class
  is when the network is down, nor how this fits with conformance
  tests “without a network”. It checks only that an image alias can do images, not that
  an agent's alias in `task` can do `tools` and, with `schema`, `structured_outputs`.
  The wording “aliases exist in `/models`” does not hold, in `/models` there are ids.
- **Proposal:** “`validate` verifies `models.<alias>.id` against `/models`
  (the result is cached for 24 h in `<runs>/_models.json`). Without a network and without a
  cache → `transient`. The alias of an agent used in `task` must have
  `tools` in `supported_parameters`, and when the step has `schema`, also
  `structured_outputs` or `tools`. Otherwise `config`. With the `base_url` of a fake
  provider it is checked against its `/models`.”

### D22. `call`: a file cannot be passed, the input type at run time
- **Where:** `scenario.md:82`, `scenario.md:108`, `scenario.md:421`, `scenario.schema.json:50`.
- **What:** A called scenario can return a `file`, but `inputs` have no type `file`
  (verified: the schema rejects it). An image from one scenario thus cannot be passed to
  another. When the type of a value behind `call.inputs` is not known in advance, the spec does not say
  the error class at run time.
- **Proposal:** Allow `type: file` in `inputs` (only for `call`; from the webhook
  and the CLI a `config` error). Add: “An input type that cannot be verified in advance is
  checked at `call`; a mismatch = `expression`.”

### D23. `schema: string` / `schema: [string]` passes the schema, but the output has no fields
- **Where:** `scenario.schema.json:58-70`, `scenario.md:129-130`, `scenario.md:209-219`.
- **What:** The `shape` type allows also a scalar and a list at the root (verified: both
  `ok`). But the output is defined only as “fields from the schema”
  (`steps.<id>.<field>`) and a strict JSON schema at providers wants an object as the
  root.
- **Proposal:** In `scenario.schema.json` make `ask.schema` and `task.schema`
  `{"type": "object", "minProperties": 1, …}` (the root only a map). Add to
  `scenario.md:216` “the root of `schema` is always a map”.

---

## MINOR

### M1. `ig-post.yaml`: comments do not match the steps and an explanation of the thresholds is missing
- **Where:** `ig-post.yaml:23-82`, `:46`, `:72`; `run-record.md:243-252`.
- **What:** The comments are numbered 1–7, there are 8 steps (`stop_image` has no number).
  `summary.md` numbers 1–8, so a beginner cannot match the numbers. The thresholds `0.7`
  and `0.5` and the term `noul` are not explained.
- **Proposal:** Number 1–8 the same as `summary.md` (`# 6. When the prompt violates the
  rules, the run ends.`). Add to `tone_check` `# noul = the degree of “yes” from 0 to
  1; 0.5 = Jev is unsure`. Add to `:72` `# a stricter threshold than for tone:
  rather stop`.

### M2. The word `prompt` has three meanings in `photo_prompt`
- **Where:** `ig-post.yaml:53-57`, `:62`, `:79`.
- **What:** `ask.prompt` (the instruction), the output field `prompt` and `image.prompt`.
  Then `steps.photo_prompt.prompt` reads as a tautology.
- **Proposal:** Rename the output field to `photo_description`:
  `schema: { photo_description: string }`, `prompt: "{{ steps.photo_prompt.photo_description }}"`.

### M3. `limits.max_turns` is required even for agents that are used only in `ask`
- **Where:** `agent.schema.json:29`, `agent.md:45`, `copywriter.md:6-8`, `photographer.md:6-8`.
- **What:** `max_turns: 1` on the copywriter means nothing (`ask` ignores it),
  and a beginner reads it as a setting.
- **Proposal:** `max_turns` required only when the agent has `mcp` (schema:
  `if: {required: [mcp]} then: {properties: {limits: {required: [max_turns]}}}`).
  `validate`: a `task` with an agent without `max_turns` = a `config` error
  (§5.1 point 6 stays satisfied). Remove `max_turns: 1` from the examples.

### M4. `outputs: {}` cannot be satisfied
- **Where:** `scenario.schema.json:18-30`, `scenario.schema.json:340-344`, `scenario.md:483-485`.
- **What:** The schema allows `outputs: {}`. A scenario with `outputs` must then have
  an `output`, but `output` wants at least one key.
- **Proposal:** Add `"minProperties": 1` to `outputs`.

### M5. `mcp.yaml`: only `https://`, SSE cannot be configured
- **Where:** `mcp.schema.json:37`, `config.md:141-144`, `config.md:168` vs. `DESIGN.md:325`.
- **What:** A local HTTP server (a sidecar in a container, `http://127.0.0.1`,
  as spike (d) used it) cannot be written. SSE, which §5.8 names, has no field.
- **Proposal:** `url` pattern `^(https://|http://(127\.0\.0\.1|localhost)[:/])`.
  Add `transport`: `streamable-http` or `sse` (default `streamable-http`), or
  state explicitly in `config.md` “SSE is not in v1”.

### M6. `config.yaml`: `base_url` to any host and one variable for several purposes
- **Where:** `config.schema.json:17`, `config.schema.json:79-90`, `config.md:78`.
- **What:** `base_url` is “only for conformance tests”, but the schema lets through
  `http://evil.example.com`, where the OpenRouter key would go. The same
  variable as `webhook.token_env` and `openrouter.api_key_env` passes (verified),
  so n8n would get the OpenRouter key.
- **Proposal:** `base_url` pattern
  `^(https://openrouter\.ai/|http://(127\.0\.0\.1|localhost)[:/])`.
  `validate`: two different `*_env` fields with the same value = a `config` error.

### M7. The `runs/` folder has no place in the configuration
- **Where:** `run-record.md:42`.
- **What:** “a folder from the server configuration”, but `config.yaml` has no such field
  and no other server configuration exists.
- **Proposal:** Add `runs_dir` to `config.yaml` (default `./runs`, on
  Modal the path to a Volume), or write “the CLI switch `--runs-dir`, default `./runs`”.

### M8. Numbers in expressions: `int`, `round`, NaN, `integer` vs. `number`, the format in text
- **Where:** `scenario.md:521-522`, `scenario.md:583-584`, `scenario.md:596`, `scenario.md:606-608`, `scenario.md:622-624`.
- **What:** `int(2.7)`: 2, or an error? `round(2.5)` = `3`, or `3.0`? (and
  `str(4 / 2)` = `"2.0"`?) Python accepts `float("nan")` and `float("inf")`,
  but the result is not valid JSON. The result of `/` (`2.0`) into an input of type
  `integer`? The format of a number in text (`0.1 + 0.2`) is not determined. The depth limit
  “before reading the expression” cannot be measured for operators without a parser.
- **Proposal:** “`int(x)` truncates the fractional part of a number, from text only a whole
  number. `round(x)` without `n` gives an integer. `nan`/`inf` = an `expression` error.
  A number with a zero fractional part is accepted as `integer`.
  A number in text = the shortest representation that reads back the same (`0.30000000000000004`).
  The length is checked before the parser, the depth over the AST before evaluation.”

### M9. `tools` for a server the agent does not have in `mcp`; subfolders
- **Where:** `agent.md:43`, `scenario.md:249-250`; `agent.md:3`, `scenario.md:3`.
- **What:** An agent with `tools: {github: [...]}` and without `mcp` passes the schema
  (verified) and the spec does not say what it means. We also do not know whether
  subfolders of `agents/` and `scenarios/` are read (two `copywriter.md` in different
  folders).
- **Proposal:** “A `tools` key outside `mcp` = a `config` error.” “Only files
  directly in the folder are read, subfolders are a `config` error.”
- **Relaxed 2026-09-25 (framework 0.2.3, ISSUES 37):** subfolders are silently
  ignored, it is not a `config` error. The concern about two same-named files
  is already addressed by subfolders not being read.

### M10. Deviations from DESIGN that are not in OPEN-QUESTIONS
- **Where:** `scenario.md:169-178` vs. `DESIGN.md:102-103`; `scenario.md:631` vs. `DESIGN.md:269-270`.
- **What:** D1d gives `retry`, `timeout`, `on_error` to “any step”. The spec
  forbids them on `parallel`, `set`, `switch`, `fail` and `output`. §5.4 says
  that comparing across types is a **validation** error, the spec moves it for unknown
  types to run time (`expression`). Both are reasonable, but according to `CLAUDE.md` this
  needs the user's consent.
- **Proposal:** Add questions 12 and 13 to OPEN-QUESTIONS with these wordings and
  the recommendation “keep”.

### M11. `CLAUDE.md` does not refer to the spec; DESIGN in the branch is outdated
- **Where:** `CLAUDE.md:6-9`; `docs/DESIGN.md` in the `phase-1-spec` branch (without §5.8).
- **What:** Phase 2 workers read only DESIGN. The spec cites “§” from a copy that
  does not have §5.8.
- **Proposal:** Add to `CLAUDE.md`: “After approval `docs/spec/` (the v1 formats) is binding
  too. Report a spec × DESIGN contradiction to the coordinator.” Unify the copy of
  `docs/DESIGN.md` in the branch with the main checkout.

### M12. The `<nn>` number of the step folder is not stable
- **Where:** `run-record.md:45-48`, `run-record.md:117-124` vs. `DESIGN.md:229`.
- **What:** In `parallel` `<nn>` is assigned “by actual start”. The same
  scenario then has different folder numbering on every run and a diff of two runs
  (R2) reads badly.
- **Proposal:** “`<nn>` = the order of the step in the file (depth-first, including branches),
  fixed for the scenario. The actual start order is visible from `ts` in `events.jsonl`.”

---

## Status of fixes

Fixed 2026-09-25 (worker `task_06392950748f`) according to the proposals above; where the
coordinator decided otherwise, their decision applies. Verified with
`uv run docs/spec/tools/check.py` (YAML 1.2 loader + jsonschema) on all
examples and snippets: agent 4×, config 2×, mcp 2×, scenario 13×, skill 2×,
**0 errors**; the new schema rules verified with 9 deliberately faulty cases (all
rejected).

| Finding | Status | Note |
|---|---|---|
| B1 skills | done | `task`: list + `load_skill` (`_skills` in the record), `ask`: whole; `skill.md`, `skill.schema.json`, the example `skills/lumen-voice`; OPEN-QUESTIONS 11 |
| B2 `tools` mandatory | done | `dependentRequired`, keys of `tools` = `mcp`, `--dry-run` prints the offer; OQ 6 resolved per §5.8 |
| B3 cascade | done | `models.<alias>.structured_output`, `_submit_output`, a transition one level down after `schema` |
| B4 dedupe | done | `<runs>/_dedupe/<sha256>.json`, atomically; OQ 12 |
| B5 webhook | done | the new `webhook.md` (`POST /runs`, 202/200/401/422); the callback always from `run_id` |
| B6 YAML 1.2 | done | text in all spec files; `tools/check.py`; `cases.propertyNames`; CHANGELOG: verification with the same loader |
| D1 MCP permissions | deviation (coordinator) | the owner in `mcp.yaml`: mandatory `agents`, plus optional `scenarios` and `tools` |
| D2 approval bypass | deviation (coordinator) | `callable` in the scenario yes; instead of `scenarios` in the agent there is `scenarios` on the server in `mcp.yaml` (agents are written by others) |
| D3 `file` type | done | only from `image`/a tool, a path inside the run, `null` from `default`, a failed upload = `transient` |
| D4 filesystem root | done | `{run_dir}` in `args`, the example `{run_dir}/work` |
| D5 guessable URL | done | `<run_id>-<32 hex>/<name>` for all files; `run_started.storage_prefix` |
| D6 secrets in results | done | replacement `<secret: NAME>` in the record and the callback |
| D7 dedupe `started` | done | `started` before the 1st tool call; `started` without `succeeded` = `config` “verify manually” |
| D8 budget | done | a check before the call, an overrun by 1 call/branch, a missing cost → `transient` → `budget`; `run_finished.image_duration_s`, a separate time limit for images is not in v1 |
| D9 `max_turns` × `retry` | done | a retry does not count toward `max_turns` |
| D10 `image` without an image | done | `refusal`/`content_filter` → `content`, otherwise `transient` → `content`; an aspect ratio check ±2 % |
| D11 `parallel` cancellation | done | `step_finished.status: cancelled`; `budget_usd`/`timeout` on `parallel`/`call` = sum / the whole duration |
| D12 complete `default` | done | all fields, `details` is filled in |
| D13 `switch` over `null` | done | `expression`; an error in `when` is covered by `on_error`; `cases` ⊆ `criteria` |
| D14 fields with templates | done | a closed list, `{{` elsewhere = `validate` |
| D15 `*`, `in` | done | operator types, a result of at most 100,000, `in` over a list/text/object |
| D16 MCP timeouts | done | `timeouts` in `mcp.yaml`, the `mcp_server` event, `stderr` into `mcp/`, a start 1× per run; `mode="legacy"` is an implementation detail from DESIGN §5.8 |
| D17 argument validation | done | validation against the original schema, `invalid_args`, a name collision after normalization = `config` |
| D18 images from tools | done | replacement of base64/`reasoning_details` in all `calls/` files; `tool-<NN>-<k>.png`, a user message |
| D19 stdio environment | done | 6 SDK variables + `env`; forbidden names in the schema |
| D20 undelivered callback | done | `callback_sent` per attempt, `callback_failed`, the run state unchanged |
| D21 `validate` × `/models` | done | a 24 h cache `_models.json`, without a network `transient`, a check of `tools`/`structured_outputs` |
| D22 `file` through `call` | done | `inputs.type: file` only for `call`; a mismatch at run time = `expression` |
| D23 root of `schema` | done | `schema_root` = a map |
| M1 ig-post comments | done | 1–8 the same as the summary, an explanation of `noul` and the thresholds |
| M2 `photo_description` | done | the example, the spec, the photographer agent |
| M3 `max_turns` | done | required only with `mcp`; a `task` without it = `config`; removed from the examples |
| M4 `outputs: {}` | done | `minProperties: 1` |
| M5 HTTP/SSE | done | `url` also `http://127.0.0.1`/`localhost`; `transport`: `streamable-http` or `sse` |
| M6 `base_url`, shared env | done | a pattern; the same value in two `_env` = `config` |
| M7 `runs_dir` | done | a field in `config.yaml` (default `./runs`) |
| M8 numbers | done | `int`, `round` without `n` whole, `nan`/`inf`, `2.0` as `integer`, the format in text, depth over the AST |
| M9 `tools` outside `mcp`, subfolders | done | `tools` outside `mcp` a `config` error; subfolders ignored since 0.2.3 (ISSUES 37) |
| M10 deviations from DESIGN | done | OPEN-QUESTIONS **13 and 14** (12 is dedupe) |
| M11 CLAUDE.md, DESIGN | partial (coordinator) | a sentence added to `CLAUDE.md`; the copy of `docs/DESIGN.md` in the branch is not unified — the merge with `main` will do that |
| M12 `<nn>` | done | the order in the file, depth-first |
