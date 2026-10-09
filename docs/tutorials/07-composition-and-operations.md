# Part 7 — Composition and operations: `call` and the webhook

Mentions of `maw` denote the historical name of AgenCast; the outputs and the limitations of the time are archival.

Run the commands from `examples/tutorial` (from the clone root: `cd examples/tutorial`).

**Time:** about 35 minutes · **Spend:** 0 USD with `--fake`; the optional live
run through the webhook ~0.001 USD
**You will learn to:** assemble a scenario from building blocks (`call`), start
`agencast serve` and call it like an automation tool (token, `request_key`, a callback with a
signature), open `report.html` and protect a step with a side effect using
`dedupe_key`.

Prerequisite: parts 1–6 (the `task` step and the `tutorial-archivist` agent from
part 6) and `curl`.

> The outputs of `validate`, `--fake` and `serve` come from the current CLI (the server is shown
> on its default port 8080). The live run (step 9) is archival: a real run from 25 Sep 2026
> against `maw` 0.2.1, with the names adapted to the English example project. Run the commands
> from the `examples/tutorial` project with the `agencast` shortcut from part 1. Your `run_id`s,
> times and texts will differ.

---

## Step 1 — a ready-made building block: `tone-check`

You already have one building-block scenario in `workflows/scenarios/`:
`tone-check.yaml` is taken over from the showcase so that the tutorial can run
on its own.

```yaml
version: 1
name: tone-check
description: Checks that a text matches the Lumen brand tone (called with a call step from other scenarios)
callable: true

inputs:
  text:
    type: string
    required: true
    description: Text to check
  threshold:
    type: number
    default: 0.7
    description: The on_brand value from which the text passes

outputs:
  on_brand:
    type: number
    description: How well the text matches the brand tone, from 0 to 1
  passed:
    type: boolean
    description: on_brand reached the threshold

steps:
  # 1. Jev rates the text; noul = degree of "yes" from 0 to 1.
  - id: check
    jev:
      state: "{{ inputs.text }}"
      questions:
        on_brand:
          type: noul
          instructions: >-
            Does the text match the tone of Lumen café — English, short, friendly and
            matter-of-fact, talks to the reader directly, no emoji and no advertising clichés?

  # 2. Comparison with the threshold; the calling scenario decides what happens next.
  - id: result
    set:
      passed: steps.check.on_brand >= inputs.threshold

  # 3. Output for the calling scenario (steps.<id>.on_brand, steps.<id>.passed).
  - id: out
    output:
      on_brand: "{{ steps.check.on_brand }}"
      passed: "{{ steps.result.passed }}"
```

Three things make it a building block:

- **`callable: true`** — only such a scenario may be called by another scenario.
  Without it, `call` is an error. This protects approval: a publishing scenario
  (without `callable`) cannot be called from the inside by anyone, which would
  bypass the human in the automation tool.
- **`inputs`** — what the caller **must** provide (`text`) and what it may
  (`threshold`, otherwise 0.7).
- **`outputs`** — what the caller gets back. It sees nothing else from the inside
  (`steps.check.details`…).

`inputs` + `outputs` are the **contract**. The building block itself does not
decide what happens next (no `fail`) — it returns `passed` and the caller
decides.

---

## Step 2 — your own building block

`workflows/scenarios/tutorial-07-slogan.yaml` — the slogan writer from part 2
wrapped in a scenario:

```yaml
version: 1
name: tutorial-07-slogan
description: Writes a slogan for a finished product name (tutorial, part 7 — building block for call)
callable: true

inputs:
  name:
    type: string
    required: true
    description: Product name
  tone:
    type: string
    default: playful
    description: Slogan tone (playful, serious…)

outputs:
  slogan:
    type: string
    description: One slogan

steps:
  # 1. The slogan writer from part 2 gets the name and the tone from the calling scenario.
  - id: write
    ask:
      agent: tutorial-slogan-writer
      prompt: |
        Product name: {{ inputs.name }}
        Tone: {{ inputs.tone }}
        Write one slogan for it.
      schema:
        slogan: string

  # 2. Output = the contract with the caller: it reads steps.<call step id>.slogan.
  - id: out
    output:
      slogan: "{{ steps.write.slogan }}"
```

A building block is a normal scenario — it can also be run on its own
(`agencast run tutorial-07-slogan -i name=Ovena`).

---

## Step 3 — composition with the `call` step

