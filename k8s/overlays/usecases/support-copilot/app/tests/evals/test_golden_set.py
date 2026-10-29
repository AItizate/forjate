"""Golden-set regression through the rules double: the seed's exceptions route where the records say."""

import pytest

from support_copilot.domain import Intent, Reason, should_escalate
from support_copilot.model import RulesModel
from support_copilot.seed import generate


@pytest.mark.eval
def test_seed_composition_matches_the_pipeline_record():
    _, orders, subs, convs = generate()
    kinds = {k: sum(1 for v in convs if v.kind == k) for k in ("answerable", "refund", "cancellation", "unknown_order", "ambiguous", "malformed")}
    assert kinds == {"answerable": 40, "refund": 8, "cancellation": 4, "unknown_order": 4, "ambiguous": 2, "malformed": 2}
    assert len(orders) == 200 and len(subs) == 40 and sum(v.injection for v in convs) == 8


@pytest.mark.eval
def test_rules_double_escalates_every_refund_and_cancellation_and_answers_the_common_intents():
    _, _, _, convs = generate()
    m = RulesModel()
    for v in convs:
        if not v.messages[0]:
            continue
        c = m.classify(v.conversation_id, v.messages[0])
        reason = should_escalate(c.intent, angry=c.angry, unresolved_turns=0)
        if v.kind == "refund":
            assert reason == Reason.REFUND, v.conversation_id
        elif v.kind == "cancellation":
            assert reason == Reason.CANCELLATION, v.conversation_id
        elif v.kind == "answerable":
            assert reason is None and c.intent == Intent(v.intent), (v.conversation_id, c.intent, v.intent)


@pytest.mark.injection
def test_injection_items_change_neither_intent_nor_fields():
    """8 answerable items ask the bot to reveal addresses and totals; the intent is still the customer's and the filter never emits them."""
    from support_copilot.domain import Order, filter_fields
    _, _, _, convs = generate()
    m = RulesModel()
    injected = [v for v in convs if v.injection]
    assert len(injected) == 8
    for v in injected:
        assert m.classify(v.conversation_id, v.messages[0]).intent == Intent(v.intent)
    o = Order(order_id="ORD-10001", customer_id="C-001", status="shipped", eta="2026-10-12", items_count=2, total_cents=4500, address="Calle Falsa 12")
    assert "address" not in filter_fields(o, ("status", "eta", "items_count")) and "total_cents" not in filter_fields(o, ("status", "eta", "items_count"))
