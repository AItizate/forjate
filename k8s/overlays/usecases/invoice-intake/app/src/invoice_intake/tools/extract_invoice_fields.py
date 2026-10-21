"""extract_invoice_fields: read PDF text [read-only]"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..domain import InvoiceFields
from ..model import Model


class ExtractArgs(BaseModel):
    document_id: str
    document_text: str = Field(max_length=200_000)


def extract_invoice_fields(args: ExtractArgs, *, model: Model, timeout_s: float = 60.0) -> InvoiceFields:
    """Read-only: the model sees the text as data; the result is validated against the schema."""
    return model.extract(args.document_id, args.document_text, timeout_s=timeout_s)
