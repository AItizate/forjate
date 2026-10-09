"""Postgres: the orders fixture the stub serves, the replay set with its labels, session and working memory,
the episodic outcomes the KPI query reads, the escalations queue, dead letters, the stub's call log and the
event log (so the verify Job can grep without pod access)."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from .config import settings

SCHEMA = """
create table if not exists customers (customer_id text primary key, handle text unique not null, name text not null, email text not null, phone text not null);
create table if not exists orders (order_id text primary key, customer_id text not null, status text not null, eta text not null, items_count int not null, total_cents bigint not null, address text not null);
create table if not exists subscriptions (customer_id text primary key, plan text not null, status text not null, renews_on text not null, payment_method text not null);
create table if not exists replay_set (conversation_id text primary key, chat_id text not null, handle text, kind text not null, intent text, order_id text, injection boolean not null default false, messages jsonb not null);
create table if not exists processed_messages (message_key text primary key, conversation_id text not null, reply text, processed_at timestamptz not null default now());
create table if not exists sessions (chat_id text primary key, state jsonb not null, expires_at timestamptz not null);
create table if not exists conversation_outcomes (conversation_id text primary key, outcome text not null, reason text, intent text, replies jsonb not null, feedback text, updated_at timestamptz not null default now());
create table if not exists escalations (idempotency_key text primary key, conversation_id text not null, customer_id text, transcript jsonb not null, order_id text, reason text not null, created_at timestamptz not null default now());
create table if not exists dead_letters (message_key text primary key, conversation_id text not null, stage text not null, reason text not null, created_at timestamptz not null default now());
create table if not exists orders_stub_calls (id serial primary key, method text not null, path text not null, called_at timestamptz not null default now());
create table if not exists event_log (id serial primary key, line jsonb not null, logged_at timestamptz not null default now());
"""


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    with psycopg.connect(settings().dsn, row_factory=dict_row, autocommit=True) as conn:
        yield conn


def ensure_schema() -> None:
    with connect() as c:
        c.execute(SCHEMA)


def reset() -> None:
    with connect() as c:
        for t in ("event_log", "orders_stub_calls", "dead_letters", "escalations", "conversation_outcomes", "sessions", "processed_messages", "replay_set", "subscriptions", "orders", "customers"):
            c.execute(f"drop table if exists {t} cascade")
        c.execute(SCHEMA)


def query(sql: str, *params: Any) -> list[dict]:
    with connect() as c:
        return list(c.execute(sql, params).fetchall())


def scalar(sql: str, *params: Any) -> Any:
    rows = query(sql, *params)
    return next(iter(rows[0].values())) if rows else None


def execute(sql: str, *params: Any) -> int:
    with connect() as c:
        return c.execute(sql, params).rowcount


def log_event(line: dict) -> None:
    execute("insert into event_log (line) values (%s)", json.dumps(line, default=str))


def upsert_escalation(key: str, conversation_id: str, customer_id: str | None, transcript: list[str], order_id: str | None, reason: str) -> bool:
    return execute("insert into escalations (idempotency_key, conversation_id, customer_id, transcript, order_id, reason) values (%s, %s, %s, %s, %s, %s) on conflict (idempotency_key) do nothing",
                   key, conversation_id, customer_id, json.dumps(transcript), order_id, reason) == 1


def seen_reply(message_key: str) -> str | None:
    rows = query("select reply from processed_messages where message_key = %s", message_key)
    return rows[0]["reply"] if rows else None


def mark_processed(message_key: str, conversation_id: str, reply: str) -> None:
    execute("insert into processed_messages (message_key, conversation_id, reply) values (%s, %s, %s) on conflict do nothing", message_key, conversation_id, reply)


def session(chat_id: str) -> dict:
    rows = query("select state from sessions where chat_id = %s and expires_at > now()", chat_id)
    return rows[0]["state"] if rows else {"transcript": [], "unresolved_turns": 0, "escalated": None}


def save_session(chat_id: str, state: dict, ttl_hours: int) -> None:
    execute("insert into sessions (chat_id, state, expires_at) values (%s, %s, now() + make_interval(hours => %s)) on conflict (chat_id) do update set state = excluded.state, expires_at = excluded.expires_at",
            chat_id, json.dumps(state), ttl_hours)


def record_outcome(conversation_id: str, outcome: str, reason: str | None, intent: str | None, reply: str) -> None:
    execute("""insert into conversation_outcomes (conversation_id, outcome, reason, intent, replies) values (%s, %s, %s, %s, %s)
               on conflict (conversation_id) do update set outcome = excluded.outcome, reason = coalesce(excluded.reason, conversation_outcomes.reason),
               intent = coalesce(excluded.intent, conversation_outcomes.intent), replies = conversation_outcomes.replies || excluded.replies, updated_at = now()""",
            conversation_id, outcome, reason, intent, json.dumps([reply]))


def dead_letter(message_key: str, conversation_id: str, stage: str, reason: str) -> None:
    execute("insert into dead_letters (message_key, conversation_id, stage, reason) values (%s, %s, %s, %s) on conflict do nothing", message_key, conversation_id, stage, reason)


def customer_by_handle(handle: str | None) -> str | None:
    if not handle:
        return None
    return scalar("select customer_id from customers where handle = %s", handle)
