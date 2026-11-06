"""post_invoice: create one payable in Odoo [idempotent, requires approval token, max 1 per invoice]

A Walk tool. The approval token is verified before anything else, then the judge, then the lookup before create. At Crawl no token
can exist: the default verifier refuses everything, so nothing here can reach Odoo.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings
from ..policy import judge
from ..toolkit import ApprovalRequired, OutOfPolicy, PausedRefusal, ToolNotFound, call_system, timed_call
from .find_payable import FindPayableArgs, find_payable


class PostInvoiceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_key: str = Field(min_length=1, max_length=64)
    supplier_id: str = Field(min_length=1, max_length=128)
    invoice_number: str = Field(min_length=1, max_length=64)
    amount_cents: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    po_number: str = Field(min_length=1, max_length=64)


class PostInvoiceResult(BaseModel):
    posting_id: str
    duplicate: bool


@dataclass(frozen=True)
class ApprovalClaims:
    token_id: str
    reviewer: str
    fields_hash: str
    amount_cents: int


class TokenVerifier(Protocol):
    def verify(self, approval_token: str, args: PostInvoiceArgs) -> ApprovalClaims: ...


class NoIssuerAtCrawl:
    """Crawl has no review surface, so no token exists. The Walk verifier checks an Ed25519 signature with the public key
    (security record: asymmetric, review-api alone holds the private key); it arrives with review-api."""

    def verify(self, approval_token: str, args: PostInvoiceArgs) -> ApprovalClaims:
        raise ApprovalRequired("post_invoice needs the AP clerk's approval token for this invoice")


_verifier: TokenVerifier = NoIssuerAtCrawl()
_paused_reader: Callable[[], bool] | None = None


def configure(verifier: TokenVerifier | None = None, paused_reader: Callable[[], bool] | None = None) -> None:
    global _verifier, _paused_reader
    _verifier = verifier or NoIssuerAtCrawl()
    _paused_reader = paused_reader


def fields_hash(args: PostInvoiceArgs) -> str:
    return hashlib.sha256(json.dumps(args.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


def post_invoice(args: PostInvoiceArgs, *, approval_token: str, idempotency_key: str, timeout_s: float = 15.0) -> PostInvoiceResult:
    if not approval_token:
        raise ApprovalRequired("post_invoice needs the AP clerk's approval token for this invoice")
    claims = _verifier.verify(approval_token, args)
    verdict = judge("post_invoice", write_actions=get_settings().write_actions, paused=_paused_reader,
                    approved_fields_hash=claims.fields_hash, fields_hash=fields_hash(args),
                    approved_amount_cents=claims.amount_cents, amount_cents=args.amount_cents)
    with timed_call("post_invoice", args, judge=verdict.decision, judge_reason=verdict.reason, approval_token_id=claims.token_id, reviewer=claims.reviewer):
        if verdict.decision == "paused":
            raise PausedRefusal(verdict.reason)
        if verdict.decision != "allow":
            raise OutOfPolicy(verdict.reason)
        if not idempotency_key:
            raise OutOfPolicy("idempotency-key-required")
        try:
            existing = find_payable(FindPayableArgs(supplier_id=args.supplier_id, invoice_number=args.invoice_number))
            return PostInvoiceResult(posting_id=existing.posting_id, duplicate=True)
        except ToolNotFound:
            pass
        response = call_system("odoo", "post_invoice", "POST", "/api/payables", timeout_s=timeout_s,
                               json=args.model_dump(mode="json"), headers={"Idempotency-Key": idempotency_key})
        body = response.json()
        return PostInvoiceResult(posting_id=body["posting_id"], duplicate=bool(body.get("duplicate")))
