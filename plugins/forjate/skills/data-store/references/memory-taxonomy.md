# Memory taxonomy

Five kinds. Each has a shape, a lifetime and a query pattern; the store follows from those, never from habit.

| Kind | Holds | Lifetime | Query | Is not |
|------|-------|----------|-------|--------|
| `session` | the live conversation or request: turns, scratch state, the current item | minutes to hours; dies with the session | by session id, last N | a transcript archive (that is `episodic`) |
| `working` | state of a unit of work in flight: steps done, pending approval, idempotency keys, cursors (last mailbox UID, last offset) | until the unit completes; then summarised into `episodic` | by work id, by status | a queue (the broker's job) |
| `episodic` | what happened per item over time: this invoice's extraction, decisions, approvals; this customer's escalations | the business or legal retention | by item id, by time, by actor | the system of record (the ERP keeps the payable; you keep what the agent did) |
| `semantic` | embeddings over unstructured text for retrieval: policies, manuals, past resolved cases | as long as the corpus is valid | by similarity, filtered by metadata | a lookup an API answers; a cache of the ERP |
| `artifacts` | files: source PDFs, parsed outputs, prompts and responses for audit, run logs, seed datasets | retention of the evidence, often the longest | by key or prefix; listed, not searched | chat history; structured state of any kind |

## Scope

Every kind has a scope, written in `memory_scopes` as `<kind>: <scope>`:

| Scope | Whose it is | Typical kinds | Isolation it needs |
|-------|-------------|---------------|--------------------|
| `session` | one conversation or one request | `session`, `working` during the unit of work | a key or row tagged by session id; dies with the TTL |
| `user` | one person or one customer across sessions | `episodic` (their history), `working` (their pending approvals) | every query filtered by user id; the actor in front of the agent is the only user it may read |
| `project` | the use case across users | `episodic` (the extraction log), `artifacts`, `working` (cursors) | the use case's own schema, bucket or database; another use case never reads it |
| `org` | the organisation | `semantic` (policies, manuals), reference data | governed knowledge with an owner and a refresh cadence; read by many, written by few |

The brief's `isolation` sets the floor for how scopes are kept apart (`scope_isolation`): `none` allows a key prefix in one store, `logical` needs a schema, database or bucket per tenant on shared infrastructure, `physical` needs a cluster per tenant. A scope a store cannot enforce (a cache with no namespaces for `user` data of two tenants) is a risk with a mitigation, never an omission.

## Recognising each in a brief

- "keeps the conversation context" → `session`; "hands anything to a human with the full context attached" → `working` (the handoff) and `episodic` (the record of it).
- "approves anything that does not match" → `working` with a status and an approval token.
- "audit", "regulated", "evidence" → `episodic` plus `artifacts`, with retention from legal.
- "answers questions about their orders" → no `semantic` memory; the orders API is the lookup. "Answers questions from the product manual" → `semantic`.
- "PDFs land in a mailbox" → `artifacts` for the files, `working` for the mailbox cursor.
- "migrate table A to B" → no agent memory at all; `working` for the migration progress, `artifacts` for the verification report.

## Short-term vs long-term

Short-term is `session` and `working`: small, hot, TTL-driven, lost without consequence once the unit of work is done. Long-term is `episodic`, `semantic`, `artifacts`: grows, queried later, retention-governed, backed up. The record separates them at Walk without exception; at Crawl one Postgres may hold both if the split is named.
