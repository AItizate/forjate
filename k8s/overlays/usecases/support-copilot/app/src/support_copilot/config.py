"""Configuration: environment variables only, read once. Defaults match the Crawl overlay."""

from __future__ import annotations

import os
from dataclasses import dataclass


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"{name} is not set")
    return value


@dataclass(frozen=True)
class Settings:
    pg_host: str = env("PGHOST", "postgres")
    pg_port: int = int(env("PGPORT", "5432"))
    pg_db: str = env("POSTGRES_DB", "appdb")
    pg_user: str = env("POSTGRES_USER", "app")
    pg_password: str = env("POSTGRES_PASSWORD", "")
    orders_url: str = env("ORDERS_URL", "http://orders-stub:8001")   # the stub at Crawl, the orders API at Walk
    orders_token: str = env("ORDERS_API_TOKEN", "")
    agent_url: str = env("AGENT_URL", "http://agent-api:8000")
    model_mode: str = env("MODEL_MODE", "live")                        # live | rules
    ollama_url: str = env("OLLAMA_URL", "http://ollama-service:11434")
    model_name: str = env("MODEL_NAME", "qwen2.5:7b")
    prompt_name: str = env("PROMPT_NAME", "support-v1")
    telegram_secret_token: str = env("TELEGRAM_SECRET_TOKEN", "")      # the webhook's api-key (Walk); unused by the replay
    # ASSUMED until the head of CS answers Q1 (allowed order fields shown in chat).
    allowed_fields: tuple[str, ...] = tuple(f for f in env("ALLOWED_ORDER_FIELDS", "status,eta,items_count").split(",") if f)
    max_tool_calls: int = int(env("MAX_TOOL_CALLS", "6"))
    turn_timeout_s: float = float(env("TURN_TIMEOUT_S", "20"))
    session_ttl_hours: int = int(env("SESSION_TTL_HOURS", "4"))
    data_class: str = env("DATA_CLASS", "pii")

    @property
    def dsn(self) -> str:
        return f"host={self.pg_host} port={self.pg_port} dbname={self.pg_db} user={self.pg_user} password={self.pg_password} application_name=support-copilot"


def settings() -> Settings:
    return Settings()
