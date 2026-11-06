"""What every tool shares: typed errors, the argument hash, the log line, bounded HTTP, and the execution bounds."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel

from .config import Settings, get_settings
from .logs import emit

T = TypeVar("T")


# ---------------------------------------------------------------- typed errors; never an empty result
class ToolError(Exception):
    code = "tool-error"


class ToolNotFound(ToolError):
    code = "not-found"


class ToolUnavailable(ToolError):
    code = "unavailable"


class ToolTimeout(ToolUnavailable):
    code = "timeout"


class ToolUnauthorized(ToolError):
    code = "unauthorized"


class ResultTooLarge(ToolError):
    code = "result-too-large"


class AttachmentOutOfBounds(ToolError):
    code = "attachment-out-of-bounds"


class ApprovalRequired(ToolError):
    code = "approval-required"


class OutOfPolicy(ToolError):
    code = "out-of-policy"


class PausedRefusal(ToolError):
    """A stop is a wait, not a failure: typed and never retried (ai-engineering guardrail, from Walk)."""

    code = "paused"


class BoundExceeded(Exception):
    """An execution bound was passed: the attempt stops and the item goes to the AP clerk with reason=timeout."""

    def __init__(self, bound: str, step: str) -> None:
        super().__init__(f"{bound} exceeded at {step}")
        self.bound = bound
        self.step = step


# ---------------------------------------------------------------- the log line
def args_hash(args: BaseModel) -> str:
    canonical = json.dumps(args.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@contextmanager
def timed_call(tool: str, args: BaseModel, **extra: object) -> Iterator[None]:
    """Tool name, argument hash, caller, data class, duration and outcome. Argument values never."""
    started = time.monotonic()
    outcome = "ok"
    try:
        yield
    except ToolError as exc:
        outcome = exc.code
        raise
    except Exception as exc:
        outcome = type(exc).__name__
        raise
    finally:
        emit("tool_call", tool=tool, args_hash=args_hash(args),
             duration_ms=int((time.monotonic() - started) * 1000), outcome=outcome, **extra)


# ---------------------------------------------------------------- bounded HTTP
class HttpClient(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response: ...


_clients: dict[str, HttpClient] = {}
_factory: Callable[[str], HttpClient] | None = None


def _base_url(system: str, settings: Settings) -> str:
    return {"odoo": settings.odoo_url, "mailbox": settings.mailbox_url}[system]


def set_client_factory(factory: Callable[[str], HttpClient] | None) -> None:
    """Tests point the tools at the stubs' ASGI apps. The real client and the stub share the same routes."""
    global _factory
    _factory = factory
    _clients.clear()


def _client(system: str) -> HttpClient:
    if _factory is not None:
        return _factory(system)
    if system not in _clients:
        _clients[system] = httpx.Client(base_url=_base_url(system, get_settings()))
    return _clients[system]


def call_system(
    system: str, tool: str | None, method: str, path: str, *, timeout_s: float, max_bytes: int = 1_000_000,
    token: str | None = None, **kwargs: Any,
) -> httpx.Response:
    """One HTTP call under the tool's own credential, its timeout and its result bound."""
    settings = get_settings()
    bearer = token if token is not None else settings.credentials.get(tool or "", "")
    if not bearer:
        raise ToolUnauthorized(f"no credential configured for {tool or system}")
    headers = {**kwargs.pop("headers", {}), "Authorization": f"Bearer {bearer}"}
    try:
        response = _client(system).request(method, path, headers=headers, timeout=timeout_s, **kwargs)
    except httpx.TimeoutException as exc:
        raise ToolTimeout(f"{system} timed out") from exc
    except httpx.TransportError as exc:
        raise ToolUnavailable(f"{system} unreachable") from exc
    if response.status_code in (401, 403):
        raise ToolUnauthorized(f"{system} refused the credential")
    if response.status_code == 404:
        raise ToolNotFound(f"{system}: not found")
    if response.status_code >= 500:
        raise ToolUnavailable(f"{system} answered {response.status_code}")
    if response.status_code >= 400:
        raise ToolError(f"{system} answered {response.status_code}")
    if len(response.content) > max_bytes:
        raise ResultTooLarge(f"{system}: result over {max_bytes} bytes")
    return response


# ---------------------------------------------------------------- execution bounds
@dataclass(frozen=True)
class Bounds:
    max_steps: int
    step_timeout_s: float
    delegation_depth: int
    budget_tokens: int
    max_model_calls: int

    @classmethod
    def of(cls, settings: Settings) -> "Bounds":
        return cls(settings.max_steps, settings.step_timeout_s, settings.delegation_depth,
                   settings.budget_tokens, settings.max_model_calls)


class Attempt:
    """One invoice's attempt. Enforced in code, and passing a bound stops the attempt, never a retry."""

    def __init__(self, bounds: Bounds, *, depth: int = 0) -> None:
        self.bounds = bounds
        self.steps = 0
        self.model_calls = 0
        if depth > bounds.delegation_depth:
            raise BoundExceeded("delegation_depth", "start")

    def step(self, name: str, fn: Callable[[], T]) -> T:
        self.steps += 1
        if self.steps > self.bounds.max_steps:
            raise BoundExceeded("max_steps", name)
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(fn)
        try:
            return future.result(timeout=self.bounds.step_timeout_s)
        except FuturesTimeout:
            if future.done():  # the step's own timeout error, not this bound
                raise
            raise BoundExceeded("step_timeout_s", name) from None
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def model_call(self, step: str, tokens: int) -> None:
        if self.model_calls >= self.bounds.max_model_calls:
            raise BoundExceeded("max_model_calls", step)
        if tokens > self.bounds.budget_tokens:
            raise BoundExceeded("budget_tokens", step)
        self.model_calls += 1
