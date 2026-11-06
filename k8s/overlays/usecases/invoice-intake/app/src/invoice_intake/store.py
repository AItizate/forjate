"""Working and episodic memory. Two schemas on one Postgres at Crawl, reached through separate connection settings and never
joined or sharing a transaction, so the split into two databases at Walk changes configuration only (data-store R2).
Every row carries the project scope tag.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import psycopg


def Jsonb(value: Any) -> Any:  # noqa: N802 - psycopg's name; the driver loads only where a real database is used
    from psycopg.types.json import Jsonb as wrapper
    return wrapper(value)


WORKING_DDL = """
CREATE SCHEMA IF NOT EXISTS working;
CREATE TABLE IF NOT EXISTS working.items (
  scope text NOT NULL, key text NOT NULL, mailbox text NOT NULL, uid bigint NOT NULL, uidvalidity bigint NOT NULL,
  message_id text, attachment_index int NOT NULL, filename text, sender text, received_at text, sha256 text NOT NULL,
  object_key text, state text NOT NULL, reason text, failed_step text, payable_key text, recommendation jsonb,
  first_pass int NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (scope, key));
CREATE TABLE IF NOT EXISTS working.review_queue (
  scope text NOT NULL, key text NOT NULL, reason text NOT NULL, failed_step text, fields jsonb NOT NULL,
  linked_key text, context jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (scope, key));
CREATE TABLE IF NOT EXISTS working.cursors (
  scope text NOT NULL, mailbox text NOT NULL, uidvalidity bigint NOT NULL, last_uid bigint NOT NULL, PRIMARY KEY (scope, mailbox));
CREATE TABLE IF NOT EXISTS working.passes (
  scope text NOT NULL, pass_no int NOT NULL, from_start boolean NOT NULL, items_seen int NOT NULL DEFAULT 0, rows_added int NOT NULL DEFAULT 0,
  states_changed int NOT NULL DEFAULT 0, review_added int NOT NULL DEFAULT 0, finished boolean NOT NULL DEFAULT false, PRIMARY KEY (scope, pass_no));
"""

EPISODIC_DDL = """
CREATE SCHEMA IF NOT EXISTS episodic;
CREATE TABLE IF NOT EXISTS episodic.invoice_events (
  scope text NOT NULL, key text NOT NULL, extraction jsonb, literal jsonb, match_result jsonb, status text NOT NULL,
  model text, prompt text, tokens_in int, tokens_out int, duration_ms int, recorded_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (scope, key));
