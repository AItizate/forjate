"""One pass over the mailbox: fetch, land, parse, mask, extract, validate, match, route.

Only extract calls a model, which holds no tools. Every other step is code. An item ends in a terminal state with a recommendation or
a review_queue row; nothing is written to Odoo at Crawl. A key already terminal is skipped, which is what makes a second pass, a
lost cursor and a killed pass harmless.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from pydantic import ValidationError

from .config import Settings
from .domain import (
    ESCALATION_FIELDS, Decision, InvoiceExtraction, PurchaseOrder, attachment_key, bank_account_on, compare_bank,
    file_bound_violation, literal_source_check, mask_bank_numbers, payable_key, route, salted_bank_hash,
)
from .logs import add_sink, emit, remove_sink
from .model import Model, build_messages
from .objects import INBOX, PARSED, ObjectStore
from .parser import ParseFailed, Parser
from .store import Store
from .toolkit import Attempt, AttachmentOutOfBounds, Bounds, BoundExceeded, ToolError, ToolNotFound
from .tools.fetch_invoice_attachment import FetchInvoiceAttachmentArgs, fetch_invoice_attachment
from .tools.find_payable import FindPayableArgs, find_payable
from .tools.get_supplier_bank_ref import GetSupplierBankRefArgs, get_supplier_bank_ref
from .tools.list_mailbox_messages import AttachmentMeta, ListMailboxMessagesArgs, MailboxMessage, list_mailbox_messages
from .tools.lookup_po import LookupPoArgs, lookup_po


@dataclass
class Ctx:
    settings: Settings
    store: Store
    objects: ObjectStore
    parser: Parser
    model: Model
    should_stop: Callable[[], bool] = lambda: False


class _Escalate(Exception):
    """The item ends here, with this decision. Used by the file-bound, parse and classification exits."""

    def __init__(self, decision: Decision, failed_step: str | None) -> None:
        self.decision = decision
        self.failed_step = failed_step


def _dead_letter(check: str, fields: list[str], step: str) -> _Escalate:
    decision = Decision("in_review", "parse-failed", check, fields, "none: read the source, then reject or type the fields")
    return _Escalate(decision, step)


@dataclass
class _Run:
    extraction: InvoiceExtraction | None = None
    literal: dict = field(default_factory=dict)
    po: PurchaseOrder | None = None
    bank: str = "unknown"
    consulted: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0


def _extract(ctx: Ctx, attempt: Attempt, masked: str, sha256: str, run: _Run) -> InvoiceExtraction:
    """Schema-validated extraction with one repair attempt. Still invalid after that goes to the clerk as low-confidence."""
    s = ctx.settings
    hint: str | None = None
    for step in ("extract", "repair"):
        messages, tokens = build_messages(s.prompt_name, masked, s.budget_tokens, hint)
        attempt.model_call(step, tokens)
        started = time.monotonic()

        def ask() -> object:
            try:
                return ctx.model.extract(s.prompt_name, masked, source_sha256=sha256, repair_hint=hint)
            except httpx.TimeoutException as exc:
                raise BoundExceeded("step_timeout_s", step) from exc

        reply = attempt.step(step, ask)
        run.tokens_in += reply.tokens_in or tokens
        run.tokens_out += reply.tokens_out
        duration = int((time.monotonic() - started) * 1000)
        try:
            parsed = InvoiceExtraction.model_validate_json(reply.raw)
        except ValidationError as exc:
            hint = ",".join(sorted({str(e["loc"][0]) if e["loc"] else "schema" for e in exc.errors()}))
            emit("model_call", model=ctx.model.name, mode=s.model_mode, prompt=s.prompt_name, duration_ms=duration,
                 tokens_in=reply.tokens_in, tokens_out=reply.tokens_out, outcome="schema-invalid")
            continue
        emit("model_call", model=ctx.model.name, mode=s.model_mode, prompt=s.prompt_name, duration_ms=duration,
             tokens_in=reply.tokens_in, tokens_out=reply.tokens_out, outcome="ok")
        return parsed
    raise _Escalate(Decision("in_review", "low-confidence", "schema", (hint or "schema").split(","), "review the source document"), "validate")


def _parsed_text(ctx: Ctx, attempt: Attempt, key: str, filename: str, content: bytes) -> str:
    s = ctx.settings
    own_key = f"{s.scope}/{key}.json"

    def parse() -> str:
        cached = ctx.objects.get(PARSED, own_key) or ctx.objects.get(PARSED, f"{s.source_scope}/{key}.json")
        if cached:
            text = json.loads(cached)["text"]
        else:
            text = ctx.parser.parse(filename, content)
        ctx.objects.put(PARSED, own_key, json.dumps({"parser": "docling", "text": text}).encode())
        return text

    try:
        return attempt.step("parse", parse)
    except ParseFailed as exc:
        raise _dead_letter("parser", ["document"], "parse") from exc


def _lookups(ctx: Ctx, attempt: Attempt, run: _Run, extraction: InvoiceExtraction, invoice_hash: str | None) -> str | None:
    """find_payable, lookup_po and the bank reference. A missing record is a fact; a failing system is lookup-failed."""
    try:
        duplicate_of: str | None = None
        run.consulted.append("find_payable")
        try:
            found = attempt.step("find_payable", lambda: find_payable(FindPayableArgs(
                supplier_id=extraction.supplier_id, invoice_number=extraction.invoice_number or "")))
            duplicate_of = f"odoo:{found.posting_id}"
        except (ToolNotFound, ValidationError):
            pass
        if extraction.po_number:
            run.consulted.append("lookup_po")
            try:
                run.po = attempt.step("lookup_po", lambda: lookup_po(LookupPoArgs(po_number=extraction.po_number or ""))).purchase_order
            except (ToolNotFound, ValidationError):
                run.po = None
        known: str | None = None
        run.consulted.append("get_supplier_bank_ref")
        try:
            known = attempt.step("bank_reference", lambda: get_supplier_bank_ref(GetSupplierBankRefArgs(supplier_id=extraction.supplier_id))).bank_ref_hash
        except (ToolNotFound, ValidationError):
            known = None
        run.bank = compare_bank(invoice_hash, known)
        return duplicate_of
    except ToolError as exc:
        decision = Decision("in_review", "lookup-failed", "odoo-lookup", [], "none: retry when Odoo answers")
        raise _Escalate(decision, run.consulted[-1] if run.consulted else "lookup") from exc


def _decide(ctx: Ctx, attempt: Attempt, msg: MailboxMessage, att: AttachmentMeta, key: str, object_key: str, run: _Run, uidvalidity: int) -> Decision:
    s = ctx.settings
    violation = file_bound_violation(att.filename, att.content_type, b"%PDF-", max_bytes=10**12, max_pages=10**6)
    if att.size_bytes > s.max_file_bytes:
        violation = "over-10-mb"
    if violation:
        raise _dead_letter("file-bounds", [violation], "file-bounds")

    def fetch() -> bytes:
        result = fetch_invoice_attachment(FetchInvoiceAttachmentArgs(mailbox=s.mailbox, uid=msg.uid, attachment_index=att.index))
        bound = file_bound_violation(result.filename, result.content_type, result.content, max_bytes=s.max_file_bytes, max_pages=s.max_pdf_pages)
        if bound:
            raise _dead_letter("file-bounds", [bound], "file-bounds")
        ctx.objects.put(INBOX, object_key, result.content)
        return result.content

    run.consulted.append("fetch_invoice_attachment")
    try:
        content = attempt.step("fetch", fetch)
    except AttachmentOutOfBounds as exc:
        raise _dead_letter("file-bounds", [str(exc)], "file-bounds") from exc

    text = _parsed_text(ctx, attempt, key, att.filename, content)

    def mask() -> tuple[str, str | None]:
        account = bank_account_on(text)
        return mask_bank_numbers(text), salted_bank_hash(account, s.bank_hash_salt) if account else None

    masked, invoice_hash = attempt.step("mask", mask)

    extraction = _extract(ctx, attempt, masked, att.sha256, run)
    run.extraction = extraction
    if extraction.document_type != "invoice":
        raise _dead_letter("classification", ["document_type"], "extract")

    run.literal = attempt.step("validate", lambda: literal_source_check(extraction, masked))
    payable = payable_key(extraction.supplier_id, extraction.invoice_number or "")
    ctx.store.set_payable_key(s.scope, key, payable)
    in_odoo = _lookups(ctx, attempt, run, extraction, invoice_hash)
    earlier = ctx.store.earlier_with_payable(s.scope, payable, msg.uid, att.index)
    return attempt.step("compare_route", lambda: route(extraction, run.literal, earlier or in_odoo, run.po, run.bank))


def _context(key: str, msg: MailboxMessage, object_key: str, run: _Run, decision: Decision, failed_step: str | None) -> list[dict]:
    """The escalation context, in the UX record's order with the recommendation last. No bank number is a field."""
    ex = run.extraction

    def extracted(name: str) -> dict:
        return {"value": getattr(ex, name) if ex else None, "literal_source": run.literal.get(name)}

    values = {
        "item_id": key, "received_at": msg.received_at, "sender": msg.sender, "pdf_object_key": object_key,
        "po_fields": run.po.model_dump() if run.po else None, "bank_comparison": run.bank, "tools_consulted": run.consulted,
        "check_fired": decision.check_fired, "failed_step": failed_step, "fields_disagree": decision.fields,
        "extracted_supplier": extracted("supplier"), "extracted_invoice_number": extracted("invoice_number"),
        "extracted_amount": extracted("amount"), "extracted_currency": extracted("currency"),
        "extracted_date": extracted("date"), "extracted_po_number": extracted("po_number"),
        "reason": decision.reason, "recommendation": decision.recommendation,
    }
    return [{"field": name, "value": values[name]} for name in ESCALATION_FIELDS]


