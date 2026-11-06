"""The run Job: `worker`, the architecture record's one container at Crawl, one idempotent batch over the mailbox.

It makes two passes, because the runner runs each Job once: the first from the cursor, the second from the start of the mailbox double,
which proves both replay and cursor loss. A killed pass loses nothing: state sits under the key and a rerun resumes.
"""

from __future__ import annotations

import signal
import sys

from .config import Settings, get_settings
from .logs import emit
from .model import ModelUnavailable, UnlabelledInput, model_for
from .objects import MinioObjects, ObjectStore, read_label
from .parser import DoclingParser, ParserUnavailable
from .pipeline import Ctx, run_pass
from .readiness import route_checks, wait_ready
from .store import PgStore
from .toolkit import ToolError

_stop = {"requested": False}


def build_ctx(settings: Settings, objects: ObjectStore | None = None) -> Ctx:
    store_objects = objects or MinioObjects(settings)
    store = PgStore(settings.working_dsn, settings.episodic_dsn)
    store.init()
    store_objects.ensure_buckets()
    parser = DoclingParser(settings.docling_url, timeout_s=settings.step_timeout_s)
    model = model_for(settings, lambda sha256: read_label(store_objects, settings.source_scope, sha256))
    return Ctx(settings, store, store_objects, parser, model, should_stop=lambda: _stop["requested"])


def run_job(ctx: Ctx) -> dict[str, int]:
    """Every pass of the Job. The verify Job's rerun reaches this through the same command."""
    settings = ctx.settings
    totals = {"items_seen": 0, "rows_added": 0, "states_changed": 0, "review_added": 0}
    for number in range(settings.worker_passes):
        stats = run_pass(ctx, from_start=settings.worker_from_start or number > 0)
        for name, value in stats.items():
            totals[name] += value
        # A rerun from a finished cursor reads nothing new; an empty first read with no state at all means no intake.
        if number == 0 and stats["items_seen"] == 0 and not ctx.store.items(settings.scope):
            raise ToolError("intake read 0 items")
    return totals


def main() -> int:
    settings = get_settings()
    signal.signal(signal.SIGTERM, lambda *_: _stop.update(requested=True))
    wait_ready(route_checks(settings, parser=True, model=settings.model_mode == "live"), settings.ready_timeout_s)
    try:
        run_job(build_ctx(settings))
    except (ToolError, ParserUnavailable, ModelUnavailable, UnlabelledInput) as exc:
        # The dependency is named and no invoice content is printed. Nothing is lost: a rerun resumes by key.
        emit("pass_failed", error=type(exc).__name__, detail=str(exc), outcome="failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
