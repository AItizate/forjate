"""post_to_erp: write payable to Odoo [idempotent, requires approval token]

At Crawl the ERP is the stub; the token is issued by the deterministic check for straight-through
items and by the AP clerk's approval in the review queue for everything else (the ux checkpoint)."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from ..config import settings
from ..toolkit import ApprovalRequired, ToolError, approval_valid, timed_call


class PostToErpArgs(BaseModel):
    invoice_id: str
    supplier: str
    invoice_number: str
    amount_cents: int = Field(ge=0)
    po_number: str


class PostToErpResult(BaseModel):
    posting_id: str
    duplicate: bool
    source: str = "erp"


def post_to_erp(args: PostToErpArgs, *, approval_token: str, idempotency_key: str, timeout_s: float = 10.0) -> PostToErpResult:
    """Refuses before any I/O without a token bound to this invoice; idempotent on the key."""
    cfg = settings()
    if not approval_valid(approval_token, args.invoice_id):
        raise ApprovalRequired("post_to_erp needs an approval token bound to this invoice")
    with timed_call("tool", "post_to_erp", args, data_class=cfg.data_class):
        r = httpx.post(f"{cfg.erp_url}/postings", json={**args.model_dump(), "idempotency_key": idempotency_key}, timeout=timeout_s,
                       headers={"X-Approval-Token": approval_token, **({"Authorization": f"Bearer {cfg.erp_token}"} if cfg.erp_token else {})})
        if r.status_code == 403:
            raise ApprovalRequired("the ERP rejected the approval token")
        if r.status_code >= 400:
            raise ToolError(f"ERP returned {r.status_code}")
        return PostToErpResult.model_validate(r.json())
