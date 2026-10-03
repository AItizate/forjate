# Residency, transfer, legal basis and retention

## Residency per hop

`data_residency` is a region (`eu`, `us`, `br`, ...) that every store and every processor of the data must sit in. List the hops; each is either inside the region or needs a `transfer_mechanism`:

| Hop | Inside the region when | Otherwise |
|-----|------------------------|-----------|
| cluster PVCs (Longhorn) | the nodes are in the region | a managed cluster elsewhere is a transfer |
| object storage | MinIO in-cluster, or an S3 bucket in the region | cross-region replication is a transfer |
| model inference | Ollama or vLLM in-cluster (`model_provider: local`) | an API provider: the provider's processing region, under a DPA |
| LLM gateway logs (LiteLLM) | its Postgres is in-cluster | a hosted gateway is a transfer |
| metrics, logs, traces | Prometheus, Grafana, OTel in-cluster | a SaaS backend receiving payloads or identifiers is a transfer; metric names alone usually are not |
| email and chat providers | n/a: the data originates there | the provider is a controller or processor in its own region; name it |
| backups (Velero target) | offsite target in the region | an offsite target elsewhere is a transfer |

`transfer_mechanism`: `none` when every hop is inside; `adequacy` when the destination has an adequacy decision; `sccs` when standard contractual clauses are signed; `unknown` when a hop exists and nobody has told you how it is covered, with an open question.

A pack `data_residency` that contradicts the brief is not yours to resolve: leave `data_residency` unset for the affected stages, write in `rationale` which hops are blocked, and raise the open question with `caused_by_rule`.

## Legal basis per data class

| Data class | Usual basis | Note |
|------------|-------------|------|
| `none`, `internal` | n/a | no personal data; say so |
| `pii` (customers, employees) | `contract` when processing serves the contract with the person; `legitimate-interest` for support and fraud; `consent` only when nothing else fits | an LLM reading messages is still the same basis; the DPIA documents it |
| `financial` (invoices, bank accounts) | `contract` plus `legal-obligation` for the accounting records | supplier contact details are `pii` too |
| `health` | explicit `consent` or a specific legal provision | the DPIA is mandatory and the open question names the provision |
| `secret` | n/a (credentials, keys) | security's domain; retention is "until rotated" |

Write `legal_basis: unknown` and an open question rather than guessing when the brief is silent on the relationship with the data subjects.

## Retention: ranges and owners

You state the range the data class usually carries and who owns the figure. The organisation's number is an open question blocking Run unless the brief gives it.

| Kind (data-store taxonomy) | Operational copy (data-store decides) | Legal copy (you state the range) | Owner of the figure |
|----------------------------|----------------------------------------|----------------------------------|---------------------|
| `session` | hours to a day | none: no legal copy of live conversation | n/a |
| `working` | until the unit completes plus days | none | n/a |
| `episodic` (what the agent decided per item) | 90 days to a year | financial: the accounting-records period (commonly 5 to 10 years, by jurisdiction); pii support history: the shortest that serves the purpose, commonly 1 to 3 years | finance / legal |
| `semantic` (embeddings of a corpus) | while the corpus is current | none, but the corpus itself may carry personal data: re-index on erasure | data owner |
| `artifacts` (invoices, transcripts, prompts and outputs) | 90 days for inputs | financial documents: the accounting period; prompts and outputs on regulated data: the audit period the organisation sets | finance / legal / DPO |

Rules:

- Operational retention never exceeds the legal copy's; the legal copy is one, immutable (object lock at Run), and separate from the operational store.
- `retention_reconciled: true` only when the data-store record's `retention_<kind>` for every kind is at or below the legal figure you state and an audit copy exists at the legal figure. Otherwise `false`, with an open question naming both numbers and both records.
- Crawl retention is the ephemeral TTL; nothing legal applies to seeded or synthetic data, and a seed that copies real regulated data is a finding (the pipeline expert's `seed_strategy` should be `synthetic` or `anonymised-copy`).

## Subject rights

Access, rectification, erasure, portability, objection. The use case needs a path for each that touches personal data: where the records are (data-store record), how they are found by subject (an index by customer id), what erasure does to the operational copy (delete or pseudonymise) and to the legal copy (kept under `legal-obligation`, with the basis documented). `subject_rights_path: defined` only when that paragraph exists in `rationale`; otherwise `open`, with an open question for the DPO.
