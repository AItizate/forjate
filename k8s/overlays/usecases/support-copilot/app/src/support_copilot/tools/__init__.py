"""One module per line of the AI-engineering record's tools; the flags are code."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from .escalate import EscalateArgs, escalate
from .get_order import GetOrderArgs, get_order
from .get_subscription import GetSubscriptionArgs, get_subscription


@dataclass(frozen=True)
class Tool:
    name: str
    fn: Callable[..., Any]
    args: type[BaseModel]
    flags: tuple[str, ...]

    @property
    def schema(self) -> dict:
        return self.args.model_json_schema()


TOOLS: dict[str, Tool] = {
    "get_order": Tool("get_order", get_order, GetOrderArgs, ("read-only",)),
    "get_subscription": Tool("get_subscription", get_subscription, GetSubscriptionArgs, ("read-only",)),
    "escalate": Tool("escalate", escalate, EscalateArgs, ("idempotent",)),
}
