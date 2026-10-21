from __future__ import annotations

from pathlib import Path

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"


def load(name: str) -> str:
    path = PROMPTS / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"prompt {name} not found under {PROMPTS}")
    return path.read_text()