CREATE TABLE IF NOT EXISTS episodic.run_trace (seq bigserial PRIMARY KEY, scope text NOT NULL, line text NOT NULL);
"""

# What a repeated episodic write replaces; the key columns stay.
EVENT_UPDATE_COLUMNS = ("extraction", "literal", "match_result", "status", "model", "prompt", "tokens_in", "tokens_out", "duration_ms")
EVENT_UPSERT_SET = ", ".join(f"{column}=EXCLUDED.{column}" for column in EVENT_UPDATE_COLUMNS)

# Serialises concurrent DDL of the seed, the worker and the verify Job.
_DDL_LOCK = 7421903


class Store(Protocol):
    def init(self) -> None: ...
    def get_item(self, scope: str, key: str) -> dict | None: ...
    def add_item(self, scope: str, key: str, row: dict[str, Any], pass_no: int) -> bool: ...
    def set_payable_key(self, scope: str, key: str, payable: str) -> None: ...
    def earlier_with_payable(self, scope: str, payable: str, uid: int, attachment_index: int) -> str | None: ...
    def finish_item(self, scope: str, key: str, *, state: str, reason: str | None, failed_step: str | None, recommendation: dict | None,
                    fields: list[str], linked_key: str | None, context: list[dict] | None) -> bool: ...
    def record_event(self, scope: str, key: str, event: dict[str, Any]) -> None: ...
    def get_cursor(self, scope: str, mailbox: str) -> tuple[int, int] | None: ...
    def set_cursor(self, scope: str, mailbox: str, uidvalidity: int, last_uid: int) -> None: ...
    def begin_pass(self, scope: str, from_start: bool) -> int: ...
    def finish_pass(self, scope: str, pass_no: int, stats: dict[str, int]) -> None: ...
    def append_trace(self, scope: str, lines: list[str]) -> None: ...
    def items(self, scope: str) -> list[dict]: ...
    def review(self, scope: str) -> list[dict]: ...
    def events(self, scope: str) -> list[dict]: ...
    def passes(self, scope: str) -> list[dict]: ...
    def trace(self, scope: str) -> list[str]: ...
    def drop_scope(self, scope: str) -> None: ...


class PgStore:
    def __init__(self, working_dsn: str, episodic_dsn: str) -> None:
        self._w, self._e = working_dsn, episodic_dsn

    def _conn(self, dsn: str) -> "psycopg.Connection":
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10)

    def init(self) -> None:
        for dsn, ddl in ((self._w, WORKING_DDL), (self._e, EPISODIC_DDL)):
            with self._conn(dsn) as conn:
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (_DDL_LOCK,))
                conn.execute(ddl)

    def get_item(self, scope: str, key: str) -> dict | None:
        with self._conn(self._w) as conn:
            return conn.execute("SELECT * FROM working.items WHERE scope=%s AND key=%s", (scope, key)).fetchone()

    def add_item(self, scope: str, key: str, row: dict[str, Any], pass_no: int) -> bool:
        with self._conn(self._w) as conn:
            cur = conn.execute(
                """INSERT INTO working.items (scope,key,mailbox,uid,uidvalidity,message_id,attachment_index,filename,sender,received_at,
                   sha256,object_key,state,first_pass) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'processing',%s)
                   ON CONFLICT (scope,key) DO NOTHING""",
                (scope, key, row["mailbox"], row["uid"], row["uidvalidity"], row["message_id"], row["attachment_index"], row["filename"],
                 row["sender"], row["received_at"], row["sha256"], row["object_key"], pass_no))
            return cur.rowcount == 1

    def set_payable_key(self, scope: str, key: str, payable: str) -> None:
        with self._conn(self._w) as conn:
            conn.execute("UPDATE working.items SET payable_key=%s WHERE scope=%s AND key=%s", (payable, scope, key))

    def earlier_with_payable(self, scope: str, payable: str, uid: int, attachment_index: int) -> str | None:
        with self._conn(self._w) as conn:
            row = conn.execute(
                """SELECT key FROM working.items WHERE scope=%s AND payable_key=%s AND (uid,attachment_index) < (%s,%s)
                   ORDER BY uid,attachment_index LIMIT 1""", (scope, payable, uid, attachment_index)).fetchone()
            return row["key"] if row else None

    def finish_item(self, scope: str, key: str, *, state: str, reason: str | None, failed_step: str | None, recommendation: dict | None,
                    fields: list[str], linked_key: str | None, context: list[dict] | None) -> bool:
        with self._conn(self._w) as conn, conn.transaction():
            added = False
            if context is not None:
                cur = conn.execute(
                    """INSERT INTO working.review_queue (scope,key,reason,failed_step,fields,linked_key,context) VALUES (%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (scope,key) DO NOTHING""",
                    (scope, key, reason, failed_step, Jsonb(fields), linked_key, Jsonb(context)))
                added = cur.rowcount == 1
            conn.execute(
                """UPDATE working.items SET state=%s,reason=%s,failed_step=%s,recommendation=%s,updated_at=now() WHERE scope=%s AND key=%s""",
                (state, reason, failed_step, Jsonb(recommendation) if recommendation is not None else None, scope, key))
            return added

    def record_event(self, scope: str, key: str, event: dict[str, Any]) -> None:
        with self._conn(self._e) as conn:
            conn.execute(
                """INSERT INTO episodic.invoice_events (scope,key,extraction,literal,match_result,status,model,prompt,tokens_in,tokens_out,duration_ms)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (scope,key) DO UPDATE SET """ + EVENT_UPSERT_SET,
                (scope, key, Jsonb(event.get("extraction")), Jsonb(event.get("literal")), Jsonb(event.get("match_result")), event["status"],
                 event.get("model"), event.get("prompt"), event.get("tokens_in"), event.get("tokens_out"), event.get("duration_ms")))

    def get_cursor(self, scope: str, mailbox: str) -> tuple[int, int] | None:
        with self._conn(self._w) as conn:
            row = conn.execute("SELECT uidvalidity,last_uid FROM working.cursors WHERE scope=%s AND mailbox=%s", (scope, mailbox)).fetchone()
            return (row["uidvalidity"], row["last_uid"]) if row else None

    def set_cursor(self, scope: str, mailbox: str, uidvalidity: int, last_uid: int) -> None:
        with self._conn(self._w) as conn:
            conn.execute(
                """INSERT INTO working.cursors (scope,mailbox,uidvalidity,last_uid) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (scope,mailbox) DO UPDATE SET uidvalidity=EXCLUDED.uidvalidity,last_uid=EXCLUDED.last_uid""",
                (scope, mailbox, uidvalidity, last_uid))

    def begin_pass(self, scope: str, from_start: bool) -> int:
        with self._conn(self._w) as conn:
            row = conn.execute(
                """INSERT INTO working.passes (scope,pass_no,from_start)
                   SELECT %s, COALESCE(MAX(pass_no),0)+1, %s FROM working.passes WHERE scope=%s RETURNING pass_no""",
                (scope, from_start, scope)).fetchone()
            return row["pass_no"]

    def finish_pass(self, scope: str, pass_no: int, stats: dict[str, int]) -> None:
        with self._conn(self._w) as conn:
            conn.execute(
                """UPDATE working.passes SET items_seen=%s,rows_added=%s,states_changed=%s,review_added=%s,finished=true WHERE scope=%s AND pass_no=%s""",
                (stats["items_seen"], stats["rows_added"], stats["states_changed"], stats["review_added"], scope, pass_no))

    def append_trace(self, scope: str, lines: list[str]) -> None:
        if not lines:
            return
        with self._conn(self._e) as conn, conn.cursor() as cur:
            cur.executemany("INSERT INTO episodic.run_trace (scope,line) VALUES (%s,%s)", [(scope, line) for line in lines])

    def _all(self, dsn: str, sql: str, scope: str) -> list[dict]:
        with self._conn(dsn) as conn:
            return conn.execute(sql, (scope,)).fetchall()

    def items(self, scope: str) -> list[dict]:
        return self._all(self._w, "SELECT * FROM working.items WHERE scope=%s ORDER BY uid,attachment_index", scope)

    def review(self, scope: str) -> list[dict]:
        return self._all(self._w, "SELECT * FROM working.review_queue WHERE scope=%s ORDER BY key", scope)

    def events(self, scope: str) -> list[dict]:
        return self._all(self._e, "SELECT * FROM episodic.invoice_events WHERE scope=%s ORDER BY key", scope)

    def passes(self, scope: str) -> list[dict]:
        return self._all(self._w, "SELECT * FROM working.passes WHERE scope=%s ORDER BY pass_no", scope)

    def trace(self, scope: str) -> list[str]:
        return [r["line"] for r in self._all(self._e, "SELECT line FROM episodic.run_trace WHERE scope=%s ORDER BY seq", scope)]

    def drop_scope(self, scope: str) -> None:
        with self._conn(self._w) as conn:
            for table in ("items", "review_queue", "cursors", "passes"):
                conn.execute(f"DELETE FROM working.{table} WHERE scope=%s", (scope,))
        with self._conn(self._e) as conn:
            for table in ("invoice_events", "run_trace"):
                conn.execute(f"DELETE FROM episodic.{table} WHERE scope=%s", (scope,))


class MemoryStore:
    """The same contract in memory, for tests without a cluster."""

    def __init__(self) -> None:
        self.t: dict[str, dict] = {"items": {}, "review": {}, "cursors": {}, "passes": {}, "events": {}}
        self._trace: dict[str, list[str]] = {}

    def init(self) -> None:
        return None

    def get_item(self, scope: str, key: str) -> dict | None:
        return self.t["items"].get((scope, key))

    def add_item(self, scope: str, key: str, row: dict[str, Any], pass_no: int) -> bool:
        if (scope, key) in self.t["items"]:
            return False
        self.t["items"][(scope, key)] = {**row, "scope": scope, "key": key, "state": "processing", "reason": None, "failed_step": None,
                                         "payable_key": None, "recommendation": None, "first_pass": pass_no}
        return True

    def set_payable_key(self, scope: str, key: str, payable: str) -> None:
        self.t["items"][(scope, key)]["payable_key"] = payable

    def earlier_with_payable(self, scope: str, payable: str, uid: int, attachment_index: int) -> str | None:
        rows = [r for r in self.items(scope) if r["payable_key"] == payable and (r["uid"], r["attachment_index"]) < (uid, attachment_index)]
        return rows[0]["key"] if rows else None

    def finish_item(self, scope: str, key: str, *, state: str, reason: str | None, failed_step: str | None, recommendation: dict | None,
                    fields: list[str], linked_key: str | None, context: list[dict] | None) -> bool:
        added = False
        if context is not None and (scope, key) not in self.t["review"]:
            self.t["review"][(scope, key)] = {"scope": scope, "key": key, "reason": reason, "failed_step": failed_step, "fields": fields,
                                              "linked_key": linked_key, "context": json.loads(json.dumps(context))}
            added = True
        self.t["items"][(scope, key)].update(state=state, reason=reason, failed_step=failed_step, recommendation=recommendation)
        return added

    def record_event(self, scope: str, key: str, event: dict[str, Any]) -> None:
        self.t["events"][(scope, key)] = {"scope": scope, "key": key, **event}

    def get_cursor(self, scope: str, mailbox: str) -> tuple[int, int] | None:
        return self.t["cursors"].get((scope, mailbox))

    def set_cursor(self, scope: str, mailbox: str, uidvalidity: int, last_uid: int) -> None:
        self.t["cursors"][(scope, mailbox)] = (uidvalidity, last_uid)

    def begin_pass(self, scope: str, from_start: bool) -> int:
        number = len(self.passes(scope)) + 1
        self.t["passes"][(scope, number)] = {"scope": scope, "pass_no": number, "from_start": from_start, "items_seen": 0, "rows_added": 0,
                                             "states_changed": 0, "review_added": 0, "finished": False}
        return number

    def finish_pass(self, scope: str, pass_no: int, stats: dict[str, int]) -> None:
        self.t["passes"][(scope, pass_no)].update(stats, finished=True)

    def append_trace(self, scope: str, lines: list[str]) -> None:
        self._trace.setdefault(scope, []).extend(lines)

    def _scoped(self, table: str, scope: str) -> list[dict]:
        return [dict(v) for k, v in self.t[table].items() if k[0] == scope]

    def items(self, scope: str) -> list[dict]:
        return sorted(self._scoped("items", scope), key=lambda r: (r["uid"], r["attachment_index"]))

    def review(self, scope: str) -> list[dict]:
        return sorted(self._scoped("review", scope), key=lambda r: r["key"])

    def events(self, scope: str) -> list[dict]:
        return sorted(self._scoped("events", scope), key=lambda r: r["key"])

    def passes(self, scope: str) -> list[dict]:
        return sorted(self._scoped("passes", scope), key=lambda r: r["pass_no"])

    def trace(self, scope: str) -> list[str]:
        return list(self._trace.get(scope, []))

    def drop_scope(self, scope: str) -> None:
        for table in self.t.values():
            for key in [k for k in table if k[0] == scope]:
                del table[key]
        self._trace.pop(scope, None)