def _recommendation(decision: Decision, po: PurchaseOrder | None) -> dict | None:
    if decision.state == "recommended":
        return {"text": decision.recommendation, "po_number": po.number if po else None}
    if decision.reason == "duplicate":
        return None  # no second result
    return {"text": decision.recommendation, "withheld": decision.recommendation == "withheld"}


def process_attachment(ctx: Ctx, uidvalidity: int, msg: MailboxMessage, att: AttachmentMeta, pass_no: int, stats: dict[str, int]) -> None:
    s = ctx.settings
    stats["items_seen"] += 1
    key = attachment_key(msg.message_id, att.sha256, uidvalidity, msg.uid, att.index)
    existing = ctx.store.get_item(s.scope, key)
    if existing and existing["state"] != "processing":
        return
    object_key = f"{s.scope}/{key}.pdf"
    row = {"mailbox": s.mailbox, "uid": msg.uid, "uidvalidity": uidvalidity, "message_id": msg.message_id, "attachment_index": att.index,
           "filename": att.filename, "sender": msg.sender, "received_at": msg.received_at, "sha256": att.sha256, "object_key": object_key}
    if ctx.store.add_item(s.scope, key, row, pass_no):
        stats["rows_added"] += 1

    started = time.monotonic()
    run = _Run()
    failed_step: str | None = None
    try:
        decision = _decide(ctx, Attempt(Bounds.of(s)), msg, att, key, object_key, run, uidvalidity)
    except _Escalate as exc:
        decision, failed_step = exc.decision, exc.failed_step
    except BoundExceeded as exc:
        # Stops the attempt with a typed error and a log line, never a retry.
        emit("bound_exceeded", item=key[:12], bound=exc.bound, step=exc.step, outcome="stopped")
        decision = Decision("in_review", "timeout", "execution-bound", [exc.bound], "none: read the source, then type the fields")
        failed_step = exc.step

    duration = int((time.monotonic() - started) * 1000)
    # The episodic write first and idempotent by key: the two stores share no transaction (data-store R2, R4).
    ctx.store.record_event(s.scope, key, {
        "extraction": run.extraction.model_dump() if run.extraction else None, "literal": run.literal,
        "match_result": {"reason": decision.reason, "fields": decision.fields, "bank": run.bank}, "status": decision.state,
        "model": ctx.model.name, "prompt": s.prompt_name, "tokens_in": run.tokens_in, "tokens_out": run.tokens_out, "duration_ms": duration,
    })
    review_added = ctx.store.finish_item(
        s.scope, key, state=decision.state, reason=decision.reason, failed_step=failed_step,
        recommendation=_recommendation(decision, run.po), fields=decision.fields, linked_key=decision.linked_key,
        context=None if decision.state == "recommended" else _context(key, msg, object_key, run, decision, failed_step))
    stats["states_changed"] += 1
    stats["review_added"] += 1 if review_added else 0
    emit("item_done", item=key[:12], state=decision.state, reason=decision.reason, failed_step=failed_step, duration_ms=duration, outcome="ok")


