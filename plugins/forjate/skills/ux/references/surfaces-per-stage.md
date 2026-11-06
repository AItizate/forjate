# Surfaces per stage

## The surfaces

| `surface` | What it is | Fits when | Needs from other records |
|-----------|------------|-----------|--------------------------|
| `none` | no human touches the result interactively; outputs land in a system, a file or a log | nightly batch, API consumed by a system, one-off migration | failure UX names where the operator reads a failure |
| `cli` | `kubectl`, `psql`, the verify Job log, a script's output | Crawl of almost everything; operator-only use cases at every stage | the verify Job prints the exceptions and the KPI line |
| `notebook` | a notebook over the seeded data | Crawl of analysis-shaped use cases where the requester explores results | the endpoints in `usecase.yaml` |
| the `chat-ui` component (by its catalog name) | the catalog's chat front-end over the gateway or an inference server | a conversational use case whose users are internal and not in a channel yet; the fastest demo for a Walk pilot of a chat assistant | the `llm-gateway` or `inference` component in the AI-engineering record; `auth_in_front: oauth2-proxy` from Walk |
| `chat-channel` | the channel the users already use (Telegram, Slack, WhatsApp, email) through the architecture's webhook or poller | customers or colleagues already converse there | `trigger: chat`, the webhook or poll in the architecture record, `auth_in_front: api-key` on the webhook |
| `custom-web` | a page served by one of the architecture's workloads (a review queue, an approval screen) | an exception path with a token: approve, reject, correct, with the source of truth side by side | the workload in `architecture.workloads`; `auth_in_front: oauth2-proxy`; the `[requires approval token]` tool in the AI-engineering record |
| `existing-tool` | the system of record's own UI (a draft in the ERP, a ticket in the helpdesk) | the humans live in that tool and the token can be issued there (a validation step, a status change the app reads back) | an integration pattern in the architecture record that reads the decision back; an open question when the token path is unclear |
| `api-only` | no human surface; another system calls the use case | apification; a machine consumer | `api_surface` and `auth_in_front: api-key` in the architecture record |

## The ladder

| | Crawl | Walk | Run |
|---|---|---|---|
| default surface | `cli` (the verify Job log and the tables) | the channel the users are in, or the review page the exception path needs | the Walk surface, filtered or multiplied by the second audience (entity, team, region) |
| who is in front of it | the requester and the operator | the end-users named in the brief, the approver reading the report | every actor in the brief |
| feedback | `verify-job-log` | the `feedback` component on a page, `in-channel` in a channel, `review-queue-flag` on a queue | same, with the response rate as a metric |
| auth | `none` (nothing exposed) | `oauth2-proxy` on any human page, `api-key` on a webhook (architecture's value) | same, the org IdP when a pack names one |
| onboarding | `none` | walkthrough on the seeded exceptions, or a shadow period | per new audience |

## Choosing

Answer four questions and write the answers into `rationale`:

1. **Who is in front of it, per stage?** From the brief's actors with `role: end-user` and `approver`, and the business record's as-is process. No end-user interacts at this stage → `none` or `cli`.
2. **Where are they already?** A channel they use every day beats a new page; a tool they already approve things in beats a second tool, if the token can be issued there.
3. **Is there an exception path with a decision?** Then there is a surface for it, with the information to decide and the token the write tool needs. This is the one surface you never skip.
4. **Does the stage's goal mention a person using the result?** If the plan's goal is "prove X on seeded data" the surface is the log; if it is "clerks rely on it for a month" the surface is theirs.

## Per-audience lines

`audiences` has one line per human actor who sees anything at the stage: `<actor>: <what they see> <where>`. The approver appears with the report they read; the operator with the logs and alerts they watch. An actor in the brief who appears in no stage's audiences is either a mistake or `role: system`.

## Components

The UI-shaped capabilities are `chat-ui` and `feedback`; resolve each from `wiki/catalog.json` and check its `stages` before writing `choice` (`catalog-snapshot.md` shows what they resolved to on the compile date). A custom page and a chat channel are not components.
