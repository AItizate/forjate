"""Deterministic steps: schemas, arithmetic, matching, idempotency keys, redaction. No model, no I/O."""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum

from pydantic import BaseModel, Field


class InvoiceFields(BaseModel):
    """What the model extracts. Amounts in cents: no floats in money."""
    supplier: str = Field(min_length=1)
    invoice_number: str = Field(min_length=1)
    amount_cents: int = Field(ge=0)
    invoice_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    po_number: str = Field(min_length=1)
    bank_account: str | None = None  # never logged, never placed in a prompt


class PurchaseOrder(BaseModel):
    po_number: str
    supplier: str
    amount_cents: int
    bank_account: str | None = None
    source: str = "erp"


class Reason(StrEnum):
    MATCHED = "matched"
    AMOUNT_MISMATCH = "amount-mismatch"
    SUPPLIER_MISMATCH = "supplier-mismatch"
    BANK_ACCOUNT_CHANGE = "bank-account-change"
    PO_NOT_FOUND = "po-not-found"
    DUPLICATE = "duplicate"
    PARSE_FAILED = "parse-failed"
    EXTRACTION_TIMEOUT = "extraction-timeout"


class Decision(BaseModel):
    reason: Reason
    straight_through: bool
    detail: str = ""


def idempotency_key(pdf_bytes: bytes) -> str:
    """The pipeline record's key: sha256 of the PDF; supplier and invoice number are checked after extraction."""
    return hashlib.sha256(pdf_bytes).hexdigest()


def normalise_supplier(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def compare(fields: InvoiceFields, po: PurchaseOrder) -> Decision:
    """Arithmetic in code, never in the model. Any difference routes to review."""
    if normalise_supplier(fields.supplier) != normalise_supplier(po.supplier):
        return Decision(reason=Reason.SUPPLIER_MISMATCH, straight_through=False,
                        detail=f"invoice supplier != PO supplier")
    if fields.amount_cents != po.amount_cents:
        return Decision(reason=Reason.AMOUNT_MISMATCH, straight_through=False,
                        detail=f"difference of {fields.amount_cents - po.amount_cents} cents")
    if po.bank_account and fields.bank_account and fields.bank_account != po.bank_account:
        # The ux record: a bank-account change is a checkpoint even when the amount matches.
        return Decision(reason=Reason.BANK_ACCOUNT_CHANGE, straight_through=False, detail="bank account differs from the supplier record")
    return Decision(reason=Reason.MATCHED, straight_through=True)


IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")


def redact(text: str) -> str:
    """Bank account numbers never reach a log line or a review note."""
    return IBAN.sub("[IBAN]", text)


def field_accuracy(extracted: InvoiceFields, label: InvoiceFields) -> float:
    fields = ("supplier", "invoice_number", "amount_cents", "invoice_date", "po_number")
    hits = sum(1 for f in fields if getattr(extracted, f) == getattr(label, f))
    return hits / len(fields)
