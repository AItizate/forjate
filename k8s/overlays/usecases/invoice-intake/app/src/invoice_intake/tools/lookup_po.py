"""lookup_po: read purchase order by number [read-only]"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from ..config import settings
from ..domain import PurchaseOrder
from ..toolkit import NotFound, ToolError, timed_call


class LookupPoArgs(BaseModel):
    po_number: str = Field(min_length=1, max_length=64)


def lookup_po(args: LookupPoArgs, *, timeout_s: float = 10.0) -> PurchaseOrder:
    """Read-only, bounded: one PO by number from the ERP (the stub at Crawl). Not found is a typed error."""
    cfg = settings()
    with timed_call("tool", "lookup_po", args, data_class=cfg.data_class):
        r = httpx.get(f"{cfg.erp_url}/purchase-orders/{args.po_number}", timeout=timeout_s,
                      headers={"Authorization": f"Bearer {cfg.erp_token}"} if cfg.erp_token else {})
        if r.status_code == 404:
            raise NotFound(f"purchase order {args.po_number} not found")
        if r.status_code >= 400:
            raise ToolError(f"ERP returned {r.status_code}")
        return PurchaseOrder.model_validate(r.json())
