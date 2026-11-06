"""lookup_po: read one purchase order by exact number from Odoo [read-only]"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..domain import PurchaseOrder
from ..toolkit import call_system, timed_call


class LookupPoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    po_number: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")  # goes into a URL path: no slash, no leading dot


class LookupPoResult(BaseModel):
    purchase_order: PurchaseOrder


def lookup_po(args: LookupPoArgs, *, timeout_s: float = 10.0) -> LookupPoResult:
    """A number that does not exist raises ToolNotFound, never an empty result."""
    with timed_call("lookup_po", args):
        response = call_system("odoo", "lookup_po", "GET", f"/api/purchase-orders/{args.po_number}", timeout_s=timeout_s)
        return LookupPoResult(purchase_order=PurchaseOrder.model_validate(response.json()))