`workflows/scenarios/tutorial-07-composition.yaml`:

```yaml
version: 1
name: tutorial-07-composition
description: Comes up with a name, the tutorial-07-slogan scenario supplies a slogan and tone-check checks the tone (tutorial, part 7)

inputs:
  product:
    type: string
    required: true
    description: The product we are naming

outputs:
  name:
    type: string
    description: The proposed name
  slogan:
    type: string
    description: Slogan from the tutorial-07-slogan scenario
  on_brand:
    type: number
    description: Tone rating from the tone-check scenario

steps:
  # 1. A plain ask from part 2.
  - id: propose
    ask:
      agent: tutorial-namer
      prompt: "Come up with one name for this product: {{ inputs.product }}."
      schema:
        name: string

  # 2. Our own building block: the name input is required, tone has a default.
  - id: slogan
    call:
      scenario: tutorial-07-slogan
      inputs:
        name: "{{ steps.propose.name }}"

  # 3. A ready-made building block from workflows/: threshold has a default of 0.7.
  - id: tone
    call:
      scenario: tone-check
      inputs:
        text: "{{ steps.propose.name }}. {{ steps.slogan.slogan }}"

  - id: out
    output:
      name: "{{ steps.propose.name }}"
      slogan: "{{ steps.slogan.slogan }}"
      on_brand: "{{ steps.tone.on_brand }}"
```

- `call.scenario` = the name of the scenario, `call.inputs` = its inputs
  (templates as in `prompt`).
- The output of a `call` step is the `outputs` of the called scenario:
  `steps.slogan.slogan`, `steps.tone.on_brand`.
- The called scenario runs **inside the same run**: the same budget, the same
  timeout, one record. It is not a new run in the queue.

### The fixture: the path to a step inside

The steps of a called scenario have a **path**
`<call step id>/<step id inside>` in the fixture (and in the record).
`fake/tutorial-07-composition.yaml`:

```yaml
# Scripted responses for tutorial-07-composition. Steps of called scenarios
# have the path <call step id>/<step id in the called scenario>.
propose:
  - json: { name: "Ovena" }
slogan/write:
  - json: { slogan: "Ovena. Ice cream that grows in the field." }
tone/check:
  - answers: { on_brand: 0.82 }
```

(And `fake/tutorial-07-slogan.yaml` with the key `write` for the building block
on its own — it is a golden test too.)

```bash
agencast validate tutorial-07-composition
agencast run tutorial-07-composition -i product="vegan ice cream made from oat milk" --fake fake/tutorial-07-composition.yaml
```

```
valid: tutorial-07-composition (4 steps)
run 20260929-190129-tutorial-07-composition-e97b: succeeded · 0.0 s · 0.0003 USD
```

```
| 1 | propose | ask | ✓ | 0.0 s | 0.0001 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | slogan | call | ✓ | 0.0 s | 0.0001 | scenario tutorial-07-slogan (2 steps) |
| 3 | tone | call | ✓ | 0.0 s | 0.0001 | scenario tone-check (3 steps) |
| 4 | out | output | ✓ | 0.0 s | 0 |  |
| | Total | | | 0.0 s | 0.0003 |  |
…
## Output
- name: “Ovena”
- slogan: “Ovena. Ice cream that grows in the field.”
- on_brand: 0.82
```

The record of a called scenario is a subfolder of the `call` step:

```
steps/
  01-propose/
  02-slogan/
    inputs.json            what the building block received (after filling in the default: tone = playful)
    output.json            what it returned
    steps/01-write/        prompt.md, calls/…
    steps/02-out/
  03-tone/
    inputs.json
    output.json
    steps/01-check/ …
  04-out/
```

And in `events.jsonl` the steps inside have a path: `slogan/write`,
`tone/check`, `tone/result`…

### What `validate` says when the contract does not match

Try it in a copy (`rm -rf /tmp/experiment && mkdir -p /tmp/experiment && cp -r
workflows /tmp/experiment/`) and run `agencast validate
/tmp/experiment/workflows/scenarios/tutorial-07-composition.yaml`.

A required input is missing (you pass `product` instead of `name`):

```
config: tutorial-07-composition.yaml: step "slogan", call.inputs: scenario 'tutorial-07-slogan' has no inputs named: product (has: name, tone)
config: tutorial-07-composition.yaml: step "slogan", call.inputs: missing required inputs for scenario 'tutorial-07-slogan': name
```

