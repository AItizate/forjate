"""Deterministic steps: pure functions, no model and no I/O.

Normalisation, bank number masking and hashing, idempotency keys, the literal-source check, the purchase-order match
and the routing predicate. The model extracts; it never decides whether an amount matches.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

MASK = "[MASKED-BANK-NUMBER]"

# The UX record's reason vocabulary, which the verify Job asserts.
REASONS = (
    "mismatch", "po-missing", "partial-delivery", "duplicate", "bank-details-differ",
    "parse-failed", "low-confidence", "timeout", "lookup-failed",
)

# The UX record's escalation_context order, recommendation last. The bank account number is never a field.
ESCALATION_FIELDS = (
    "item_id", "received_at", "sender", "pdf_object_key",
    "po_fields", "bank_comparison", "tools_consulted",
    "check_fired", "failed_step", "fields_disagree",
    "extracted_supplier", "extracted_invoice_number", "extracted_amount",
    "extracted_currency", "extracted_date", "extracted_po_number",
    "reason", "recommendation",
)


# ---------------------------------------------------------------- amounts and text
def parse_amount(text: str | None) -> int | None:
    """An amount as printed, in cents: 1,234.56, 1.234,56, 842.50, 842,50 and 842 all parse."""
    if text is None:
        return None
    raw = str(text).strip().replace("'", "")
    if not re.fullmatch(r"\d[\d.,]*", raw):
        return None
    last = max(raw.rfind("."), raw.rfind(","))
    if last >= 0 and 1 <= len(raw) - last - 1 <= 2:
        whole, cents = raw[:last], raw[last + 1:].ljust(2, "0")
    else:
        whole, cents = raw, "00"
    whole = re.sub(r"[.,]", "", whole)
    if not whole.isdigit():
        return None
    return int(whole) * 100 + int(cents)


def format_cents(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def _fold(text: str) -> str:
    """Upper-case alphanumerics, with the O/0 confusion OCR makes folded away, for literal comparison of identifiers."""
    return re.sub(r"[^A-Z0-9]", "", text.upper()).replace("O", "0")


def _amounts_in(text: str) -> set[int]:
    found = set()
    for token in re.findall(r"\d(?:[\d.,']*\d)?", text):
        cents = parse_amount(token)
        if cents is not None:
            found.add(cents)
    return found


def _date_forms(iso: str) -> list[str]:
    year, month, day = iso.split("-")
    months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    forms = [f"{year}-{month}-{day}", f"{day}/{month}/{year}", f"{day}.{month}.{year}", f"{day}-{month}-{year}"]
    if 1 <= int(month) <= 12:
        forms.append(f"{day}{months[int(month) - 1]}{year}")
        forms.append(f"{int(day)}{months[int(month) - 1]}{year}")
    return forms


def literal_source_check(extraction: "InvoiceExtraction", source_text: str) -> dict[str, bool | None]:
    """Whether each extracted value appears literally in the source after normalisation; None when it was not extracted."""
    compact = re.sub(r"\s+", "", source_text).upper()
    folded = _fold(source_text)
    amounts = _amounts_in(source_text)

    def identifier(value: str | None) -> bool | None:
        return None if not value else _fold(value) in folded

    return {
        "supplier": identifier(extraction.supplier),
        "invoice_number": identifier(extraction.invoice_number),
        "amount": None if extraction.amount is None else parse_amount(extraction.amount) in amounts,
        "currency": None if not extraction.currency else extraction.currency.upper() in compact,
        "date": None if not extraction.date else any(form in compact for form in _date_forms(extraction.date)),
        "po_number": identifier(extraction.po_number),
    }


# Only these three decide the route; the UX record's low-confidence rule names them.
LITERAL_GATED = ("amount", "date", "po_number")


def literal_failures(literal: dict[str, bool | None]) -> list[str]:
    return [name for name in LITERAL_GATED if literal.get(name) is False]


# ---------------------------------------------------------------- bank numbers
_IBAN_SHAPE = re.compile(r"\b[A-Z]{2}\s?\d{2}(?:[\s-]?[A-Z0-9]{2,4}){2,8}\b")
_LABELLED = re.compile(
    r"(?i)\b(?:bank\s+)?(?:account|acct|konto)(?:\s+(?:no|nr|number))?\.?\s*[:#]?\s*(\d[\d \-]{5,30}\d)"
)


def iban_valid(candidate: str) -> bool:
    """The mod-97 check of ISO 13616."""
    compact = re.sub(r"[\s-]", "", candidate).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", compact):
        return False
    digits = "".join(str(int(ch, 36)) for ch in compact[4:] + compact[:4])
    return int(digits) % 97 == 1


def _iban_spans(text: str) -> list[tuple[int, int, str | None]]:
    """(start, end, valid IBAN or None). A word printed right after the number is shaved off, but never a group of digits:
    a shorter prefix of a misread number can pass mod-97 by chance and would read as a changed bank account."""
    spans: list[tuple[int, int, str | None]] = []
    for match in _IBAN_SHAPE.finditer(text):
        raw = match.group(0)
        if len(re.sub(r"[\s-]", "", raw)) < 15:
            continue
        body = raw
        while not iban_valid(body):
            shaved = re.sub(r"[\s-]+[A-Z0-9]*[A-Z][A-Z0-9]*$", "", body)
            if shaved == body:
                break
            body = shaved
        if iban_valid(body):
            spans.append((match.start(), match.start() + len(body), re.sub(r"[\s-]", "", body).upper()))
        else:
            spans.append((match.start(), match.end(), None))
    return spans


def mask_bank_numbers(text: str) -> str:
    """Masks every IBAN-shaped string, checksum valid or not (OCR breaks checksums), and labelled account numbers."""
    for start, end, _ in sorted(_iban_spans(text), reverse=True):
        text = text[:start] + MASK + text[end:]
    return _LABELLED.sub(lambda m: m.group(0).replace(m.group(1), MASK), text)


def bank_account_on(text: str) -> str | None:
    """The account printed on the document, normalised. An IBAN that fails its checksum is unreadable, not different."""
    for _, _, valid in _iban_spans(text):
        if valid:
            return valid
    labelled = _LABELLED.search(text)
    return re.sub(r"[^0-9]", "", labelled.group(1)) if labelled else None


def salted_bank_hash(account: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}|{re.sub(r'[^A-Z0-9]', '', account.upper())}".encode()).hexdigest()


def compare_bank(invoice_hash: str | None, known_hash: str | None) -> str:
    """same, different or unknown, as the review row shows it."""
    if not invoice_hash or not known_hash:
        return "unknown"
    return "same" if invoice_hash == known_hash else "different"


# ---------------------------------------------------------------- idempotency keys
def attachment_key(message_id: str | None, sha256: str, uidvalidity: int, uid: int, attachment_index: int = 0) -> str:
    """The data-pipeline key: Message-ID + attachment sha256, or UIDVALIDITY + UID + position with no Message-ID."""
    if message_id:
        basis, prefix = f"{message_id.strip()}|{sha256}", "m"
    else:
        basis, prefix = f"{uidvalidity}|{uid}|{attachment_index}", "u"
    return prefix + hashlib.sha256(basis.encode()).hexdigest()[:32]


def payable_key(supplier_id: str, invoice_number: str) -> str:
    """The second check: supplier id + supplier invoice number, normalised."""
    return f"{_fold(supplier_id)}|{_fold(invoice_number)}"


# ---------------------------------------------------------------- the schema the model answers to
class InvoiceExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["invoice", "other"]
    supplier: str | None = None
    supplier_vat: str | None = None
    invoice_number: str | None = None
    amount: str | None = None
    currency: str | None = None
    date: str | None = None
    po_number: str | None = None

    @model_validator(mode="after")
    def _invoice_fields(self) -> "InvoiceExtraction":
        if self.document_type != "invoice":
            return self
        missing = [n for n in ("supplier", "invoice_number", "amount", "currency", "date") if not getattr(self, n)]
        if missing:
            raise ValueError(f"missing: {','.join(missing)}")
        if parse_amount(self.amount) is None:
            raise ValueError("amount: not a number")
        if not re.fullmatch(r"[A-Z]{3}", self.currency or ""):
            raise ValueError("currency: not a three-letter code")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.date or ""):
            raise ValueError("date: not YYYY-MM-DD")
        return self

    @property
    def supplier_id(self) -> str:
        return self.supplier_vat or self.supplier or ""


class PurchaseOrder(BaseModel):
    number: str
    supplier_id: str
    supplier_name: str
    amount_cents: int
    currency: str


# ---------------------------------------------------------------- match and route
def _same_supplier(extraction: InvoiceExtraction, po: PurchaseOrder) -> bool:
    if extraction.supplier_vat:
        return _fold(extraction.supplier_vat) == _fold(po.supplier_id)
    return _fold(extraction.supplier or "") == _fold(po.supplier_name)


def match_po(extraction: InvoiceExtraction, po: PurchaseOrder) -> tuple[str, list[str]]:
    """Exact on supplier and PO number, amount tolerance 0 (the plan's assumption, business Q8).

    Returns matched, partial or mismatch, and the fields that disagree. A PO number that resolves to another supplier's
    order at another amount names the PO number itself: this invoice cites the wrong order.
    """
    supplier_ok = _same_supplier(extraction, po)
    cents = parse_amount(extraction.amount) or 0
    fields: list[str] = []
    if not supplier_ok:
        fields.append("supplier")
    if cents != po.amount_cents:
        fields.append("amount")
    if (extraction.currency or "") != po.currency:
        fields.append("currency")
    if "supplier" in fields and "amount" in fields:
        fields.insert(0, "po_number")
    if not fields:
        return "matched", []
    if fields == ["amount"] and cents < po.amount_cents:
        return "partial", fields
    return "mismatch", fields


@dataclass(frozen=True)
class Decision:
    state: str  # recommended | in_review
    reason: str | None
    check_fired: str
    fields: list[str] = field(default_factory=list)
    recommendation: str = "none"
    linked_key: str | None = None


def route(
    extraction: InvoiceExtraction,
    literal: dict[str, bool | None],
    duplicate_of: str | None,
    po: PurchaseOrder | None,
    bank_comparison: str,
) -> Decision:
    """The escalation predicate. Every result is a recommendation; at Crawl nothing is written anywhere else."""
    failures = literal_failures(literal)
    if failures:
        return Decision("in_review", "low-confidence", "literal-source", failures, "review the source document")
    if duplicate_of:
        return Decision("in_review", "duplicate", "second-key", ["invoice_number"], "none", duplicate_of)
    if not extraction.po_number or po is None:
        return Decision("in_review", "po-missing", "po-lookup", ["po_number"], "link a purchase order or reject")
    if bank_comparison == "different":
        return Decision("in_review", "bank-details-differ", "bank-hash", ["bank_account"], "withheld")
    status, fields = match_po(extraction, po)
    if status == "partial":
        return Decision("in_review", "partial-delivery", "po-match", fields, "review the delivered quantity")
    if status == "mismatch":
        return Decision("in_review", "mismatch", "po-match", fields, "do not post until resolved")
    return Decision("recommended", None, "po-match", [], f"post against {po.number}")


def page_count(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", pdf))


def file_bound_violation(filename: str, content_type: str, content: bytes, *, max_bytes: int, max_pages: int) -> str | None:
    """The UX record's file-out-of-bounds rule: not a PDF, over the size or over the pages. Never truncated."""
    if len(content) > max_bytes:
        return "over-10-mb"
    declared_pdf = content_type.lower() == "application/pdf" or filename.lower().endswith(".pdf")
    if not declared_pdf or not content.startswith(b"%PDF-"):
        return "not-a-pdf"
    if page_count(content) > max_pages:
        return "over-20-pages"
    return None
