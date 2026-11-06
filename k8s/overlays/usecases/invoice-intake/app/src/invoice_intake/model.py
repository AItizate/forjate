"""The model behind a Protocol. MODEL_MODE picks one: replay and rules are the deterministic doubles CI runs, live is
the in-cluster Ollama of the ai-engineering record. The model holds no tools, so a planted instruction can at most
produce a wrong field, which the literal-source check and the match catch.

At Crawl `gateway: none` means Ollama directly. There is no provider client anywhere in this package.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

from . import prompts
from .config import Settings
from .domain import InvoiceExtraction
from .logs import emit


class ModelUnavailable(Exception):
    """The model server cannot be reached: the pass fails loudly and a rerun resumes. Not an invoice's fault."""


class UnlabelledInput(Exception):
    """The replay double met an input the seed wrote no label for, which is the right failure."""


@dataclass(frozen=True)
class ModelReply:
    raw: str
    tokens_in: int = 0
    tokens_out: int = 0


class Model(Protocol):
    name: str

    def extract(self, prompt_name: str, document_text: str, *, source_sha256: str, repair_hint: str | None = None) -> ModelReply: ...


def build_messages(prompt_name: str, document_text: str, budget_tokens: int, repair_hint: str | None = None) -> tuple[list[dict[str, str]], int]:
    """System prompt plus the data block; synthetic examples dropped first when over the ceiling."""
    system = prompts.load(prompt_name)
    user = prompts.document_block(document_text)
    if repair_hint:
        user += f"\nThe previous answer failed validation on: {repair_hint}. Return the corrected JSON object only."
    if prompts.estimate_tokens(system + user) > budget_tokens:
        system = prompts.without_examples(system)
    tokens = prompts.estimate_tokens(system + user)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}], tokens


class ReplayModel:
    """Returns the label the seed wrote next to the input. Proves flow, never extraction."""

    name = "replay"

    def __init__(self, read_label: Callable[[str], dict | None]) -> None:
        self._read_label = read_label

    def extract(self, prompt_name: str, document_text: str, *, source_sha256: str, repair_hint: str | None = None) -> ModelReply:
        label = self._read_label(source_sha256)
        if label is None:
            raise UnlabelledInput(f"no label for input {source_sha256[:12]}")
        return ModelReply(json.dumps(label))


class RulesModel:
    """A deterministic reader of the printed labels, so the delimited text itself goes through the code path."""

    name = "rules"
    _FIELDS = {
        "invoice_number": r"(?im)^\s*invoice number:\s*(\S+)",
        "supplier_vat": r"(?im)^\s*vat id:\s*(\S+)",
        "date": r"(?im)^\s*date:\s*(\d{4}-\d{2}-\d{2})",
        "po_number": r"(?im)^\s*po number:\s*(\S+)",
    }

    def extract(self, prompt_name: str, document_text: str, *, source_sha256: str, repair_hint: str | None = None) -> ModelReply:
        if not re.search(r"(?im)^\s*invoice\s*$", document_text):
            return ModelReply(json.dumps({"document_type": "other"}))
        out: dict[str, str | None] = {"document_type": "invoice"}
        for name, pattern in self._FIELDS.items():
            found = re.search(pattern, document_text)
            out[name] = found.group(1) if found else None
        total = re.search(r"(?im)^\s*total:\s*([\d.,]+)\s+([A-Z]{3})", document_text)
        out["amount"], out["currency"] = (total.group(1).replace(",", ""), total.group(2)) if total else (None, None)
        supplier = re.search(r"(?im)^\s*supplier:\s*(.+?)\s*$", document_text)
        out["supplier"] = supplier.group(1) if supplier else None
        return ModelReply(json.dumps(out))


class LiveModel:
    """Ollama over HTTP, temperature 0, the output schema enforced by `format` and validated by the caller."""

    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.name = settings.model_id
        self._client = client or httpx.Client(base_url=settings.ollama_url)

    def extract(self, prompt_name: str, document_text: str, *, source_sha256: str, repair_hint: str | None = None) -> ModelReply:
        messages, _ = build_messages(prompt_name, document_text, self.settings.budget_tokens, repair_hint)
        body = {
            "model": self.settings.model_id.removeprefix("ollama/"),
            "messages": messages,
            "stream": False,
            "tools": [],
            "format": InvoiceExtraction.model_json_schema(),
            "options": {"temperature": 0, "num_ctx": self.settings.budget_tokens},
        }
        started = time.monotonic()
        try:
            response = self._client.post("/api/chat", json=body, timeout=self.settings.step_timeout_s)
        except httpx.TimeoutException:
            raise
        except httpx.TransportError as exc:
            raise ModelUnavailable("ollama unreachable") from exc
        if response.status_code >= 400:
            raise ModelUnavailable(f"ollama answered {response.status_code}")
        data = response.json()
        reply = ModelReply(data["message"]["content"], int(data.get("prompt_eval_count") or 0), int(data.get("eval_count") or 0))
        emit("model_exchange", model=self.name, duration_ms=int((time.monotonic() - started) * 1000), outcome="ok")
        return reply


def model_for(settings: Settings, read_label: Callable[[str], dict | None]) -> Model:
    if settings.model_mode == "replay":
        return ReplayModel(read_label)
    if settings.model_mode == "rules":
        return RulesModel()
    if settings.model_mode == "live":
        return LiveModel(settings)
    raise ValueError(f"unknown MODEL_MODE {settings.model_mode!r}: replay, rules or live")
