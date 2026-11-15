from .config import settings
from .model import classify_damage
from .seed import REPORTS
from .toolkit import wait_ready
from .tools.lookup_shipment import LookupShipmentArgs, lookup_shipment


def run_once() -> dict:
    out = {}
    for report in REPORTS:
        lookup_shipment(LookupShipmentArgs(tracking=report["tracking"]))
        out[report["tracking"]] = classify_damage(report)
    return out


def main() -> None:
    wait_ready(f"{settings.carrier_url}/readyz")
    print(run_once())


if __name__ == "__main__":
    main()
