"""Unit layer of the quality record's test_pyramid: normalisation, literal source, arithmetic, match, keys, bank hash. No model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from invoice_intake.domain import (
    InvoiceExtraction, PurchaseOrder, attachment_key, compare_bank, file_bound_violation, literal_failures, literal_source_check,
    match_po, parse_amount, payable_key, route, salted_bank_hash,
)


def extraction(**over: object) -> InvoiceExtraction:
    base = dict(document_type="invoice", supplier="Alder Finch Supplies", supplier_vat="DE810000000", invoice_number="INV-1",
                amount="1234.56", currency="EUR", date="2026-10-14", po_number="PUR-50001")
    return InvoiceExtraction(**{**base, **over})


PO = PurchaseOrder(number="PUR-50001", supplier_id="DE810000000", supplier_name="Alder Finch Supplies", amount_cents=123456, currency="EUR")
SOURCE = "INVOICE Alder Finch Supplies VAT ID: DE810000000 Invoice number: INV-1 Date: 14/10/2026 PO number: PUR-50001 Total: 1,234.56 EUR"


@pytest.mark.parametrize("text,cents", [("1,234.56", 123456), ("1.234,56", 123456), ("842.50", 84250), ("842,5", 84250), ("842", 84200), ("0.01", 1), ("abc", None), (None, None)])
def test_amount_arithmetic_to_the_cent(text: str | None, cents: int | None) -> None:
    assert parse_amount(text) == cents


def test_literal_source_finds_normalised_values() -> None:
    literal = literal_source_check(extraction(), SOURCE)
    assert literal["amount"] and literal["date"] and literal["po_number"] and literal["supplier"]
    assert literal_failures(literal) == []


def test_literal_source_names_a_value_not_in_the_text() -> None:
    literal = literal_source_check(extraction(amount="1234.57", po_number="PUR-99999", date="2026-10-15"), SOURCE)
    assert literal_failures(literal) == ["amount", "date", "po_number"]


def test_a_po_number_absent_from_the_invoice_is_not_a_literal_failure() -> None:
    assert literal_source_check(extraction(po_number=None), SOURCE)["po_number"] is None


def test_exact_match() -> None:
    assert match_po(extraction(), PO) == ("matched", [])


def test_amount_one_cent_over_is_a_mismatch() -> None:
    assert match_po(extraction(amount="1234.57"), PO) == ("mismatch", ["amount"])


def test_amount_below_the_po_is_a_partial_delivery() -> None:
    assert match_po(extraction(amount="1000.00"), PO) == ("partial", ["amount"])


def test_supplier_and_amount_off_names_the_po_number() -> None:
    status, fields = match_po(extraction(supplier_vat="DE810000001", amount="5.00"), PO)
    assert status == "mismatch" and fields[0] == "po_number"


LITERAL_OK = {"amount": True, "date": True, "po_number": True}


def test_route_order_and_reasons() -> None:
    ok = extraction()
    assert route(ok, LITERAL_OK, None, PO, "same").state == "recommended"
    assert route(ok, {**LITERAL_OK, "amount": False}, None, PO, "same").reason == "low-confidence"
    assert route(ok, LITERAL_OK, "earlier", PO, "same").reason == "duplicate"
    assert route(ok, LITERAL_OK, None, None, "same").reason == "po-missing"
    assert route(extraction(po_number=None), LITERAL_OK, None, None, "same").reason == "po-missing"


def test_changed_bank_withholds_the_recommendation_though_all_else_matches() -> None:
    decision = route(extraction(), LITERAL_OK, None, PO, "different")
    assert (decision.reason, decision.recommendation) == ("bank-details-differ", "withheld")


def test_a_duplicate_carries_no_posting_recommendation() -> None:
    decision = route(extraction(), LITERAL_OK, "earlier-key", PO, "same")
    assert decision.recommendation == "none" and decision.linked_key == "earlier-key"


def test_unknown_bank_reference_is_not_an_exception() -> None:
    assert compare_bank(None, "abc") == "unknown" and route(extraction(), LITERAL_OK, None, PO, "unknown").state == "recommended"


def test_attachment_key_is_stable_and_differs_per_message() -> None:
    assert attachment_key("<a@x>", "sha", 1, 1) == attachment_key("<a@x>", "sha", 9, 7)
    assert attachment_key("<a@x>", "sha", 1, 1) != attachment_key("<b@x>", "sha", 1, 1)


def test_attachment_key_falls_back_to_uidvalidity_and_uid() -> None:
    assert attachment_key(None, "sha", 1, 5).startswith("u")
    assert attachment_key(None, "sha", 1, 5) != attachment_key(None, "sha", 2, 5)


def test_payable_key_normalises() -> None:
    assert payable_key("de 810000000", "inv-1") == payable_key("DE810000000", "INV 1")


def test_salted_hash_compares_without_the_number() -> None:
    assert salted_bank_hash("DE89 3704", "s") == salted_bank_hash("de893704", "s")
    assert salted_bank_hash("DE893704", "s") != salted_bank_hash("DE893704", "t")


@pytest.mark.parametrize("over", [{"amount": "twelve"}, {"amount": None}, {"date": "14/10/2026"}, {"currency": "euro"}, {"supplier": None}, {"unexpected": "x"}])
def test_schema_refuses_an_invalid_extraction(over: dict) -> None:
    with pytest.raises(ValidationError):
        extraction(**over)


def test_a_non_invoice_needs_no_fields() -> None:
    assert InvoiceExtraction(document_type="other").po_number is None


# One test per file bound of the UX record's file-out-of-bounds rule: no seed item on purpose, so these are its only proof.
def test_file_bound_not_a_pdf() -> None:
    assert file_bound_violation("a.docx", "application/msword", b"PK..", max_bytes=100, max_pages=20) == "not-a-pdf"
    assert file_bound_violation("a.pdf", "application/pdf", b"PK..", max_bytes=100, max_pages=20) == "not-a-pdf"


def test_file_bound_over_size() -> None:
    assert file_bound_violation("a.pdf", "application/pdf", b"%PDF-" + b"x" * 200, max_bytes=100, max_pages=20) == "over-10-mb"


def test_file_bound_over_pages() -> None:
    assert file_bound_violation("a.pdf", "application/pdf", b"%PDF-" + b"/Type /Page\n" * 21 + b"/Type /Pages", max_bytes=10_000, max_pages=20) == "over-20-pages"


def test_file_within_bounds() -> None:
    assert file_bound_violation("a.pdf", "application/pdf", b"%PDF-" + b"/Type /Page\n" * 20, max_bytes=10_000, max_pages=20) is None
