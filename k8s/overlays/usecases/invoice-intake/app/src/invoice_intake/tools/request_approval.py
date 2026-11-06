"""request_approval: create one approval request for the AP clerk with the fields and the source reference
[idempotent, requires deterministic check result, max 1 per invoice version]

A Walk tool. Crawl's write_actions is none, so the judge refuses it there. Past the judge it raises NotImplementedError: the review
queue behind it is review-api, which is not generated at Crawl (scaffold.yaml notes).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings
from ..policy import judge
from ..toolkit import OutOfPolicy, timed_call


class DeterministicCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check: str = Field(min_length=1)
    passed: bool
    invoice_version: int = Field(ge=1)


class RequestApprovalArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_key: str = Field(min_length=1, max_length=64)
    fields_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_object_key: str = Field(min_length=1)


class RequestApprovalResult(BaseModel):
    request_id: str
    duplicate: bool


def request_approval(args: RequestApprovalArgs, *, check_result: DeterministicCheck, idempotency_key: str, timeout_s: float = 10.0) -> RequestApprovalResult:
    settings = get_settings()
    verdict = judge("request_approval", write_actions=settings.write_actions, paused=lambda: False)
    with timed_call("request_approval", args, judge=verdict.decision, judge_reason=verdict.reason):
        if verdict.decision != "allow":
            raise OutOfPolicy(verdict.reason)
        if not idempotency_key or not check_result.check:
            raise OutOfPolicy("deterministic-check-result-required")
        raise NotImplementedError("request_approval writes to the review queue of review-api, which arrives with the Walk scaffold")
