# Documents and CDC

## Documents

The `document-parsing` capability resolves to the catalog's parser (`catalog-snapshot.md` names today's single option): PDF, DOCX, PPTX, HTML, images, to structured Markdown or JSON with tables and layout preserved, OCR included. Stateless, CPU image, seconds per page, a sync endpoint and an async one for large inputs.

Pipeline shape for documents:

1. `land`: the file arrives in the artifacts landing zone (`inbox` bucket) under a key that embeds the source id and a content hash.
2. `parse`: the parser converts to Markdown or JSON; the output is written next to the input (`parsed/`), never only kept in memory.
3. `extract (model)`: the AI-engineering expert's structured extraction over the parsed text, with the schema.
4. `validate`: deterministic checks (amount arithmetic, dates, PO lookup) in code.
5. `route`: clean items to the posting step; exceptions to the review queue with the reason.

At Crawl, steps 1 to 5 run inside the run Job over the seeded bucket. At Walk, `land` becomes the poll or webhook, and the parser runs as a service with workers sized to the volume (worker count, max pages and max file size patched by the kustomize skill from the component's documented settings).

Denied parser: when a pack denies the only `document-parsing` component, there is no alternative in the catalog. Native PDFs with a text layer can be read by a library in the worker (no tables, no OCR); scans cannot. The record says exactly that, keeps `document_parser: none`, and raises the open question with `caused_by_rule`.

## CDC

The `cdc` capability resolves to one connector per supported source and broker, all Walk+, named `<source>-<broker>` (`catalog-snapshot.md` lists today's pairs). The connector name fixes both the source and the broker; the broker component must be in some record's `choice` for the same stage, and it must be the architecture's.

Prerequisites, each an open question if unknown:

- A relational source with logical decoding (`wal_level = logical`, a replication slot, a publication); the organisation must operate the instance or grant it.
- A relational source with a binary log: ROW format, a replication user.
- A document source: a replica set (the catalog ships one as a sub-component of the store), oplog access.
- Initial snapshot of a large table takes time and load; schedule it.

Use CDC when the trigger is "a row changed" and downstream must react or keep an audit trail (`cdc-event-sourcing` overlay). Do not use it for a one-off migration (batch with checkpoints), for a system you do not operate (pull its API), or at Crawl (no live source exists; the seed is a batch).

## Brokers for pipelines

The `message-broker` candidates differ in protocol and footprint: the lightweight streaming one (persistent streams with retention by age or size, consumers with replay, a few MB of footprint) is the factory default; the AMQP one (classic and stream queues, a management UI) when AMQP clients already exist or the organisation operates it. Record the choice as the architecture record has it, and the subject or exchange naming convention in `rationale` (`cdc.<db>.<table>`, `uc.<usecase>.<step>`).
