# Memory taxonomy

Five kinds. Each has a shape, a lifetime and a query pattern; the store follows from those, never from habit.

| Kind | Holds | Lifetime | Query | Is not |
|------|-------|----------|-------|--------|
| `session` | the live conversation or request: turns, scratch state, the current item | minutes to hours; dies with the session | by session id, last N | a transcript archive (that is `episodic`) |
| `working` | state of a unit of work in flight: steps done, pending approval, idempotency keys, cursors (last mailbox UID, last offset) | until the unit completes; then summarised into `episodic` | by work id, by status | a queue (the broker's job) |
| `episodic` | what happened per item over time: this invoice's extraction, decisions, approvals; this customer's escalations | the business or legal retention | by item id, by time, by actor | the system of record (the ERP keeps the payable; you keep what the agent did) |
| `semantic` | embeddings over unstructured text for retrieval: policies, manuals, past resolved cases | as long as the corpus is valid | by similarity, filtered by metadata | a lookup an API answers; a cache of the ERP |
| `artifacts` | files: source PDFs, parsed outputs, prompts and responses for audit, run logs, seed datasets | retention of the evidence, often the longest | by key or prefix; listed, not searched | chat history; structured state of any kind |

## Recognising each in a brief

- "keeps the conversation context" → `session`; "hands anything to a human with the full context attached" → `working` (the handoff) and `episodic` (the record of it).
- "approves anything that does not match" → `working` with a status and an approval token.
- "audit", "regulated", "evidence" → `episodic` plus `artifacts`, with retention from legal.
- "answers questions about their orders" → no `semantic` memory; the orders API is the lookup. "Answers questions from the product manual" → `semantic`.
- "PDFs land in a mailbox" → `artifacts` for the files, `working` for the mailbox cursor.
- "migrate table A to B" → no agent memory at all; `working` for the migration progress, `artifacts` for the verification report.

## Short-term vs long-term

Short-term is `session` and `working`: small, hot, TTL-driven, lost without consequence once the unit of work is done. Long-term is `episodic`, `semantic`, `artifacts`: grows, queried later, retention-governed, backed up. The record separates them at Walk without exception; at Crawl one Postgres may hold both if the split is named.
