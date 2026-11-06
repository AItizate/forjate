"""One test per execution bound (G-AI-4, G-Q-14), the approval-token refusal and the judge's verdicts. A bound in a prompt is not a bound."""

from __future__ import annotations

import json
import time
from dataclasses import replace

import pytest

from invoice_intake import config
from invoice_intake.model import ModelReply
from invoice_intake.pipeline import run_pass
from invoice_intake.policy import judge
from invoice_intake.toolkit import ApprovalRequired, Attempt, BoundExceeded, Bounds, OutOfPolicy, PausedRefusal
from invoice_intake.tools.post_invoice import ApprovalClaims, PostInvoiceArgs, configure, fields_hash, post_invoice
from invoice_intake.tools.request_approval import DeterministicCheck, RequestApprovalArgs, request_approval

from conftest import TEST_SETTINGS, TOKEN

BOUNDS = Bounds(max_steps=10, step_timeout_s=0.2, delegation_depth=0, budget_tokens=8000, max_model_calls=2)


def test_an_eleventh_step_stops() -> None:
    attempt = Attempt(BOUNDS)
    for _ in range(10):
        attempt.step("s", lambda: None)
    with pytest.raises(BoundExceeded) as info:
        attempt.step("eleventh", lambda: None)
    assert info.value.bound == "max_steps" and info.value.step == "eleventh"


def test_a_third_model_call_stops() -> None:
    attempt = Attempt(BOUNDS)
    attempt.model_call("extract", 10)
    attempt.model_call("repair", 10)
    with pytest.raises(BoundExceeded) as info:
        attempt.model_call("again", 10)
    assert info.value.bound == "max_model_calls"


def test_an_over_budget_request_stops() -> None:
    with pytest.raises(BoundExceeded) as info:
        Attempt(BOUNDS).model_call("extract", 8001)
    assert info.value.bound == "budget_tokens"


def test_a_timed_out_step_stops() -> None:
    with pytest.raises(BoundExceeded) as info:
        Attempt(BOUNDS).step("slow", lambda: time.sleep(1))
    assert info.value.bound == "step_timeout_s"


def test_delegation_depth_stops() -> None:
    with pytest.raises(BoundExceeded) as info:
        Attempt(BOUNDS, depth=1)
    assert info.value.bound == "delegation_depth"


def _reasons(env) -> dict[str, str]:
    return {r["message_id"]: (r["reason"], r["failed_step"]) for r in env.store.items(env.settings.scope)}


def test_breaching_a_bound_routes_the_invoice_to_the_clerk_with_reason_timeout(seeded) -> None:
    ctx = seeded.ctx(max_steps=3)
    run_pass(ctx, from_start=True)
    items = seeded.store.items(seeded.settings.scope)
    timed_out = [r for r in items if r["reason"] == "timeout"]
    assert timed_out and all(r["failed_step"] == "extract" for r in timed_out)
    assert {r["key"] for r in timed_out} <= {r["key"] for r in seeded.store.review(seeded.settings.scope)}


def test_an_over_budget_document_goes_to_the_clerk(seeded) -> None:
    run_pass(seeded.ctx(budget_tokens=5), from_start=True)
    assert "timeout" in {r["reason"] for r in seeded.store.items(seeded.settings.scope)}


class Slow:
    name = "slow"

    def extract(self, prompt_name, document_text, *, source_sha256, repair_hint=None):
        time.sleep(1)
        return ModelReply("{}")


def test_a_timed_out_model_step_goes_to_the_clerk_and_the_pass_moves_on(seeded) -> None:
    ctx = seeded.ctx(step_timeout_s=0.3)
    ctx.model = Slow()
    run_pass(ctx, from_start=True)
    items = seeded.store.items(seeded.settings.scope)
    assert len(items) == 12 and {r["failed_step"] for r in items if r["reason"] == "timeout"} == {"extract"}


class Invalid:
    name = "invalid"
    calls = 0

    def extract(self, prompt_name, document_text, *, source_sha256, repair_hint=None):
        Invalid.calls += 1
        return ModelReply(json.dumps({"document_type": "invoice", "amount": "not a number"}))


def test_schema_still_invalid_after_one_repair_is_low_confidence_with_two_calls_per_item(seeded) -> None:
    Invalid.calls = 0
    ctx = seeded.ctx()
    ctx.model = Invalid()
    run_pass(ctx, from_start=True)
    items = seeded.store.items(seeded.settings.scope)
    parsed = [r for r in items if r["reason"] == "low-confidence"]
    assert len(parsed) == 11 and Invalid.calls == 22


