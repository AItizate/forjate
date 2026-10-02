# Integration patterns

Record each system as `<system>: <pattern>` in `settings.integrations` and the distinct patterns in `settings.integration_patterns`.

| Pattern | Use when | Stage fitness | Catalog | Costs you |
|---------|----------|---------------|---------|-----------|
| `rest-pull` | the system has an API and the use case asks it for data (POs from Odoo, orders from an orders API) | all | none; credentials via the secrets mechanism of the stage | rate limits, pagination, a credential scoped to read |
| `rest-push` | the use case writes to a system of record (post an invoice, close a ticket) | all | none | idempotency key per write; the step that must not run twice |
| `poll` | the source only offers inbound (IMAP mailbox, Telegram `getUpdates`, a folder) | Crawl default for anything inbound | none; a CronJob or a loop in the worker | latency equal to the poll interval; a cursor to persist |
| `webhook` | the source pushes (Telegram, WhatsApp, Stripe, GitHub) and latency matters | Walk+ (needs `external` surface, tunnel, auth) | `apps/cloudflare-tunnel`, `apps/auth/gotrue-auth` or a shared-secret check | an open route, signature verification, replay protection |
| `broker` | two workloads of the use case must be decoupled or fan out | Walk+ | `apps/brokers/nats` (default), `apps/brokers/rabbitmq` (AMQP shops) | one more stateful component; message schema versioning |
| `cdc` | the trigger is "a row changed" in a database the organisation owns | Walk+ | `apps/cdc/debezium-<source>-<broker>` matched to the broker | logical decoding / replica set on the source; the connector's own state |
| `file-drop` | documents arrive as files (email attachments, SFTP, scans) | all | `apps/minio/single-server` (`apps/minio/dev` at Crawl) as the landing bucket | a naming convention that carries the idempotency key |

## Rules

- **The system's API over its database.** A direct database connection to an ERP is a support contract violation waiting to happen. If the API is missing, say so in an open question; do not route around it.
- **Pull at Crawl, push at Walk.** Polling needs no open route and no auth; it is the honest Crawl shape for every inbound channel. Telegram supports both; WhatsApp requires webhooks, so a WhatsApp use case has no inbound at Crawl and replays recorded messages instead.
- **One pattern per system.** Odoo is `rest-pull` for POs and `rest-push` for posting; record both as two entries, not as "REST".
- **Every write has a key.** `rest-push` entries name the idempotency key in `rationale` (invoice number + supplier, conversation id + refund request id). The AI-engineering expert turns it into a tool contract; the pipeline expert uses it for replays.
- **Broker matches connector.** `debezium-postgres-nats` needs NATS; `debezium-mongo-rabbitmq` needs RabbitMQ. If the pipeline expert picks a connector for a broker you did not choose, the validator reports the conflict and one of you asks the question.
- **Mailboxes are files plus a cursor.** IMAP integration is `poll` for the cursor plus `file-drop` for the attachments; the pipeline expert owns the seed and the parsing.
