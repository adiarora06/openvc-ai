"""Market data and news adapters with shared HTTP client, caching, and retries."""

import asyncio
from datetime import date, datetime, timedelta, timezone

import httpx
import pandas as pd

from openvc_ai.adapters.cache import TTLCache
from openvc_ai.config.logging_config import get_logger
from openvc_ai.config.settings import settings
from openvc_ai.domain.models import DependencyHealth, NewsItem, PricePoint, ProviderStatus

logger = get_logger(__name__)

# Shared, lazily-created async HTTP client reused across requests (connection pooling).
_http_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


async def get_http_client() -> httpx.AsyncClient:
    """Return a shared AsyncClient, creating it on first use."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        async with _client_lock:
            if _http_client is None or _http_client.is_closed:
                _http_client = httpx.AsyncClient(
                    timeout=settings.request_timeout_seconds,
                    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                    headers={"User-Agent": "OpenVC-AI/0.1.0"},
                    verify=False,
                )
    return _http_client


async def close_http_client() -> None:
    """Close the shared client (called on application shutdown)."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None


async def _get_with_retry(
    url: str, params: dict, *, retries: int = 2, backoff: float = 0.75
) -> httpx.Response:
    """GET with simple exponential backoff for transient failures."""
    client = await get_http_client()
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            # Do not retry deterministic client errors (except rate limiting).
            if status is not None and status < 500 and status != 429:
                raise
            if attempt < retries:
                await asyncio.sleep(backoff * (2**attempt))
    assert last_exc is not None
    raise last_exc


def _demo_price_points(ticker: str, days: int = 120) -> list[PricePoint]:
    """Deterministic synthetic prices used when demo mode is enabled."""
    today = datetime.now(timezone.utc).date()
    base = 80.0 + (sum(ord(ch) for ch in ticker.upper()) % 90)
    points: list[PricePoint] = []
    for i in range(days):
        d = today - timedelta(days=days - i)
        trend = 1.0 + (i / max(days, 1)) * 0.08
        cycle = ((i % 11) - 5) * 0.004
        close = round(base * trend * (1.0 + cycle), 2)
        points.append(PricePoint(timestamp=d, close=close))
    return points


def _demo_news_items(ticker: str) -> list[NewsItem]:
    now = datetime.now(timezone.utc)
    return [
        NewsItem(
            headline=f"{ticker.upper()} posts steady operating momentum in demo data",
            summary="Synthetic demo item: revenue and margin discussion appears constructive, but real news requires a Finnhub key.",
            source="OpenVC demo",
            published_at=now - timedelta(days=1),
        ),
        NewsItem(
            headline=f"Analysts debate valuation sensitivity for {ticker.upper()}",
            summary="Synthetic demo item: valuation risk remains sensitive to rates, earnings revisions, and sector momentum.",
            source="OpenVC demo",
            published_at=now - timedelta(days=3),
        ),
    ]


class AlphaVantageMarketDataAdapter:
    """Daily price data via Alpha Vantage with TTL caching."""

    _cache: TTLCache[list[PricePoint]] = TTLCache(ttl_seconds=settings.cache_ttl_seconds)

    async def daily_prices(self, ticker: str, outputsize: str = "compact") -> list[PricePoint]:
        ticker = ticker.upper()
        if not settings.alpha_vantage_api_key:
            if settings.demo_mode:
                return _demo_price_points(ticker)
            raise RuntimeError("ALPHA_VANTAGE_API_KEY is not configured")

        cache_key = f"prices:{ticker}:{outputsize}"

        async def _fetch() -> list[PricePoint]:
            params = {
                "function": "TIME_SERIES_DAILY",
                "symbol": ticker,
                "outputsize": outputsize,
                "apikey": settings.alpha_vantage_api_key,
            }
            response = await _get_with_retry("https://www.alphavantage.co/query", params)
            data = response.json()

            series = data.get("Time Series (Daily)")
            if not series:
                message = data.get("Note") or data.get("Error Message") or str(data)[:300]
                raise RuntimeError(f"Alpha Vantage returned no daily series: {message}")

            points = [
                PricePoint(timestamp=date.fromisoformat(day), close=float(values["4. close"]))
                for day, values in series.items()
            ]
            return sorted(points, key=lambda p: p.timestamp)

        try:
            return await self._cache.get_or_compute(cache_key, _fetch)
        except Exception:
            if settings.demo_mode:
                logger.warning("Alpha Vantage unavailable; falling back to demo prices for %s", ticker)
                return _demo_price_points(ticker)
            raise

    async def health(self) -> DependencyHealth:
        if not settings.alpha_vantage_api_key:
            if settings.demo_mode:
                return DependencyHealth(
                    name="alpha_vantage",
                    status=ProviderStatus.OK,
                    detail="Demo mode: synthetic daily prices are enabled",
                )
            return DependencyHealth(
                name="alpha_vantage",
                status=ProviderStatus.NOT_CONFIGURED,
                detail="ALPHA_VANTAGE_API_KEY missing",
            )
        return DependencyHealth(name="alpha_vantage", status=ProviderStatus.OK)


class FinnhubNewsAdapter:
    """Company news via Finnhub with TTL caching."""

    _cache: TTLCache[list[NewsItem]] = TTLCache(ttl_seconds=settings.cache_ttl_seconds)

    async def company_news(self, ticker: str, days_back: int = 14) -> list[NewsItem]:
        ticker = ticker.upper()
        if not settings.finnhub_api_key:
            if settings.demo_mode:
                return _demo_news_items(ticker)
            raise RuntimeError("FINNHUB_API_KEY is not configured")

        cache_key = f"news:{ticker}:{days_back}"

        async def _fetch() -> list[NewsItem]:
            today = datetime.now(timezone.utc).date()
            params = {
                "symbol": ticker,
                "from": (today - timedelta(days=days_back)).isoformat(),
                "to": today.isoformat(),
                "token": settings.finnhub_api_key,
            }
            response = await _get_with_retry("https://finnhub.io/api/v1/company-news", params)
            data = response.json()

            items: list[NewsItem] = []
            for item in data[:20]:
                published_at = None
                if item.get("datetime"):
                    published_at = datetime.fromtimestamp(item["datetime"], tz=timezone.utc)
                items.append(
                    NewsItem(
                        headline=item.get("headline", ""),
                        summary=item.get("summary"),
                        source=item.get("source"),
                        url=item.get("url"),
                        published_at=published_at,
                    )
                )
            return items

        try:
            return await self._cache.get_or_compute(cache_key, _fetch)
        except Exception:
            if settings.demo_mode:
                logger.warning("Finnhub unavailable; falling back to demo news for %s", ticker)
                return _demo_news_items(ticker)
            raise

    async def health(self) -> DependencyHealth:
        if not settings.finnhub_api_key:
            if settings.demo_mode:
                return DependencyHealth(
                    name="finnhub",
                    status=ProviderStatus.OK,
                    detail="Demo mode: synthetic company news is enabled",
                )
            return DependencyHealth(
                name="finnhub",
                status=ProviderStatus.NOT_CONFIGURED,
                detail="FINNHUB_API_KEY missing",
            )
        return DependencyHealth(name="finnhub", status=ProviderStatus.OK)


def price_points_to_frame(points: list[PricePoint]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"date": p.timestamp, "close": p.close} for p in points]
    ).sort_values("date")
