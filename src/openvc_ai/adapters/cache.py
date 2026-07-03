"""Lightweight async-safe in-memory TTL cache."""

import asyncio
import time
from typing import Any, Awaitable, Callable, Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """A minimal thread/async-safe TTL cache with single-flight semantics.

    Concurrent callers requesting the same missing key await a single
    underlying computation rather than triggering duplicate fetches
    (which matters for rate-limited upstream APIs).
    """

    def __init__(self, ttl_seconds: float):
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, T]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    def _is_fresh(self, expires_at: float) -> bool:
        return time.monotonic() < expires_at

    async def get_or_compute(self, key: str, compute: Callable[[], Awaitable[T]]) -> T:
        cached = self._store.get(key)
        if cached and self._is_fresh(cached[0]):
            return cached[1]

        async with self._guard:
            lock = self._locks.setdefault(key, asyncio.Lock())

        async with lock:
            # Re-check after acquiring the per-key lock (another coroutine may have filled it).
            cached = self._store.get(key)
            if cached and self._is_fresh(cached[0]):
                return cached[1]

            value = await compute()
            self._store[key] = (time.monotonic() + self._ttl, value)
            return value

    def invalidate(self, key: str | None = None) -> None:
        if key is None:
            self._store.clear()
        else:
            self._store.pop(key, None)

    def stats(self) -> dict[str, Any]:
        now = time.monotonic()
        fresh = sum(1 for expires_at, _ in self._store.values() if now < expires_at)
        return {"entries": len(self._store), "fresh": fresh, "ttl_seconds": self._ttl}
