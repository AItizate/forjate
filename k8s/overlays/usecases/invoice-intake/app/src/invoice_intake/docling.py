"""Docling (apps/document-processing/docling): PDF to text. A parse failure is a typed error, routed to review."""

from __future__ import annotations

import httpx

from .config import settings
from .toolkit import ToolError


class ParseFailed(ToolError):
    pass


def wait_ready(timeout_s: float = 600.0) -> None:
    """Docling pulls a large image and loads models before /readyz answers; the batch waits for it once."""
    import time
    cfg = settings()
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            if httpx.get(f"{cfg.docling_url}/readyz", timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            raise ParseFailed("docling did not become ready")
        time.sleep(5)


def parse_pdf(document_id: str, pdf: bytes, *, timeout_s: float = 120.0) -> str:
    cfg = settings()
    files = {"files": (f"{document_id}.pdf", pdf, "application/pdf")}
    data = {"to_formats": "md", "do_ocr": "false"}
    last = None
    for path in ("/v1/convert/file", "/v1alpha/convert/file"):
        try:
            r = httpx.post(f"{cfg.docling_url}{path}", files=files, data=data, timeout=timeout_s)
        except httpx.HTTPError as exc:
            raise ParseFailed(f"docling unreachable: {type(exc).__name__}") from exc
        if r.status_code == 404:
            last = r; continue
        if r.status_code >= 400:
            raise ParseFailed(f"docling returned {r.status_code}")
        body = r.json()
        doc = body.get("document") or {}
        text = doc.get("md_content") or doc.get("text_content") or ""
        if body.get("status") not in (None, "success") or not text.strip():
            raise ParseFailed(f"docling status {body.get('status')}, empty text")
        return text
    raise ParseFailed(f"docling API not found ({last.status_code if last is not None else 'no response'})")
