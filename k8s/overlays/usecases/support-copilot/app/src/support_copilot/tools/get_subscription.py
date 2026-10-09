"""get_subscription: read subscription by customer [read-only]"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from ..config import settings
from ..domain import Subscription
from ..toolkit import NotFound, ToolError, timed_call


class GetSubscriptionArgs(BaseModel):
    customer_id: str = Field(min_length=1)


def get_subscription(args: GetSubscriptionArgs, *, timeout_s: float = 3.0) -> Subscription:
    cfg = settings()
    with timed_call("tool", "get_subscription", args, data_class=cfg.data_class):
        try:
            r = httpx.get(f"{cfg.orders_url}/subscriptions/{args.customer_id}", timeout=timeout_s,
                          headers={"Authorization": f"Bearer {cfg.orders_token}"} if cfg.orders_token else {})
        except httpx.HTTPError as exc:
            raise ToolError(f"orders API unreachable: {type(exc).__name__}") from exc
        if r.status_code == 404:
            raise NotFound(f"no subscription for customer {args.customer_id}")
        if r.status_code >= 400:
            raise ToolError(f"orders API returned {r.status_code}")
        return Subscription.model_validate(r.json())
