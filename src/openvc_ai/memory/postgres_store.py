"""Postgres-backed persistent memory store.

This uses the same interface as the SQLite and in-memory stores, so the API can
switch to a hosted database by setting DATABASE_URL.
"""

from __future__ import annotations

import json
import threading

from psycopg import Connection
from psycopg.rows import dict_row

from openvc_ai.domain.models import MemoryRecord

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS memory_records (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL,
    tier        TEXT NOT NULL DEFAULT 'short'
);
CREATE INDEX IF NOT EXISTS idx_memory_session
    ON memory_records (session_id, tier, created_at);
CREATE INDEX IF NOT EXISTS idx_memory_tier
    ON memory_records (tier, created_at);
"""


class PostgresMemoryStore:
    """Thread-safe Postgres memory store with short-term and long-term tiers."""

    def __init__(self, database_url: str, max_records_per_session: int = 50) -> None:
        self.database_url = database_url
        self.max_records_per_session = max_records_per_session
        self._lock = threading.Lock()
        self._conn = Connection.connect(database_url, row_factory=dict_row)
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    def _row_to_record(self, row: dict) -> MemoryRecord:
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return MemoryRecord(
            record_id=row["id"],
            session_id=row["session_id"],
            kind=row["kind"],
            content=row["content"],
            metadata=metadata,
            created_at=row["created_at"],
        )

    def add(
        self,
        session_id: str,
        kind: str,
        content: str,
        metadata: dict | None = None,
    ) -> MemoryRecord:
        record = MemoryRecord(
            session_id=session_id,
            kind=kind,
            content=content,
            metadata=metadata or {},
        )
        with self._lock:
            with self._conn.transaction():
                self._conn.execute(
                    """
                    INSERT INTO memory_records
                        (id, session_id, kind, content, metadata, created_at, tier)
                    VALUES
                        (%s, %s, %s, %s, %s::jsonb, %s, 'short')
                    """,
                    (
                        record.record_id,
                        session_id,
                        kind,
                        content,
                        json.dumps(metadata or {}),
                        record.created_at,
                    ),
                )
                self._evict_session(session_id)
        return record

    def _evict_session(self, session_id: str) -> None:
        self._conn.execute(
            """
            DELETE FROM memory_records
            WHERE id IN (
                SELECT id
                FROM memory_records
                WHERE session_id = %s AND tier = 'short'
                ORDER BY created_at DESC
                OFFSET %s
            )
            """,
            (session_id, self.max_records_per_session),
        )

    def recent(self, session_id: str, limit: int = 10) -> list[MemoryRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT *
                FROM memory_records
                WHERE session_id = %s AND tier = 'short'
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (session_id, max(1, limit)),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS count FROM memory_records WHERE tier = 'short'"
            ).fetchone()
        return int(row["count"])

    def sessions(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT DISTINCT session_id
                FROM memory_records
                WHERE tier = 'short'
                ORDER BY session_id
                """
            ).fetchall()
        return [row["session_id"] for row in rows]

    def add_long_term(
        self,
        kind: str,
        content: str,
        metadata: dict | None = None,
    ) -> MemoryRecord:
        record = MemoryRecord(
            session_id="__long_term__",
            kind=kind,
            content=content,
            metadata=metadata or {},
        )
        with self._lock:
            with self._conn.transaction():
                self._conn.execute(
                    """
                    INSERT INTO memory_records
                        (id, session_id, kind, content, metadata, created_at, tier)
                    VALUES
                        (%s, '__long_term__', %s, %s, %s::jsonb, %s, 'long')
                    """,
                    (
                        record.record_id,
                        kind,
                        content,
                        json.dumps(metadata or {}),
                        record.created_at,
                    ),
                )
        return record

    def long_term_recent(self, limit: int = 50) -> list[MemoryRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT *
                FROM memory_records
                WHERE tier = 'long'
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (max(1, limit),),
            ).fetchall()
        return [self._row_to_record(row) for row in reversed(rows)]

    def long_term_count(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS count FROM memory_records WHERE tier = 'long'"
            ).fetchone()
        return int(row["count"])

    def search_long_term(self, query: str, limit: int = 10) -> list[MemoryRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT *
                FROM memory_records
                WHERE tier = 'long' AND content ILIKE %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (f"%{query}%", max(1, limit)),
            ).fetchall()
        return [self._row_to_record(row) for row in reversed(rows)]
