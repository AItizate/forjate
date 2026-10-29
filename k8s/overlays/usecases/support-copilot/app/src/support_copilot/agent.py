"""The agent loop: one customer message in, one reply out, with the deterministic handoffs and the field filter.
The same loop serves the Telegram webhook and the replay route; the model is behind a Protocol."""

from __future__ import annotations

from dataclasses import dataclass

from . import stores
from .config import Settings, settings
from .domain import (HANDOFF, ORDER_INTENTS, SUBSCRIPTION_INTENTS, Intent, Reason, filter_fields, message_key, redact, should_escalate)
from .logging import log
from .model import Model, model_for
from .toolkit import NotFound, ToolError
from .tools.escalate import EscalateArgs, escalate
from .tools.get_order import GetOrderArgs, get_order
from .tools.get_subscription import GetSubscriptionArgs, get_subscription

STATIC_ANSWERS = {
    Intent.RETURN_POLICY: "You can return any item within 30 days of delivery; start the return from your account page and we send a label.",
    Intent.OPENING_HOURS: "Support is available Monday to Friday, 9:00 to 18:00 CET; this chat answers around the clock.",
}


@dataclass(frozen=True)
class Incoming:
    conversation_id: str
    chat_id: str
    message_id: str
    handle: str | None
    text: str


@dataclass(frozen=True)
class Reply:
    text: str
    outcome: str          # resolved | escalated | dead-lettered
    reason: str | None = None
    intent: str | None = None


class Agent:
    def __init__(self, cfg: Settings | None = None, model: Model | None = None):
        self.cfg = cfg or settings()
        self.model = model or model_for(self.cfg)

    def handle(self, msg: Incoming) -> Reply:
        key = message_key(msg.chat_id, msg.message_id)
        seen = stores.seen_reply(key)
        if seen is not None:
            return Reply(text=seen, outcome="duplicate-delivery")   # Telegram retried: same reply, no second effect
        state = stores.session(msg.chat_id)
        if state.get("escalated"):
            reply = Reply(text="A colleague has this conversation and will follow up here.", outcome="escalated", reason=state["escalated"])
            return self._finish(msg, key, state, reply)
        text = (msg.text or "").strip()
        if not text:
            stores.dead_letter(key, msg.conversation_id, "normalise", "empty or unparseable message")
            return self._finish(msg, key, state, Reply(text=HANDOFF[Reason.LOW_CONFIDENCE], outcome="dead-lettered", reason="malformed"))
        state["transcript"] = (state.get("transcript") or []) + [f"customer: {redact(text)}"]
        customer_id = stores.customer_by_handle(msg.handle)
        try:
            c = self.model.classify(msg.conversation_id, text, timeout_s=self.cfg.turn_timeout_s)
        except Exception:
            return self._handoff(msg, key, state, customer_id, Reason.TIMEOUT, order_id=None, intent=None)
        reason = should_escalate(c.intent, angry=c.angry, unresolved_turns=state.get("unresolved_turns", 0))
        if reason:
            return self._handoff(msg, key, state, customer_id, reason, order_id=c.order_id, intent=c.intent)
        if c.intent in STATIC_ANSWERS:
            return self._finish(msg, key, state, Reply(text=STATIC_ANSWERS[c.intent], outcome="resolved", intent=c.intent))
        if c.intent in ORDER_INTENTS or c.intent in SUBSCRIPTION_INTENTS:
            if not customer_id:
                return self._handoff(msg, key, state, None, Reason.UNKNOWN_SENDER, order_id=c.order_id, intent=c.intent)
            try:
                if c.intent in SUBSCRIPTION_INTENTS:
                    sub = get_subscription(GetSubscriptionArgs(customer_id=customer_id))
                    answer = {"plan": sub.plan, "status": sub.status, "renews_on": sub.renews_on} if c.intent != Intent.PAYMENT_METHOD else {"payment_method": sub.payment_method}
                else:
                    if not c.order_id:
                        state["unresolved_turns"] = state.get("unresolved_turns", 0) + 1
                        return self._finish(msg, key, state, Reply(text="Which order is this about? Please send the order number (it looks like ORD-12345).", outcome="pending", intent=c.intent))
                    order = get_order(GetOrderArgs(order_id=c.order_id, customer_id=customer_id))
                    answer = filter_fields(order, self.cfg.allowed_fields)
                    if c.intent == Intent.CHANGE_ADDRESS:
                        return self._handoff(msg, key, state, customer_id, Reason.LOW_CONFIDENCE, order_id=c.order_id, intent=c.intent)
                    if c.intent == Intent.INVOICE_COPY:
                        answer = {**answer, "invoice": "sent to the email on the order"}
            except NotFound:
                return self._handoff(msg, key, state, customer_id, Reason.UNKNOWN_ORDER, order_id=c.order_id, intent=c.intent)
            except ToolError:
                return self._handoff(msg, key, state, customer_id, Reason.LOOKUP_FAILED, order_id=c.order_id, intent=c.intent)
            text_out = "; ".join(f"{k}: {v}" for k, v in answer.items())
            return self._finish(msg, key, state, Reply(text=f"Here is what I can see for {c.order_id or 'your account'}: {text_out}.", outcome="resolved", intent=c.intent))
        state["unresolved_turns"] = state.get("unresolved_turns", 0) + 1
        if state["unresolved_turns"] >= 2:
            return self._handoff(msg, key, state, customer_id, Reason.UNRESOLVED_TURNS, order_id=c.order_id, intent=c.intent)
        return self._finish(msg, key, state, Reply(text="I am not sure I understood. Could you tell me which order or subscription this is about?", outcome="pending", intent=c.intent))

    def _handoff(self, msg: Incoming, key: str, state: dict, customer_id: str | None, reason: Reason, *, order_id: str | None, intent: Intent | None) -> Reply:
        escalate(EscalateArgs(conversation_id=msg.conversation_id, customer_id=customer_id, transcript=state["transcript"], order_id=order_id, reason=reason),
                 idempotency_key=f"{msg.conversation_id}:{reason.value}")
        state["escalated"] = reason.value
        return self._finish(msg, key, state, Reply(text=HANDOFF[reason], outcome="escalated", reason=reason.value, intent=intent.value if intent else None))

    def _finish(self, msg: Incoming, key: str, state: dict, reply: Reply) -> Reply:
        state["transcript"] = (state.get("transcript") or []) + [f"bot: {reply.text}"]
        stores.save_session(msg.chat_id, state, self.cfg.session_ttl_hours)
        stores.mark_processed(key, msg.conversation_id, reply.text)
        stores.record_outcome(msg.conversation_id, reply.outcome, reply.reason, reply.intent, reply.text)
        log("turn", data_class=self.cfg.data_class, conversation_id=msg.conversation_id, outcome=reply.outcome, reason=reply.reason, intent=reply.intent)
        return reply
