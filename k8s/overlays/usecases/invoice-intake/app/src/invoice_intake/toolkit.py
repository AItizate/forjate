"""Shared pieces of the tool contract: typed errors, the approval token, the timed log line."""

from __future__ import annotations

import hashlib
import hmac

from .config import settings
from .logging import timed_call  # re-exported for the tools

__all__ = ["ToolError", "NotFound", "ApprovalRequired", "approval_token_for", "approval_valid", "timed_call"]


class ToolError(Exception):
    """A typed error the model can act on; never an empty result."""


class NotFound(ToolError):
    pass


class ApprovalRequired(ToolError):
    """The write tool was called without a valid approval token for this item."""


def approval_token_for(invoice_id: str, *, secret: str | None = None) -> str:
    """The token the ux checkpoint issues: HMAC over the invoice id. Bound to one item."""
    key = (secret if secret is not None else settings().approval_secret).encode()
    return hmac.new(key, invoice_id.encode(), hashlib.sha256).hexdigest()[:32]


def approval_valid(token: str, invoice_id: str, *, secret: str | None = None) -> bool:
    return bool(token) and hmac.compare_digest(token, approval_token_for(invoice_id, secret=secret))
