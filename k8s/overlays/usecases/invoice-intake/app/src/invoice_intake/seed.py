"""The seed Job: exactly the data-pipeline record's seed_size, idempotently.

12 PDF attachments in 11 messages delivered to the mailbox double under fixed Message-IDs, 500 open purchase orders and the suppliers'
salted bank hashes on the Odoo double, and the labels the replay double reads. It writes nothing to episodic memory.
"""

from __future__ import annotations

import base64
import json
import sys

from .config import Settings, get_settings
from .generator import SeedSet, injection_set, purchase_orders, supplier_docs, verify_set
from .logs import emit
from .objects import LABELS, MinioObjects, ObjectStore, label_key
from .readiness import route_checks, wait_ready
from .store import PgStore
from .toolkit import call_system


def _admin(system: str, method: str, path: str, settings: Settings, **kwargs: object) -> dict:
    return call_system(system, None, method, path, timeout_s=60.0, token=settings.admin_token, max_bytes=2_000_000, **kwargs).json()


def seed_odoo(settings: Settings) -> dict:
    if not settings.bank_hash_salt:
        raise RuntimeError("BANK_HASH_SALT is empty: the suppliers' known accounts cannot be hashed")
    orders = purchase_orders()
    notes = injection_set().po_notes  # the supplier-authored untrusted field the injection suite plants, always there
    for order in orders:
        if order["number"] in notes:
            order["notes"] = notes[order["number"]]
    return _admin("odoo", "POST", "/_double/seed", settings, json={"suppliers": supplier_docs(settings.bank_hash_salt), "purchase_orders": orders})


def deliver(seed: SeedSet, mailbox: str, objects: ObjectStore, scope: str, settings: Settings) -> dict[str, int]:
    delivered = skipped = labels = 0
    for message in seed.messages:
        body = {
            "mailbox": mailbox, "message_id": message.message_id, "sender": message.sender, "subject": message.subject, "received_at": message.received_at,
            "attachments": [{"index": item.attachment_index, "filename": item.filename, "content_type": "application/pdf",
                             "size_bytes": len(item.content), "sha256": item.sha256,
                             "content_b64": base64.b64encode(item.content).decode()} for item in message.items],
        }
        if _admin("mailbox", "POST", "/_double/messages", settings, json=body)["delivered"]:
            delivered += 1
        else:
            skipped += 1
        for item in message.items:
            if item.label is not None:
                objects.put(LABELS, label_key(scope, item.sha256), json.dumps(item.label).encode())
                labels += 1
    return {"delivered": delivered, "skipped": skipped, "labels": labels}


def run_once(settings: Settings, objects: ObjectStore) -> dict[str, int]:
    objects.ensure_buckets()
    odoo = seed_odoo(settings)
    counts = deliver(verify_set(), settings.mailbox, objects, settings.scope, settings)
    counts["purchase_orders"] = odoo["purchase_orders"]
    counts["attachments"] = len(verify_set().items)
    emit("seed_done", outcome="ok", **counts)
    return counts


def main() -> int:
    settings = get_settings()
    wait_ready(route_checks(settings, parser=False, model=False), settings.ready_timeout_s)
    PgStore(settings.working_dsn, settings.episodic_dsn).init()
    counts = run_once(settings, MinioObjects(settings))
    print(f"seed: {counts['delivered']} messages delivered, {counts['skipped']} already there, {counts['attachments']} attachments, "
          f"{counts['purchase_orders']} purchase orders, {counts['labels']} labels", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
