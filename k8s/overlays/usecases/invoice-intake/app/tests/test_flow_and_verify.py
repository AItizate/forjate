"""The whole Crawl flow in memory, and the verify script's checks against it, including that they fail when the state is wrong."""

from __future__ import annotations

from invoice_intake import worker
from invoice_intake.generator import verify_set
from invoice_intake.pipeline import run_pass
from invoice_intake.seed import run_once
from invoice_intake.verify import A_EXIT, A_KILL, A_LOGS, A_MATCH, A_STUB, ASSERTIONS, CHECKS, Harness, run_checks


class Killed(BaseException):
    """Stands in for SIGKILL: nothing in the pass can catch it."""


def harness(env) -> Harness:
    def rerun_main() -> str:
        worker.run_job(env.ctx(worker_passes=1, worker_from_start=True))
        env.ctx()
        return ""

    def kill_and_rerun(scope: str) -> tuple[bool, str]:
        ctx = env.ctx(scope=scope, source_scope=env.settings.scope, worker_passes=1)
        count = {"n": 0}
        real_finish = env.store.finish_item

        def finish(*args, **kwargs):
            count["n"] += 1
            if count["n"] == 4:
                raise Killed()
            return real_finish(*args, **kwargs)

        env.store.finish_item = finish
        try:
            run_pass(ctx, from_start=False)
            mid_pass = False
        except Killed:
            mid_pass = True
        finally:
            env.store.finish_item = real_finish
        worker.run_job(ctx)
        worker.run_job(ctx)
        env.ctx()
        return mid_pass, ""

    env.ctx()
    return Harness(env.settings, env.store, env.objects, rerun_main, kill_and_rerun)


def full_run(env) -> None:
    run_once(env.settings, env.objects)
    worker.run_job(env.ctx())


def test_the_verify_script_passes_on_a_correct_run(env, capsys) -> None:
    full_run(env)
    assert run_checks(harness(env)) == 0
    out = capsys.readouterr().out
    for assertion in ASSERTIONS:
        assert f"[PASS] {assertion}" in out
    assert "KPI straight_through_rate=0.1667" in out
    assert "EVAL dead_letter_rate=0.2" in out and "EVAL replay_wrong_amount_count=0" in out


def test_every_exception_lands_with_its_reason(env) -> None:
    full_run(env)
    rows = {(r["message_id"], r["attachment_index"]): r for r in env.store.items(env.settings.scope)}
    for item in verify_set().items:
        row = rows[(item.message_id, item.attachment_index)]
        assert row["reason"] == item.reason, item.ref
        assert (row["state"] == "recommended") == (item.reason is None), item.ref


def test_the_second_pass_changes_nothing_and_never_reparses(env) -> None:
    full_run(env)
    calls = env.parser.calls
    passes = env.store.passes(env.settings.scope)
    assert (passes[0]["rows_added"], passes[0]["review_added"]) == (12, 10)
    assert (passes[1]["rows_added"], passes[1]["states_changed"], passes[1]["review_added"]) == (0, 0, 0) and passes[1]["from_start"]
    assert env.parser.calls == calls == 12


def test_nothing_is_written_to_the_odoo_double(env) -> None:
    full_run(env)
    assert env.odoo_kv.counter("odoo.reads") > 0 and env.odoo_kv.counter("odoo.write_attempts") == 0


def _failed(env, capsys) -> tuple[int, str]:
    code = run_checks(harness(env))
    return code, capsys.readouterr().out


def test_verify_fails_naming_a_write_on_the_double(env, capsys) -> None:
    full_run(env)
    env.odoo_kv.incr("odoo.write_attempts")
    code, out = _failed(env, capsys)
    assert code == 1 and f"[FAIL] {A_STUB}" in out and f"[FAIL] {A_EXIT}" in out


def test_verify_fails_when_a_clean_item_lost_its_recommendation(env, capsys) -> None:
    full_run(env)
    row = next(r for r in env.store.t["items"].values() if r["state"] == "recommended")
    row["recommendation"] = {"text": "x", "po_number": "PUR-1"}
    code, out = _failed(env, capsys)
    assert code == 1 and f"[FAIL] {A_MATCH}" in out


def test_verify_fails_on_a_bank_number_in_a_log(env, capsys) -> None:
    full_run(env)
    from invoice_intake.generator import known_bank_strings
    env.store.append_trace(env.settings.scope, [f"oops {known_bank_strings()[0]}"])
    code, out = _failed(env, capsys)
    assert code == 1 and f"[FAIL] {A_LOGS}" in out


def test_verify_fails_when_the_kill_did_not_land(env, capsys) -> None:
    full_run(env)
    h = harness(env)
    h.kill_and_rerun = lambda scope: (False, "")
    assert run_checks(h) == 1
    assert f"[FAIL] {A_KILL}" in capsys.readouterr().out


def test_an_unexpected_lookup_failure_is_named(env, capsys) -> None:
    full_run(env)
    review = next(iter(env.store.t["review"].values()))
    review["reason"] = "lookup-failed"
    code, out = _failed(env, capsys)
    assert code == 1 and "Odoo double unreachable" in out


def test_a_double_down_is_lookup_failed_not_a_false_mismatch(seeded, monkeypatch) -> None:
    from invoice_intake import pipeline
    from invoice_intake.toolkit import ToolUnavailable

    def down(*_a, **_k):
        raise ToolUnavailable("odoo unreachable")

    monkeypatch.setattr(pipeline, "lookup_po", down)
    run_pass(seeded.ctx(), from_start=True)
    reasons = {r["reason"] for r in seeded.store.items(seeded.settings.scope)}
    assert "lookup-failed" in reasons and "mismatch" not in reasons


def test_checks_cover_every_assertion_in_order() -> None:
    assert tuple(a for a, _ in CHECKS) + (A_EXIT,) == ASSERTIONS
