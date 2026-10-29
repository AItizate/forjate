# invoice-intake app

Supplier invoices arrive as PDFs; this service parses them (Docling), extracts the fields (a local model), matches them against purchase orders in code, posts matches to the ERP behind an approval token and routes every exception to a review queue. Scaffolded by `forjate:app-scaffold` from the decision records under `../.builder/`.

## Workloads (one package, one image)

| Workload | Command | Kind |
|----------|---------|------|
| `inv-seed` | `python -m invoice_intake.seed` | Job: 20 synthetic PDFs with labels, the purchase orders, the schema |
| `intake-job` | `python -m invoice_intake.batch` | Job: one pass over the inbox bucket |
| `inv-validate` | `python -m invoice_intake.verify` | Job: the quality record's assertions, `KPI straight_through_rate=`, `EVAL field_accuracy=` |
| `erp-stub` | `python -m invoice_intake.erp_stub` | Deployment on :8001: purchase orders and postings, token-checked |

Tools (`src/invoice_intake/tools/`): `extract_invoice_fields` [read-only], `lookup_po` [read-only], `queue_for_review` [idempotent], `post_to_erp` [idempotent, requires approval token]. The token is an HMAC bound to one invoice: the deterministic check issues it when amount, supplier and PO agree; the AP clerk's approval issues it for everything else (Walk).

## Model modes

`MODEL_MODE=replay` (CI): the extractor returns the labels the seed wrote next to each PDF, so the verify Job measures routing, arithmetic, idempotency, the exception path and log hygiene deterministically. `MODEL_MODE=live`: the same Job against Ollama (`qwen2.5:7b`, structured output, temperature 0), the run that measures field accuracy for the finance ops lead. Postgres, MinIO and Docling are real in both.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest -q                 # unit, contract, eval and injection tests; no cluster
../../../../../scripts/ephemeral/ephemeral.sh up invoice-intake   # builds invoice-intake:dev (usecase.yaml spec.build), imports it into k3d, seed -> intake -> verify
```

At Walk the shared template (`build-push-generic-template.yml@v1`) builds the same Dockerfile, scans it with Trivy and pushes `ghcr.io/aitizate/invoice-intake:<sha>`; the `app-image-updated` dispatch writes the SHA into the Walk overlay's `images:` block. This repo has no build or push step of its own by design.

## Notes

- Bank account numbers never reach a log line, a review note or the prompt; `redact()` and `args_hash()` enforce it.
- Every log line also lands in `event_log` so the verify Job can assert on it without pod access.
