"""Postgres (working and episodic memory) and MinIO (artifacts), per the data-store record.

Tables: purchase_orders (the seeded ERP fixture the stub serves), invoices (processed items keyed by the
PDF sha, the idempotency table), review_queue (the exception path), invoice_decisions (episodic: one row
per invoice with the extracted fields and the decision), erp_postings / erp_rejections (what the stub
received), event_log (every structured log line, so the verify Job can grep without pod access),
labels (the seed's ground truth the replay model reads and the verify Job scores against)."""

from __future__ import annotations

import io
import json
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from minio import Minio
from psycopg.rows import dict_row

from .config import settings

SCHEMA = """
create table if not exists purchase_orders (po_number text primary key, supplier text not null, amount_cents bigint not null, bank_account text);
create table if not exists labels (document_id text primary key, fields jsonb not null);
create table if not exists invoices (idempotency_key text primary key, document_id text not null, invoice_number text, supplier text,
  reason text not null, straight_through boolean not null, processed_at timestamptz not null default now());
create table if not exists review_queue (idempotency_key text primary key, invoice_id text not null, reason text not null, item jsonb not null,
  created_at timestamptz not null default now());
create table if not exists invoice_decisions (idempotency_key text primary key, document_id text not null, extracted jsonb, po jsonb, reason text not null,
  straight_through boolean not null, decided_at timestamptz not null default now());
create table if not exists erp_postings (idempotency_key text primary key, posting_id text not null, invoice_id text not null, invoice_number text not null,
  supplier text not null, amount_cents bigint not null, po_number text not null, received_at timestamptz not null default now());
create table if not exists erp_rejections (id serial primary key, invoice_id text, reason text not null, received_at timestamptz not null default now());
create table if not exists event_log (id serial primary key, line jsonb not null, logged_at timestamptz not null default now());
create unique index if not exists invoices_number_supplier on invoices (invoice_number, supplier) where reason <> 'duplicate' and invoice_number is not null;
"""


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    with psycopg.connect(settings().dsn, row_factory=dict_row, autocommit=True) as conn:
        yield conn


def ensure_schema() -> None:
    wait_ready()
    with connect() as c:
        c.execute(SCHEMA)


def reset() -> None:
    wait_ready()
    with connect() as c:
        for t in ("event_log", "erp_rejections", "erp_postings", "invoice_decisions", "review_queue", "invoices", "labels", "purchase_orders"):
            c.execute(f"drop table if exists {t} cascade")
        c.execute(SCHEMA)


def query(sql: str, *params: Any) -> list[dict]:
    with connect() as c:
        return list(c.execute(sql, params).fetchall())


def scalar(sql: str, *params: Any) -> Any:
    rows = query(sql, *params)
    return next(iter(rows[0].values())) if rows else None


def upsert_review(key: str, item: dict) -> bool:
    with connect() as c:
        r = c.execute("insert into review_queue (idempotency_key, invoice_id, reason, item) values (%s, %s, %s, %s) on conflict (idempotency_key) do nothing",
                      (key, item["invoice_id"], item["reason"], json.dumps(item)))
        return r.rowcount == 1


def record_invoice(key: str, document_id: str, fields: dict | None, reason: str, straight_through: bool, po: dict | None) -> bool:
    with connect() as c:
        r = c.execute("insert into invoices (idempotency_key, document_id, invoice_number, supplier, reason, straight_through) values (%s, %s, %s, %s, %s, %s) on conflict do nothing",
                      (key, document_id, (fields or {}).get("invoice_number"), (fields or {}).get("supplier"), reason, straight_through))
        if r.rowcount == 1:
            safe = dict(fields or {}); safe.pop("bank_account", None)
            c.execute("insert into invoice_decisions (idempotency_key, document_id, extracted, po, reason, straight_through) values (%s, %s, %s, %s, %s, %s) on conflict do nothing",
                      (key, document_id, json.dumps(safe) if fields else None, json.dumps(po) if po else None, reason, straight_through))
        return r.rowcount == 1


def labels() -> dict[str, dict]:
    return {r["document_id"]: r["fields"] for r in query("select document_id, fields from labels")}


def log_event(line: dict) -> None:
    with connect() as c:
        c.execute("insert into event_log (line) values (%s)", (json.dumps(line, default=str),))


# ---------------------------------------------------------------- MinIO

def minio_client(timeout_s: float = 180.0) -> Minio:
    """MinIO answers (the dev Pod has no readiness probe)."""
    import time
    cfg = settings()
    client = Minio(cfg.minio_endpoint, access_key=cfg.minio_access_key, secret_key=cfg.minio_secret_key, secure=False)
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            client.list_buckets()
            return client
        except Exception:
            if time.monotonic() > deadline:
                raise
            time.sleep(2)


def ensure_bucket(client: Minio, name: str, *, empty: bool = False) -> None:
    if not client.bucket_exists(name):
        client.make_bucket(name)
    elif empty:
        for obj in list(client.list_objects(name, recursive=True)):
            client.remove_object(name, obj.object_name)


def put_object(client: Minio, bucket: str, name: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    client.put_object(bucket, name, io.BytesIO(data), len(data), content_type=content_type)


def get_object(client: Minio, bucket: str, name: str) -> bytes:
    resp = client.get_object(bucket, name)
    try:
        return resp.read()
    finally:
        resp.close(); resp.release_conn()


def list_objects(client: Minio, bucket: str, suffix: str = "") -> list[str]:
    return sorted(o.object_name for o in client.list_objects(bucket, recursive=True) if o.object_name.endswith(suffix))

def wait_ready(timeout_s: float = 180.0) -> None:
    """Postgres accepts connections (the component's readiness probe says ready before the DB does)."""
    import time
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            with connect() as c:
                c.execute("select 1")
            return
        except Exception:
            if time.monotonic() > deadline:
                raise
            time.sleep(2)
