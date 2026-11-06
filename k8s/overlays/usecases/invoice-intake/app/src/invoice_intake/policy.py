"""The policy judge: deterministic code before every write tool, no model. At Crawl write_actions is none: all refused.

Intent validation at Crawl is `schema` (each tool's argument model); this hook is the `policy-judge` the Walk records ask
for, in place from the first commit so the refusal is exercised in CI.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

ALLOWED_ACTIONS = ("request_approval", "post_invoice")


@dataclass(frozen=True)
class Verdict:
    decision: str  # allow | refuse | paused
    reason: str


def judge(
    tool_name: str, *, write_actions: str, paused: Callable[[], bool] | None = None,
    approved_fields_hash: str | None = None, fields_hash: str | None = None,
    approved_amount_cents: int | None = None, amount_cents: int | None = None,
) -> Verdict:
    if tool_name not in ALLOWED_ACTIONS:
        return Verdict("refuse", "action-not-allowed")
    if write_actions == "none":
        return Verdict("refuse", "stage-allows-no-write")
    if write_actions != "approval-required":
        return Verdict("refuse", "unknown-write-policy")
    if paused is None:
        return Verdict("refuse", "paused-state-unreadable")
    try:
        if paused():
            return Verdict("paused", "paused-state-set")
    except Exception:  # noqa: BLE001 - fails closed whatever went wrong
        return Verdict("refuse", "paused-state-unreadable")
    if tool_name == "post_invoice":
        if approved_fields_hash is None or approved_fields_hash != fields_hash:
            return Verdict("refuse", "fields-changed-after-approval")
        if approved_amount_cents is None or approved_amount_cents != amount_cents:
            return Verdict("refuse", "amount-changed-after-approval")
    return Verdict("allow", "within-policy")