An extra input (`length: short`):

```
config: tutorial-07-composition.yaml: step "slogan", call.inputs: scenario 'tutorial-07-slogan' has no inputs named: length (has: name, tone)
```

The wrong type (`threshold: high` into `tone-check`):

```
config: tutorial-07-composition.yaml: step "tone", call.inputs.threshold: input has type number, value is string
```

Reading an output the building block does not have (`steps.slogan.text` — as
with an `ask` without `schema`):

```
config: tutorial-07-composition.yaml: step "out", output.slogan: 'steps.slogan' has no key 'text' (available: slogan)
  {{ steps.slogan.text }}
                  ^
```

Calling a scenario without `callable: true` (`scenario: tutorial-02-name-and-slogan`):

```
config: tutorial-07-composition.yaml: step "slogan", call.scenario: scenario 'tutorial-02-name-and-slogan' has no callable: true — it cannot be called (protects human approval, §5.2)
```

**A cycle.** Put `callable: true` into the copy of
`tutorial-07-composition.yaml`, and into the copy of `tutorial-07-slogan.yaml`,
before `out`, a step that calls the composition back:

```yaml
  - id: again
    call:
      scenario: tutorial-07-composition
      inputs:
        product: "{{ inputs.name }}"
```

```
config: tutorial-07-slogan.yaml: step "again", call.scenario: call cycle: tutorial-07-composition → tutorial-07-slogan → tutorial-07-composition
```

The framework would otherwise call the scenarios endlessly (and pay for it).
Besides cycles it also guards the nesting depth: `limits.max_call_depth` in
`config.yaml`, 3 in our project.

---

## Step 4 — `agencast serve`: the framework as a web service

In operation, runs are not started by you from a terminal but by an automation tool: it sends
a `POST` saying what to run, immediately gets a `run_id`, and the result
arrives later at its address (the callback). That is exactly what
`agencast serve` does.

### Two secret values in `.env`

`config.yaml` (the owner) says how the variables are named:

```yaml
webhook:
  token_env: WEBHOOK_TOKEN
callback:
  secret_env: CALLBACK_SECRET
```

- **`WEBHOOK_TOKEN`** — the password that everyone who wants to start a run must
  send (the header `Authorization: Bearer …`). Without it, anyone who knows the
  address could run scenarios at your expense.
- **`CALLBACK_SECRET`** — the secret the framework signs the result with. The
  recipient uses the signature to tell that the message was really sent by
  your framework and that nobody changed it on the way.

Generate the values and append them to `.env` **without printing them to the
screen** (`.env` is in `.gitignore`, so it will not get into git):

```bash
python3 -c "import secrets; open('.env', 'a').write(f'\nWEBHOOK_TOKEN={secrets.token_urlsafe(32)}\nCALLBACK_SECRET={secrets.token_urlsafe(32)}\n')"
cut -d= -f1 .env
```

```
OPENROUTER_API_KEY

WEBHOOK_TOKEN
CALLBACK_SECRET
```

`cut` shows only the names. Do not copy or print the values anywhere — when you
set up the caller, store them in its secret store. If you have
`export CALLBACK_SECRET=…` in the terminal from part 5, remove it
(`unset CALLBACK_SECRET`): a variable from the environment takes precedence
over `.env`.

Without `WEBHOOK_TOKEN` the server does not start:

```
config: missing environment variable WEBHOOK_TOKEN (.env or environment)
```

Without `CALLBACK_SECRET` it starts, but a request with a `callback_url` is
rejected (422) — the framework will not accept a run whose callback it could
not sign:

```
{"error": "invalid request", "details": ["missing environment variable CALLBACK_SECRET (callback signature)"]}
```

### Three terminals

**Terminal 1 — the callback receiver.** Instead of the real receiver, a small script,
[`docs/tutorials/callback-receiver.py`](callback-receiver.py) (stdlib only): it
prints what arrived and verifies the signature. It reads the secret from the
environment (or from a `.env` in the repository root), so pass it from the
tutorial's `.env` without printing it:

```bash
CALLBACK_SECRET=$(sed -n 's/^CALLBACK_SECRET=//p' .env) python3 ../../docs/tutorials/callback-receiver.py
```

```
waiting for a callback at http://127.0.0.1:8799/ (Ctrl+C to stop)
```

**Terminal 2 — the server**, for now with the fake provider and the fixture
from step 3:

