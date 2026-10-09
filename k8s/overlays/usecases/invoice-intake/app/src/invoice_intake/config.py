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
    # Postgres: the component Secret postgres-secret is mounted with envFrom.
    pg_host: str = env("PGHOST", "postgres")
    pg_port: int = int(env("PGPORT", "5432"))
    pg_db: str = env("POSTGRES_DB", "appdb")
    pg_user: str = env("POSTGRES_USER", "app")
    pg_password: str = env("POSTGRES_PASSWORD", "")
    # MinIO (apps/minio/dev): credentials from minio-secret.
    minio_endpoint: str = env("MINIO_ENDPOINT", "minio:9000")
    minio_access_key: str = env("MINIO_ROOT_USER", "")
    minio_secret_key: str = env("MINIO_ROOT_PASSWORD", "")
    bucket_inbox: str = env("BUCKET_INBOX", "inbox")
    bucket_parsed: str = env("BUCKET_PARSED", "parsed")
    # Docling (apps/document-processing/docling).
    docling_url: str = env("DOCLING_URL", "http://docling:5001")
    # Model: live (Ollama) or replay (the seed's labels). CI runs replay.
    model_mode: str = env("MODEL_MODE", "live")
    ollama_url: str = env("OLLAMA_URL", "http://ollama-service:11434")
    model_name: str = env("MODEL_NAME", "qwen2.5:7b")
    prompt_name: str = env("PROMPT_NAME", "extract-v1")
    # ERP: the stub at Crawl, Odoo at Walk; credentials from odoo-api-secret.
    erp_url: str = env("ERP_URL", "http://erp-stub:8001")
    erp_token: str = env("ODOO_API_TOKEN", "")
    # Security record: data class for the log line; approval secret for the token.
    data_class: str = env("DATA_CLASS", "financial")
    approval_secret: str = env("APPROVAL_SECRET", "replay-approval-secret")
    seed_size: int = int(env("SEED_SIZE", "20"))

    @property
    def dsn(self) -> str:
        return f"host={self.pg_host} port={self.pg_port} dbname={self.pg_db} user={self.pg_user} password={self.pg_password} application_name=invoice-intake"


def settings() -> Settings:
    return Settings()
