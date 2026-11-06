"""The tool registry, by stage. The code calls these tools; the model holds none at any stage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from .fetch_invoice_attachment import FetchInvoiceAttachmentArgs, FetchInvoiceAttachmentResult, fetch_invoice_attachment
from .find_payable import FindPayableArgs, FindPayableResult, find_payable
from .get_supplier_bank_ref import GetSupplierBankRefArgs, GetSupplierBankRefResult, get_supplier_bank_ref
from .list_mailbox_messages import ListMailboxMessagesArgs, ListMailboxMessagesResult, list_mailbox_messages
from .lookup_po import LookupPoArgs, LookupPoResult, lookup_po
from .post_invoice import PostInvoiceArgs, PostInvoiceResult, post_invoice
from .request_approval import RequestApprovalArgs, RequestApprovalResult, request_approval


@dataclass(frozen=True)
class Tool:
    name: str
    fn: Callable[..., BaseModel]
    args_model: type[BaseModel]
    result_model: type[BaseModel]
    stages: tuple[str, ...]
    writes: bool = False

    @property
    def schema(self) -> dict:
        return self.args_model.model_json_schema()


_ALL = ("crawl", "walk", "run")
_WRITE = ("walk", "run")

TOOLS: dict[str, Tool] = {t.name: t for t in (
    Tool("list_mailbox_messages", list_mailbox_messages, ListMailboxMessagesArgs, ListMailboxMessagesResult, _ALL),
    Tool("fetch_invoice_attachment", fetch_invoice_attachment, FetchInvoiceAttachmentArgs, FetchInvoiceAttachmentResult, _ALL),
    Tool("lookup_po", lookup_po, LookupPoArgs, LookupPoResult, _ALL),
    Tool("find_payable", find_payable, FindPayableArgs, FindPayableResult, _ALL),
    Tool("get_supplier_bank_ref", get_supplier_bank_ref, GetSupplierBankRefArgs, GetSupplierBankRefResult, _ALL),
    Tool("request_approval", request_approval, RequestApprovalArgs, RequestApprovalResult, _WRITE, writes=True),
    Tool("post_invoice", post_invoice, PostInvoiceArgs, PostInvoiceResult, _WRITE, writes=True),
)}


def tools_for(stage: str) -> dict[str, Tool]:
    return {name: tool for name, tool in TOOLS.items() if stage in tool.stages}
