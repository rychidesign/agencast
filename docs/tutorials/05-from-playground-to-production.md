# Part 5 — From playground to production

Mentions of `maw` denote the historical name of AgenCast; the outputs and the limitations of the time are archival.

Run the commands from `examples/tutorial` (from the clone root: `cd examples/tutorial`).

**Time:** about 20 minutes · **Spend:** 0 USD (everything with `--fake` or without
calling a model)
**You will learn to:** swap a model with one line, turn a scenario into a golden
test, read the run record in depth, send a result to n8n
(`--callback-url`) and know what will never break while the framework is being improved.

Prerequisite: parts 1–4.

---

## Step 1 — model aliases: a swap = one line

Your agents know only aliases (`smart`, `fast`, `gemini-image`, `gemini-image-api`).
What hides behind them is in `workflows/config.yaml`:

```
models:
  smart:       { id: anthropic/claude-haiku-4.5 }
  fast:       { id: google/gemini-3.5-flash-lite, structured_output: tool_wrapper }
  gemini-image: { id: google/gemini-3.1-flash-image }
  gemini-image-api: { id: google/gemini-3.1-flash-image, api: images }   # Images API: reference images (image.images)
```

Only the **owner** changes this file — you in the role of an administrator, not
as a scenario author, and knowingly: changing an alias changes the model for
**all** agents that use it. That is why we first try the swap on a copy:

```bash
rm -rf /tmp/experiment && mkdir -p /tmp/experiment && cp -r workflows /tmp/experiment/
```

In `/tmp/experiment/workflows/config.yaml`, make the most common typo in the
`smart` row — `anthropic/claude-haiku-4-5` (a dash instead of a dot):

```bash
agencast validate /tmp/experiment/workflows/scenarios/tutorial-02-name-and-slogan.yaml
```

```
config: config.yaml: models.smart.id 'anthropic/claude-haiku-4-5' is not in GET /models — typo? (e.g. claude-haiku-4.5, not -4-5)
```

`validate` asks OpenRouter for the list of models, so a model that does not
exist does not get through. (It checks an alias only against what the scenario
needs from it, for example structured output. That is why the check uses a
scenario with a `schema`: `tutorial-01-names` needs nothing special from the
model, so the typo would not show there.) Now rewrite the row to another real
model:

```
  smart:       { id: google/gemini-3.5-flash-lite, structured_output: tool_wrapper }
```

```bash
agencast validate /tmp/experiment/workflows/scenarios/tutorial-02-name-and-slogan.yaml
agencast run /tmp/experiment/workflows/scenarios/tutorial-02-name-and-slogan.yaml -i product="ice cream" --dry-run
```

```
valid: tutorial-02-name-and-slogan (4 steps)
…
| 1 | propose | ask |  | agent tutorial-namer → smart (google/gemini-3.5-flash-lite); schema: names (cascade from tool_wrapper) | 0.01 USD, 2m |
```

Neither the agent nor the scenario changed by a single letter. What
`structured_output: tool_wrapper` is: this model cannot reliably do native
JSON Schema, so the framework hands it the JSON by another route (see the
“cascade” in part 2). Which route a model needs is found out by the owner by
trying — it is set once on the alias, not in every scenario.

Which version of the model really ran in which run is always in the record
(step 3).

---

## Step 2 — golden tests

This part about the framework's tests requires a clone of the repository and
working in `examples/tutorial`. From a package you verify your scenario directly
with `agencast run … --fake fake/…`.

Since part 1 you have been writing a fixture into `fake/` for every scenario.
Here is why:

> **Every file in `workflows/` is a framework test.** Every agent must
> pass validation and every scenario must run to the end with the fake
> provider. When a fixture `fake/<scenario name>.yaml` exists for it, the run
> must end in **success**; without a fixture, success or an intentional
> `fail` is enough.

When someone (typically an agent-worker) improves the framework, they run
these tests. When your scenario stops working, **they** will see it before you.

```bash
cd ../../framework && uv run pytest
```

```
......................................................................   [100%]
548 passed in 54.90s
```

(I shorten the extra rows of dots.) Only your files — you are still in the
`framework/` folder of the repository:

```bash
uv run pytest tests/test_golden.py -k tutorial -v
```

