"""The golden set through the replay double (G-AI-1). It proves the code path with every output guardrail exercised on labelled items, and says
nothing about the model: invoice-intake-eval on the real model is what G-Q-2 reads."""

from __future__ import annotations

import json

import pytest

from invoice_intake.eval_run import score
from invoice_intake.generator import golden_set
from invoice_intake.model import ModelReply
from invoice_intake.pipeline import run_pass
from invoice_intake.seed import deliver

pytestmark = pytest.mark.eval


def _run(env, model=None):
    deliver(golden_set(), "golden", env.objects, env.settings.scope, env.settings)
    ctx = env.ctx(mailbox="golden")
    if model:
        ctx.model = model
    run_pass(ctx, from_start=True)
    return score(golden_set(), env.store, env.settings.scope)


def test_the_set_has_the_records_shape() -> None:
    items = golden_set().items
    clean = [i for i in items if i.reason is None]
    assert len(items) == 50 and len(clean) == 40
    assert sum(i.kind == "digital" for i in clean) == 28 and sum(i.kind == "scanned" for i in clean) == 12
    assert golden_set().expected_kpi == 0.8


def test_the_double_reaches_the_ceiling_with_no_wrong_amount(env) -> None:
    results = _run(env)
    assert results["live_straight_through_rate"] == 0.8 and results["live_wrong_amount_count"] == 0
    assert results["live_exception_recall"] == 1.0 and results["live_document_accuracy"] == 1.0


class MisreadsAmounts:
    """A model that misreads every amount by a cent: the literal-source check has to catch all of them."""

    name = "misreads"

    def __init__(self, labels) -> None:
        self.labels = labels

    def extract(self, prompt_name, document_text, *, source_sha256, repair_hint=None):
        label = dict(self.labels[source_sha256])
        if label.get("amount"):
            whole, cents = label["amount"].split(".")
            label["amount"] = f"{whole}.{(int(cents) + 1) % 100:02d}"
        return ModelReply(json.dumps(label))


def test_a_misread_amount_never_reaches_a_recommendation(env) -> None:
    labels = {i.sha256: i.label for i in golden_set().items if i.label}
    results = _run(env, MisreadsAmounts(labels))
    assert results["live_wrong_amount_count"] == 0 and results["live_straight_through_rate"] == 0.0
    reasons = {r["reason"] for r in env.store.items(env.settings.scope)}
    assert "low-confidence" in reasons
