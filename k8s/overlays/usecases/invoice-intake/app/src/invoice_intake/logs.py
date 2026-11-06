"""One JSON log line per event to stdout. Ids, reasons, hashes and the data class; never a payload.

`scan` repeats the data class in the literal form the log-dataclass-scan gate greps (quality R8).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import datetime, timezone

from .config import get_settings

_sinks: list[Callable[[str], None]] = []


def add_sink(sink: Callable[[str], None]) -> None:
    _sinks.append(sink)


def remove_sink(sink: Callable[[str], None]) -> None:
    if sink in _sinks:
        _sinks.remove(sink)


def emit(event: str, **fields: object) -> None:
    settings = get_settings()
    line = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event": event,
        "caller": settings.workload,
        "data_class": settings.data_class,
        "scan": f"data_class={settings.data_class}",
        **fields,
    }
    text = json.dumps(line, sort_keys=False, default=str)
    print(text, file=sys.stdout, flush=True)
    for sink in list(_sinks):
        sink(text)
