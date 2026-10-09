"""The intake batch (architecture: topology batch, durable_execution job). One pass over the inbox bucket.

Per PDF: idempotency key (sha256) -> skip when seen -> Docling -> extract (model) -> lookup_po -> compare in
code -> post_to_erp with the deterministic token when everything agrees, queue_for_review otherwise.
Idempotent: a second run over the same inbox changes nothing (the invoices table is the dedupe table)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import stores
from .config import Settings, settings
from .docling import ParseFailed, parse_pdf, wait_ready as docling_ready
from .domain import Decision, InvoiceFields, Reason, compare, idempotency_key
from .logging import log
from .model import Model, model_for
from .toolkit import ApprovalRequired, NotFound, ToolError, approval_token_for
from .tools.extract_invoice_fields import ExtractArgs, extract_invoice_fields
from .tools.lookup_po import LookupPoArgs, lookup_po
from .tools.post_to_erp import PostToErpArgs, post_to_erp
from .tools.queue_for_review import ReviewItem, queue_for_review


@dataclass
class RunReport:
    processed: int = 0
    skipped_seen: int = 0
    by_reason: dict[str, int] = field(default_factory=dict)

    def add(self, reason: Reason) -> None:
        self.by_reason[reason.value] = self.by_reason.get(reason.value, 0) + 1


def decide(fields: InvoiceFields, *, lookup) -> tuple[Decision, dict | None]:
    """Pure routing given an extracted invoice and a PO lookup function; unit-tested without I/O."""
    try:
        po = lookup(LookupPoArgs(po_number=fields.po_number))
    except NotFound:
        return Decision(reason=Reason.PO_NOT_FOUND, straight_through=False, detail="no purchase order with that number"), None
    return compare(fields, po), po.model_dump()


def process_one(document_id: str, pdf: bytes, *, cfg: Settings, model: Model, report: RunReport) -> None:
    key = idempotency_key(pdf)
    client = stores.minio_client()
    seen = stores.scalar("select reason from invoices where idempotency_key = %s", key)
    if seen is not None:
        report.skipped_seen += 1
        return
    # Duplicate: same bytes under another name, already processed under its first name.
    dup_of = stores.scalar("select document_id from invoices where idempotency_key = %s", key)
    try:
        text = parse_pdf(document_id, pdf)
    except ParseFailed as exc:
        stores.put_object(client, cfg.bucket_parsed, f"{document_id}.json", json.dumps({"document_id": document_id, "error": "parse-failed"}).encode(), "application/json")
        queue_for_review(ReviewItem(invoice_id=document_id, reason=Reason.PARSE_FAILED, detail=str(exc), pdf_object=f"{cfg.bucket_inbox}/{document_id}.pdf"), idempotency_key=key + ":review")
        stores.record_invoice(key, document_id, None, Reason.PARSE_FAILED.value, False, None)
        report.processed += 1; report.add(Reason.PARSE_FAILED)
        return
    try:
        fields = extract_invoice_fields(ExtractArgs(document_id=document_id, document_text=text), model=model)
    except (TimeoutError, ToolError, KeyError, ValueError) as exc:
        queue_for_review(ReviewItem(invoice_id=document_id, reason=Reason.EXTRACTION_TIMEOUT, detail=type(exc).__name__, pdf_object=f"{cfg.bucket_inbox}/{document_id}.pdf"), idempotency_key=key + ":review")
        stores.record_invoice(key, document_id, None, Reason.EXTRACTION_TIMEOUT.value, False, None)
        report.processed += 1; report.add(Reason.EXTRACTION_TIMEOUT)
        return
    safe = fields.model_dump(); safe.pop("bank_account", None)
    stores.put_object(client, cfg.bucket_parsed, f"{document_id}.json", json.dumps({"document_id": document_id, "fields": safe}).encode(), "application/json")
    # The duplicate check the pipeline record names: supplier + invoice number already processed.
    earlier = stores.scalar("select document_id from invoices where invoice_number = %s and supplier = %s and reason <> 'duplicate'", fields.invoice_number, fields.supplier)
    if earlier:
        queue_for_review(ReviewItem(invoice_id=document_id, reason=Reason.DUPLICATE, supplier=fields.supplier, extracted=safe,
                                    detail=f"duplicate of {earlier}", pdf_object=f"{cfg.bucket_inbox}/{document_id}.pdf"), idempotency_key=key + ":review")
        stores.record_invoice(key, document_id, fields.model_dump(), Reason.DUPLICATE.value, False, None)
        report.processed += 1; report.add(Reason.DUPLICATE)
        return
    decision, po = decide(fields, lookup=lookup_po)
    if decision.straight_through:
        # The deterministic check passed: it issues the token the write tool requires (security: tool_write_gate deterministic-check at Crawl).
        token = approval_token_for(document_id)
        try:
            post_to_erp(PostToErpArgs(invoice_id=document_id, supplier=fields.supplier, invoice_number=fields.invoice_number,
                                      amount_cents=fields.amount_cents, po_number=fields.po_number), approval_token=token, idempotency_key=key)
        except ApprovalRequired:
            decision = Decision(reason=Reason.AMOUNT_MISMATCH, straight_through=False, detail="ERP rejected the token")
    if not decision.straight_through:
        queue_for_review(ReviewItem(invoice_id=document_id, reason=decision.reason, supplier=fields.supplier, extracted=safe, po=po,
                                    detail=decision.detail, pdf_object=f"{cfg.bucket_inbox}/{document_id}.pdf"), idempotency_key=key + ":review")
    stores.record_invoice(key, document_id, fields.model_dump(), decision.reason.value, decision.straight_through, po)
    report.processed += 1; report.add(decision.reason)


def run_once(cfg: Settings | None = None) -> RunReport:
    cfg = cfg or settings()
    stores.ensure_schema()
    from .logging import _SINKS, add_sink
    if not _SINKS:
        add_sink(stores.log_event)
    model = model_for(cfg, labels=stores.labels() if cfg.model_mode == "replay" else None)
    client = stores.minio_client()
    docling_ready()
    report = RunReport()
    for name in stores.list_objects(client, cfg.bucket_inbox, ".pdf"):
        document_id = name[:-4]
        process_one(document_id, stores.get_object(client, cfg.bucket_inbox, name), cfg=cfg, model=model, report=report)
    log("batch_done", data_class=cfg.data_class, model_mode=cfg.model_mode, processed=report.processed, skipped_seen=report.skipped_seen, **report.by_reason)
    return report


def main() -> None:
    r = run_once()
    print(f"  Processed {r.processed} (skipped {r.skipped_seen} already seen): {r.by_reason}")


if __name__ == "__main__":
    main()
