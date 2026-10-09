"""queue_for_review: write review item [idempotent]"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..config import settings
from ..domain import Reason, redact
from ..toolkit import timed_call
from .. import stores


class ReviewItem(BaseModel):
    """The ux record's escalation context: what a clerk needs to decide, in one row."""
    invoice_id: str
    reason: Reason
    supplier: str | None = None
    extracted: dict | None = None
    po: dict | None = None
    detail: str = Field(default="", max_length=500)
    pdf_object: str


class ReviewResult(BaseModel):
    invoice_id: str
    created: bool
    source: str = "postgres"


def queue_for_review(args: ReviewItem, *, idempotency_key: str, timeout_s: float = 10.0) -> ReviewResult:
    """Idempotent on the invoice's key: a second call with the same key changes nothing."""
    cfg = settings()
    with timed_call("tool", "queue_for_review", args, data_class=cfg.data_class):
        row = args.model_dump(mode="json")
        row["detail"] = redact(row["detail"])
        for part in ("extracted", "po"):
            if row.get(part):
                row[part].pop("bank_account", None)  # the clerk sees a flag, never the number
        created = stores.upsert_review(idempotency_key, row)
        return ReviewResult(invoice_id=args.invoice_id, created=created)
