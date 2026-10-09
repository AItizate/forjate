"""The ERP stub (architecture: `Odoo REST API: stub` at Crawl). Same routes and errors as the real client
expects; records every posting it receives and every rejected token, so the verify Job can count both."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import stores
from .config import settings
from .domain import PurchaseOrder
from .toolkit import approval_valid

app = FastAPI(title="erp-stub")


class Posting(BaseModel):
    invoice_id: str
    supplier: str
    invoice_number: str
    amount_cents: int
    po_number: str
    idempotency_key: str


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/readyz")
def readyz() -> dict:
    stores.scalar("select 1")
    return {"ok": True}


@app.get("/purchase-orders/{po_number}", response_model=PurchaseOrder)
def purchase_order(po_number: str) -> PurchaseOrder:
    rows = stores.query("select po_number, supplier, amount_cents, bank_account from purchase_orders where po_number = %s", po_number)
    if not rows:
        raise HTTPException(status_code=404, detail="purchase order not found")
    return PurchaseOrder(**rows[0], source="erp-stub")


@app.post("/postings")
def post(posting: Posting, x_approval_token: str = Header(default="")) -> dict:
    if not approval_valid(x_approval_token, posting.invoice_id):
        stores.query("insert into erp_rejections (invoice_id, reason) values (%s, %s) returning id", posting.invoice_id, "missing-or-invalid-approval-token")
        raise HTTPException(status_code=403, detail="approval token missing or invalid")
    existing = stores.query("select posting_id from erp_postings where idempotency_key = %s", posting.idempotency_key)
    if existing:
        return {"posting_id": existing[0]["posting_id"], "duplicate": True, "source": "erp-stub"}
    posting_id = f"P-{uuid.uuid4().hex[:8]}"
    stores.query("insert into erp_postings (idempotency_key, posting_id, invoice_id, invoice_number, supplier, amount_cents, po_number) values (%s, %s, %s, %s, %s, %s, %s) returning posting_id",
                 posting.idempotency_key, posting_id, posting.invoice_id, posting.invoice_number, posting.supplier, posting.amount_cents, posting.po_number)
    return {"posting_id": posting_id, "duplicate": False, "source": "erp-stub"}


def main() -> None:
    import uvicorn
    stores.ensure_schema()
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="warning")


if __name__ == "__main__":
    settings()
    main()
