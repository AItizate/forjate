"""The DSN survives any password, and the episodic upsert replaces exactly the columns it should."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit

import pytest

from invoice_intake.config import from_env
from invoice_intake.store import EVENT_UPSERT_SET


def test_a_password_with_url_characters_stays_one_field_of_the_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    placeholder = "p@ss:w/ord"
    monkeypatch.setenv("POSTGRES_USER", "app@corp")
    monkeypatch.setenv("POSTGRES_PASSWORD", placeholder)
    monkeypatch.setenv("POSTGRES_DB", "appdb")
    for name in ("POSTGRES_HOST", "POSTGRES_PORT", "WORKING_DATABASE_URL", "EPISODIC_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    for dsn in (from_env().working_dsn, from_env().episodic_dsn):
        parts = urlsplit(dsn)
        assert (parts.hostname, parts.port, parts.path) == ("postgres", 5432, "/appdb")
        assert unquote(parts.username or "") == "app@corp"
        assert unquote(parts.password or "") == placeholder


def test_the_episodic_upsert_clause_is_the_statement_it_replaced() -> None:
    columns = ("extraction", "literal", "match_result", "status", "model", "prompt", "tokens_in", "tokens_out", "duration_ms")
    assert EVENT_UPSERT_SET.split(", ") == [c + "=" + "EXCLUDED." + c for c in columns]
