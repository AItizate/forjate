"""fetch_invoice_attachment: read one PDF attachment by mailbox message id [read-only, max 10 MB]"""

from __future__ import annotations

import base64
import hashlib

from pydantic import BaseModel, ConfigDict, Field

from ..toolkit import AttachmentOutOfBounds, call_system, timed_call

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


class FetchInvoiceAttachmentArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mailbox: str = Field(default="shared", pattern=r"^[a-z0-9-]+$")
    uid: int = Field(ge=1)
    attachment_index: int = Field(default=0, ge=0)


class FetchInvoiceAttachmentResult(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    content: bytes


def fetch_invoice_attachment(args: FetchInvoiceAttachmentArgs, *, timeout_s: float = 30.0) -> FetchInvoiceAttachmentResult:
    with timed_call("fetch_invoice_attachment", args):
        response = call_system(
            "mailbox", "fetch_invoice_attachment", "GET", "/mailbox/attachment", timeout_s=timeout_s,
            max_bytes=MAX_ATTACHMENT_BYTES * 2,
            params={"mailbox": args.mailbox, "uid": args.uid, "index": args.attachment_index},
        )
        body = response.json()
        content = base64.b64decode(body["content_b64"])
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise AttachmentOutOfBounds("over-10-mb")
        return FetchInvoiceAttachmentResult(filename=body["filename"], content_type=body["content_type"], size_bytes=len(content),
                                            sha256=hashlib.sha256(content).hexdigest(), content=content)
