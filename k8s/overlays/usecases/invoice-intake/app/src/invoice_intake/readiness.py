"""A Job waits for everything on its route, bounded, and fails naming what never answered."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

import httpx

from .config import Settings
from .logs import emit
from .objects import MinioObjects
from .parser import docling_ready
from .store import PgStore


def http_ready(url: str) -> Callable[[], bool]:
    def check() -> bool:
        try:
            return httpx.get(url, timeout=5.0).status_code == 200
        except httpx.HTTPError:
            return False
    return check


def _quiet(check: Callable[[], object]) -> Callable[[], bool]:
    def run() -> bool:
        try:
            check()
            return True
        except Exception:  # noqa: BLE001 - not ready yet, whatever the reason; the deadline is the failure
            return False
    return run


def route_checks(settings: Settings, *, parser: bool, model: bool) -> dict[str, Callable[[], bool]]:
    checks: dict[str, Callable[[], bool]] = {
        "postgres": _quiet(PgStore(settings.working_dsn, settings.episodic_dsn).init),
        "minio": _quiet(MinioObjects(settings).ensure_buckets),
        "Odoo double": http_ready(f"{settings.odoo_url}/readyz"),
        "mailbox double": http_ready(f"{settings.mailbox_url}/readyz"),
    }
    if parser:
        checks["docling"] = lambda: docling_ready(settings.docling_url)
    if model:
        checks["ollama"] = http_ready(f"{settings.ollama_url}/api/tags")
    return checks


def wait_ready(checks: dict[str, Callable[[], bool]], timeout_s: float, *, pause_s: float = 3.0) -> None:
    deadline = time.monotonic() + timeout_s
    pending = dict(checks)
    while pending:
        pending = {name: check for name, check in pending.items() if not check()}
        if not pending:
            break
        if time.monotonic() >= deadline:
            names = ", ".join(sorted(pending))
            emit("not_ready", dependency=names, waited_s=int(timeout_s), outcome="failed")
            print(f"[FAIL] dependency unreachable after {int(timeout_s)} s: {names}", flush=True)
            sys.exit(1)
        time.sleep(pause_s)
    emit("ready", dependencies=sorted(checks), outcome="ok")
