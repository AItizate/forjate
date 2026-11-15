"""file_claim: create one claim at the carrier [idempotent, requires approval token]"""
from pydantic import BaseModel

from ..toolkit import ApprovalRequired


class FileClaimArgs(BaseModel):
    tracking: str


class FileClaimResult(BaseModel):
    claim_id: str
    duplicate: bool


def file_claim(args: FileClaimArgs, *, approval_token: str, idempotency_key: str, timeout_s: float = 10.0) -> FileClaimResult:
    if not approval_token:
        raise ApprovalRequired("file_claim needs the clerk's approval token")
    # SEAM claim-filing: POST /claims at the carrier with the idempotency key (backlog, Walk)
    raise NotImplementedError("backlog ticket T-claim-filing")
