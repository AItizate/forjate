# support-copilot app

Customers write to a Telegram group about their orders and subscriptions; this service answers the common questions from the orders API with only the allowed fields, keeps the conversation context, and hands refunds, cancellations, unknown orders and angry customers to a support agent with the full transcript and the order id. Scaffolded by `forjate:app-scaffold` from the decision records under `../.builder/`.

## Workloads (one package, one image)

| Workload | Command | Kind |
|----------|---------|------|
| `agent-api` | `python -m support_copilot.api` | Deployment on :8000: `POST /webhook/telegram` (Walk, secret token verified), `POST /replay/turn` (Crawl) |
| `orders-stub` | `python -m support_copilot.orders_stub` | Deployment on :8001: read-only orders and subscriptions from the seed, every call recorded |
| `seed-job` | `python -m support_copilot.seed` | Job: 40 customers, 200 orders, 50 subscriptions, the 60-conversation replay set |
| `replay-job` | `python -m support_copilot.replay` | Job: feeds the replay set to the agent API in order |
| `verify-job` | `python -m support_copilot.verify` | Job: the quality record's assertions, `KPI resolved_without_human_rate=` |

Tools (`src/support_copilot/tools/`): `get_order` [read-only, bound to the sender's customer], `get_subscription` [read-only], `escalate` [idempotent on conversation id plus reason]. The handoffs are a pure predicate (`should_escalate`): refund, cancellation, anger, two unresolved turns.

## Model modes

`MODEL_MODE=rules` (CI): a keyword classifier over the same tool loop, so the verify Job measures routing, escalation, idempotency and the allowed-field filter deterministically. `MODEL_MODE=live`: the same loop against Ollama (`qwen2.5:7b`, structured output), the run the resolution rate is read from. Postgres, the agent API and the orders stub are real in both.

`ALLOWED_ORDER_FIELDS=status,eta,items_count` is an ASSUMED value until the head of CS answers Q1 of the AI-engineering record; the verify Job fails closed when it is empty.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest -q
../../../../../scripts/ephemeral/ephemeral.sh up support-copilot   # builds support-copilot:dev from usecase.yaml spec.build, imports it into k3d, seed -> replay -> verify
```

At Walk the shared template (`build-push-generic-template.yml@v1`) builds, scans and pushes `ghcr.io/aitizate/support-copilot:<sha>` and the `app-image-updated` dispatch writes the SHA into the Walk overlay. This repo has no build or push step of its own by design; the Telegram transport (typing indicator, `sendMessage`) is added with the Walk webhook.
