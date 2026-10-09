"""escalate: write escalation with transcript [idempotent]

The handoff itself: writes the escalation record (the ux record's escalation context) into the agents'
queue table. Idempotent on the conversation id plus the reason; never touches the orders API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..config import settings
from ..domain import Reason, redact
from ..toolkit import timed_call
from .. import stores


class EscalateArgs(BaseModel):
    conversation_id: str
    customer_id: str | None
    transcript: list[str] = Field(min_length=1)
    order_id: str | None
    reason: Reason


class EscalateResult(BaseModel):
    escalation_id: str
    created: bool
    source: str = "postgres"


def escalate(args: EscalateArgs, *, idempotency_key: str, timeout_s: float = 5.0) -> EscalateResult:
    cfg = settings()
    with timed_call("tool", "escalate", args, data_class=cfg.data_class):
        transcript = [redact(t) for t in args.transcript]
        created = stores.upsert_escalation(idempotency_key, args.conversation_id, args.customer_id, transcript, args.order_id, args.reason.value)
        return EscalateResult(escalation_id=idempotency_key, created=created)
