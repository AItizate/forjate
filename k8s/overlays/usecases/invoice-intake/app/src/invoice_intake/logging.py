"""One JSON line per event, to stdout. Never the payload: the data class, hashes, counts and durations."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator


def args_hash(args: Any) -> str:
    """sha256 of the canonical JSON of the arguments: useful in a log, safe in a log."""
    payload = args.model_dump() if hasattr(args, "model_dump") else args
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


_SINKS: list[Any] = []


def add_sink(fn: Any) -> None:
    """A second destination for every line (the event_log table), so the verify Job can grep without pod access."""
    _SINKS.append(fn)


def log(event: str, **fields: Any) -> None:
    line = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "event": event, **fields}
    sys.stdout.write(json.dumps(line, default=str) + "\n")
    sys.stdout.flush()
    for sink in _SINKS:
        try:
            sink(line)
        except Exception:  # a sink failure never breaks the batch; stdout still has the line
            pass


@contextmanager
def timed_call(kind: str, name: str, args: Any, *, data_class: str, **extra: Any) -> Iterator[dict]:
    """Logs `<kind>_call` with the argument hash, the data class, the duration and the outcome."""
    started = time.monotonic()
    info: dict[str, Any] = {}
    try:
        yield info
        outcome = "ok"
    except Exception as exc:  # the error type is logged, never its message (it may carry payload)
        outcome = f"error:{type(exc).__name__}"
        raise
    finally:
        log(f"{kind}_call", **{kind if kind == "model" else "tool": name}, args_hash=args_hash(args), data_class=data_class,
            duration_ms=int((time.monotonic() - started) * 1000), outcome=outcome, **extra, **info)
