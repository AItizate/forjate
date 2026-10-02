# Topologies

Four shapes cover every use case the factory has seen. Pick with the four questions, then take the stage ladder for that shape.

## The four questions

| Question | Answers → |
|----------|-----------|
| **Who starts a unit of work?** | a person in a chat → `chat-durable` or `request-response`; a file or message arriving → `event-driven` or `batch`; a schedule → `batch`; a row changing → `event-driven` (CDC) |
| **How long is one unit of work?** | under a few seconds, one model call → `request-response`; seconds to hours, several steps → needs durability |
| **Can a step be lost or run twice?** | yes (idempotent, replayable) → Job or stateless worker; no (money, messages to people, writes to a system of record) → durable execution |
| **Does anything outside the cluster call it?** | no → `api_surface: none`; other namespaces or Jobs → `internal`; users or SaaS webhooks → `external` |

## request-response

One agent service behind a ClusterIP or an Ingress; each request is one model call with tools, answered synchronously.

| Stage | Shape |
|-------|-------|
| Crawl | one Deployment (`agent-api`), called by the verify Job; no auth, no broker |
| Walk | same plus GoTrue + oauth2-proxy in front, Prometheus metrics; still no broker |
| Run | two replicas, PSA restricted, rate limiting at Traefik, OTel traces |

Reference: `docs/overlays/agentic-simple-workflow.md`. Breaks when a request exceeds the ingress timeout or when a failed request must be retried without the caller: that is the moment it becomes `chat-durable`.

## chat-durable

A chat-facing agent decides whether to answer inline or to start a durable workflow; a worker executes workflows. The factory's `agentic-orchestration` overlay.

| Stage | Shape |
|-------|-------|
| Crawl | one container polls the channel (or a replay Job feeds recorded conversations), answers via the gateway, keeps session state in the store the data-store expert picks; escalations are rows in Postgres with an idempotency key; no Temporal |
| Walk | `agent-api` receives the channel webhook through the tunnel, `bundles/temporal-stack` runs the escalation and refund workflows, `worker` executes them; Temporal UI behind oauth2-proxy |
| Run | Temporal with Postgres via operator, worker autoscaled, every workflow id derived from the conversation so a retry never double-posts |

Breaks when workflow state is kept in the agent's memory, or when the same workflow id is not derivable from the business key.

## event-driven

Something arrives (a file in MinIO, a message on a broker, a CDC event) and a worker reacts. The factory's `cdc-event-sourcing` overlay for the CDC flavour.

| Stage | Shape |
|-------|-------|
| Crawl | seed Job writes the inputs, a worker Job consumes them in one pass; no broker, the "queue" is the input bucket or table |
| Walk | `apps/brokers/nats` (JetStream) between producer and worker; Debezium connector when the trigger is a database change; dead-letter stream; consumer is idempotent by the message key |
| Run | NATS clustered or RabbitMQ quorum queues, replay from stream for audit, backpressure limits in the worker |

Breaks when two consumers process the same message with different results, or when the broker is the only copy of a message that matters: the pipeline expert owns the persistence rules.

## batch

A schedule or an operator runs a Job that reads everything pending, processes it, writes results. Migrations, nightly reports, reconciliation.

| Stage | Shape |
|-------|-------|
| Crawl | seed Job, run Job, verify Job, as in `usecases/db-migration-a-to-b`; no services beyond the stores |
| Walk | a CronJob under ArgoCD with a lock in Postgres so two runs never overlap; metrics on duration and rows |
| Run | same with alerting on missed runs and a replay runbook |

Breaks when a run must react within minutes: that is `event-driven`.

## Mixed use cases

Most real use cases are one of these plus a batch seed. Invoice intake is `event-driven` at Walk (invoices arrive) with a `batch` Crawl (seeded PDFs, one pass). A support copilot is `chat-durable`. A migration is `batch` and stays `batch`. Pick the topology for the stage, not for the whole use case, and show the transition in `rationale`.
