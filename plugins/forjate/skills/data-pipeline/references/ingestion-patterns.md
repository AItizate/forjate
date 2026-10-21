# Ingestion patterns

| Pattern | Shape | Stage fitness | Catalog | Fails when |
|---------|-------|---------------|---------|------------|
| `batch` | a Job reads everything pending, processes, writes; a schedule or an operator starts it | Crawl for everything; Walk and Run for migrations, reconciliations, nightly extracts | none beyond the stores | two runs overlap (lock in working memory), or a run must react within minutes |
| `poll` | a loop or CronJob asks the source for new items since a cursor | Walk for mailboxes, folders, chat channels that support it (Telegram), APIs without push | none | the cursor is lost (idempotency key makes it harmless), poll interval exceeds the SLA |
| `webhook` | the source pushes to an endpoint | Walk+ with an `external` API surface, tunnel and signature check; never Crawl | `apps/cloudflare-tunnel`; the endpoint is a workload | the endpoint is down (the source retries or does not: say which), replay attacks, no backpressure |
| `stream` | producer and consumer decoupled by a broker; consumer is idempotent by message key | Walk+ when workloads must be decoupled or fan out | `apps/brokers/nats` (default, JetStream), `apps/brokers/rabbitmq` (AMQP, work queues) | duplicate delivery without a key, consumer lag with no metric, broker as the only copy |
| `cdc` | a connector reads the source database's change log and publishes to the broker | Walk+ on a database the organisation operates | `apps/cdc/debezium-<source>-<broker>` plus the broker | source lacks logical decoding / replica set, schema changes, snapshot of a large table at start |

## Choosing per stage

Crawl: `batch`, always. The seed Job writes inputs into the landing zone (bucket or table), the run Job processes them once, the verify Job asserts. The live pattern is named in `rationale` as "arrives at Walk".

Walk: the pattern the brief's trigger implies. Mailbox → `poll`. Chat with push support → `webhook` (Telegram either; WhatsApp only webhook). Files dropped → `poll` on the bucket or `stream` if the dropper can publish. Row changes → `cdc`. Nightly → `batch`.

Run: the Walk pattern with the operational edges: backpressure, consumer lag metrics, DLQ review, replay runbook.

## Throughput

Derive `throughput_target` from the brief: 300 invoices/month is 15 a day, one worker; 200 chat messages/day is 10 an hour, one worker; 2M rows once is a batch with checkpoints every N rows and a 30-minute budget. Say the number so the risk ("Docling at 5 s/page against 100 pages/hour") is arithmetic, not opinion.

## Idempotency and replay

| Source | Key | Replay |
|--------|-----|--------|
| mailbox | mail UID + attachment sha256 | re-poll from an older cursor; duplicates skipped by key |
| files | object key (which embeds the source id) | re-list the prefix |
| chat | channel message id | re-fetch by offset or replay the recorded set |
| API pull | the system's id + updated_at | re-pull with an older watermark |
| CDC | primary key + LSN / resume token | reset the connector offset; consumer dedupes by key |
| database batch | primary key range | re-run the range; writes are upserts |

`settings.replay` is one sentence that says which of these applies and what the operator runs.