```bash
agencast serve --fake fake/tutorial-07-composition.yaml
```

```
agencast serve: http://127.0.0.1:8080 — POST /runs, GET /runs/<run_id>, GET /projects/… · workers 1 · queued 0 runs · run records …/runs · fake provider
```

It listens only on `127.0.0.1` (the default `--host`) — you cannot reach it from
another computer. Leave it that way: the server is plain HTTP and the token
travels in a header; it belongs outside only behind a reverse proxy with HTTPS.

**Terminal 3 — you as the caller.** Load the token into a terminal variable (it is not
printed):

```bash
TOKEN=$(sed -n 's/^WEBHOOK_TOKEN=//p' .env)
```

---

## Step 5 — `POST /runs`: 401, 422, 202

Without a token (or with a wrong one):

```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST http://127.0.0.1:8080/runs \
  -H 'Content-Type: application/json' \
  -d '{"scenario": "tutorial-07-composition", "inputs": {"product": "vegan ice cream"}, "callback_url": "http://127.0.0.1:8799/cb"}'
```

```
{"error": "missing or invalid token (Authorization: Bearer … header)"}
HTTP 401
```

With a token, but without the required input (`"inputs": {}`):

```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST http://127.0.0.1:8080/runs \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"scenario": "tutorial-07-composition", "inputs": {}, "callback_url": "http://127.0.0.1:8799/cb"}'
```

```
{"error": "scenario 'tutorial-07-composition' or its inputs failed validation", "details": ["missing required input 'product' (string)"]}
HTTP 422
```

More 422s that are worth seeing (you change only the body):

| Body | Response |
|---|---|
| `"scenario": "tutorial-07-compositionn"` | `{"error": "unknown scenario 'tutorial-07-compositionn'", "details": []}` |
| `"inputs": {"product": 42}` | `"details": ["input 'product' must be string, got number"]` |
| `"callback_url": "http://example.com/cb"` | `"details": ["callback_url: missing or does not start with https://"]` |
| additionally `"priority": "high"` | `"details": ["unknown field 'priority' (allowed: scenario, inputs, callback_url, request_key)"]` |

Everything that can be detected without running — the token, the shape of the
body, the inputs, the scenario's `validate` — is rejected **immediately**. Then
no `run_id` and no callback are created; the caller has the error in the response and
does not have to wait for anything.

`callback_url` may only be `https://`. The one exception is `http://127.0.0.1` —
for experiments like this one.

A correct request, this time with a `request_key`:

```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST http://127.0.0.1:8080/runs \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"scenario": "tutorial-07-composition", "inputs": {"product": "vegan ice cream made from oat milk"}, "callback_url": "http://127.0.0.1:8799/cb", "request_key": "tutorial-07-1"}'
```

```
{"run_id": "20260929-190232-tutorial-07-composition-ad60", "queue_position": 1}
HTTP 202
```

**202 = accepted**, not finished. The run is in the queue (`queue_position` 1 =
it is next). Runs go one after another.

### The callback

In terminal 1 this appears right away:

```
POST /cb  X-Run-Id: 20260929-190232-tutorial-07-composition-ad60
signature: valid
{
  "run_id": "20260929-190232-tutorial-07-composition-ad60",
  "scenario": "tutorial-07-composition",
  "request_key": "tutorial-07-1",
  "status": "succeeded",
  "outputs": {
    "name": "Ovena",
    "slogan": "Ovena. Ice cream that grows in the field.",
    "on_brand": 0.82
  },
  "error": null,
  "warnings": [],
  "cost_usd": 0.0003,
  "duration_s": 0.004,
  "report_url": "file:///…/outputs/20260929-190232-tutorial-07-composition-ad60-d204c61d8af9461e26c990aba1d00f26/report.html",
  "sent_at": "2026-09-29T19:02:32.733Z"
}
```

The same shape as in part 5 (the fields are in the table there). New is
`report_url` (step 7). How the receiver verifies the signature is in its code,
in ten lines: it computes the HMAC-SHA256 of the **exact bytes of the body**
with `CALLBACK_SECRET` and compares it with the `X-Signature` header using
`hmac.compare_digest` (a comparison whose duration does not reveal where they
differ). When the signature does not match, it prints "INVALID" and answers
401 — the framework then tries twice more and records `callback_failed`
(part 5).

### `GET /runs/<run_id>`

When the callback did not arrive (the receiver was down at that moment), the state can
be looked up:

