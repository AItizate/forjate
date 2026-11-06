"""The document parser: the catalog's docling-serve over its REST API. The same real parser runs in CI's verify Job."""

from __future__ import annotations

import time
from typing import Protocol

import httpx


class ParseFailed(Exception):
    """The parser read this file and could not convert it: a property of the file. Goes to the clerk as parse-failed."""


class ParserUnavailable(Exception):
    """The parser is not answering: a property of the environment. The pass fails loudly and a rerun resumes."""


class Parser(Protocol):
    def parse(self, filename: str, content: bytes) -> str: ...


# docling-serve answers these while busy or past DOCLING_SERVE_MAX_SYNC_WAIT, the first conversion loading its models.
_BUSY = {429, 503, 504}


class DoclingParser:
    def __init__(self, base_url: str, *, timeout_s: float, retry_pause_s: float = 5.0, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(base_url=base_url)
        self._timeout_s = timeout_s
        self._pause = retry_pause_s

    def _post(self, path: str, filename: str, content: bytes, timeout: float) -> httpx.Response:
        return self._client.post(
            path,
            files={"files": (filename or "attachment.pdf", content, "application/pdf")},
            data={"to_formats": ["md", "text"], "image_export_mode": "placeholder", "do_ocr": "true"},
            timeout=timeout,
        )

    def parse(self, filename: str, content: bytes) -> str:
        deadline = time.monotonic() + self._timeout_s
        path = "/v1/convert/file"
        while True:
            remaining = max(1.0, deadline - time.monotonic())
            try:
                response = self._post(path, filename, content, remaining)
            except httpx.TimeoutException as exc:
                raise ParserUnavailable("docling timed out") from exc
            except httpx.TransportError as exc:
                raise ParserUnavailable("docling unreachable") from exc
            if response.status_code == 404 and path == "/v1/convert/file":
                path = "/v1alpha/convert/file"  # older docling-serve; the component's image floats on latest
                continue
            if response.status_code in _BUSY:
                if time.monotonic() + self._pause >= deadline:
                    raise ParserUnavailable(f"docling answered {response.status_code} until the step bound")
                time.sleep(self._pause)
                continue
            break
        if response.status_code >= 400:
            raise ParseFailed(f"docling answered {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise ParseFailed("docling answered no JSON") from exc
        status = str(body.get("status", "")).lower()
        document = body.get("document") or {}
        text = document.get("md_content") or document.get("text_content") or ""
        if status not in ("success", "partial_success") or not text.strip():
            raise ParseFailed(f"docling status {status or 'unknown'}")
        return text


def docling_ready(base_url: str, client: httpx.Client | None = None) -> bool:
    http = client or httpx
    for path in ("/readyz", "/health"):
        try:
            if http.get(f"{base_url}{path}", timeout=5.0).status_code == 200:
                return True
        except httpx.HTTPError:
            continue
    return False
