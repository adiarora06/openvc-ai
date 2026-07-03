"""Simple session-scoped memory store with short-term and long-term tiers.

Short-term memory is session-scoped and bounded.
Long-term memory persists across sessions (in-memory for now, durable adapter later).
"""

from __future__ import annotations

from collections import defaultdict, deque

from openvc_ai.domain.models import MemoryRecord


class InMemoryMemoryStore:
    def __init__(self, max_records_per_session: int = 50) -> None:
        self.max_records_per_session = max_records_per_session
        self._records: dict[str, deque[MemoryRecord]] = defaultdict(
            lambda: deque(maxlen=max_records_per_session)
        )
        self._long_term: list[MemoryRecord] = []

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
        self._records[session_id].append(record)
        return record

    def recent(self, session_id: str, limit: int = 10) -> list[MemoryRecord]:
        records = list(self._records.get(session_id, []))
        return records[-max(1, limit) :]

    def count(self) -> int:
        return sum(len(records) for records in self._records.values())

    def sessions(self) -> list[str]:
        return sorted(self._records.keys())

    # Long-term memory

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
        self._long_term.append(record)
        return record

    def long_term_recent(self, limit: int = 50) -> list[MemoryRecord]:
        return self._long_term[-max(1, limit) :]

    def long_term_count(self) -> int:
        return len(self._long_term)

    def search_long_term(self, query: str, limit: int = 10) -> list[MemoryRecord]:
        query_lower = query.lower()
        matches = [r for r in self._long_term if query_lower in r.content.lower()]
        return matches[-limit:]