```bash
curl -s -w '\nHTTP %{http_code}\n' -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/runs/20260929-190232-tutorial-07-composition-ad60
```

```
{"run_id": "20260929-190232-tutorial-07-composition-ad60", "scenario": "tutorial-07-composition", "request_key": "tutorial-07-1", "status": "succeeded", "outputs": {"name": "Ovena", "slogan": "Ovena. Ice cream that grows in the field.", "on_brand": 0.82}, "error": null, "warnings": [], "cost_usd": 0.0003, "duration_s": 0.004, "report_url": "file:///…/report.html", "sent_at": "2026-09-29T19:02:32.733Z", "callback_failed": false}
HTTP 200
```

A finished run = the callback body + `callback_failed`. While the run waits or
runs, it returns `{"status": "queued", "queue_position": …}` or
`{"status": "running"}` respectively. An unknown `run_id` → 404. `GET` needs the
token too.

---

## Step 6 — `request_key`: send it twice

The caller sometimes sends the same request again — the network drops before it
receives the response, and it repeats the request. Send exactly the
same `curl` (with the same `request_key`) a second time:

```
{"run_id": "20260929-190232-tutorial-07-composition-ad60", "queue_position": null}
HTTP 200
```

**200 instead of 202**, the original `run_id`, no new run, no second callback.
The server remembers the key in `runs/_queue/keys/` (one file per key), so this
holds even after a server restart.

Watch out: **only the key** decides. A request with the same `request_key` but
different inputs also gets 200 and the original run. That is why the caller must send a
key that belongs to one request (e.g. the id of its own run), not to a topic.

---

## Step 7 — `report.html`

Besides `summary.md`, every run also has `report.html` — a single file, CSS
inside, no external resources, so it can be sent by e-mail or opened offline.
The framework copies it to the storage and puts its address into the callback
(`report_url`). In our project `storage.type: local`, so it is a `file://`
path:

```bash
xdg-open "$(ls -d outputs/20260929-190232-tutorial-07-composition-ad60-*)/report.html"   # macOS: open
```

(Or copy `report_url` into a browser.) At the top is the same summary as in
`summary.md`, under each step an expandable `<details>`:

```
Prompt
Call 1 · smart → anthropic/claude-haiku-4.5 · stop · 264+15 tokens · 0.0003 USD · 1.4 s
Step output
```

(This line is from the live run in step 9.) The steps of called scenarios are in
the report too, including the Jev calls. Base64 images and secret values are not
in it (the same rules as the run record, part 5).

Why it is in the callback: the caller sees only `outputs` and `error`. When a
result looks odd, `report_url` is one click to everything the model received and
returned. With R2 storage (the owner, `config.yaml`) it becomes a public HTTPS
address with 32 random characters that nobody can guess.

---

## Step 8 — `dedupe_key`: a side effect at most once

`request_key` protects against **the same request** twice. But it does not
protect against **two different requests** that do the same thing — typically
when the caller starts a workflow again (a manual "Retry", a new run = a new key). For
a step that only writes something into `outputs`, that does not matter. For a
step with a **side effect** — it writes a file, publishes a post, sends an
e-mail — it does: the post would go out twice.

That is what `dedupe_key` on a `task` step is for.
`workflows/scenarios/tutorial-07-archive.yaml` (the archivist from part 6):

```yaml
version: 1
name: tutorial-07-archive
description: Writes the day's note to the archive at most once, even when the request comes again (tutorial, part 7)

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
    description: What the archivist wrote (on a repeat, the reply from the first run)

steps:
  # 1. A step with a side effect (writing). dedupe_key: for the same day it runs
  #    at most once — the next run takes the output from <runs>/_dedupe/ and skips the step.
  - id: write
    dedupe_key: "archive-{{ inputs.day }}"
    task:
      agent: tutorial-archivist
      prompt: |
        Day: {{ inputs.day }}
        Note: {{ inputs.text }}
        Write the note to the archive and check it.
      max_turns: 5

  - id: out
    output:
      message: "{{ steps.write.text }}"
```

The fixture `fake/tutorial-07-archive.yaml` has the same turns as
`tutorial-06-archive`. Restart the server (terminal 2, Ctrl+C) with it:

```bash
agencast serve --fake fake/tutorial-07-archive.yaml
```

and send two **different** requests (`caller-5001`, `caller-5002`) for the same day:

