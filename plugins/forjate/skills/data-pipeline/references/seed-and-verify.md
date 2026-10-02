# Seed and verify

The Crawl stage is only as good as its seed. The ephemeral runner (`scripts/ephemeral/ephemeral.sh`) un-suspends `seed`, `run`, `verify` Jobs in order and blocks on `verify` exiting 0; `usecase.yaml` names the Jobs. Your record designs what those Jobs do; the kustomize skill writes them.

## Seed strategies

| `seed_strategy` | Use when | How |
|-----------------|----------|-----|
| `synthetic` | no real data may leave its system, or none exists yet | generate items from templates that match the real shape (PDF invoices rendered from a template with known fields; conversations scripted per intent) |
| `anonymised-copy` | real data exists and the data class allows a pseudonymised copy inside the cluster | copy a subset with identifiers replaced; the mapping stays outside the ephemeral environment |
| `recorded-replay` | the source is a stream or a chat | a fixed set of recorded messages replayed in order with their original timing collapsed |
| `subset` | the source is a database the organisation owns and the data class permits | a deterministic slice (first N keys, or a hash range) |

Regulated or `pii`/`financial`/`health` data defaults to `synthetic` or `anonymised-copy`; `subset` only with the compliance expert's agreement, raised as an open question.

## Sizing

Enough to cover every path once and the common path a few times: tens to low hundreds of items. `seed_size` says the total and how many are exceptions, e.g. `20 invoices: 14 clean, 3 amount mismatches, 2 missing PO, 1 duplicate`. Every exception in the business record is represented at least once.

## Where it lands

By memory kind, so the data-store expert maps it: `artifacts: inbox bucket with 20 PDFs`, `working: purchase_orders table with 25 rows`, `episodic: empty`. The seed Job writes to those; it never writes to a system of record.

## Verify assertions

`verify_assertions` is the list the verify Job checks, each observable from the stores:

- counts: items processed = seed size; duplicates = 0 after a second run of the run Job
- outcomes: each seeded exception landed in the expected place (mismatches in the review queue, duplicates rejected, missing PO escalated)
- correctness: extracted fields equal the known values for the synthetic items; zero wrong amounts
- dead letters: the poison item (if seeded) is in the dead-letter table with a reason
- stubs: the stub system of record received the expected calls (and no call for exceptions)

The first assertion of every use case is "run Job twice, same result": idempotency is the property the whole stage rests on. The AI-engineering expert's golden set starts from this seed.
