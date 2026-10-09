from support_copilot.config import Settings
from support_copilot.domain import Classification, Intent
from support_copilot.logging import args_hash
from support_copilot.model import RulesModel, model_for
from support_copilot.tools import TOOLS
from support_copilot.tools.escalate import EscalateArgs
from support_copilot.tools.get_order import GetOrderArgs
import pytest


def test_registry_carries_the_record_flags():
    assert TOOLS["get_order"].flags == ("read-only",)
    assert TOOLS["get_subscription"].flags == ("read-only",)
    assert TOOLS["escalate"].flags == ("idempotent",)
    assert set(TOOLS["get_order"].schema["properties"]) == {"order_id", "customer_id"}


def test_get_order_args_bind_the_customer():
    with pytest.raises(Exception):
        GetOrderArgs(order_id="not-an-id", customer_id="C-1")
    assert GetOrderArgs(order_id="ORD-10001", customer_id="C-1").customer_id == "C-1"


def test_escalation_context_has_the_fields_the_ux_record_names():
    a = EscalateArgs(conversation_id="conv-1", customer_id="C-1", transcript=["customer: refund please"], order_id="ORD-10001", reason="refund")
    assert a.transcript and a.order_id and a.reason == "refund"


def test_rules_model_classifies_the_common_intents_and_refunds():
    m = RulesModel()
    assert m.classify("c", "I want a refund for ORD-10001").intent == Intent.REFUND
    assert m.classify("c", "When will ORD-10002 arrive?").intent == Intent.DELIVERY_ETA
    assert m.classify("c", "This is unacceptable!!!").angry is True
    assert m.classify("c", "hello there").intent == Intent.UNKNOWN


def test_model_mode_selects_the_double():
    assert model_for(Settings(model_mode="rules")).mode == "rules"
    assert model_for(Settings(model_mode="live")).mode == "live"
    with pytest.raises(ValueError):
        model_for(Settings(model_mode="magic"))


def test_args_hash_hides_values():
    assert "example" not in args_hash({"email": "a@example.net"})
