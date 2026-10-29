"""One module per line of the AI-engineering record's tools; the flags are code (see toolkit)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from .extract_invoice_fields import ExtractArgs, extract_invoice_fields
from .lookup_po import LookupPoArgs, lookup_po
from .post_to_erp import PostToErpArgs, post_to_erp
from .queue_for_review import ReviewItem, queue_for_review


@dataclass(frozen=True)
class Tool:
    name: str
    fn: Callable[..., Any]
    args: type[BaseModel]
    flags: tuple[str, ...]

    @property
    def schema(self) -> dict:
        return self.args.model_json_schema()


TOOLS: dict[str, Tool] = {
    "extract_invoice_fields": Tool("extract_invoice_fields", extract_invoice_fields, ExtractArgs, ("read-only",)),
    "lookup_po": Tool("lookup_po", lookup_po, LookupPoArgs, ("read-only",)),
    "queue_for_review": Tool("queue_for_review", queue_for_review, ReviewItem, ("idempotent",)),
    "post_to_erp": Tool("post_to_erp", post_to_erp, PostToErpArgs, ("idempotent", "requires approval token")),
}
