"""The model behind a Protocol: a live Ollama classifier and a deterministic rules double (MODEL_MODE=rules).

CI runs the rules double so the verify Job measures routing, escalation, idempotency and the field filter;
MODEL_MODE=live is the same loop against the local model, the run the resolution rate is read from."""

from __future__ import annotations

import json
from typing import Protocol

import httpx

from .config import Settings, settings
from .domain import ANGER, Classification, Intent, extract_order_id
from .logging import timed_call
from .prompts import load


class Model(Protocol):
    mode: str

    def classify(self, conversation_id: str, text: str, *, timeout_s: float = 20.0) -> Classification: ...


RULES = [
    (Intent.REFUND, ("refund", "money back", "reimburse")),
    (Intent.CANCELLATION, ("cancel",)),
    (Intent.SUBSCRIPTION_RENEWAL, ("renew", "renewal")),
    (Intent.PAYMENT_METHOD, ("payment method", "card on file", "pay with")),
    (Intent.SUBSCRIPTION_STATUS, ("subscription", "plan")),
    (Intent.DELIVERY_ETA, ("when will", "eta", "arrive", "delivery date", "how long")),
    (Intent.ITEMS_IN_ORDER, ("what is in", "items", "contents", "what did i order")),
    (Intent.CHANGE_ADDRESS, ("change the address", "change my address", "new address", "wrong address")),
    (Intent.INVOICE_COPY, ("invoice", "receipt")),
    (Intent.RETURN_POLICY, ("return policy", "return it", "send it back", "returns")),
    (Intent.OPENING_HOURS, ("opening hours", "open on", "what time do you open", "business hours")),
    (Intent.ORDER_STATUS, ("status", "where is my order", "track", "shipped")),
]


class RulesModel:
    """Keyword intents over the same tool loop as the live model: a test double, not a product."""
    mode = "rules"

    def classify(self, conversation_id: str, text: str, *, timeout_s: float = 20.0) -> Classification:
        low = text.lower()
        with timed_call("model", "rules", {"conversation_id": conversation_id}, data_class=settings().data_class, mode=self.mode, prompt=settings().prompt_name):
            intent = next((i for i, kws in RULES if any(k in low for k in kws)), Intent.UNKNOWN)
            return Classification(intent=intent, order_id=extract_order_id(text), angry=ANGER.search(text) is not None)


class OllamaModel:
    mode = "live"

    def __init__(self, cfg: Settings | None = None):
        self.cfg = cfg or settings()

    def classify(self, conversation_id: str, text: str, *, timeout_s: float = 20.0) -> Classification:
        body = {
            "model": self.cfg.model_name,
            "messages": [{"role": "system", "content": load(self.cfg.prompt_name)}, {"role": "user", "content": f"<message>\n{text[:4000]}\n</message>"}],
            "format": Classification.model_json_schema(),
            "options": {"temperature": 0},
            "stream": False,
        }
        with timed_call("model", self.cfg.model_name, {"conversation_id": conversation_id}, data_class=self.cfg.data_class, mode=self.mode, prompt=self.cfg.prompt_name) as info:
            r = httpx.post(f"{self.cfg.ollama_url}/api/chat", json=body, timeout=timeout_s)
            r.raise_for_status()
            info["tokens_in"] = r.json().get("prompt_eval_count"); info["tokens_out"] = r.json().get("eval_count")
            c = Classification.model_validate(json.loads(r.json()["message"]["content"]))
            c.order_id = extract_order_id(text) or c.order_id  # the id comes from the text, never invented
            return c


def model_for(cfg: Settings) -> Model:
    if cfg.model_mode == "rules":
        return RulesModel()
    if cfg.model_mode == "live":
        return OllamaModel(cfg)
    raise ValueError(f"unknown MODEL_MODE {cfg.model_mode!r}; expected live or rules")
