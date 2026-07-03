import asyncio

import pytest

from openvc_ai.adapters.cache import TTLCache


@pytest.mark.asyncio
async def test_cache_returns_cached_value():
    cache: TTLCache[int] = TTLCache(ttl_seconds=60)
    calls = {"n": 0}

    async def compute():
        calls["n"] += 1
        return 42

    assert await cache.get_or_compute("k", compute) == 42
    assert await cache.get_or_compute("k", compute) == 42
    assert calls["n"] == 1  # second call served from cache


@pytest.mark.asyncio
async def test_cache_single_flight():
    cache: TTLCache[int] = TTLCache(ttl_seconds=60)
    calls = {"n": 0}

    async def compute():
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return 7

    results = await asyncio.gather(
        *(cache.get_or_compute("same", compute) for _ in range(10))
    )
    assert results == [7] * 10
    assert calls["n"] == 1  # only one underlying computation


@pytest.mark.asyncio
async def test_cache_expiry():
    cache: TTLCache[int] = TTLCache(ttl_seconds=0.01)
    calls = {"n": 0}

    async def compute():
        calls["n"] += 1
        return calls["n"]

    assert await cache.get_or_compute("k", compute) == 1
    await asyncio.sleep(0.05)
    assert await cache.get_or_compute("k", compute) == 2


def test_cache_invalidate():
    cache: TTLCache[int] = TTLCache(ttl_seconds=60)
    cache._store["a"] = (float("inf"), 1)
    cache._store["b"] = (float("inf"), 2)
    cache.invalidate("a")
    assert "a" not in cache._store
    assert "b" in cache._store
    cache.invalidate()
    assert cache._store == {}
