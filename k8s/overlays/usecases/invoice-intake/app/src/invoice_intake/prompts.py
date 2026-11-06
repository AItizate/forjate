"""Prompts are files under app/prompts/, loaded by name (extract/v1), never literals in code."""

from __future__ import annotations

import os
from pathlib import Path

EXAMPLES_MARKER = "<!-- examples:"


def _root() -> Path:
    configured = os.environ.get("PROMPTS_DIR")
    return Path(configured) if configured else Path(__file__).resolve().parents[2] / "prompts"


def load(name: str) -> str:
    return (_root() / f"{name}.md").read_text(encoding="utf-8")


def without_examples(prompt: str) -> str:
    """The context strategy's first cut when a request would pass the token ceiling."""
    return prompt.split(EXAMPLES_MARKER, 1)[0].rstrip() + "\n"


def estimate_tokens(text: str) -> int:
    """About four characters per token: enough for a ceiling checked before the call."""
    return len(text) // 4 + 1


def document_block(masked_text: str) -> str:
    """Untrusted text reaches the model as data, inside one delimited block whose delimiter it cannot close."""
    safe = masked_text.replace("</document>", "[/document]").replace("<document>", "[document]")
    return f"<document>\n{safe}\n</document>"
