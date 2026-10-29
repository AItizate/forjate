"""get_order: read order by id [read-only]"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from ..config import settings
from ..domain import Order
from ..toolkit import NotFound, ToolError, timed_call


class GetOrderArgs(BaseModel):
    order_id: str = Field(pattern=r"^ORD-\d{4,6}$")
    customer_id: str = Field(min_length=1)   # authorisation: the order must belong to the bound customer


def get_order(args: GetOrderArgs, *, timeout_s: float = 3.0) -> Order:
    """Read-only, bounded (3 s): one order by id, and only if it belongs to the customer bound to the sender."""
    cfg = settings()
    with timed_call("tool", "get_order", args, data_class=cfg.data_class):
        try:
            r = httpx.get(f"{cfg.orders_url}/orders/{args.order_id}", timeout=timeout_s,
                          headers={"Authorization": f"Bearer {cfg.orders_token}"} if cfg.orders_token else {})
        except httpx.HTTPError as exc:
            raise ToolError(f"orders API unreachable: {type(exc).__name__}") from exc
        if r.status_code == 404:
            raise NotFound(f"order {args.order_id} not found")
        if r.status_code >= 400:
            raise ToolError(f"orders API returned {r.status_code}")
        order = Order.model_validate(r.json())
        if order.customer_id != args.customer_id:
            raise NotFound(f"order {args.order_id} not found for this customer")  # no oracle for other customers' orders
        return order
