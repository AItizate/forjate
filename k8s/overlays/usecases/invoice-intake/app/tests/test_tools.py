import pytest

from invoice_intake.domain import InvoiceFields, Reason
from invoice_intake.logging import args_hash
from invoice_intake.model import ReplayModel, model_for
from invoice_intake.config import Settings
from invoice_intake.toolkit import ApprovalRequired, approval_token_for, approval_valid
from invoice_intake.tools import TOOLS
from invoice_intake.tools.post_to_erp import PostToErpArgs, post_to_erp
from invoice_intake.tools.queue_for_review import ReviewItem


def test_registry_carries_the_record_flags():
    assert TOOLS["lookup_po"].flags == ("read-only",)
    assert TOOLS["queue_for_review"].flags == ("idempotent",)
    assert TOOLS["post_to_erp"].flags == ("idempotent", "requires approval token")
    assert "po_number" in TOOLS["lookup_po"].schema["properties"]


def test_post_to_erp_refuses_without_a_token_before_any_io():
    args = PostToErpArgs(invoice_id="inv-01", supplier="X", invoice_number="1", amount_cents=10, po_number="PO-1")
    with pytest.raises(ApprovalRequired):
        post_to_erp(args, approval_token="", idempotency_key="k")
    with pytest.raises(ApprovalRequired):
        post_to_erp(args, approval_token=approval_token_for("inv-02"), idempotency_key="k")  # bound to another item


def test_approval_token_is_bound_to_one_invoice():
    t = approval_token_for("inv-01")
    assert approval_valid(t, "inv-01") and not approval_valid(t, "inv-02")


def test_review_item_is_the_escalation_context():
    item = ReviewItem(invoice_id="inv-15", reason=Reason.AMOUNT_MISMATCH, supplier="X", extracted={"amount_cents": 1}, po={"amount_cents": 2}, detail="d", pdf_object="inbox/inv-15.pdf")
    assert item.reason == "amount-mismatch" and item.pdf_object.endswith(".pdf")


def test_args_hash_hides_values():
    h = args_hash({"bank_account": "DE89370400440532013000"})
    assert "DE89" not in h and len(h) == 16


def test_replay_model_returns_the_label_and_fails_loud_without_one():
    label = InvoiceFields(supplier="S", invoice_number="1", amount_cents=5, invoice_date="2026-01-01", po_number="PO-1").model_dump()
    m = ReplayModel({"inv-00": label})
    assert m.extract("inv-00", "whatever").amount_cents == 5
    with pytest.raises(KeyError):
        m.extract("inv-99", "whatever")


def test_model_mode_selects_the_double():
    assert model_for(Settings(model_mode="replay"), {}).mode == "replay"
    assert model_for(Settings(model_mode="live")).mode == "live"
    with pytest.raises(ValueError):
        model_for(Settings(model_mode="magic"))
