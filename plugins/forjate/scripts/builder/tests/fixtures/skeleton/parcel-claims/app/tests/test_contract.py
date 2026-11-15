import pytest

from parcel_claims.toolkit import ApprovalRequired
from parcel_claims.tools.file_claim import FileClaimArgs, file_claim


def test_file_claim_refuses_without_token():
    with pytest.raises(ApprovalRequired):
        file_claim(FileClaimArgs(tracking="T1"), approval_token="", idempotency_key="k")
