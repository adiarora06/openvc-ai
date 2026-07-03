"""SQLite-backed persistent memory store.

Provides the same interface as InMemoryMemoryStore but survives server restarts.
Short-term records are session-scoped and capped; long-term records are unbounded.
The database file is created next to this module by default, overridable via
the MEMORY_DB_PATH environment variable.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from openvc_ai.domain.models import MemoryRecord

_DEFAULT_DB_PATH = Path(os.environ.get("MEMORY_DB_PATH", Path(__file__).parent / "memory.db"))

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS memory_records (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    tier        TEXT NOT NULL DEFAULT 'short'
);
CREATE INDEX IF NOT EXISTS idx_session ON memory_records (session_id, tier, created_at);
CREATE INDEX IF NOT EXISTS idx_tier    ON memory_records (tier, created_at);
"""


class SQLiteMemoryStore:
    """Thread-safe SQLite memory store with short-term and long-term tiers."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        max_records_per_session: int = 50,
    ) -> None:
        self.db_path = Path(db_path or _DEFAULT_DB_PATH)
        self.max_records_per_session = max_records_per_session
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_CREATE_TABLE)

    # ------------------------------------------------------------------ helpers

    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        import json

        return MemoryRecord(
            record_id=row["id"],
            session_id=row["session_id"],
            kind=row["kind"],
            content=row["content"],
            metadata=json.loads(row["metadata"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ------------------------------------------------------------------ short-term

    def add(
        self,
        session_id: str,
        kind: str,
        content: str,
        metadata: dict | None = None,
    ) -> MemoryRecord:
        import json

        record = MemoryRecord(
            session_id=session_id,
            kind=kind,
            content=content,
            metadata=metadata or {},
        )
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO memory_records (id, session_id, kind, content, metadata, created_at, tier) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'short')",
                    (
                        record.record_id,
                        session_id,
                        kind,
                        content,
                        json.dumps(metadata or {}),
                        record.created_at.isoformat(),
                    ),
                )
            # Evict oldest records beyond the per-session cap
            self._evict_session(session_id)
        return record

    def _evict_session(self, session_id: str) -> None:
        rows = self._conn.execute(
            "SELECT id FROM memory_records WHERE session_id=? AND tier='short' "
            "ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        if len(rows) > self.max_records_per_session:
            excess = [r["id"] for r in rows[: len(rows) - self.max_records_per_session]]
            with self._conn:
                self._conn.execute(
                    f"DELETE FROM memory_records WHERE id IN ({','.join('?' * len(excess))})",
                    excess,
                )

    def recent(self, session_id: str, limit: int = 10) -> list[MemoryRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM memory_records WHERE session_id=? AND tier='short' "
                "ORDER BY created_at ASC LIMIT ?",
                (session_id, max(1, limit)),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def count(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM memory_records WHERE tier='short'"
            ).fetchone()[0]

    def sessions(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT session_id FROM memory_records WHERE tier='short' ORDER BY session_id"
            ).fetchall()
        return [r["session_id"] for r in rows]

    # ------------------------------------------------------------------ long-term

    def add_long_term(
        self,
        kind: str,
        content: str,
        metadata: dict | None = None,
    ) -> MemoryRecord:
        import json

        record = MemoryRecord(
            session_id="__long_term__",
            kind=kind,
            content=content,
            metadata=metadata or {},
        )
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO memory_records (id, session_id, kind, content, metadata, created_at, tier) "
                    "VALUES (?, '__long_term__', ?, ?, ?, ?, 'long')",
                    (
                        record.record_id,
                        kind,
                        content,
                        json.dumps(metadata or {}),
                        record.created_at.isoformat(),
                    ),
                )
        return record

    def long_term_recent(self, limit: int = 50) -> list[MemoryRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM memory_records WHERE tier='long' ORDER BY created_at DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [self._row_to_record(r) for r in reversed(rows)]

    def long_term_count(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM memory_records WHERE tier='long'"
            ).fetchone()[0]

    def search_long_term(self, query: str, limit: int = 10) -> list[MemoryRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM memory_records WHERE tier='long' AND content LIKE ? "
                "ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", max(1, limit)),
            ).fetchall()
        return [self._row_to_record(r) for r in reversed(rows)]
