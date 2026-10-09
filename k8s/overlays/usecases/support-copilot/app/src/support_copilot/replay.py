"""The run Job (architecture workload replay-job): feeds the recorded conversations to the agent API in order."""

from __future__ import annotations

import httpx

from . import stores
from .config import settings
from .logging import log


def run_once() -> dict:
    cfg = settings()
    stores.ensure_schema()
    rows = stores.query("select conversation_id, chat_id, handle, messages from replay_set order by conversation_id")
    counts = {"conversations": 0, "messages": 0, "errors": 0}
    with httpx.Client(base_url=cfg.agent_url, timeout=cfg.turn_timeout_s + 10) as client:
        for r in rows:
            counts["conversations"] += 1
            for i, text in enumerate(r["messages"]):
                counts["messages"] += 1
                resp = client.post("/replay/turn", json={"conversation_id": r["conversation_id"], "chat_id": r["chat_id"], "message_id": str(i), "handle": r["handle"], "text": text})
                if resp.status_code != 200:
                    counts["errors"] += 1
                    stores.dead_letter(f"{r['chat_id']}:{i}", r["conversation_id"], "replay", f"agent returned {resp.status_code}")
    log("replay_done", data_class=cfg.data_class, **counts)
    return counts


def main() -> None:
    c = run_once()
    print(f"  Replayed {c['conversations']} conversations, {c['messages']} messages, {c['errors']} errors")


if __name__ == "__main__":
    main()
