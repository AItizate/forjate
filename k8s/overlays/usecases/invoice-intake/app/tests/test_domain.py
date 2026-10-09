from invoice_intake.domain import InvoiceFields, PurchaseOrder, Reason, compare, field_accuracy, idempotency_key, redact


def fields(**kw) -> InvoiceFields:
    base = dict(supplier="Nordwind Papier GmbH", invoice_number="INV-1", amount_cents=12500, invoice_date="2026-09-01", po_number="PO-1", bank_account="DE89370400440532013000")
    return InvoiceFields(**{**base, **kw})


def po(**kw) -> PurchaseOrder:
    base = dict(po_number="PO-1", supplier="Nordwind Papier GmbH", amount_cents=12500, bank_account="DE89370400440532013000")
    return PurchaseOrder(**{**base, **kw})


def test_match_is_arithmetic_in_code():
    assert compare(fields(), po()).straight_through is True


def test_amount_difference_routes_to_review():
    d = compare(fields(amount_cents=12600), po())
    assert d.reason == Reason.AMOUNT_MISMATCH and not d.straight_through and "100" in d.detail


def test_supplier_normalisation_tolerates_punctuation_but_not_another_supplier():
    assert compare(fields(supplier="NORDWIND-PAPIER GMBH"), po()).straight_through
    assert compare(fields(supplier="Atelier Lumen SAS"), po()).reason == Reason.SUPPLIER_MISMATCH


def test_bank_account_change_is_a_checkpoint_even_when_the_amount_matches():
    assert compare(fields(bank_account="DE00000000000000000001"), po()).reason == Reason.BANK_ACCOUNT_CHANGE


def test_idempotency_key_is_the_pdf_hash():
    assert idempotency_key(b"abc") == idempotency_key(b"abc") != idempotency_key(b"abd")


def test_redaction_removes_ibans():
    assert "DE89" not in redact("pay to DE89370400440532013000 please")


def test_field_accuracy_counts_five_fields():
    assert field_accuracy(fields(), fields()) == 1.0
    assert field_accuracy(fields(amount_cents=1), fields()) == 0.8
