"""The verify Job: decisions/quality.yaml verify_assertions as named checks, the KPI and EVAL lines, exit code.

Reads only in-namespace endpoints. Runs the batch a second time itself to prove idempotency."""

from __future__ import annotations

import json
import re
import sys

from . import stores
from .batch import run_once
from .config import settings
from .domain import IBAN, InvoiceFields, field_accuracy

PASS = 0
FAIL = 0
EXPECTED = {"processed": 20, "matched": 15, "amount-mismatch": 3, "duplicate": 1, "parse-failed": 1}


def check(name: str, fn) -> None:
    global PASS, FAIL
    try:
        ok = bool(fn())
    except Exception as exc:  # a broken check is a failed check, named
        ok = False
        print(f"         {type(exc).__name__}: {exc}")
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    PASS += ok; FAIL += (not ok)


def counts() -> dict:
    rows = stores.query("select reason, count(*) as n from invoices group by reason")
    c = {r["reason"]: r["n"] for r in rows}
    c["processed"] = sum(c.values())
    return c


def main() -> int:
    cfg = settings()
    print(f"  Validating invoice-intake (MODEL_MODE={cfg.model_mode})")
    first = counts()
    check("20 items processed, 15 matched, 3 mismatched in review, 1 duplicate skipped, 1 parse failure in review",
          lambda: all(first.get(k, 0) == v for k, v in EXPECTED.items()))
    postings = stores.query("select p.invoice_id, p.amount_cents, po.amount_cents as po_amount from erp_postings p join purchase_orders po on po.po_number = p.po_number")
    check("0 wrong amounts on matched items: every posted amount equals the PO amount by arithmetic",
          lambda: len(postings) == EXPECTED["matched"] and all(p["amount_cents"] == p["po_amount"] for p in postings))
    before = (counts(), stores.scalar("select count(*) from review_queue"), stores.scalar("select count(*) from erp_postings"), stores.scalar("select count(*) from invoice_decisions"))
    run_once(cfg)
    after = (counts(), stores.scalar("select count(*) from review_queue"), stores.scalar("select count(*) from erp_postings"), stores.scalar("select count(*) from invoice_decisions"))
    check("a second run changes no counts, writes no duplicate row in the episodic table and records no second posting in the stub", lambda: before == after)
    mismatched_posted = stores.scalar("select count(*) from erp_postings p join invoices i on i.document_id = p.invoice_id where i.reason <> 'matched'")
    rejected = stores.scalar("select count(*) from erp_rejections")
    check("no posting recorded by the stub for mismatches, and no write reached the stub without an approval token",
          lambda: mismatched_posted == 0 and rejected == 0)
    review = {r["reason"]: r["n"] for r in stores.query("select reason, count(*) as n from review_queue group by reason")}
    items = stores.query("select item from review_queue")
    check("each of the 5 seeded exceptions (3 mismatches, 1 duplicate, 1 unparseable) has a review-queue row carrying its reason",
          lambda: review.get("amount-mismatch", 0) == 3 and review.get("duplicate", 0) == 1 and review.get("parse-failed", 0) == 1
          and all(it["item"].get("reason") and it["item"].get("pdf_object") for it in items)
          and all(it["item"].get("extracted") and it["item"].get("po") for it in items if it["item"]["reason"] == "amount-mismatch"))
    labels = stores.labels()
    decided = stores.query("select document_id, extracted from invoice_decisions where extracted is not null")
    accs = [field_accuracy(InvoiceFields.model_validate({**d["extracted"], "bank_account": None}), InvoiceFields.model_validate({**labels[d["document_id"]], "bank_account": None}))
            for d in decided if d["document_id"] in labels]
    accuracy = round(sum(accs) / len(accs), 4) if accs else 0.0
    print(f"  EVAL field_accuracy={accuracy}")
    check("field accuracy against the labelled seed: 1.0 with EXTRACTOR=replay, at least 0.95 with the live model",
          lambda: accuracy >= (1.0 if cfg.model_mode == "replay" else 0.95))
    processed = first.get("processed", 0)
    kpi = round(first.get("matched", 0) / processed, 4) if processed else 0.0
    print(f"  KPI straight_through_rate={kpi}")
    check("the KPI measured once on the seed and printed as KPI straight_through_rate=<value>", lambda: processed > 0)
    lines = [json.dumps(r["line"]) for r in stores.query("select line from event_log")]
    calls = [l for l in lines if '"model_call"' in l or '"tool_call"' in l]
    amounts = {str(f["amount_cents"]) for f in labels.values()}
    check("model-call and tool-call logs carry data_class=financial and no payload (no IBAN, no bank account number, no invoice amount), at least 20 model-call lines",
          lambda: sum('"model_call"' in l for l in calls) >= 20 and all('"data_class": "financial"' in l for l in calls)
          and not any(IBAN.search(l) for l in calls) and not any(re.search(rf'\b{a}\b', l) for l in calls for a in amounts))
    client = stores.minio_client()
    inbox = {n[:-4] for n in stores.list_objects(client, cfg.bucket_inbox, ".pdf")}
    parsed = {n[:-5] for n in stores.list_objects(client, cfg.bucket_parsed, ".json")}
    check("every seeded PDF and its parsed JSON is present in the MinIO artifact bucket, read through in-namespace endpoints", lambda: inbox and inbox <= parsed)
    print(f"  Results: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
