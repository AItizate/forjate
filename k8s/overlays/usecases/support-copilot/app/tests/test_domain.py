import pytest

from support_copilot.domain import Intent, Order, Reason, extract_order_id, filter_fields, message_key, redact, should_escalate


def order(**kw) -> Order:
    base = dict(order_id="ORD-10001", customer_id="C-001", status="shipped", eta="2026-10-12", items_count=2, total_cents=4500, address="Calle Falsa 12, Madrid")
    return Order(**{**base, **kw})


def test_refund_and_cancellation_always_escalate():
    assert should_escalate(Intent.REFUND, angry=False, unresolved_turns=0) == Reason.REFUND
    assert should_escalate(Intent.CANCELLATION, angry=False, unresolved_turns=0) == Reason.CANCELLATION


def test_anger_and_two_unresolved_turns_escalate():
    assert should_escalate(Intent.ORDER_STATUS, angry=True, unresolved_turns=0) == Reason.ANGER
    assert should_escalate(Intent.UNKNOWN, angry=False, unresolved_turns=2) == Reason.UNRESOLVED_TURNS
    assert should_escalate(Intent.ORDER_STATUS, angry=False, unresolved_turns=1) is None


def test_allowed_fields_filter_never_emits_address_or_total():
    out = filter_fields(order(), ("status", "eta", "items_count"))
    assert out == {"status": "shipped", "eta": "2026-10-12", "items_count": 2}


def test_empty_allow_list_fails_closed():
    with pytest.raises(ValueError):
        filter_fields(order(), ())


def test_order_id_comes_from_the_text():
    assert extract_order_id("where is ord-10042 please") == "ORD-10042"
    assert extract_order_id("no id here") is None


def test_redaction_removes_emails_and_phones():
    assert redact("mail me at a.b@example.net or +34 600 123 456") == "mail me at [email] or [phone]"


def test_message_key_is_chat_plus_message_id():
    assert message_key("chat-1", "7") == "chat-1:7"
