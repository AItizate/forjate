"""Readiness of the services a Job calls: wait on their /readyz before the first request, bounded and loud."""

from __future__ import annotations

import time

import httpx


class NotReady(RuntimeError):
    pass


def wait_ready(url: str, what: str, timeout_s: float = 180.0) -> None:
    """A lookup against a stub that is still starting is a false exception in the review queue, and a verify
    that passes or fails by timing proves nothing: wait for `url`/readyz, then give up naming the service."""
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            if httpx.get(f"{url}/readyz", timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            raise NotReady(f"{what} did not become ready")
        time.sleep(2)
