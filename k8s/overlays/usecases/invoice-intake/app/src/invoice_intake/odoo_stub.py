"""The Odoo double: purchase orders, supplier bank references and payables over HTTP, backed by the seed.

The routes and fields are ASSUMED: the real Odoo version and API are architecture Q1, and G-ARCH-2 compares them. Every read and
write attempt is counted, so "the Odoo double received 0 write calls" is a count and not a belief. Access logs stay off: a path
carries a PO number.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Callable

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .config import get_settings
from .double_store import DoubleKV, PgKV
from .logs import emit

PORT = 8001


def _bearer(authorization: str) -> str:
    return authorization.removeprefix("Bearer ").strip()


def _accepts(env_name: str, authorization: str) -> bool:
    expected = os.environ.get(env_name, "")
    return bool(expected) and hmac.compare_digest(expected, _bearer(authorization))


def require(env_name: str) -> Callable[[str], None]:
    def dependency(authorization: str = Header(default="")) -> None:
        if not _accepts(env_name, authorization):
            raise HTTPException(status_code=401, detail="unauthorized")
    return dependency


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="not_found")


def create_app(kv: DoubleKV) -> FastAPI:
    app = FastAPI(title="Odoo double", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        try:
            kv.ping()
        except Exception:  # noqa: BLE001 - any store failure means not ready
            return JSONResponse({"status": "store unavailable"}, status_code=503)
        return JSONResponse({"status": "ready"})

    @app.get("/api/purchase-orders/{number}", dependencies=[Depends(require("ODOO_LOOKUP_PO_TOKEN"))])
    def purchase_order(number: str) -> dict:
        kv.incr("odoo.reads")
        doc = kv.get("odoo.po", number)
        if doc is None:
            raise _not_found()
        return doc

    @app.get("/api/payables", dependencies=[Depends(require("ODOO_FIND_PAYABLE_TOKEN"))])
    def payables(supplier_id: str, invoice_number: str) -> dict:
        kv.incr("odoo.reads")
        doc = kv.get("odoo.payable", f"{supplier_id}|{invoice_number}")
        if doc is None:
            raise _not_found()
        return doc

    @app.get("/api/suppliers/{supplier_id}/bank-ref", dependencies=[Depends(require("ODOO_BANK_REF_TOKEN"))])
    def bank_ref(supplier_id: str) -> dict:
        kv.incr("odoo.reads")
        doc = kv.get("odoo.supplier", supplier_id)
        if doc is None:
            raise _not_found()
        return {"supplier_id": supplier_id, "bank_ref_hash": doc["bank_ref_hash"]}

    @app.post("/api/payables")
    def create_payable(body: dict, request: Request, authorization: str = Header(default=""), idempotency_key: str = Header(default="")) -> dict:
        # Counted before anything else: an attempt is what the assistive ceiling forbids.
        kv.incr("odoo.write_attempts")
        if not _accepts("ODOO_POST_INVOICE_TOKEN", authorization):
            kv.incr("odoo.write_refused")
            raise HTTPException(status_code=403, detail="forbidden")
        if not idempotency_key:
            raise HTTPException(status_code=422, detail="idempotency key required")
        posting = {**body, "posting_id": "BILL-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:12], "idempotency_key": idempotency_key}
        created = kv.put_if_absent("odoo.payable", f"{body.get('supplier_id')}|{body.get('invoice_number')}", posting)
        return {**posting, "duplicate": not created}

    @app.post("/_double/seed", dependencies=[Depends(require("DOUBLE_ADMIN_TOKEN"))])
    def seed(body: dict) -> dict:
        kv.upsert_many("odoo.supplier", {s["supplier_id"]: s for s in body.get("suppliers", [])})
        kv.upsert_many("odoo.po", {p["number"]: p for p in body.get("purchase_orders", [])})
        return {"suppliers": kv.count("odoo.supplier"), "purchase_orders": kv.count("odoo.po")}

    @app.get("/_double/stats", dependencies=[Depends(require("DOUBLE_ADMIN_TOKEN"))])
    def stats() -> dict:
        docs = kv.all_docs("odoo.po")
        digest = hashlib.sha256(json.dumps(docs, sort_keys=True).encode()).hexdigest()
        return {"reads": kv.counter("odoo.reads"), "write_attempts": kv.counter("odoo.write_attempts"),
                "write_refused": kv.counter("odoo.write_refused"), "purchase_orders": len(docs), "po_checksum": digest}

    return app


def main() -> None:
    settings = get_settings()
    emit("stub_start", stub="odoo", outcome="ok")
    uvicorn.run(create_app(PgKV(settings.working_dsn)), host="0.0.0.0", port=PORT, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
