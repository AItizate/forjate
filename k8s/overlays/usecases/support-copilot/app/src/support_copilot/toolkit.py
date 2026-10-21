"""Shared pieces of the tool contract: typed errors and the timed log line."""

from __future__ import annotations

from .logging import timed_call  # re-exported for the tools

__all__ = ["ToolError", "NotFound", "timed_call"]


class ToolError(Exception):
    """A typed error the model can act on; never an empty result."""


class NotFound(ToolError):
    pass
