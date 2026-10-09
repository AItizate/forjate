# Reconstructing the as-is process

The brief describes a wish; the as-is process is what happens today. Reconstruct it from the problem statement, the actors and the sources. Mark every inference `ASSUMED:` so the requester can correct it in one pass.

## Template

```yaml
as_is_process:
  - "shared mailbox: invoice PDF arrives from a supplier"
  - "AP clerk: opens the PDF, types supplier, amount, date, PO number into Odoo"
  - "AP clerk: compares the amount with the PO; flags mismatches to the finance ops lead"
  - "finance ops lead: resolves the mismatch with the supplier (ASSUMED: by email, within days)"
as_is_exceptions:
  - "amount differs from the PO: finance ops lead chases the supplier"
  - "PO number missing on the invoice: clerk searches Odoo by supplier and amount (ASSUMED)"
  - "duplicate invoice: caught only if the clerk remembers the first one (ASSUMED)"
as_is_sla: "ASSUMED: invoices posted within 5 working days of arrival"
```

## What to look for

- **The exception path is the product.** Automation handles the happy path cheaply; its value is decided by how it routes exceptions to the person who handles them today. Name that person per exception.
- **Who waits.** The SLA is the wait the business tolerates; the KPI target should shorten it or hold it while removing labour, never lengthen it.
- **The system of record.** The step where someone types into a system is where the system of record is. The automation writes there through its API and never keeps a competing copy of the truth.
- **Volume and shape.** `data.sources[].volume` gives the volume; the shape (PDF, chat, rows) is what the pipeline expert needs. Repeat the volume in the hypothesis so the maths is visible.

## Rejecting claims

When the requester offers a number you cannot derive ("this saves two people"), record it in `alternatives` with `rejected_because: "no derivation from volume × time; the brief gives 300 invoices/month"` and replace it with the hypothesis you can show. You are not contradicting the requester; you are writing down what can be measured.