```bash
for k in caller-5001 caller-5002; do
  curl -s -w '\nHTTP %{http_code}\n' -X POST http://127.0.0.1:8080/runs \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d "{\"scenario\": \"tutorial-07-archive\", \"inputs\": {\"day\": \"2026-09-25\", \"text\": \"It rained in the morning. In the afternoon we finished part 7.\"}, \"callback_url\": \"http://127.0.0.1:8799/cb\", \"request_key\": \"$k\"}"
  sleep 3
done
```

```
{"run_id": "20260929-190253-tutorial-07-archive-4a37", "queue_position": 1}
HTTP 202
{"run_id": "20260929-190256-tutorial-07-archive-42ac", "queue_position": 1}
HTTP 202
```

Two runs, two callbacks, both `succeeded` with the same `message`. The
difference is in the cost (`cost_usd` 0.0004 vs. **0.0**) and in the
`summary.md` of the second run:

```
| 1 | write | task | skipped |  |  | dedupe_key 'archive-2026-09-25': step already ran in run 20260929-190253-tutorial-07-archive-4a37 |
| 2 | out | output | ✓ | 0.0 s | 0 |  |
| | Total | | | 0.0 s | 0 |  |
```

The second run has no `work/` or `mcp/` folder — the server did not start at
all. The step output was taken from a file in `runs/_dedupe-fake/` (runs with
`--fake` have their own folder since `maw` 0.2.2, live runs use
`runs/_dedupe/` — see [below](#watch-out---fake-has-its-own-runs_dedupe-fake)):

```bash
cat runs/_dedupe-fake/*.json
```

```
{"state": "succeeded", "run_id": "20260929-190253-tutorial-07-archive-4a37", "output": {"text": "Written: 2026-09-25.md and index.md. The entry has 2 sentences."}}
```

The file name is the SHA-256 of `scenario/step/key` — the same day in another
scenario (say `tutorial-06-archive`) will not clash.

### When a step crashes in the middle

The framework writes `"state": "started"` **before the first tool call** and
`succeeded` only after the step has ended successfully. What if the step
crashes in between? Simulate it from the CLI — `/tmp/interrupted.yaml` writes a
file and then keeps looping until the turns run out:

```yaml
# Writes a file and then only keeps calling tools until the turns run out (max_turns) — the step fails after the side effect.
write:
  - tool_calls:
      - name: filesystem__write_file
        arguments: { path: 2026-09-26.md, content: "# Entry 2026-09-26\n- Draft.\n" }
  - tool_calls:
      - { name: filesystem__list_directory, arguments: { path: . } }
```

```bash
agencast run tutorial-07-archive -i day=2026-09-26 -i text="Draft." --fake /tmp/interrupted.yaml
agencast run tutorial-07-archive -i day=2026-09-26 -i text="Draft." --fake /tmp/interrupted.yaml
```

```
budget in step write: max_turns 5 exhausted without a final answer (model keeps calling tools)
run 20260929-190315-tutorial-07-archive-3cd9: failed · 1.0 s · 0.0005 USD
…
config in step write: step may have run only partially (dedupe_key 'archive-2026-09-26', run 20260929-190315-tutorial-07-archive-3cd9), check manually and delete …/runs/_dedupe-fake/2f3d332e9f17953dc0ebe9557a55653cd0f503dc80ccf668a0470750b1847dff.json
run 20260929-190317-tutorial-07-archive-d83a: failed · 0.0 s · 0 USD
```

The second run did **not** start the step. The framework does not know whether
the first run managed to publish (here it managed to write the file) — and it
will not guess. Look into the record of the first run (`tool_call`, `work/`),
and once you know it is fine, delete the file. Nothing is silently repeated.

### Watch out: `--fake` has its own `runs/_dedupe-fake/`

Fake runs write the dedupe state to `runs/_dedupe-fake/`, live runs to
`runs/_dedupe/`, and they never read each other's. So a rehearsal with `--fake`
does not skip a live side effect: a live run for a day you rehearsed with
`--fake` really performs the `write` step. You recognise a fake run in
`summary.md` by the line under the header:

```
**Fake run** (`--fake`) — model responses are fabricated, dedupe in `_dedupe-fake/`.
```

and in `events.jsonl` by `"fake": true` in `run_started`. (In `maw` 0.2.1 both
modes shared `runs/_dedupe/`, and a live run after a rehearsal returned a made-up
output — BUGS.md, item 8.)

---

## Step 9 — a live run through the webhook (optional)

Stop the server (Ctrl+C) and start it **without** `--fake`:

```bash
agencast serve
```

```
agencast serve: http://127.0.0.1:8080 — POST /runs, GET /runs/<run_id>, GET /projects/… · workers 1 · queued 0 runs · run records …/runs
```

```bash
curl -s -w '\nHTTP %{http_code} in %{time_total} s\n' -X POST http://127.0.0.1:8080/runs \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"scenario": "tutorial-07-composition", "inputs": {"product": "vegan ice cream made from oat milk"}, "callback_url": "http://127.0.0.1:8799/cb", "request_key": "tutorial-07-live-1"}'
```

```
{"run_id": "20260925-161929-tutorial-07-composition-217a", "queue_position": 1}
HTTP 202 in 0.032238 s
```

The callback in under 4 s:

```
POST /cb  X-Run-Id: 20260925-161929-tutorial-07-composition-217a
signature: valid
{
  …
  "status": "succeeded",
  "outputs": {
    "name": "Oat Cream",
    "slogan": "Oat Cream - health in every spoonful!",
    "on_brand": 0.25
  },
  "error": null,
  "warnings": [],
  "cost_usd": 0.00071494,
  "duration_s": 3.787,
  …
}
```

```
| 1 | propose | ask | ✓ | 1.4 s | 0.0003 | smart → anthropic/claude-haiku-4.5 (native_schema) |
| 2 | slogan | call | ✓ | 2.0 s | 0.0004 | scenario tutorial-07-slogan (2 steps) |
| 3 | tone | call | ✓ | 0.4 s | 0.00002 | scenario tone-check (3 steps) |
```

`on_brand` 0.25 — a slogan with an exclamation mark and "health in every
spoonful" is not the Lumen tone. The run still ended in success: `tone-check`
only measures, the caller decides, and `tutorial-07-composition` has no `fail`.
If you wanted to stop an unsuitable text, add a step after `tone` as in the
showcase's `demo-call.yaml`:

```yaml
  - id: stop
    when: not steps.tone.passed
    fail: "The slogan does not match the brand (on_brand = {{ steps.tone.on_brand }})"
```

At the end, stop both the server and the receiver (Ctrl+C).

---

## Step 10 — what the caller needs from this

We do not set up an automation tool here, only what the caller needs to do. It
can be built from two workflows in any tool that can send an HTTP request and
receive a webhook:

**Workflow A — starting**

1. A trigger (a webhook, a form, a schedule) receives the input, e.g. `product`.
2. An HTTP request: `POST https://<your-agencast>/runs`, the header
   `Authorization: Bearer <WEBHOOK_TOKEN>` (store the token in the tool's secret
   store, not in the workflow text), the body:

   ```json
   {
     "scenario": "tutorial-07-composition",
     "inputs": {"product": "…from step 1…"},
     "callback_url": "https://<caller>/webhook/agencast-result",
     "request_key": "caller-<caller run id>"
   }
   ```

   A 202 response → done, save the `run_id`. 401/422 → the error is right in the
   response (`details`), no callback will come.

**Workflow B — the result**

3. A webhook on the path `agencast-result`, method `POST`, with access to the
   **raw body** (the signature is computed from the exact bytes of the body, not
   from the JSON that the caller parses and reassembles — part 5), answering
   immediately (the framework only waits for a 2xx).
4. Compute HMAC-SHA256 of the raw body with `CALLBACK_SECRET`, hex-encoded, and
   compare it with the `x-signature` header without the `sha256=` prefix. No
   match → stop, do not trust the message.
5. Branch on `status` and `error.class`: `succeeded` → continue (approval,
   publishing), `fail` → an intentional stop by the scenario (e.g. the tone),
   other classes → a malfunction, alert a human. Attach `report_url` to the
   alert.

Instead of workflow B, the caller can wait for the callback in workflow A if its
tool supports a per-run resume address, and send that address as the
`callback_url` (as `/webhook-waiting/4711` in part 5). Then set a time limit on the wait:
a run can wait in the queue, and if the callback never arrives, the caller would
otherwise wait forever.

What the caller does **not** need to know: the models, the agents, the MCP servers or
what a scenario looks like inside. The contract is `scenario` + `inputs` in,
`outputs` + `status` + `error` out.

---

## What you have learned

- `callable: true` + `inputs` + `outputs` = a building block. `call` runs in the
  same run; `validate` guards missing/extra inputs, types, outputs that are read,
  `callable` and cycles.
- The fixture and the record: steps inside have the path `<call>/<step>`.
- `agencast serve`: `WEBHOOK_TOKEN` and `CALLBACK_SECRET` in `.env`; 401/422
  immediately and without a callback, 202 = queued, a callback always and signed,
  `GET /runs/<id>` as a fallback.
- `request_key` = the same request only once; `dedupe_key` = the same side
  effect only once, even across runs. `started` without `succeeded` = check
  manually.
- `report_url` = the whole record with one link.

---

## Exercise

You want two slogans for one name at once — a playful one and a serious one.
Write `workflows/scenarios/tutorial-07-exercise.yaml` that calls
`tutorial-07-slogan` **twice in parallel** (part 4) with a different `tone`,
and a fixture for it. Hint: what will the steps inside be called in the
fixture?

<details>
<summary>Solution</summary>

```yaml
version: 1
name: tutorial-07-exercise
description: Two slogans for one name at once — the tutorial-07-slogan building block twice in parallel (tutorial, part 7 — exercise solution)

inputs:
  name:
    type: string
    required: true
    description: Product name

outputs:
  playful:
    type: string
    description: Playful slogan
  serious:
    type: string
    description: Serious slogan

steps:
  # The same scenario twice, each branch with a different tone. The call steps have different ids,
  # so they have different paths in the record and in the fixture (playful_slogan/write, serious_slogan/write).
  - id: variants
    parallel:
      playful:
        - id: playful_slogan
          call:
            scenario: tutorial-07-slogan
            inputs:
              name: "{{ inputs.name }}"
      serious:
        - id: serious_slogan
          call:
            scenario: tutorial-07-slogan
            inputs:
              name: "{{ inputs.name }}"
              tone: serious

  - id: out
    output:
      playful: "{{ steps.playful_slogan.slogan }}"
      serious: "{{ steps.serious_slogan.slogan }}"
```

`fake/tutorial-07-exercise.yaml`:

```yaml
# Scripted responses for tutorial-07-exercise (exercise solution from part 7).
# Path = <call step id>/<step id in the called scenario>; the parallel branch is not part of the path.
playful_slogan/write:
  - json: { slogan: "Ovena. The spoon that smiles." }
serious_slogan/write:
  - json: { slogan: "Ovena. Plant-based smoothness in every spoonful." }
```

Inside both calls there is a `write` step — only the `id` of the `call` step
tells them apart. That is why every call must have its own `id` (`validate`
would insist on it anyway).

```bash
agencast run tutorial-07-exercise -i name=Ovena --fake fake/tutorial-07-exercise.yaml
```

```
| 1 | variants | parallel | ✓ | 0.0 s | 0.0002 |  |
| 2 | playful_slogan | call | ✓ | 0.0 s | 0.0001 | scenario tutorial-07-slogan (2 steps) |
| 3 | serious_slogan | call | ✓ | 0.0 s | 0.0001 | scenario tutorial-07-slogan (2 steps) |
| 4 | out | output | ✓ | 0.0 s | 0 |  |
| | Total | | | 0.0 s | 0.0002 |  |
…
## Output
- playful: “Ovena. The spoon that smiles.”
- serious: “Ovena. Plant-based smoothness in every spoonful.”
```

You can verify that every branch got its own tone in the prompts:

```bash
grep Tone runs/20260929-190326-tutorial-07-exercise-f544/steps/*/steps/01-write/prompt.md
```

```
runs/…/steps/02-playful_slogan/steps/01-write/prompt.md:Tone: playful
runs/…/steps/03-serious_slogan/steps/01-write/prompt.md:Tone: serious
```

`playful` came from the building block's `default`, `serious` from the call.

```bash
cd ../../framework && uv run pytest -k tutorial-07 -v; cd ../examples/tutorial
```

```
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-07-archive] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-07-composition] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-07-exercise] PASSED
tests/test_golden.py::test_workflow_scenario_runs_with_fake[tutorial-07-slogan] PASSED
```

</details>

---

## What comes next

This is where the series ends. What `maw` 0.2.1 cannot do yet and what comes with
Phase 3c of the framework: a hosted deployment and R2 storage, with which
`report_url` and the files from `output` will be a public HTTPS address. An
overview of all the parts is in [README.md](README.md).
