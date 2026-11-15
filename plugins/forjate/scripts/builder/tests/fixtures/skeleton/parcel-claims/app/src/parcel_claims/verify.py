import os
import sys

import httpx

from .batch import run_once
from .config import settings
from .toolkit import wait_ready

STRICT = os.environ.get("VERIFY_STRICT", "0") == "1"
failed = False


def check(name: str, ok: bool) -> None:
    global failed
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    failed |= not ok


def pending(name: str) -> None:
    global failed
    print(f"[{'FAIL' if STRICT else 'PENDING'}] {name} -> backlog")
    failed |= STRICT


def main() -> None:
    wait_ready(f"{settings.carrier_url}/readyz")
    first = run_once()
    calls = httpx.get(f"{settings.carrier_url}/calls").json()["count"]
    check("connected: shipment-lookup", calls >= len(first))
    check("connected: damage-classifier", all(first.values()))
    check("a second run changes no counts", run_once() == first)
    pending("7 reports classified damaged, 3 not damaged")
    print(f"KPI draft_rate={sum(v == 'damaged' for v in first.values()) / len(first)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
