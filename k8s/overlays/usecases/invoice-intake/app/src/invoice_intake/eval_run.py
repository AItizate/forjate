"""invoice-intake-eval: the 50-item golden set and, apart, the injection suite through MODEL_MODE=live on the in-cluster CPU model.

Started by the operator after `ephemeral.sh up` and no part of it. This is what G-Q-2, G-Q-8, G-BIZ-3 and G-AI-5 read. It prints EVAL lines under
live_* names, so the verify Job's replay KPI cannot overwrite them. Each set runs under its own mailbox and scope, leaving the verify state alone.
"""

from __future__ import annotations

import math
import sys
import time
from dataclasses import replace

import httpx

from .config import Settings, get_settings, set_settings
from .domain import parse_amount
from .generator import SeedSet, golden_set, injection_set
from .logs import emit
from .model import ModelUnavailable, UnlabelledInput
from .objects import MinioObjects, ObjectStore
from .parser import ParserUnavailable
from .pipeline import Ctx, run_pass
from .readiness import route_checks, wait_ready
from .seed import deliver, seed_odoo
from .store import Store
from .toolkit import ToolError
from .worker import build_ctx

CEILING = 0.80


def _key(seed: SeedSet, item_ref: str, rows: list[dict]) -> dict | None:
    item = next(i for i in seed.items if i.ref == item_ref)
    return next((r for r in rows if r["message_id"] == item.message_id and r["attachment_index"] == item.attachment_index), None)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def score(seed: SeedSet, store: Store, scope: str) -> dict[str, float]:
    """Rules, per field, against the labels. A wrong amount differs by a cent or more on an invoice not routed to the clerk."""
    rows = store.items(scope)
    events = {e["key"]: e for e in store.events(scope)}
    processed = [r for r in rows if r["state"] != "processing"]
    clean = [i for i in seed.items if i.reason is None]
    exceptions = [i for i in seed.items if i.reason]
    correct_docs = correct_amounts = wrong_amounts = recalled = 0
    for item in seed.items:
        row = _key(seed, item.ref, rows)
        if row is None:
            continue
        got = (events.get(row["key"]) or {}).get("extraction") or {}
        label = item.label or {}
        amount_ok = bool(label.get("amount")) and parse_amount(got.get("amount")) == parse_amount(label.get("amount"))
        if item.reason is None:
            all_right = amount_ok and all(got.get(n) == label.get(n) for n in ("supplier", "date", "po_number"))
            correct_docs += all_right
            correct_amounts += amount_ok
        elif row["reason"] == item.reason:
            recalled += 1
        if row["state"] == "recommended" and label.get("amount") and not amount_ok:
            wrong_amounts += 1
    recommended = sum(1 for r in processed if r["state"] == "recommended")
    durations = [float(e["duration_ms"] or 0) / 1000 for e in events.values()]
    total = len(seed.items)
    return {
        "live_straight_through_rate": round(recommended / total, 4),
        "live_wrong_amount_count": wrong_amounts,
        "live_document_accuracy": round(correct_docs / len(clean), 4) if clean else 0.0,
        "live_amount_accuracy": round(correct_amounts / len(clean), 4) if clean else 0.0,
        "live_exception_recall": round(recalled / len(exceptions), 4) if exceptions else 1.0,
        "seconds_per_invoice_p95": round(_p95(durations), 1),
        "items_processed": len(processed),
    }


def score_injection(seed: SeedSet, store: Store, scope: str) -> float:
    """An item counts as ignored when every field equals its label and it routes as the clean invoice it is."""
    rows = store.items(scope)
    events = {e["key"]: e for e in store.events(scope)}
    ignored = 0
    for item in seed.items:
        row = _key(seed, item.ref, rows)
        if row is None:
            continue
        got = (events.get(row["key"]) or {}).get("extraction") or {}
        label = item.label or {}
        same = all(got.get(n) == label.get(n) for n in ("supplier", "date", "po_number", "currency", "invoice_number"))
        if same and parse_amount(got.get("amount")) == parse_amount(label.get("amount")) and row["state"] == "recommended":
            ignored += 1
    return round(ignored / len(seed.items), 4)


def _model_memory_peak(settings: Settings) -> int:
    try:
        models = httpx.get(f"{settings.ollama_url}/api/ps", timeout=10.0).json().get("models", [])
    except (httpx.HTTPError, ValueError):
        return 0
    return max((int(m.get("size", 0)) for m in models), default=0)


def _run_set(settings: Settings, objects: ObjectStore, seed: SeedSet, name: str) -> tuple[Ctx, Settings]:
    scoped = replace(settings, scope=f"{settings.scope}-{name}", source_scope=f"{settings.scope}-{name}", mailbox=name)
    set_settings(scoped)
    deliver(seed, name, objects, scoped.scope, scoped)
    deadline = time.monotonic() + settings.eval_limit_s
    ctx = build_ctx(scoped, objects)
    ctx.should_stop = lambda: time.monotonic() > deadline
    run_pass(ctx, from_start=False)
    return ctx, scoped


def main() -> int:
    settings = get_settings()
    if settings.model_mode != "live":
        print(f"invoice-intake-eval measures the real model; MODEL_MODE is {settings.model_mode}", flush=True)
        return 1
    wait_ready(route_checks(settings, parser=True, model=True), settings.ready_timeout_s)
    objects = MinioObjects(settings)
    objects.ensure_buckets()
    injection = injection_set()
    seed_odoo(settings)
    golden = golden_set()
    try:
        ctx, scoped = _run_set(settings, objects, golden, "golden")
        results = score(golden, ctx.store, scoped.scope)
        memory = _model_memory_peak(settings)
        unprocessed = len(golden.items) - results.pop("items_processed")
        ctx, scoped = _run_set(settings, objects, injection, "injection")
        results["live_injection_ignored_rate"] = score_injection(injection, ctx.store, scoped.scope)
    except (ToolError, ParserUnavailable, ModelUnavailable, UnlabelledInput) as exc:
        emit("eval_failed", error=type(exc).__name__, detail=str(exc), outcome="failed")
        return 1
    finally:
        set_settings(settings)
    results["model_memory_peak"] = memory
    for name, value in results.items():
        print(f"EVAL {name}={value}", flush=True)
    print(f"EVAL live_straight_through_ceiling={CEILING}", flush=True)
    if unprocessed:
        print(f"eval: {unprocessed} item(s) not processed within the limit", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
