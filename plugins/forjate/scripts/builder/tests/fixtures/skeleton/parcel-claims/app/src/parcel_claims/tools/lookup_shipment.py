"""lookup_shipment: read one shipment by tracking number from the carrier [read-only]"""
import httpx
from pydantic import BaseModel

from ..config import settings


class LookupShipmentArgs(BaseModel):
    tracking: str


class LookupShipmentResult(BaseModel):
    tracking: str
    status: str


def lookup_shipment(args: LookupShipmentArgs, *, timeout_s: float = 10.0) -> LookupShipmentResult:
    # SEAM shipment-lookup: the transport is real; mapping the carrier's fields is backlog
    r = httpx.get(f"{settings.carrier_url}/shipments/{args.tracking}", timeout=timeout_s)
    r.raise_for_status()
    return LookupShipmentResult(**r.json())
