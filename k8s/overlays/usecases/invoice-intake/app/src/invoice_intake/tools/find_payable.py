"""find_payable: read an existing payable by supplier id and invoice number from Odoo [read-only]"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..toolkit import call_system, timed_call


class FindPayableArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: str = Field(min_length=1, max_length=128)
    invoice_number: str = Field(min_length=1, max_length=64)


class FindPayableResult(BaseModel):
    posting_id: str
    supplier_id: str
    invoice_number: str


def find_payable(args: FindPayableArgs, *, timeout_s: float = 10.0) -> FindPayableResult:
    """No such payable raises ToolNotFound, never an empty result."""
    with timed_call("find_payable", args):
        response = call_system("odoo", "find_payable", "GET", "/api/payables", timeout_s=timeout_s, params=args.model_dump())
        body = response.json()
        return FindPayableResult(posting_id=body["posting_id"], supplier_id=body["supplier_id"], invoice_number=body["invoice_number"])