```
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-01-exercise] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-01-names] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-02-exercise] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-02-name-and-slogan] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-03-decisions] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-03-exercise] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-03-expressions] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-04-exercise] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-04-parallel] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-05-exercise] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-06-archive] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-06-exercise] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-07-archive] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-07-composition] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-07-exercise] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-07-slogan] PASSED
tests/test_golden.py::test_workflow_agent_valid[tutorial-archivist] PASSED
tests/test_golden.py::test_workflow_agent_valid[tutorial-illustrator] PASSED
tests/test_golden.py::test_workflow_agent_valid[tutorial-namer] PASSED
tests/test_golden.py::test_workflow_agent_valid[tutorial-slogan-writer] PASSED
tests/test_golden.py::test_workflow_skill_valid[tutorial-entry] PASSED
====================== 21 passed, 38 deselected in 0.87s =======================
```

(`-k tutorial` selects the tests with “tutorial” in their name and
`tests/test_golden.py` limits them to the golden tests; I show only the result
lines.) Back to the tutorial project: `cd ../examples/tutorial`.

### What a test looks like when it fails

A fixture is a contract, just like a scenario: when an answer in it does not
match the `schema`, the test fails. Here is a fixture with a field that the
`schema` of the `propose` step does not know (`name_extra`):

```yaml
propose:
  - json:
      name_extra: "this field is not in the schema"
      name: "Ovena"
```

```
FAILED tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-05-exercise]
…
E           AssertionError: {'class': 'schema', 'step': 'propose', 'message': "response does not match schema: unknown field 'name_extra' (typo?) (root)"}
E           assert 'failed' == 'succeeded'
```

Read the `AssertionError` line: it holds exactly what would be in
`summary.md` — the class, the step, the message.

### How to write a fixture — a summary

