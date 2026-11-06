"""Configuration: environment variables only, read here and nowhere else.

Defaults match the Crawl overlay. Service names are the catalog's and resolve inside the namespace. Credentials come
from the component Secrets by the catalog's key names (POSTGRES_*, MINIO_ROOT_*). Execution bounds are the
ai-engineering record's Crawl values; the code enforces them, a prompt never does.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import quote

# One credential per tool (pack:regulated-corp#TOOLS). Revoking a Secret stops the tool.
TOOL_CREDENTIAL_ENV = {
    "list_mailbox_messages": "MAILBOX_LIST_TOKEN",
    "fetch_invoice_attachment": "MAILBOX_FETCH_TOKEN",
    "lookup_po": "ODOO_LOOKUP_PO_TOKEN",
    "find_payable": "ODOO_FIND_PAYABLE_TOKEN",
    "get_supplier_bank_ref": "ODOO_BANK_REF_TOKEN",
    "post_invoice": "ODOO_POST_INVOICE_TOKEN",
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _dsn(schema_env: str) -> str:
    """The DSN of one memory kind. Working and episodic have separate settings from Crawl (data-store R2), so the
    split at Walk changes configuration and not behaviour."""
    override = _env(schema_env)
    if override:
        return override
    # Encoded, because a password holding @, : or / would otherwise break the URL.
    user, password = quote(_env("POSTGRES_USER"), safe=""), quote(_env("POSTGRES_PASSWORD"), safe="")
    database = _env("POSTGRES_DB")
    host, port = _env("POSTGRES_HOST", "postgres"), _env("POSTGRES_PORT", "5432")
    return "postgresql://" + user + ":" + password + "@" + host + ":" + port + "/" + database


@dataclass(frozen=True)
class Settings:
    stage: str = "crawl"
    workload: str = "unknown"
    scope: str = "invoice-intake"
    source_scope: str = "invoice-intake"
    data_class: str = "financial"
    write_actions: str = "none"
    model_mode: str = "replay"
    model_id: str = "ollama/qwen2.5:7b-instruct"
    prompt_name: str = "extract/v1"
    ollama_url: str = "http://ollama-service:11434"
    docling_url: str = "http://docling:5001"
    odoo_url: str = "http://odoo-stub:8001"
    mailbox_url: str = "http://shared-imap-mailbox-stub:8001"
    mailbox: str = "shared"
    minio_endpoint: str = "minio:9000"
    minio_user: str = ""
    minio_password: str = ""
    working_dsn: str = ""
    episodic_dsn: str = ""
    bank_hash_salt: str = ""
    admin_token: str = ""
    credentials: dict[str, str] = field(default_factory=dict)
    max_steps: int = 10
    step_timeout_s: float = 600.0
    delegation_depth: int = 0
    budget_tokens: int = 8000
    max_model_calls: int = 2
    max_file_bytes: int = 10 * 1024 * 1024
    max_pdf_pages: int = 20
    ready_timeout_s: float = 300.0
    worker_passes: int = 2
    worker_from_start: bool = False
    item_delay_s: float = 0.0
    eval_limit_s: float = 10800.0


def from_env() -> Settings:
    scope = _env("SCOPE", "invoice-intake")
    return Settings(
        stage=_env("STAGE", "crawl"),
        workload=_env("WORKLOAD", "unknown"),
        scope=scope,
        source_scope=_env("SOURCE_SCOPE", scope),
        data_class=_env("DATA_CLASS", "financial"),
        write_actions=_env("WRITE_ACTIONS", "none"),
        model_mode=_env("MODEL_MODE", "replay"),
        model_id=_env("OLLAMA_MODEL", "ollama/qwen2.5:7b-instruct"),
        prompt_name=_env("PROMPT_NAME", "extract/v1"),
        ollama_url=_env("OLLAMA_URL", "http://ollama-service:11434"),
        docling_url=_env("DOCLING_URL", "http://docling:5001"),
        # ERP_URL is the name the Walk assembly patches onto every workload; the Crawl name is the double's.
        odoo_url=_env("ERP_URL") or _env("ODOO_URL", "http://odoo-stub:8001"),
        mailbox_url=_env("MAILBOX_URL", "http://shared-imap-mailbox-stub:8001"),
        mailbox=_env("MAILBOX_NAME", "shared"),
        minio_endpoint=_env("MINIO_ENDPOINT", "minio:9000"),
        minio_user=_env("MINIO_ROOT_USER"),
        minio_password=_env("MINIO_ROOT_PASSWORD"),
        working_dsn=_dsn("WORKING_DATABASE_URL"),
        episodic_dsn=_dsn("EPISODIC_DATABASE_URL"),
        bank_hash_salt=_env("BANK_HASH_SALT"),
        admin_token=_env("DOUBLE_ADMIN_TOKEN"),
        credentials={tool: _env(name) for tool, name in TOOL_CREDENTIAL_ENV.items()},
        max_steps=int(_env("MAX_STEPS", "10")),
        step_timeout_s=float(_env("STEP_TIMEOUT_S", "600")),
        delegation_depth=int(_env("DELEGATION_DEPTH", "0")),
        budget_tokens=int(_env("BUDGET_TOKENS", "8000")),
        max_model_calls=int(_env("MAX_MODEL_CALLS", "2")),
        max_file_bytes=int(_env("MAX_FILE_BYTES", str(10 * 1024 * 1024))),
        max_pdf_pages=int(_env("MAX_PDF_PAGES", "20")),
        ready_timeout_s=float(_env("READY_TIMEOUT_S", "300")),
        worker_passes=int(_env("WORKER_PASSES", "2")),
        worker_from_start=_env("WORKER_FROM_START") == "1",
        item_delay_s=float(_env("ITEM_DELAY_S", "0")),
        eval_limit_s=float(_env("EVAL_LIMIT_S", "10800")),
    )


_current: Settings | None = None


def get_settings() -> Settings:
    global _current
    if _current is None:
        _current = from_env()
    return _current


def set_settings(settings: Settings | None) -> None:
    """Tests and the verify Job's in-process steps replace the settings; nothing else calls this."""
    global _current
    _current = settings
