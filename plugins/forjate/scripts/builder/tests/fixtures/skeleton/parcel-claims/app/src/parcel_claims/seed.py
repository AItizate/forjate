from .config import settings
from .toolkit import wait_ready

REPORTS = [{"tracking": f"T{i}", "label": "damaged" if i < 7 else "not-damaged"} for i in range(10)]


def main() -> None:
    wait_ready(f"{settings.carrier_url}/readyz")
    print(f"seeded {len(REPORTS)} reports")


if __name__ == "__main__":
    main()
