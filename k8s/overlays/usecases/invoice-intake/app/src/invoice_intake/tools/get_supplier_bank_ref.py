"""get_supplier_bank_ref: read the salted hash of a supplier's known bank account from Odoo, never the number [read-only]"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..toolkit import ToolError, call_system, timed_call


class GetSupplierBankRefArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._ &-]+$")


class GetSupplierBankRefResult(BaseModel):
    supplier_id: str
    bank_ref_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def get_supplier_bank_ref(args: GetSupplierBankRefArgs, *, timeout_s: float = 10.0) -> GetSupplierBankRefResult:
    """An answer that is not a hash is refused: the number itself never enters this process."""
    with timed_call("get_supplier_bank_ref", args):
        response = call_system("odoo", "get_supplier_bank_ref", "GET", f"/api/suppliers/{args.supplier_id}/bank-ref", timeout_s=timeout_s)
        try:
            return GetSupplierBankRefResult.model_validate(response.json())
        except ValueError as exc:
            raise ToolError("bank reference is not a salted hash") from exc
