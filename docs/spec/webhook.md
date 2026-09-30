# Webhook — starting a run (specification v1)

A run is started by n8n (or anyone with the token) with a request to the
webhook. The response comes immediately; the result comes later to
`callback_url` (D2). Shape of the callback:
[run-record.md](run-record.md#callback).

Notation: **proposal** = not covered by DESIGN.md; proposed default behavior.

Reading projects and runs over HTTP (`GET /projects/...`) and starting a run
in a specific project (`POST /projects/<p>/runs`, otherwise the same as
`POST /runs`) are described in [api.md](api.md) (since framework 0.4.0);
starting from the GUI without `callback_url` and with `dry_run` only there
([api.md “Starting from the GUI”](api.md#starting-from-the-gui-since-060),
since 0.6.0). This contract does not change.

## Request

```http
POST /runs
Authorization: Bearer <token>
Content-Type: application/json

{
  "scenario": "ig-post",
  "inputs": { "topic": "new coffee" },
  "callback_url": "https://n8n.example.com/webhook-waiting/4711",
  "request_key": "n8n-4711"
}
```

| Field | Required | What it does | When missing | Example |
|---|---|---|---|---|
| `Authorization` header | yes | `Bearer <token>`; the token is the value of the variable named in `webhook.token_env` in `config.yaml` (Modal endpoints are otherwise public, D5). | 401 | |
| `scenario` | yes | Name of a scenario from `workflows/scenarios/`. | 422 | `"ig-post"` |
| `inputs` | no | Inputs according to the scenario's `inputs`. Types `file` and `files` are not allowed from the webhook (422) — a JSON string is never a path. | `{}` — the scenario gets its `default` values. | `{"topic": "new coffee"}` |
| `callback_url` | yes | Where to send the result. `https://` only. Typically the resume URL of a waiting n8n workflow. | 422 | |
| `request_key` | no | Idempotency key (§5.2): a repeated request with the same key does not start a second run. | Every request = a new run. | `"n8n-4711"` |

## Responses

| Status | When | Body | `run_id` / callback |
|---|---|---|---|
| **202** | request accepted, run is queued | `{"run_id": "…", "queue_position": 2}` | yes / yes |
| **200** | `request_key` was already used | `{"run_id": "<original>", "queue_position": null}` | original run / callback of the original run, no new one is created |
| **401** | token missing or wrong | `{"error": "…"}` | no / no |
| **422** | unknown scenario, inputs do not match `inputs`, `callback_url` is not `https`, or the scenario did not pass `validate` | `{"error": "…", "details": [...]}` | no / no |

- **Synchronously** (401, 422) everything that can be detected without
  starting is rejected: token, body shape, inputs, `validate` of the
  scenario. Then **no `run_id` and no callback are created** — the caller
  gets the error right in the response.
- **`queue_position`** is computed by the framework (Modal does not provide
  it reliably, D5); it may be `null` when unknown. It is information, not a
  promise.
- **Concurrent runs** (since framework 0.3.0): `agencast serve --workers N`
  (default 1) runs N runs at once from a single queue. `queue_position`
  then counts waiting and running requests including this one — a value ≤ N
  means the run is already running or starts as soon as a worker is free.
  **The order of completion (and therefore of callbacks) is not
  guaranteed**; with `--workers 1` runs go one after another in the order
  received. With `limits.max_parallel_runs`
  ([config.md](config.md#limits--safeguards-for-the-whole-run), since 0.3.1)
  a dequeued run also waits for a free slot, which is shared with the CLI
  and cron.
- **Once a `run_id` is assigned, the callback is always sent** — even when
  `validate` fails only after the run is taken from the queue (e.g. a file
  changed in the meantime), then with class `config`; a slot of
  `max_parallel_runs` not obtained in time → `timeout`, exhausted
  `daily_budget_usd` → `budget` (since 0.3.1).
- In `POST /projects/<p>/runs`, `callback_url` may be omitted; in that case
  neither `callback.secret_env` nor a signature is required. The
  `POST /runs` contract stays unchanged and still requires `callback_url`.
- A `request_key` record is kept for as long as run directories are
  retained (**proposal**).
- The timeout in n8n must also account for waiting in the queue (D2).
