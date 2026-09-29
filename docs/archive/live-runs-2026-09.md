# Live runs — September 2026

These are archived protocols from development; they preserve the results and context of the time.
Scenario, step, agent and file names, the run folder names under `runs/` and the request
key follow the current English names in `examples/showcase/`; timestamps, hashes and results
are kept as recorded.

## Live webhook test (Phase 3b, 2026-09-25)

`agencast serve --port 8788` locally (against OpenRouter, `examples/showcase/workflows/config.yaml`
unchanged), a callback receiver at `http://127.0.0.1:8799/cb` (verifies the
HMAC), `WEBHOOK_TOKEN` and `CALLBACK_SECRET` generated just for the test.
One `POST /runs` with `ig-post`, the topic “morning espresso on the way to work”,
`request_key: live-test-3b-1`.

| What | Result |
|---|---|
| response to `POST /runs` | **202** `{"run_id": "20260925-152331-ig-post-3820", "queue_position": 1}` in **0.10 s** |
| callback | arrived **4.1 s** after the POST, `X-Signature` verified, `X-Run-Id` matches |
| run | `failed`, class `fail` in step `stop`: on_brand = 0.56 (threshold 0.7) — a deliberate end by the scenario, as in Phase 2 |
| steps | `copy` (Claude Haiku 4.5, 3.6 s, 0.0013 USD) → `tone_check` (Jev 1.13, 0.4 s) → `stop` |
| cost, run time | **0.0013 USD**, 3.96 s |
| `report_url` | `file://…/outputs/20260925-152331-ig-post-3820-<32 hex>/report.html` (4.8 kB, without base64 and secret values) |
| `GET /runs/<run_id>` | 200, `status: failed`, `callback_failed: false` |
| a repeated POST with the same `request_key` | **200**, the original `run_id`, no new run |

Phase 3b spend: **0.0013 USD**.

## Live run (Phase 2, 2026-09-25)

`agencast --project examples/showcase run ig-post` against OpenRouter, the aliases
`smart` = `anthropic/claude-haiku-4.5`, `fast` =
`google/gemini-3.5-flash-lite` (`tool_wrapper`), `gemini-image` =
`google/gemini-3.1-flash-image`. `agencast validate` against `GET /models` passed.

| Run | Topic | Result | Time | Cost |
|---|---|---|---|---|
| `runs/20260925-145904-ig-post-81e5` | morning coffee with friends | `fail` in step `stop`: on_brand = 0.68 | 6.2 s | 0.0013 USD |
| `runs/20260925-145923-ig-post-d686` | new Lumen coffee | `fail` in step `stop`: on_brand = 0.63 | 2.8 s | 0.0013 USD |

Phase 2 spend in total **0.0026 USD**. Both runs went exactly as the
scenario says: `copy` (Claude Haiku via Amazon Bedrock, `native_schema`,
2.6–5.8 s, 0.0012 USD) → `tone_check` (Jev `typesafe/jev-1.13-20260917`,
0.27–0.41 s, 0.000016 USD) → a deliberate `fail` below the threshold of 0.7. The record
(summary, events, request/response without the key) is complete.

**A threshold of 0.7 is strict for text from Haiku; the scenario behaved correctly.** Jev
rated the copywriter's text (Claude Haiku 4.5) below the threshold twice (0.68
and 0.63), so the run ended with a deliberate `fail` before it got to the photo. The content
of the text and the threshold are in the user layer (the `copywriter` agent,
`ig-post.yaml`), not in the framework. I did not start a third `ig-post` run, per the brief
(at most 2 attempts).

The remaining steps were verified, with the coordinator's consent, by **one** live run
of a temporary scenario `live-image` (outside `workflows/`, not committed):
an `ask` with the agent `photographer` + `image` with `aspect_ratio: "4:5"`.

| Run | Step | Result | Time | Cost |
|---|---|---|---|---|
| `runs/20260925-150206-live-image-7210` (success, 11.0 s in total, 0.0676 USD) | `photo_prompt` | `google/gemini-3.5-flash-lite` via `tool_wrapper`: `finish_reason: tool_calls` (natively `STOP`), `_submit_output` valid on the first try | 1.5 s | 0.0003 USD |
| | `photo` | `google/gemini-3.1-flash-image`, `image_config.aspect_ratio: "4:5"` → PNG **928×1152** (1.83 MB), ratio 0.806 vs. 0.8 = a deviation of 0.7 % → **4:5 holds** (spec D10 check, tolerance 2 %) | 9.5 s | 0.0672 USD |

Record: there is no base64 or `reasoning_details` in `calls/*.json` (only
`<file: steps/02-photo/image.png, 1834634 B>`), the image is in the step
folder and copied to `outputs/<run_id>-<32 hex>/image.png`.

**Phase 2 spend in total 0.0702 USD** (2× `ig-post` 0.0026 + `live-image`
0.0676; `GET /models` is free).

## Live run of Phase 3a (2026-09-25): a `task` step with a real MCP server

`agencast --project examples/showcase run demo-task -i books="Karel Čapek:
Rossum's Universal Robots (1920); Božena Němcová: The Grandmother (1855); Jaroslav Hašek:
The Good Soldier Schweik (1921)"`, the agent `librarian` on the alias `smart` =
`anthropic/claude-haiku-4.5` (`native_schema`), the MCP server
`@modelcontextprotocol/server-filesystem@2026.8.31` via `npx -y`,
root `runs/<run>/work`. `agencast validate` against `GET /models` passed.

| Run | Result | Time | Turns | Cost |
|---|---|---|---|---|
| `runs/20260925-152451-demo-task-9190` | **success**: `catalog.md` with 3 books sorted by surname (per the skill), output `{path, count: 3}` | 21.7 s | 4 turns, 4 tools | 0.0104 USD |
| `runs/20260925-152121-demo-task-f370` | step `timeout` (3m): turn 2 — the HTTP request to OpenRouter got no response for 160 s | 180.0 s | 1 turn, 2 tools | 0.0019 USD |

The successful run: server start + handshake 0.77 s; turn 1 `list_allowed_directories`
+ `load_skill catalog` (1.7 s), turn 2 `write_file` (4.0 s), turn 3
`read_text_file` (1.7 s), turn 4 the final JSON (13.5 s, provider
Anthropic; turns 1–3 Amazon Bedrock). Tools 5–7 ms. After the run 0 server processes,
`summary.md` and `events.jsonl` complete (`mcp_server`
started/stopped, 4× `tool_call`, 4× `model_call` with `turn`).

The first run failed on a stuck provider call: the framework behaved
per the spec (class `timeout`, the server terminated, the record complete), but a stuck
connection is only detected by the step limit — see `docs/spec/ISSUES.md` item 34.
The same request (`calls/04.request.json`) repeated by hand went through in
2.1 s with and without `response_format` (0.0055 USD).

**Phase 3a spend in total 0.0178 USD** (2 runs 0.0123 + diagnostics 0.0055).
