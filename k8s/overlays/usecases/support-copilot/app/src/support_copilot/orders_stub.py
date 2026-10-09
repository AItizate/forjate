"""The orders API stub (architecture: `orders API: stub` at Crawl): same routes, fields and errors as the
real one, read-only, backed by the seed; it records every call so the verify Job can prove write calls = 0."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import stores
from .config import settings
from .domain import Order, Subscription

app = FastAPI(title="orders-stub")


@app.middleware("http")
async def record(request: Request, call_next):
    stores.execute("insert into orders_stub_calls (method, path) values (%s, %s)", request.method, request.url.path)
    if request.method != "GET":
        return JSONResponse(status_code=405, content={"detail": "the orders API is read-only for this client"})
    return await call_next(request)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/readyz")
def readyz() -> dict:
    stores.scalar("select 1")
    return {"ok": True}


@app.get("/orders/{order_id}", response_model=Order)
def order(order_id: str) -> Order:
    rows = stores.query("select * from orders where order_id = %s", order_id.upper())
    if not rows:
        raise HTTPException(status_code=404, detail="order not found")
    return Order(**rows[0], source="orders-stub")


@app.get("/subscriptions/{customer_id}", response_model=Subscription)
def subscription(customer_id: str) -> Subscription:
    rows = stores.query("select * from subscriptions where customer_id = %s", customer_id)
    if not rows:
        raise HTTPException(status_code=404, detail="no subscription")
    return Subscription(**rows[0], source="orders-stub")


def main() -> None:
    import uvicorn
    stores.ensure_schema()
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="warning")


if __name__ == "__main__":
    settings()
    main()