def run_pass(ctx: Ctx, *, from_start: bool) -> dict[str, int]:
    """One pass. Returns its counts, and records them: the second pass's zeros are the idempotency proof the verify Job reads."""
    s = ctx.settings
    trace: list[str] = []
    add_sink(trace.append)
    try:
        pass_no = ctx.store.begin_pass(s.scope, from_start)
        stats = {"items_seen": 0, "rows_added": 0, "states_changed": 0, "review_added": 0}
        cursor = ctx.store.get_cursor(s.scope, s.mailbox)
        after = 0 if from_start or cursor is None else cursor[1]
        stopped = False
        while not stopped:
            page = list_mailbox_messages(ListMailboxMessagesArgs(mailbox=s.mailbox, after_uid=after))
            if cursor is not None and cursor[0] != page.uidvalidity and after:
                emit("uidvalidity_changed", mailbox=s.mailbox, outcome="rescan")
                after = 0
                cursor = None
                continue
            if not page.messages:
                break
            for msg in page.messages:
                if ctx.should_stop():
                    stopped = True  # SIGTERM: the item in flight has finished; a restart resumes by key
                    break
                for att in msg.attachments:
                    process_attachment(ctx, page.uidvalidity, msg, att, pass_no, stats)
                    ctx.store.append_trace(s.scope, list(trace))
                    trace.clear()
                    if s.item_delay_s:
                        time.sleep(s.item_delay_s)
                ctx.store.set_cursor(s.scope, s.mailbox, page.uidvalidity, msg.uid)
                after = msg.uid
        emit("pass_done", pass_no=pass_no, from_start=from_start, outcome="ok", **stats)
        ctx.store.finish_pass(s.scope, pass_no, stats)
        ctx.store.append_trace(s.scope, list(trace))
        return stats
    finally:
        remove_sink(trace.append)