ARGS = PostInvoiceArgs(invoice_key="k", supplier_id="DE810000000", invoice_number="INV-1", amount_cents=100, currency="EUR", po_number="PUR-50000")


class Approves:
    def __init__(self, args: PostInvoiceArgs, *, amount: int | None = None) -> None:
        self.claims = ApprovalClaims("t1", "clerk", fields_hash(args), args.amount_cents if amount is None else amount)

    def verify(self, approval_token, args):
        if approval_token != "good":
            raise ApprovalRequired("token refused")
        return self.claims


@pytest.fixture
def walk(env):
    config.set_settings(replace(TEST_SETTINGS, write_actions="approval-required", stage="walk"))
    yield env
    configure()


def _writes(env) -> int:
    return env.odoo_kv.counter("odoo.write_attempts")


@pytest.mark.parametrize("token", ["", "anything"])
def test_post_invoice_is_refused_at_crawl_before_any_io(env, token: str) -> None:
    configure()
    reads = env.odoo_kv.counter("odoo.reads")
    with pytest.raises(ApprovalRequired):
        post_invoice(ARGS, approval_token=token, idempotency_key="k")
    assert _writes(env) == 0 and env.odoo_kv.counter("odoo.reads") == reads


def test_post_invoice_with_no_token_never_asks_the_verifier(walk) -> None:
    configure(Approves(ARGS), paused_reader=lambda: False)
    with pytest.raises(ApprovalRequired):
        post_invoice(ARGS, approval_token="", idempotency_key="k")
    assert _writes(walk) == 0


def test_a_bad_token_is_refused(walk) -> None:
    configure(Approves(ARGS), paused_reader=lambda: False)
    with pytest.raises(ApprovalRequired):
        post_invoice(ARGS, approval_token="forged", idempotency_key="k")
    assert _writes(walk) == 0


def test_a_changed_amount_is_refused(walk) -> None:
    configure(Approves(ARGS), paused_reader=lambda: False)
    changed = ARGS.model_copy(update={"amount_cents": 999})
    with pytest.raises(OutOfPolicy):
        post_invoice(changed, approval_token="good", idempotency_key="k")
    assert _writes(walk) == 0


def test_the_paused_state_is_a_typed_refusal_even_with_a_live_token(walk) -> None:
    configure(Approves(ARGS), paused_reader=lambda: True)
    with pytest.raises(PausedRefusal):
        post_invoice(ARGS, approval_token="good", idempotency_key="k")
    assert _writes(walk) == 0


def test_an_unreadable_paused_state_fails_closed(walk) -> None:
    def broken() -> bool:
        raise OSError("store down")
    configure(Approves(ARGS), paused_reader=broken)
    with pytest.raises(OutOfPolicy):
        post_invoice(ARGS, approval_token="good", idempotency_key="k")
    assert _writes(walk) == 0


def test_a_repeated_idempotency_key_creates_no_second_payable(walk) -> None:
    configure(Approves(ARGS), paused_reader=lambda: False)
    first = post_invoice(ARGS, approval_token="good", idempotency_key="k")
    second = post_invoice(ARGS, approval_token="good", idempotency_key="k")
    assert first.posting_id == second.posting_id and second.duplicate and _writes(walk) == 1


def test_the_credential_of_another_tool_cannot_write(walk, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ODOO_POST_INVOICE_TOKEN", "the-post-credential")
    configure(Approves(ARGS), paused_reader=lambda: False)
    with pytest.raises(Exception):
        post_invoice(ARGS, approval_token="good", idempotency_key="k")
    assert walk.odoo_kv.counter("odoo.write_refused") == 1
    assert TOKEN != "the-post-credential"


def test_request_approval_is_refused_at_crawl() -> None:
    args = RequestApprovalArgs(invoice_key="k", fields_hash="0" * 64, source_object_key="o")
    with pytest.raises(OutOfPolicy):
        request_approval(args, check_result=DeterministicCheck(check="match", passed=True, invoice_version=1), idempotency_key="k")


@pytest.mark.parametrize("action", ["correct_bill", "cancel_bill", "pay_bill", "post_invoice_v2"])
def test_any_other_action_is_refused(action: str) -> None:
    assert judge(action, write_actions="approval-required", paused=lambda: False).decision == "refuse"


def test_a_stage_with_no_writes_refuses_every_write() -> None:
    assert judge("post_invoice", write_actions="none", paused=lambda: False).reason == "stage-allows-no-write"
