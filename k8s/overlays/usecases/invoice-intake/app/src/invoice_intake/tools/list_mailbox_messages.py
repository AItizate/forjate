"""list_mailbox_messages: read new message ids from the mailbox [read-only, page of 50]"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..toolkit import call_system, timed_call


class ListMailboxMessagesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mailbox: str = Field(default="shared", pattern=r"^[a-z0-9-]+$")
    after_uid: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=50)


class AttachmentMeta(BaseModel):
    index: int
    filename: str
    content_type: str
    size_bytes: int
    sha256: str


class MailboxMessage(BaseModel):
    uid: int
    message_id: str | None = None
    sender: str = ""
    subject: str = ""
    received_at: str = ""
    attachments: list[AttachmentMeta] = []


class ListMailboxMessagesResult(BaseModel):
    uidvalidity: int
    messages: list[MailboxMessage]
    next_after_uid: int


def list_mailbox_messages(args: ListMailboxMessagesArgs, *, timeout_s: float = 10.0) -> ListMailboxMessagesResult:
    with timed_call("list_mailbox_messages", args):
        response = call_system("mailbox", "list_mailbox_messages", "GET", "/mailbox/messages", timeout_s=timeout_s,
                               params=args.model_dump())
        return ListMailboxMessagesResult.model_validate(response.json())
