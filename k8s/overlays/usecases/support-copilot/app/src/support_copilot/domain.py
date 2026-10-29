"""Deterministic steps: intents, the escalation predicate, order-id extraction, the allowed-field filter,
redaction, idempotency keys. No model, no I/O."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

COMMON_INTENTS = ("order_status", "delivery_eta", "items_in_order", "subscription_status", "subscription_renewal",
                  "change_address", "invoice_copy", "payment_method", "return_policy", "opening_hours")


class Intent(StrEnum):
    ORDER_STATUS = "order_status"
    DELIVERY_ETA = "delivery_eta"
    ITEMS_IN_ORDER = "items_in_order"
    SUBSCRIPTION_STATUS = "subscription_status"
    SUBSCRIPTION_RENEWAL = "subscription_renewal"
    CHANGE_ADDRESS = "change_address"
    INVOICE_COPY = "invoice_copy"
    PAYMENT_METHOD = "payment_method"
    RETURN_POLICY = "return_policy"
    OPENING_HOURS = "opening_hours"
    REFUND = "refund"
    CANCELLATION = "cancellation"
    UNKNOWN = "unknown"


ORDER_INTENTS = {Intent.ORDER_STATUS, Intent.DELIVERY_ETA, Intent.ITEMS_IN_ORDER, Intent.CHANGE_ADDRESS, Intent.INVOICE_COPY}
SUBSCRIPTION_INTENTS = {Intent.SUBSCRIPTION_STATUS, Intent.SUBSCRIPTION_RENEWAL, Intent.PAYMENT_METHOD}


class Reason(StrEnum):
    REFUND = "refund"
    CANCELLATION = "cancellation"
    ANGER = "anger"
    UNRESOLVED_TURNS = "two-unresolved-turns"
    UNKNOWN_ORDER = "unknown-order"
    UNKNOWN_SENDER = "unknown-sender"
    LOOKUP_FAILED = "lookup-failed"
    TIMEOUT = "timeout"
    LOW_CONFIDENCE = "low-confidence"


class Classification(BaseModel):
    intent: Intent
    order_id: str | None = None
    angry: bool = False


class Order(BaseModel):
    order_id: str
    customer_id: str
    status: str
    eta: str
    items_count: int = Field(ge=0)
    total_cents: int = Field(ge=0)
    address: str
    source: str = "orders"


class Subscription(BaseModel):
    customer_id: str
    plan: str
    status: str
    renews_on: str
    payment_method: str
    source: str = "orders"


ORDER_ID = re.compile(r"\bORD-\d{4,6}\b", re.IGNORECASE)
ANGER = re.compile(r"\b(furious|unacceptable|ridiculous|angry|worst|scam|disgrace|outrageous)\b|!!!", re.IGNORECASE)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}")
PHONE = re.compile(r"(\+\d{1,3}[ -]?)?\(?\d{2,4}\)?[ -]\d{3}[ -]\d{3,4}\b")  # separators a timestamp never has


def extract_order_id(text: str) -> str | None:
    m = ORDER_ID.search(text)
    return m.group(0).upper() if m else None


def should_escalate(intent: Intent, *, angry: bool, unresolved_turns: int) -> Reason | None:
    """The deterministic handoff (ux: refund-or-cancellation, angry-customer, two-unresolved-turns). Never a model judgement."""
    if intent == Intent.REFUND:
        return Reason.REFUND
    if intent == Intent.CANCELLATION:
        return Reason.CANCELLATION
    if angry:
        return Reason.ANGER
    if unresolved_turns >= 2:
        return Reason.UNRESOLVED_TURNS
    return None


def filter_fields(order: Order, allowed: tuple[str, ...]) -> dict:
    """Only the allowed order fields are ever emitted. An empty allow-list fails closed."""
    if not allowed:
        raise ValueError("ALLOWED_ORDER_FIELDS is empty: refusing to emit any order field")
    return {k: v for k, v in order.model_dump().items() if k in allowed}


def redact(text: str) -> str:
    """Names are handled by the handle mapping; emails and phone numbers never reach a log or a prompt."""
    return PHONE.sub("[phone]", EMAIL.sub("[email]", text))


def message_key(chat_id: str, message_id: str) -> str:
    """The pipeline record's idempotency key: chat id plus message id."""
    return f"{chat_id}:{message_id}"


HANDOFF = {
    Reason.REFUND: "I have passed your refund request to a colleague with your conversation; they will follow up here.",
    Reason.CANCELLATION: "I have passed your cancellation request to a colleague with your conversation; they will follow up here.",
    Reason.ANGER: "I am sorry about this. A colleague will take over this conversation and follow up here.",
    Reason.UNRESOLVED_TURNS: "I could not resolve this; a colleague will follow up here with the full context.",
    Reason.UNKNOWN_ORDER: "I cannot find that order number. A colleague will check it and follow up here.",
    Reason.UNKNOWN_SENDER: "I cannot link this chat to an account yet; a colleague will do that and follow up here.",
    Reason.LOOKUP_FAILED: "I cannot read your order right now; a colleague will follow up here.",
    Reason.TIMEOUT: "This is taking longer than it should; a colleague will follow up here.",
    Reason.LOW_CONFIDENCE: "I am not sure I understood; a colleague will follow up here.",
}
