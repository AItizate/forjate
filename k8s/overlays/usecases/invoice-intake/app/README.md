# invoice-intake app

Supplier invoices arrive as PDF attachments in a shared mailbox, and someone types supplier, amount, date and PO number into Odoo and flags
mismatches. This app takes one invoice from attachment to extracted fields and a purchase-order match. At Crawl every result is a recommendation
a person acts on, using synthetic invoices, doubles of the mailbox and of Odoo, and only an in-cluster model. Nothing is written to Odoo.

One package, one image, one module per workload. The Job or Deployment picks the command.

| Workload | Kind | Command |
|----------|------|---------|
| `invoice-intake-seed` | Job, seed | `python -m invoice_intake.seed` |
| `worker` | Job, run | `python -m invoice_intake.worker` |
| `invoice-intake-verify` | Job, verify | `python -m invoice_intake.verify` |
| `invoice-intake-eval` | Job, started by the operator | `python -m invoice_intake.eval_run` |
| `odoo-stub` | Deployment, port 8001 | `python -m invoice_intake.odoo_stub` |
| `shared-imap-mailbox-stub` | Deployment, port 8001 | `python -m invoice_intake.shared_imap_mailbox_stub` |

## Tests

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[test]' && .venv/bin/python -m pytest -q
```

No model, cluster or database is needed. Markers: `eval` (golden set through the double), `injection`, `redaction`. These tests use the stubs' real
apps and the real tools over memory stores and a parser that returns each seeded PDF's text, so Postgres, MinIO, docling and Ollama are proven only
on the cluster, by the verify Job and invoice-intake-eval.

## Crawl

`./scripts/ephemeral/ephemeral.sh up invoice-intake` builds `invoice-intake:dev` from `spec.build`, imports it into k3d and runs seed, run and verify.

**The verify Job runs `MODEL_MODE=replay`.** Its extraction returns the labels the seed wrote, so its exit code measures flow, routing, matching,
idempotency and the exception path against the real parser and stores, and cannot get an amount wrong. Its `KPI straight_through_rate` (2 of 12, about
0.17) is a fact of the seed's mix, not the CFO's number.

The number the CFO reads comes from the live run, on the in-cluster CPU model, after `up` and within the 4 h TTL. Pull the model first
(`kubectl exec` into `ollama-0`: `ollama pull qwen2.5:7b-instruct`), then:

```bash
kubectl -n uc-invoice-intake patch job invoice-intake-eval --type merge -p '{"spec":{"suspend":false}}'
kubectl -n uc-invoice-intake logs -f job/invoice-intake-eval | grep '^EVAL'
```

It prints `live_straight_through_rate`, `live_wrong_amount_count`, `live_document_accuracy`, `live_amount_accuracy`, `live_exception_recall`,
`live_injection_ignored_rate`, `seconds_per_invoice_p95` and `model_memory_peak`. Copy them to `.builder/metrics.yaml` and the Crawl report before the
cluster dies. The golden set's ceiling is exactly 0.80, because 10 of its 50 items are deliberate exceptions.

The AP clerk's seeded exception report comes from the tables, because the log carries only ids and reasons:

```bash
kubectl -n uc-invoice-intake exec -it postgres-0 -- sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB" -c "\copy (SELECT i.key, q.reason, q.failed_step, q.context FROM working.review_queue q JOIN working.items i USING (scope, key) WHERE q.scope = '"'"'invoice-intake'"'"') TO STDOUT CSV HEADER"'
```

## Walk

The same Dockerfile goes through `build-push-generic-template.yml@v1`, which builds, scans with Trivy and pushes under the SHA, then the workflow
dispatches `app-image-updated` to the IaC repo. Set the repository variables `IAC_REPOSITORY` and `TENANT` and the secret `IAC_FACTORY_TOKEN`.
The Walk workloads themselves are not generated yet; see below.

## Dependencies

FastAPI and uvicorn for the stubs, httpx for HTTP, psycopg for Postgres, minio for the object store, pydantic for schemas. Pillow is the one addition:
it renders the image-only seed PDFs, because the scanned path has to exercise the parser's real OCR on real pixels.

## What this scaffold refused or assumed

`.builder/scaffold.yaml` `notes` carries the full list. The ones that change how you read a result:

- **A hand-rolled build is refused.** Workflows only call the shared templates at `@v1`.
- **Walk and Run are not implemented.** `cron-job`, `review-api`, `posting-worker`, the Temporal worker, the LiteLLM client, the kill switch's paused state and the Ed25519 token verifier do not exist. `post_invoice` refuses every call at Crawl and `request_approval` stops at `NotImplementedError` past the judge. Their gates (G-AI-7 and G-AI-14 in full, G-Q-13, G-SEC-25) are not closed by this code.
- **The doubles' routes and fields are assumed.** The real Odoo API is architecture Q1, and G-ARCH-2 compares them.
- **OCR is unproven here.** The clean scan must read literally through docling's real OCR, or it lands as `low-confidence` and the verify Job fails, naming it. Only a run on the cluster shows that.
