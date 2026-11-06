"""invoice-intake-verify: the quality record's verify_assertions, one named check each, in order, on the replay double.

Prints [PASS] or [FAIL] per assertion, the KPI line and the EVAL lines, and exits non-zero on any miss with the assertion named. A KPI here
is a routing fact of the 12-item mix and not the CFO's number: that comes from invoice-intake-eval on the real model.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .config import Settings, get_settings
from .domain import ESCALATION_FIELDS, parse_amount
from .generator import SeedSet, field_values, known_bank_strings, verify_set
from .logs import add_sink, emit
from .objects import BUCKETS, INBOX, PARSED, MinioObjects, ObjectStore
from .readiness import route_checks, wait_ready
from .seed import run_once as seed_run_once
from .store import PgStore, Store
from .toolkit import call_system

OTHER_SCOPE = "not-this-project"
UNEXPECTED = {"lookup-failed": "Odoo double unreachable", "timeout": "a step passed an execution bound"}
PROVIDER_ENV = ("OPENAI_API_KEY", "OPENAI_API_BASE", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY", "LITELLM_API_KEY")

A_COUNTS = "counts: all 12 seeded attachments hold a key and a terminal state"
A_IDEMPOTENCY = "idempotency: the run Job's second pass, from the start of the mailbox double, adds 0 rows, changes 0 states and opens 0 review_queue items"
A_SEED = "seed idempotency: a second run of the seed Job delivers 0 new messages and leaves the purchase orders unchanged"
A_CORRECT = "correctness: extracted supplier, amount, date and PO number equal the seed manifest on the items that reach the model; wrong_amount_count = 0"
A_MATCH = "match: both clean items carry a recommendation against the right purchase order and no review_queue row"
A_MISMATCH = "mismatch: the amount, supplier and PO number items are in review_queue with reason=mismatch"
A_ROUTING = "routing: the missing PO, partial delivery and bank details items carry reason=po-missing, partial-delivery and bank-details-differ"
A_DUPLICATE = "duplicate: the re-send carries reason=duplicate, links the earlier item and counts no second result"
A_DEAD = "dead letter: the corrupt PDF and the non-invoice carry reason=parse-failed, told apart by the failed step; rate 2 of 10 exception items; no timeout or lookup-failed row"
A_LOW = "low confidence: the degraded scan carries reason=low-confidence under the UX record's rule (schema still invalid after one repair, or an amount, date or PO number not found literally in the source text), with the amount named, and never a wrong amount"
A_PARSER = "parser: a parsed output sits in the parsed bucket for each parseable input"
A_STUB = "stub: the Odoo double received reads and 0 write calls (G-Q-3)"
A_REASONS = "expected exceptions by reason equal the seed manifest exactly; unexpected exceptions by reason are zero (lookup-failed, timeout, and parse-failed or low-confidence beyond the seeded items), and a failure names the dependency, for example 'Odoo double unreachable'"
A_KILL = "killing the worker Job mid-pass and rerunning it, then rerunning it once more, leaves the same counts as a clean pass (G-ARCH-1)"
A_SCOPE = "a read under a scope tag other than this project's returns nothing from working, episodic and artifact state (G-DS-2)"
A_UX = "each of the 10 exception items carries every escalation_context field in the UX record's order with the recommendation last, withheld on the changed-bank item, and the log carries ids, reasons and the KPI line and no field value (G-UX-1, review_mode evidence-first)"
A_ENDPOINT = "the configured model endpoint is an in-namespace service and no external model provider appears in the client configuration (G-SEC-2; under the double this is configuration evidence, the traffic evidence comes from invoice-intake-eval)"
A_LOGS = "workload logs carry the data class and none of the seed's bank account numbers, matched by the seed's known synthetic values in IBAN and non-IBAN formats (G-SEC-4, pack:regulated-corp#SECBASE item 5)"
A_KPI = "prints KPI straight_through_rate=<items matched with no exception / 12 seeded attachments> and asserts it equals the seed manifest's value exactly; on this mix it is 0.17 to 0.25 by design, a routing fact and not the CFO's number"
A_EXIT = "exits non-zero on any miss with the failing assertion named; no catch-all exit 0"

ASSERTIONS = (A_COUNTS, A_IDEMPOTENCY, A_SEED, A_CORRECT, A_MATCH, A_MISMATCH, A_ROUTING, A_DUPLICATE, A_DEAD, A_LOW, A_PARSER, A_STUB,
              A_REASONS, A_KILL, A_SCOPE, A_UX, A_ENDPOINT, A_LOGS, A_KPI, A_EXIT)


class CheckFailed(Exception):
    """The reason a check failed: counts, ids and dependency names, never a field value."""


def require(condition: object, reason: str) -> None:
    if not condition:
        raise CheckFailed(reason)


@dataclass
class Harness:
    """What the checks do beyond reading: real subprocesses in the Job, in-process stand-ins in the tests."""

    settings: Settings
    store: Store
    objects: ObjectStore
    rerun_main: Callable[[], str]
    kill_and_rerun: Callable[[str], tuple[bool, str]]
    seed: SeedSet = field(default_factory=verify_set)
    lines: list[str] = field(default_factory=list)
    worker_output: list[str] = field(default_factory=list)

    def say(self, line: str) -> None:
        self.lines.append(line)
        print(line, flush=True)


def _rows_by_ref(h: Harness) -> dict[str, dict]:
    rows = {(r["message_id"], r["attachment_index"]): r for r in h.store.items(h.settings.scope)}
    out = {}
    for item in h.seed.items:
        row = rows.get((item.message_id, item.attachment_index))
        if row:
            out[item.ref] = row
    return out


def _review_by_ref(h: Harness, rows: dict[str, dict]) -> dict[str, dict]:
    review = {r["key"]: r for r in h.store.review(h.settings.scope)}
    return {ref: review[row["key"]] for ref, row in rows.items() if row["key"] in review}


def _snapshot(store: Store, scope: str) -> tuple:
    items = sorted((r["key"], r["state"], r["reason"], r["failed_step"]) for r in store.items(scope))
    return items, sorted(r["key"] for r in store.review(scope)), sorted(r["key"] for r in store.events(scope))


def _reason_counts(store: Store, scope: str) -> Counter:
    return Counter(r["reason"] for r in store.review(scope))


def check_counts(h: Harness) -> None:
    rows = _rows_by_ref(h)
    all_rows = h.store.items(h.settings.scope)
    require(len(all_rows) == 12, f"{len(all_rows)} items hold a key, expected 12")
    require(len(rows) == 12, f"{len(rows)} of 12 seeded attachments found")
    open_items = [r["key"][:12] for r in all_rows if r["state"] not in ("recommended", "in_review")]
    require(not open_items, f"not terminal: {open_items}")


def check_idempotency(h: Harness) -> None:
    passes = [p for p in h.store.passes(h.settings.scope) if p["finished"]]
    require(len(passes) >= 2, f"{len(passes)} finished passes recorded, expected 2")
    second = passes[-1]
    require(second["from_start"], "the last pass did not start from the start of the mailbox double")
    require(second["items_seen"] == 12, f"the second pass saw {second['items_seen']} items, expected 12")
    require((second["rows_added"], second["states_changed"], second["review_added"]) == (0, 0, 0),
            f"second pass added {second['rows_added']} rows, changed {second['states_changed']} states, opened {second['review_added']} review items")
    before = _snapshot(h.store, h.settings.scope)
    h.worker_output.append(h.rerun_main())
    require(_snapshot(h.store, h.settings.scope) == before, "invoking the run step again changed state")


def _odoo_stats(h: Harness) -> dict:
    return call_system("odoo", None, "GET", "/_double/stats", timeout_s=30.0, token=h.settings.admin_token).json()


def check_seed(h: Harness) -> None:
    before = _odoo_stats(h)
    counts = seed_run_once(h.settings, h.objects)
    after = _odoo_stats(h)
    require(counts["delivered"] == 0, f"a second seed run delivered {counts['delivered']} new messages")
    require(before["po_checksum"] == after["po_checksum"], "the purchase orders changed")
    require(after["purchase_orders"] == 500, f"{after['purchase_orders']} purchase orders, expected 500")


def _extractions(h: Harness, rows: dict[str, dict]) -> dict[str, dict | None]:
    events = {e["key"]: e for e in h.store.events(h.settings.scope)}
    return {ref: (events.get(row["key"]) or {}).get("extraction") for ref, row in rows.items()}


def wrong_amounts(h: Harness) -> int:
    rows = _rows_by_ref(h)
    extractions = _extractions(h, rows)
    wrong = 0
    for item in h.seed.items:
        got = extractions.get(item.ref)
        if item.label and item.label.get("amount") and got and rows[item.ref]["state"] == "recommended":
            wrong += parse_amount(got.get("amount")) != parse_amount(item.label["amount"])
    return wrong


def check_correctness(h: Harness) -> None:
    rows = _rows_by_ref(h)
    extractions = _extractions(h, rows)
    differing = []
    for item in h.seed.items:
        if item.label is None:
            continue
        got = extractions.get(item.ref)
        require(got is not None, f"{item.ref} reached the model and has no extraction")
        for name in ("supplier", "date", "po_number"):
            if got.get(name) != item.label.get(name):
                differing.append(f"{item.ref}:{name}")
        if parse_amount(got.get("amount")) != parse_amount(item.label.get("amount")):
            differing.append(f"{item.ref}:amount")
    require(not differing, f"differs from the manifest: {differing}")
    wrong = wrong_amounts(h)
    require(wrong == 0, f"wrong_amount_count = {wrong}")


def check_match(h: Harness) -> None:
    rows = _rows_by_ref(h)
    review = _review_by_ref(h, rows)
    for item in h.seed.items:
        if item.reason is None:
            row = rows[item.ref]
            require(row["state"] == "recommended", f"{item.ref} is {row['state']} with reason {row['reason']} at step {row['failed_step']}")
            require((row["recommendation"] or {}).get("po_number") == item.po_number, f"{item.ref} recommends another purchase order")
            require(item.ref not in review, f"{item.ref} has a review_queue row")


def _expect_reason(h: Harness, refs: list[str], reason_of: Callable[[str], str]) -> None:
    rows = _rows_by_ref(h)
    review = _review_by_ref(h, rows)
    for ref in refs:
        require(ref in review, f"{ref} is not in review_queue (state {rows[ref]['state'] if ref in rows else 'absent'})")
        require(review[ref]["reason"] == reason_of(ref), f"{ref} has reason={review[ref]['reason']}, expected {reason_of(ref)}")


def check_mismatch(h: Harness) -> None:
    _expect_reason(h, ["amount-mismatch", "supplier-mismatch", "po-number-mismatch"], lambda _: "mismatch")


def check_routing(h: Harness) -> None:
    expected = {"missing-po": "po-missing", "partial-delivery": "partial-delivery", "changed-bank-details": "bank-details-differ"}
    _expect_reason(h, list(expected), expected.__getitem__)


def check_duplicate(h: Harness) -> None:
    rows = _rows_by_ref(h)
    _expect_reason(h, ["byte-identical-resend"], lambda _: "duplicate")
    review = _review_by_ref(h, rows)
    require(review["byte-identical-resend"]["linked_key"] == rows["clean-digital"]["key"], "the re-send does not link the earlier item")
    require(rows["byte-identical-resend"]["recommendation"] is None, "the re-send counted a second result")
    recommended = [r for r in rows.values() if r["state"] == "recommended"]
    require(len(recommended) == 2, f"{len(recommended)} results counted, expected 2")


def dead_letter_rate(h: Harness) -> float:
    counts = _reason_counts(h.store, h.settings.scope)
    total = sum(counts.values())
    return round(counts["parse-failed"] / total, 4) if total else 0.0


def check_dead_letter(h: Harness) -> None:
    rows = _rows_by_ref(h)
    review = _review_by_ref(h, rows)
    _expect_reason(h, ["corrupt-pdf", "not-an-invoice"], lambda _: "parse-failed")
    require(review["corrupt-pdf"]["failed_step"] == "parse", f"corrupt PDF failed at {review['corrupt-pdf']['failed_step']}")
    require(review["not-an-invoice"]["failed_step"] == "extract", f"non-invoice failed at {review['not-an-invoice']['failed_step']}")
    counts = _reason_counts(h.store, h.settings.scope)
    require(counts["parse-failed"] == 2 and sum(counts.values()) == 10, f"dead letters {counts['parse-failed']} of {sum(counts.values())} exception items")
    require(dead_letter_rate(h) < 0.25, "dead-letter rate at or above 25%")
    for reason in ("timeout", "lookup-failed"):
        require(counts[reason] == 0, f"{counts[reason]} {reason} row(s): {UNEXPECTED[reason]}")


def check_low_confidence(h: Harness) -> None:
    rows = _rows_by_ref(h)
    _expect_reason(h, ["degraded-scan"], lambda _: "low-confidence")
    review = _review_by_ref(h, rows)["degraded-scan"]
    require("amount" in review["fields"], f"fields named: {review['fields']}")
    require(rows["degraded-scan"]["state"] != "recommended", "the degraded scan was recommended")


def check_parser(h: Harness) -> None:
    rows = _rows_by_ref(h)
    scope = h.settings.scope
    for item in h.seed.items:
        key = rows[item.ref]["key"]
        expected = item.kind != "corrupt"
        present = h.objects.get(PARSED, f"{scope}/{key}.json") is not None
        require(present == expected, f"{item.ref}: parsed output {'missing' if expected else 'present for an unparseable input'}")


def check_stub(h: Harness) -> None:
    stats = _odoo_stats(h)
    require(stats["reads"] > 0, "the Odoo double received no reads")
    require(stats["write_attempts"] == 0, f"the Odoo double received {stats['write_attempts']} write calls")


def check_reasons(h: Harness) -> None:
    got = _reason_counts(h.store, h.settings.scope)
    expected = Counter(h.seed.expected_reasons)
    for reason, dependency in UNEXPECTED.items():
        require(got[reason] == 0, f"{got[reason]} unexpected reason={reason}: {dependency}")
    if got["parse-failed"] > expected["parse-failed"]:
        raise CheckFailed(f"{got['parse-failed']} parse-failed against {expected['parse-failed']} seeded: docling")
    if got["low-confidence"] > expected["low-confidence"]:
        raise CheckFailed(f"{got['low-confidence']} low-confidence against {expected['low-confidence']} seeded: docling OCR or the literal-source check")
    require(got == expected, f"by reason {dict(got)}, the manifest says {dict(expected)}")


def check_kill(h: Harness) -> None:
    scope = f"{h.settings.scope}-killtest"
    h.store.drop_scope(scope)
    for bucket in BUCKETS:
        h.objects.delete_prefix(bucket, f"{scope}/")
    try:
        killed_mid_pass, output = h.kill_and_rerun(scope)
        h.worker_output.append(output)
        require(killed_mid_pass, "the kill did not land mid-pass, so this proves nothing")
        clean = sorted((r["key"], r["state"], r["reason"], r["failed_step"]) for r in h.store.items(h.settings.scope))
        rerun = sorted((r["key"], r["state"], r["reason"], r["failed_step"]) for r in h.store.items(scope))
        require(len(rerun) == 12, f"{len(rerun)} items after the reruns, expected 12")
        require(clean == rerun, "the counts after a kill and two reruns differ from a clean pass")
        require(_reason_counts(h.store, scope) == _reason_counts(h.store, h.settings.scope), "review_queue differs from a clean pass")
    finally:
        h.store.drop_scope(scope)
        for bucket in BUCKETS:
            h.objects.delete_prefix(bucket, f"{scope}/")


def check_scope(h: Harness) -> None:
    store = h.store
    for name, rows in (("items", store.items(OTHER_SCOPE)), ("review_queue", store.review(OTHER_SCOPE)), ("events", store.events(OTHER_SCOPE)), ("run_trace", store.trace(OTHER_SCOPE))):
        require(not rows, f"{name} returned {len(rows)} rows under another scope tag")
    for bucket in BUCKETS:
        keys = h.objects.list_keys(bucket, f"{OTHER_SCOPE}/")
        require(not keys, f"bucket {bucket} returned {len(keys)} objects under another scope tag")
    require(h.objects.list_keys(INBOX, f"{h.settings.scope}/"), "the inbox bucket holds nothing under this scope, so the read proved nothing")


def _log_lines(h: Harness) -> list[str]:
    lines = list(h.store.trace(h.settings.scope))
    for output in h.worker_output:
        lines += output.splitlines()
    return lines + list(h.lines)


def check_ux(h: Harness) -> None:
    rows = _rows_by_ref(h)
    review = _review_by_ref(h, rows)
    exceptions = [item for item in h.seed.items if item.reason]
    require(len(exceptions) == 10, f"{len(exceptions)} exception items in the manifest")
    for item in exceptions:
        require(item.ref in review, f"{item.ref} has no review row")
        context = review[item.ref]["context"]
        names = tuple(entry["field"] for entry in context)
        require(names == ESCALATION_FIELDS, f"{item.ref}: escalation context out of order")
        values = {entry["field"]: entry["value"] for entry in context}
        require(values["reason"] == item.reason, f"{item.ref}: context reason {values['reason']}")
        require(item.ref != "changed-bank-details" or values["recommendation"] == "withheld", "the recommendation is not withheld on the changed-bank item")
    require(rows["changed-bank-details"]["recommendation"].get("withheld") is True, "the changed-bank row does not record the recommendation as withheld")
    forbidden = field_values(h.seed)
    hits = [v for v in forbidden if any(v in line for line in _log_lines(h))]
    require(not hits, f"{len(hits)} field value(s) in the logs")


def check_endpoint(h: Harness) -> None:
    s = h.settings
    allowed_suffix = ".svc.cluster.local"
    namespace = f".uc-{s.scope}{allowed_suffix}"
    for name, url in (("OLLAMA_URL", s.ollama_url), ("DOCLING_URL", s.docling_url), ("ODOO_URL", s.odoo_url), ("MAILBOX_URL", s.mailbox_url)):
        host = urlparse(url).hostname or ""
        require("." not in host or host.endswith(namespace), f"{name} points outside the namespace: {host}")
    require(s.model_id.startswith("ollama/"), f"the configured model is not served in-cluster: {s.model_id}")
    require(s.model_mode in ("replay", "rules"), f"the verify Job runs MODEL_MODE={s.model_mode}; the Crawl gate runs the double")
    present = [name for name in PROVIDER_ENV if os.environ.get(name)]
    require(not present, f"provider configuration present: {present}")


def check_logs(h: Harness) -> None:
    lines = _log_lines(h)
    classified = [line for line in lines if f"data_class={h.settings.data_class}" in line]
    require(classified, "no log line carries the data class")
    hits = [v for v in known_bank_strings() if any(v in line for line in lines)]
    require(not hits, f"{len(hits)} seeded bank number(s) in the logs")


def check_kpi(h: Harness) -> None:
    items = h.store.items(h.settings.scope)
    matched = sum(1 for r in items if r["state"] == "recommended")
    value = matched / 12
    h.say(f"KPI straight_through_rate={value:.4f}")
    require(abs(value - h.seed.expected_kpi) < 1e-9, f"rate {value:.4f}, the manifest says {h.seed.expected_kpi:.4f}")


CHECKS: tuple[tuple[str, Callable[[Harness], None]], ...] = (
    (A_COUNTS, check_counts), (A_IDEMPOTENCY, check_idempotency), (A_SEED, check_seed), (A_CORRECT, check_correctness), (A_MATCH, check_match),
    (A_MISMATCH, check_mismatch), (A_ROUTING, check_routing), (A_DUPLICATE, check_duplicate), (A_DEAD, check_dead_letter), (A_LOW, check_low_confidence),
    (A_PARSER, check_parser), (A_STUB, check_stub), (A_REASONS, check_reasons), (A_KILL, check_kill), (A_SCOPE, check_scope), (A_UX, check_ux),
    (A_ENDPOINT, check_endpoint), (A_LOGS, check_logs), (A_KPI, check_kpi),
)


def run_checks(h: Harness) -> int:
    """Every check runs, a failure in one never hides another, and any exception is a [FAIL]. There is no catch-all exit 0."""
    rows = _rows_by_ref(h)
    for item in h.seed.items:
        row = rows.get(item.ref)
        h.say(f"ITEM {item.ref} id={row['key'][:12] if row else 'none'} state={row['state'] if row else 'absent'} "
              f"reason={row['reason'] if row else 'none'} step={row['failed_step'] if row else 'none'}")
    failed = 0
    for assertion, check in CHECKS:
        try:
            check(h)
        except CheckFailed as exc:
            failed += 1
            h.say(f"[FAIL] {assertion}")
            h.say(f"       why: {exc}")
        except Exception as exc:  # noqa: BLE001 - an unexpected error is a failed assertion, named by its type only
            failed += 1
            h.say(f"[FAIL] {assertion}")
            h.say(f"       why: {type(exc).__name__}, {str(exc)[:160]}")
        else:
            h.say(f"[PASS] {assertion}")
    h.say(f"[{'FAIL' if failed else 'PASS'}] {A_EXIT}")
    if failed:
        h.say(f"verify: {failed} assertion(s) failed")
        return 1
    h.say(f"EVAL replay_wrong_amount_count={wrong_amounts(h)}")
    h.say(f"EVAL pipeline_duplicates={_reason_counts(h.store, h.settings.scope)['duplicate'] - 1}")
    h.say(f"EVAL dead_letter_rate={dead_letter_rate(h)}")
    h.say("EVAL unexpected_exceptions=0")
    h.say("verify: all assertions passed; this run proves routing on the replay double, not the model")
    return 0


# ---------------------------------------------------------------- the real harness: the worker as a process
def _worker_env(**overrides: str) -> dict[str, str]:
    return {**os.environ, "WORKLOAD": "worker", "READY_TIMEOUT_S": "60", **overrides}


def _run_worker(env: dict[str, str], timeout_s: float = 240.0) -> str:
    result = subprocess.run([sys.executable, "-m", "invoice_intake.worker"], env=env, capture_output=True, text=True, timeout=timeout_s, check=False)
    if result.returncode != 0:
        raise CheckFailed(f"the worker exited {result.returncode}")
    return result.stdout


def _real_rerun_main() -> str:
    return _run_worker(_worker_env(WORKER_PASSES="1", WORKER_FROM_START="1"))


def _real_kill_and_rerun(settings: Settings, store: Store) -> Callable[[str], tuple[bool, str]]:
    def run(scope: str) -> tuple[bool, str]:
        env = _worker_env(SCOPE=scope, SOURCE_SCOPE=settings.scope, WORKER_PASSES="1")
        with tempfile.TemporaryFile("w+") as output:
            process = subprocess.Popen([sys.executable, "-m", "invoice_intake.worker"], env={**env, "ITEM_DELAY_S": "1"}, stdout=output, stderr=subprocess.DEVNULL, text=True)
            deadline = time.monotonic() + 180
            killed = False
            while time.monotonic() < deadline and process.poll() is None:
                done = [r for r in store.items(scope) if r["state"] != "processing"]
                if len(done) >= 3:
                    process.send_signal(signal.SIGKILL)
                    killed = True
                    break
                time.sleep(0.1)
            process.wait(timeout=30)
            output.seek(0)
            text = output.read()
        mid_pass = killed and len([r for r in store.items(scope) if r["state"] != "processing"]) < 12
        text += _run_worker(env)
        text += _run_worker(env)
        return mid_pass, text
    return run


def main() -> int:
    settings = get_settings()
    host = urlparse(settings.odoo_url).hostname or ""
    if "odoo-stub" not in host:
        print(f"[FAIL] refusing to start: the Odoo target {host} is not the double", flush=True)
        return 1
    wait_ready(route_checks(settings, parser=True, model=False), settings.ready_timeout_s)
    store = PgStore(settings.working_dsn, settings.episodic_dsn)
    store.init()
    objects = MinioObjects(settings)
    harness = Harness(settings, store, objects, _real_rerun_main, _real_kill_and_rerun(settings, store))
    add_sink(harness.lines.append)
    emit("verify_start", model_mode=settings.model_mode, outcome="ok")
    return run_checks(harness)


if __name__ == "__main__":
    sys.exit(main())
