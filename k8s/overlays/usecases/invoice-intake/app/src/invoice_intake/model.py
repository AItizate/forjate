"""The model behind a Protocol: a live Ollama client and a replay double that reads the seed's labels.

CI runs MODEL_MODE=replay so the verify Job measures routing, arithmetic, idempotency and the
exception path deterministically; MODEL_MODE=live is the same Job against the local model and the
run that measures field accuracy (the quality record says so)."""

from __future__ import annotations

import json
from typing import Protocol

import httpx

from .config import Settings, settings
from .domain import InvoiceFields
from .logging import timed_call
from .prompts import load


class Model(Protocol):
    mode: str

    def extract(self, document_id: str, document_text: str, *, timeout_s: float = 60.0) -> InvoiceFields: ...


class ReplayModel:
    """Returns the label the seed wrote next to the document. An unlabelled document raises: the right failure."""
    mode = "replay"

    def __init__(self, labels: dict[str, dict]):
        self.labels = labels

    def extract(self, document_id: str, document_text: str, *, timeout_s: float = 60.0) -> InvoiceFields:
        if document_id not in self.labels:
            raise KeyError(f"no label for {document_id}: replay mode needs the seed's labels")
        with timed_call("model", "replay", {"document_id": document_id}, data_class=settings().data_class, mode=self.mode, prompt=settings().prompt_name):
            return InvoiceFields.model_validate(self.labels[document_id])


class OllamaModel:
    """Structured extraction through Ollama's chat API with the JSON schema as the format, temperature 0."""
    mode = "live"

    def __init__(self, cfg: Settings | None = None):
        self.cfg = cfg or settings()

    def extract(self, document_id: str, document_text: str, *, timeout_s: float = 60.0) -> InvoiceFields:
        system = load(self.cfg.prompt_name)
        # The untrusted document is data inside delimiters; the prompt says instructions inside it are ignored.
        user = f"<document>\n{document_text[:12000]}\n</document>"
        body = {
            "model": self.cfg.model_name,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": InvoiceFields.model_json_schema(),
            "options": {"temperature": 0},
            "stream": False,
        }
        with timed_call("model", self.cfg.model_name, {"document_id": document_id}, data_class=self.cfg.data_class, mode=self.mode, prompt=self.cfg.prompt_name) as info:
            r = httpx.post(f"{self.cfg.ollama_url}/api/chat", json=body, timeout=timeout_s)
            r.raise_for_status()
            content = r.json()["message"]["content"]
            info["tokens_in"] = r.json().get("prompt_eval_count")
            info["tokens_out"] = r.json().get("eval_count")
            try:
                return InvoiceFields.model_validate(json.loads(content))
            except Exception:
                # one retry on a schema error, as the AI-engineering record's output guardrail allows
                r = httpx.post(f"{self.cfg.ollama_url}/api/chat", json=body, timeout=timeout_s)
                r.raise_for_status()
                return InvoiceFields.model_validate(json.loads(r.json()["message"]["content"]))


def model_for(cfg: Settings, labels: dict[str, dict] | None = None) -> Model:
    if cfg.model_mode == "replay":
        return ReplayModel(labels or {})
    if cfg.model_mode == "live":
        return OllamaModel(cfg)
    raise ValueError(f"unknown MODEL_MODE {cfg.model_mode!r}; expected live or replay")
