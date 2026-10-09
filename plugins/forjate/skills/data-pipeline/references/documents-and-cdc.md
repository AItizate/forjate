# Documents and CDC

## Documents

`apps/document-processing/docling` is the catalog's parser: PDF, DOCX, PPTX, HTML, images, to structured Markdown or JSON with tables and layout preserved, OCR included. Stateless, CPU image, seconds per page, `/v1/convert/file` sync and `/v1/convert/file/async` for large inputs.

Pipeline shape for documents:

1. `land`: the file arrives in the artifacts landing zone (`inbox` bucket) under a key that embeds the source id and a content hash.
2. `parse`: Docling converts to Markdown or JSON; the output is written next to the input (`parsed/`), never only kept in memory.
3. `extract (model)`: the AI-engineering expert's structured extraction over the parsed text, with the schema.
4. `validate`: deterministic checks (amount arithmetic, dates, PO lookup) in code.
5. `route`: clean items to the posting step; exceptions to the review queue with the reason.

At Crawl, steps 1 to 5 run inside the run Job over the seeded bucket. At Walk, `land` becomes the poll or webhook, and Docling runs as a service with workers sized to the volume (`DOCLING_SERVE_ENG_LOC_NUM_WORKERS`, max pages, max file size patched by the kustomize skill).

Denied Docling: there is no alternative parser in the catalog. Native PDFs with a text layer can be read by a library in the worker (no tables, no OCR); scans cannot. The record says exactly that, keeps `document_parser: none`, and raises the open question with `caused_by_rule`.

## CDC

Debezium bundles in the catalog, all Walk+: `apps/cdc/debezium-postgres-nats`, `debezium-postgres-rabbitmq`, `debezium-mariadb-nats`, `debezium-mariadb-rabbitmq`, `debezium-mongo-nats`, `debezium-mongo-rabbitmq`. The connector name fixes both the source and the broker; the broker component must be in some record's `choice` for the same stage, and it must be the architecture's.

Prerequisites, each an open question if unknown:

- Postgres: `wal_level = logical`, a replication slot, a publication; the organisation must operate the instance or grant it.
- MariaDB: binlog in ROW format, a replication user.
- MongoDB: a replica set (`apps/databases/mongodb/replica-set` in the catalog), oplog access.
- Initial snapshot of a large table takes time and load; schedule it.

Use CDC when the trigger is "a row changed" and downstream must react or keep an audit trail (`cdc-event-sourcing` overlay). Do not use it for a one-off migration (batch with checkpoints), for a system you do not operate (pull its API), or at Crawl (no live source exists; the seed is a batch).

## Brokers for pipelines

`apps/brokers/nats` with JetStream: streams with retention by age or size, consumers with replay, 20 MB footprint; the factory default. `apps/brokers/rabbitmq`: AMQP, classic and stream queues, management UI; choose when AMQP clients already exist or the organisation operates it. Record the choice as the architecture record has it, and the subject or exchange naming convention in `rationale` (`cdc.<db>.<table>`, `uc.<usecase>.<step>`).