| Step | In the fixture | When the step is missing from the fixture |
|---|---|---|
| `ask` without `schema` | `text: "…"` | “Fake response.” |
| `ask` with `schema` | `json: {field: value}` — exactly the fields from the `schema` | values generated from the schema |
| `jev` | `answers: {question: value}` | `noul` 0.5, `choice` the first option, `score` 0 |
| `image` | nothing (or `image: {width: …, height: …}`) | a grey PNG in the `aspect_ratio` |
| `set`, `switch`, `fail`, `output` | nothing | — (they don't call a model) |

- The key is the step `id`, the value is a **list** of responses: the 1st call
  takes the first, the 2nd the second…, the last one repeats.
- For simulating errors (part 4): `status: 429`, `refusal: "…"`,
  `finish_reason: error`, `sleep: 5`. **Don't** put such fixtures into
  `fake/` — a golden test with a fixture expects success. They belong in `/tmp`.
- A fixture should go through the path that matters most to you (for `switch`
  pick a branch — see the exercise).
- The tests use their own test `config.yaml` with the same aliases
  (`smart`, `fast`, `gemini-image`, `gemini-image-api`), not yours — they cost nothing and need
  no key.

---

## Step 3 — the run record in depth

Take the live run from part 3 (`runs/20260925-151536-tutorial-03-decisions-b547`).

### `events.jsonl`

One event per line; a machine reads it easily, a human with a little help.
The event types in this run in order:

```
run_started
step_started propose
model_call propose
step_finished propose
step_started check
jev_call check
step_finished check
step_skipped stop
step_started by_tone
step_skipped slogan_serious
step_skipped unknown_tone
step_started slogan_playful
model_call slogan_playful
step_finished slogan_playful
step_finished by_tone
step_started result
step_finished result
step_started out
step_finished out
run_finished
```

(The listing is made by this command:
`python3 -c "import json;[print(json.loads(l)['type'], json.loads(l).get('step','')) for l in open('runs/20260925-151536-tutorial-03-decisions-b547/events.jsonl')]"`.)

The most important lines:

**`run_started`** — what the run began with. Mainly `models`: what the aliases
were translated to **in this run**. When the owner changes an alias in a month,
you still know what ran back then.

```
{"ts":"2026-09-25T15:15:36.894Z","type":"run_started","run_id":"20260925-151536-tutorial-03-decisions-b547","scenario":"tutorial-03-decisions","scenario_version":1,"request_key":null,"inputs":{"product":"vegan ice cream made from oat milk"},"models":{"smart":"anthropic/claude-haiku-4.5","fast":"google/gemini-3.5-flash-lite","gemini-image":"google/gemini-3.1-flash-image"},"limits":{"run_budget_usd":1.0,"run_image_budget_usd":0.3,"run_timeout":"1h"},"framework_version":"0.1.0","storage_prefix":"20260925-151536-tutorial-03-decisions-b547-c6bf8457c50ee002cb94481826201908"}
```

**`model_call`** — a single model call: the attempt (`attempt`), who served it
(`provider`), how it ended (`finish_reason`), what it cost (`usage`) and where
the whole request and response are. You can find the `generation_id` in the
OpenRouter log too.

```
{"ts":"2026-09-25T15:15:40.532Z","type":"model_call","step":"propose","attempt":1,"alias":"smart","model":"anthropic/claude-haiku-4.5","structured_output":"native_schema","http_status":200,"response_model":"anthropic/claude-haiku-4.5","provider":"Amazon Bedrock","generation_id":"gen-1790349337-frPW3LQHMMPBX1MhYdjc","finish_reason":"stop","native_finish_reason":"end_turn","usage":{"input_tokens":264,"output_tokens":13,"cost_usd":0.000329},"duration_s":3.636,"request_file":"steps/01-propose/calls/01.request.json","response_file":"steps/01-propose/calls/01.response.json"}
```

**`jev_call`** — the same for Jev; `response_model` is the dated version of Jev.

```
{"ts":"2026-09-25T15:15:41.026Z","type":"jev_call","step":"check","attempt":1,"model":"jev-1.13","http_status":200,"response_model":"typesafe/jev-1.13-20260917","usage":{"input_tokens":495,"output_tokens":71,"cost_usd":2.079e-05},"answers":{"memorable":0.85,"tone":"playful","originality":0.64},"duration_s":0.492,"request_file":"steps/02-check/calls/01.request.json","response_file":"steps/02-check/calls/01.response.json"}
```

**`step_skipped`** — always with a reason and with whether a `default` was used:

```
{"ts":"2026-09-25T15:15:41.028Z","type":"step_skipped","step":"slogan_serious","kind":"ask","reason_code":"switch","reason":"switch: by_tone = \"playful\"","default_used":true}
```

**`run_finished`** — the result, warnings, the usage total, of which images:

```
{"ts":"2026-09-25T15:15:42.806Z","type":"run_finished","status":"succeeded","error":null,"warnings":[],"duration_s":5.912,"usage":{"input_tokens":1010,"output_tokens":112,"cost_usd":0.00074079},"image_cost_usd":0.0,"image_duration_s":0.0}
```

Other types you have already seen: `error` (parts 2 and 4: `class`,
`will_retry`), `image_saved`, `callback_sent` / `callback_failed` (step 4).

### `steps/<nn>-<id>/calls/`

Every API call separately: `01.request.json` (what went out) and
`01.response.json` (what came back). A retry = `02.*`, `03.*`. The beginning of
the request to Jev:

```bash
head -c 413 runs/20260925-151536-tutorial-03-decisions-b547/steps/02-check/calls/01.request.json
```

```
{
  "model": "jev-1.13",
  "state": "Product: vegan ice cream made from oat milk. Proposed name: Oatie",
  "questions": {
    "memorable": {
      "type": "noul",
      "instructions": "Is the name easy to remember and easy to pronounce?"
    },
    "tone": {
      "type": "choice",
      "instructions": "What tone does the proposed name have?",
      "criteria": {
        "playful": "Playful, witty, relaxed",
```

### What is never in the record

- **The API key** or headers — `request.json` is only the request body.
- **An image in base64.** The image model's response from part 4 would be
  over 2 MB of text; in the record there is a link to the file instead. And the
  model's encrypted “thinking” (`reasoning_details`, almost 1 MB here) is left out:

```bash
grep -o '"url": "<[^"]*"\|"reasoning_details": "<[^"]*"' runs/20260925-151755-tutorial-04-parallel-8c76/steps/05-photo/calls/01.response.json
```

```
"reasoning_details": "<omitted: reasoning_details, 1003920 B>"
"url": "<file: steps/05-photo/image.png, 1149417 B>"
```

- **Secret values anywhere.** The value of every variable referenced by an
  `*_env` field in `config.yaml` (the OpenRouter key, the callback secret…) is
  replaced by the framework with the text `<secret: NAME>` before writing
  **every** record file. You can try it safely with an invented callback
  secret that you deliberately send as an input:

```bash
export CALLBACK_SECRET=tutorial-demo-secret
agencast run workflows/scenarios/tutorial-01-names.yaml -i product="ice cream tutorial-demo-secret" --fake fake/tutorial-01-names.yaml
```

  In `inputs.json`:

```
{
  "product": "ice cream <secret: CALLBACK_SECRET>"
}
```

  in `steps/01-propose/prompt.md` (the last lines):

```
…
# Message

Come up with 3 names for this product: ice cream <secret: CALLBACK_SECRET>. Each on its own line.
```

  and in `summary.md` the warning:

```
## Warnings
- secret value CALLBACK_SECRET was replaced in the record with <secret: CALLBACK_SECRET>
```

  The value `tutorial-demo-secret` is not in any file of the run. Beware: only
  the **record** is masked — the model received that value. Secrets do not belong
  in prompts; a scenario has no way to read them (it sees only `inputs` and
  `steps`), unless you send them in as an input yourself.

---

## Step 4 — `--callback-url`: what arrives in n8n

In production n8n starts the run and waits for the result at its “resume”
address. The framework sends it there with a `POST` — **always**, on success
and on error. From the CLI you try it with the `--callback-url` switch
(`https://` only). It needs the variable from `callback.secret_env` (for us
`CALLBACK_SECRET`) — the message is signed with it. In production it is in
`.env`; for a trial the `export` from step 3 is enough.

To see exactly what n8n receives, I ran a small HTTPS server on my computer that
pretends to be n8n and prints what arrived (the script is
[below](#appendix-fake-n8n)):

```bash
agencast run workflows/scenarios/tutorial-01-names.yaml -i product="vegan ice cream" --fake fake/tutorial-01-names.yaml --callback-url https://127.0.0.1:8443/webhook-waiting/4711 --request-key n8n-4711
```

```
run 20260929-185938-tutorial-01-names-40ed: succeeded · 0.0 s · 0.0001 USD
```

The fake n8n printed:

```
POST /webhook-waiting/4711
Content-Type: application/json
X-Run-Id: 20260929-185938-tutorial-01-names-40ed
X-Signature: sha256=6cd67d35eb9636bdf981e2792be6131579d47fcbcfe48b8c59e747ef18dffe83
{"run_id": "20260929-185938-tutorial-01-names-40ed", "scenario": "tutorial-01-names", "request_key": "n8n-4711", "status": "succeeded", "outputs": {"names": "Oatsy\nFrost Oat\nFrozen Field"}, "error": null, "warnings": [], "cost_usd": 0.0001, "duration_s": 0.001, "report_url": "file:///…/outputs/20260929-185938-tutorial-01-names-40ed-b7ea967c1f7a1ea419552469a363db35/report.html", "sent_at": "2026-09-29T18:59:38.389Z"}
```

The body fields:

| Field | What you do with it in n8n |
|---|---|
| `status` | `succeeded` / `failed` — the first branching |
| `outputs` | exactly the fields from the scenario's `outputs`; `null` on error |
| `error` | `{class, step, message}` — by `class` n8n tells an intentional `fail` from a malfunction (part 3) |
| `warnings` | e.g. the image failed with `on_error: continue` (part 4) |
| `request_key` | what n8n sent (`--request-key`), so it can pair the response |
| `cost_usd`, `duration_s` | for an overview of spend |
| `report_url` | the address of `report.html` in storage (since `maw` 0.2.0; a run summary with prompts and responses, part 7); `null` only when the report could not be created or uploaded (then there is a warning about it) |

The `file` type in `outputs` is the **address** of a file in storage, not the
file. For us `storage.type: local` → a `file://…` path that Instagram can do
nothing with. A public URL comes with R2 storage (the owner changes it in
`config.yaml`).

### The signature

`X-Signature` = HMAC-SHA256 of the **exact bytes of the body** with the secret
from `CALLBACK_SECRET`. n8n computes it the same way and trusts the message only
if they match. Verification (the body saved by the fake n8n):

```bash
python3 -c "
import hmac, hashlib
body = open('/tmp/n8n-mock/last-body.json', 'rb').read()
print('sha256=' + hmac.new(b'tutorial-demo-secret', body, hashlib.sha256).hexdigest())
"
```

```
sha256=6cd67d35eb9636bdf981e2792be6131579d47fcbcfe48b8c59e747ef18dffe83
```

It matches the header. Important for n8n: compute the signature from the **raw
body**, not from JSON that n8n has already parsed and reassembled — different
spacing = a different signature. (`callback.json` in the run folder has the same
content, but nicely indented, so the signature won't come out from it.)

### When n8n does not answer

```bash
agencast run workflows/scenarios/tutorial-01-names.yaml -i product="ice cream" --fake fake/tutorial-01-names.yaml --callback-url https://127.0.0.1:8444/webhook-waiting/4713
```

```
callback not delivered
run 20260929-185946-tutorial-01-names-89df: succeeded · 0.0 s · 0.0001 USD
```

It took 35 s — three attempts with delays of 5 s and 30 s:

```
{"ts":"2026-09-29T18:59:46.112Z","type":"callback_sent","url":"https://127.0.0.1/webhook-waiting/4713","attempt":1,"http_status":null,"error":"ConnectError: All connection attempts failed"}
{"ts":"2026-09-29T18:59:51.121Z","type":"callback_sent","url":"https://127.0.0.1/webhook-waiting/4713","attempt":2,"http_status":null,"error":"ConnectError: All connection attempts failed"}
{"ts":"2026-09-29T19:00:21.152Z","type":"callback_sent","url":"https://127.0.0.1/webhook-waiting/4713","attempt":3,"http_status":null,"error":"ConnectError: All connection attempts failed"}
{"ts":"2026-09-29T19:00:21.152Z","type":"callback_failed","url":"https://127.0.0.1/webhook-waiting/4713","attempts":3,"error":"ConnectError: All connection attempts failed"}
```

The run stays `succeeded` — an undelivered callback does not change the result.
You will see it in `summary.md` (“**Callback not delivered**”) and in the overview:

```bash
agencast runs list
```

```
20260929-185946-tutorial-01-names-89df        succeeded                         0.0 s   0.0001 USD callback not delivered
```

So that n8n does not wait forever, set a timeout on its waiting step.

---

## Step 5 — what will never break for you

The framework will be improved by agent-workers. The compatibility rules
(`docs/DESIGN.md` §5.9) apply to your files:

1. **`version: 1` is only ever extended.** New optional fields and new step
   types may be added. Renaming, removing or changing the meaning of an
   existing field is not allowed. A new field always has a default value that
   keeps the existing behaviour.
2. **A breaking change = `version: 2`.** The framework then handles both
   versions at once and the `migrate` command converts your files and lists the
   changes. An old file keeps running until you convert it yourself.
3. **Golden scenarios** — every scenario, agent and skill of yours in
   `workflows/` must pass `validate` and run to the end with `--fake`
   (step 2) after every framework change. Your fixtures make sure this is kept.
4. **Deprecation with a warning.** When a construct stops being recommended,
   you first see a warning in `validate` (the run goes on); it may disappear
   only in the next version of the format.
5. **An unknown version = an error**, never a silent guess.

In practice: write `version: 1`, keep a fixture for every scenario, and framework
updates need not concern you.

---

## What comes next

Parts 1–5 were written with `maw` 0.1.0; parts 6 and 7 need `maw` 0.2.1:

- **[Part 6 — An agent with tools](06-agent-with-tools.md):** the `task` step
  (a model ↔ MCP tools loop with a turn limit), `mcp.yaml` from the owner's
  point of view, skills via `load_skill`, the record of tool calls.
- **[Part 7 — Composition and operations](07-composition-and-operations.md):** `call`
  (a scenario calls a scenario), `agencast serve` for n8n (token, `request_key`,
  a signed callback), `report.html` and `dedupe_key` for steps that may run
  only once.

An overview of all parts: [README.md](README.md).

---

## What you remember

- Swapping a model = one line in `config.yaml` (the owner); `validate` checks
  it against OpenRouter; the record keeps what ran.
- Every scenario in `workflows/` is a golden test; a fixture named after the
  scenario in `fake/`; `cd ../../framework && uv run pytest`.
- `events.jsonl` = the whole story of a run; `calls/` = every call; there are
  no keys, base64 or secret values in the record.
- Callback: always, signed with HMAC; `class` in `error` tells a `fail` from a
  malfunction.

---

## Exercise

The golden test of the scenario from part 3 goes only through the `playful`
branch. You want the `serious` branch tested too. Copy
`workflows/scenarios/tutorial-03-decisions.yaml` as
`tutorial-05-exercise.yaml` and write a fixture for it with which the run goes
through the `serious` branch. Verify it with a fake run and with `pytest`.

<details>
<summary>Solution</summary>

The scenario differs only in the header:

```bash
diff workflows/scenarios/tutorial-03-decisions.yaml workflows/scenarios/tutorial-05-exercise.yaml
```

```
2,3c2,3
< name: tutorial-03-decisions
< description: Comes up with a name, has Jev assess it and writes a slogan based on its tone (tutorial, part 3)
---
> name: tutorial-05-exercise
> description: Comes up with a name, has Jev assess it and writes a slogan based on its tone (tutorial, part 5 — exercise solution, serious branch)
```

(Watch out for a colon followed by a space in `description` — the first version
had `… exercise solution: fixture …` and YAML rejected it:
`config: tutorial-05-exercise.yaml, line 3: cannot read YAML — a value containing {, [, ': ' or ' #' must be quoted (scenario.md §5 'YAML pitfalls')`
and below it the original parser message `mapping values are not allowed here`.
Put text containing `: ` in quotes, or leave the colon out.)

`fake/tutorial-05-exercise.yaml`:

```yaml
# Scripted responses for tutorial-05-exercise (exercise solution from part 5).
# Jev returns tone: serious → the serious branch runs, so the responses need slogan_serious.
propose:
  - json:
      name: "Ovena"
check:
  - answers:
      memorable: 0.9
      tone: serious
      originality: 1.1
slogan_serious:
  - json:
      slogan: "Ovena. Plant-based smoothness in every spoonful."
```

The key is `slogan_serious`, not `slogan_playful` — the fixture answers the steps
that **really run**.

```bash
agencast run workflows/scenarios/tutorial-05-exercise.yaml -i product="vegan ice cream" --fake fake/tutorial-05-exercise.yaml
```

```
run 20260929-190038-tutorial-05-exercise-8c0a: succeeded · 0.0 s · 0.0003 USD
```

```
| 4 | by_tone | switch | ✓ | 0.0 s | 0.0001 | branch serious |
| 5 | slogan_playful | ask | skipped |  |  | switch: by_tone = "serious" |
| 6 | slogan_serious | ask | ✓ | 0.0 s | 0.0001 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 7 | unknown_tone | fail | skipped |  |  | switch: by_tone = "serious" |
…
## Output
- name: “Ovena”
- tone: “serious”
- slogan: “Ovena. Plant-based smoothness in every spoonful.”
- memorability: 90
```

```bash
cd ../../framework && uv run pytest tests/test_golden.py -k tutorial-05 -v; cd ../examples/tutorial
```

```
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-05-exercise] PASSED [100%]
```

Without `tone: serious` in the fixture the fake Jev would return the first
option (`playful`) and the test would pass — but through a different branch than
you wanted. That is why you should always check the `branch …` note in
`summary.md`.

</details>

---

## Appendix: fake n8n

For the curious — this is how I captured the callback in step 4. It needs
`openssl` and Python; it runs only on your computer.

```bash
mkdir -p /tmp/n8n-mock && cd /tmp/n8n-mock
openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 1 -subj "/CN=localhost" -addext "subjectAltName=IP:127.0.0.1,DNS:localhost"
```

`/tmp/n8n-mock/receiver.py`:

```python
# Fake n8n: an HTTPS server that prints the headers and body of an incoming callback.
import http.server, ssl

class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        print("POST", self.path)
        for k in ("Content-Type", "X-Run-Id", "X-Signature"):
            print(f"{k}: {self.headers[k]}")
        print(body.decode())
        open("last-body.json", "wb").write(body)
        self.send_response(200); self.end_headers()
    def log_message(self, *a): pass

srv = http.server.HTTPServer(("127.0.0.1", 8443), H)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain("cert.pem", "key.pem")
srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
srv.serve_forever()
```

Start it in one terminal (`cd /tmp/n8n-mock && python3 receiver.py`); in a second
one (in the `examples/tutorial` project) tell the framework to trust the
certificate and send the callback:

```bash
export CALLBACK_SECRET=tutorial-demo-secret
export SSL_CERT_FILE=/tmp/n8n-mock/cert.pem
agencast run workflows/scenarios/tutorial-01-names.yaml -i product="vegan ice cream" --fake fake/tutorial-01-names.yaml --callback-url https://127.0.0.1:8443/webhook-waiting/4711 --request-key n8n-4711
```

Leave `SSL_CERT_FILE` set only in this terminal. It says “trust **only** this
certificate”, so a connection to OpenRouter then fails (for example
`agencast validate` when there is no fresh model list cached in `runs/`):

```
transient: GET https://openrouter.ai/api/v1/models failed ([SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)) and no valid cache …/runs/_models.json exists — checking models requires network access
```

After the trial: `unset SSL_CERT_FILE CALLBACK_SECRET`.
