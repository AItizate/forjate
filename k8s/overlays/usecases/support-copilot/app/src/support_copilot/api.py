"""The agent API (architecture workload agent-api): the Telegram webhook at Walk, the replay route at Crawl."""

from __future__ import annotations

import hmac

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import stores
from .agent import Agent, Incoming
from .config import settings
from .logging import add_sink

app = FastAPI(title="agent-api")
_agent: Agent | None = None


def agent() -> Agent:
    global _agent
    if _agent is None:
        stores.ensure_schema()
        add_sink(stores.log_event)
        _agent = Agent()
    return _agent


class Turn(BaseModel):
    conversation_id: str
    chat_id: str
    message_id: str
    handle: str | None = None
    text: str


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/readyz")
def readyz() -> dict:
    stores.scalar("select 1")
    return {"ok": True}


@app.post("/replay/turn")
def replay_turn(turn: Turn) -> dict:
    """Crawl: the replay Job drives the same loop the webhook uses."""
    r = agent().handle(Incoming(turn.conversation_id, turn.chat_id, turn.message_id, turn.handle, turn.text))
    return {"reply": r.text, "outcome": r.outcome, "reason": r.reason, "intent": r.intent}


@app.post("/webhook/telegram")
def telegram_webhook(update: dict, x_telegram_bot_api_secret_token: str = Header(default="")) -> dict:
    """Walk: Telegram calls this through the tunnel; the secret token header is the api-key the architecture names."""
    cfg = settings()
    if not cfg.telegram_secret_token or not hmac.compare_digest(x_telegram_bot_api_secret_token, cfg.telegram_secret_token):
        raise HTTPException(status_code=403, detail="missing or invalid secret token")
    message = update.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))
    sender = (message.get("from") or {}).get("username")
    r = agent().handle(Incoming(conversation_id=chat_id, chat_id=chat_id, message_id=str(message.get("message_id", "")), handle=sender, text=message.get("text", "")))
    # The reply is sent back through the Bot API by the caller of this handler at Walk (sendMessage with a typing indicator first).
    return {"method": "sendMessage", "chat_id": chat_id, "text": r.text, "outcome": r.outcome}


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
