"""The mailbox double: messages with Message-ID, UID and UIDVALIDITY over HTTP, delivered by the seed and read by the worker.

Delivery deduplicates on the fixed Message-ID, so a second seed run mints no new mail. A stub over HTTP proves nothing about real
IMAP (architecture R1); the real client meets a real mailbox in the first week of Walk.
"""

from __future__ import annotations

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .config import get_settings
from .double_store import DoubleKV, PgKV
from .logs import emit
from .odoo_stub import require

PORT = 8001
UIDVALIDITY = 1


def _messages_ns(mailbox: str) -> str:
    return f"mailbox.{mailbox}.messages"


def _uid_key(uid: int) -> str:
    return f"{uid:010d}"


def _public(doc: dict) -> dict:
    attachments = [{k: v for k, v in a.items() if k != "content_b64"} for a in doc["attachments"]]
    return {**doc, "attachments": attachments}


def create_app(kv: DoubleKV) -> FastAPI:
    app = FastAPI(title="Mailbox double", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        try:
            kv.ping()
        except Exception:  # noqa: BLE001 - any store failure means not ready
            return JSONResponse({"status": "store unavailable"}, status_code=503)
        return JSONResponse({"status": "ready"})

    @app.get("/mailbox/messages", dependencies=[Depends(require("MAILBOX_LIST_TOKEN"))])
    def messages(mailbox: str = "shared", after_uid: int = 0, limit: int = 50) -> dict:
        page = kv.page(_messages_ns(mailbox), _uid_key(after_uid), min(limit, 50))
        return {"uidvalidity": UIDVALIDITY, "messages": [_public(m) for m in page],
                "next_after_uid": page[-1]["uid"] if page else after_uid}

    @app.get("/mailbox/attachment", dependencies=[Depends(require("MAILBOX_FETCH_TOKEN"))])
    def attachment(uid: int, index: int, mailbox: str = "shared") -> dict:
        doc = kv.get(_messages_ns(mailbox), _uid_key(uid))
        if doc is None or not 0 <= index < len(doc["attachments"]):
            raise HTTPException(status_code=404, detail="not_found")
        return doc["attachments"][index]

    @app.post("/_double/messages", dependencies=[Depends(require("DOUBLE_ADMIN_TOKEN"))])
    def deliver(body: dict) -> dict:
        mailbox = body.get("mailbox", "shared")
        message_id = body["message_id"]
        ns = _messages_ns(mailbox)
        existing = kv.get(f"mailbox.{mailbox}.ids", message_id)
        if existing is not None:
            return {"delivered": False, "uid": existing["uid"]}
        uid = kv.count(ns) + 1
        kv.put_if_absent(ns, _uid_key(uid), {**body, "uid": uid})
        kv.put_if_absent(f"mailbox.{mailbox}.ids", message_id, {"uid": uid})
        return {"delivered": True, "uid": uid}

    @app.get("/_double/stats", dependencies=[Depends(require("DOUBLE_ADMIN_TOKEN"))])
    def stats(mailbox: str = "shared") -> dict:
        return {"messages": kv.count(_messages_ns(mailbox)), "uidvalidity": UIDVALIDITY}

    return app


def main() -> None:
    settings = get_settings()
    emit("stub_start", stub="shared-imap-mailbox", outcome="ok")
    uvicorn.run(create_app(PgKV(settings.working_dsn)), host="0.0.0.0", port=PORT, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
