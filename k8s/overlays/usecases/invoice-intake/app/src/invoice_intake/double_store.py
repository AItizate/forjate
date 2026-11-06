"""State behind the stubs of external systems, in its own schema: it stands in for what the real systems hold, so it survives a
pod restart and is no part of this use case's memory. A small key-value contract keeps both stubs readable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .store import Jsonb

if TYPE_CHECKING:
    import psycopg

DDL = """
CREATE SCHEMA IF NOT EXISTS doubles;
CREATE TABLE IF NOT EXISTS doubles.kv (ns text NOT NULL, key text NOT NULL, doc jsonb NOT NULL, PRIMARY KEY (ns, key));
CREATE TABLE IF NOT EXISTS doubles.counters (name text PRIMARY KEY, value bigint NOT NULL);
"""
_DDL_LOCK = 7421904


class DoubleKV(Protocol):
    def ping(self) -> None: ...
    def put_if_absent(self, ns: str, key: str, doc: dict) -> bool: ...
    def upsert_many(self, ns: str, docs: dict[str, dict]) -> None: ...
    def get(self, ns: str, key: str) -> dict | None: ...
    def page(self, ns: str, after_key: str, limit: int) -> list[dict]: ...
    def all_docs(self, ns: str) -> list[tuple[str, dict]]: ...
    def count(self, ns: str) -> int: ...
    def incr(self, name: str) -> None: ...
    def counter(self, name: str) -> int: ...


class PgKV:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._ready = False

    def _conn(self) -> "psycopg.Connection":
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self._dsn, row_factory=dict_row, connect_timeout=5)

    def ping(self) -> None:
        with self._conn() as conn:
            if not self._ready:
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (_DDL_LOCK,))
                conn.execute(DDL)
            conn.execute("SELECT 1")
        self._ready = True

    def put_if_absent(self, ns: str, key: str, doc: dict) -> bool:
        with self._conn() as conn:
            cur = conn.execute("INSERT INTO doubles.kv (ns,key,doc) VALUES (%s,%s,%s) ON CONFLICT (ns,key) DO NOTHING", (ns, key, Jsonb(doc)))
            return cur.rowcount == 1

    def upsert_many(self, ns: str, docs: dict[str, dict]) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO doubles.kv (ns,key,doc) VALUES (%s,%s,%s) ON CONFLICT (ns,key) DO UPDATE SET doc=EXCLUDED.doc",
                [(ns, key, Jsonb(doc)) for key, doc in docs.items()])

    def get(self, ns: str, key: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT doc FROM doubles.kv WHERE ns=%s AND key=%s", (ns, key)).fetchone()
            return row["doc"] if row else None

    def page(self, ns: str, after_key: str, limit: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT doc FROM doubles.kv WHERE ns=%s AND key>%s ORDER BY key LIMIT %s", (ns, after_key, limit)).fetchall()
            return [r["doc"] for r in rows]

    def all_docs(self, ns: str) -> list[tuple[str, dict]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT key,doc FROM doubles.kv WHERE ns=%s ORDER BY key", (ns,)).fetchall()
            return [(r["key"], r["doc"]) for r in rows]

    def count(self, ns: str) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT count(*) AS n FROM doubles.kv WHERE ns=%s", (ns,)).fetchone()["n"]

    def incr(self, name: str) -> None:
        with self._conn() as conn:
            conn.execute("INSERT INTO doubles.counters (name,value) VALUES (%s,1) ON CONFLICT (name) DO UPDATE SET value=doubles.counters.value+1", (name,))

    def counter(self, name: str) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM doubles.counters WHERE name=%s", (name,)).fetchone()
            return row["value"] if row else 0


class MemoryKV:
    def __init__(self) -> None:
        self.kv: dict[str, dict[str, dict]] = {}
        self.counters: dict[str, int] = {}

    def ping(self) -> None:
        return None

    def put_if_absent(self, ns: str, key: str, doc: dict) -> bool:
        table = self.kv.setdefault(ns, {})
        if key in table:
            return False
        table[key] = doc
        return True

    def upsert_many(self, ns: str, docs: dict[str, dict]) -> None:
        self.kv.setdefault(ns, {}).update(docs)

    def get(self, ns: str, key: str) -> dict | None:
        return self.kv.get(ns, {}).get(key)

    def page(self, ns: str, after_key: str, limit: int) -> list[dict]:
        table = self.kv.get(ns, {})
        return [table[k] for k in sorted(table) if k > after_key][:limit]

    def all_docs(self, ns: str) -> list[tuple[str, dict]]:
        table = self.kv.get(ns, {})
        return [(k, table[k]) for k in sorted(table)]

    def count(self, ns: str) -> int:
        return len(self.kv.get(ns, {}))

    def incr(self, name: str) -> None:
        self.counters[name] = self.counters.get(name, 0) + 1

    def counter(self, name: str) -> int:
        return self.counters.get(name, 0)
