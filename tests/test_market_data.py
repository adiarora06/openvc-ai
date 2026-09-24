import pytest

from openvc_ai.adapters import market_data
from openvc_ai.adapters.market_data import AlphaVantageMarketDataAdapter
from openvc_ai.config.settings import settings


@pytest.mark.asyncio
async def test_shared_http_client_uses_default_tls_verification(monkeypatch):
    created_with: list[dict] = []

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            created_with.append(kwargs)
            self.is_closed = False

        async def aclose(self):
            self.is_closed = True

    monkeypatch.setattr(market_data.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(market_data, "_http_client", None)

    first = await market_data.get_http_client()
    second = await market_data.get_http_client()

    assert first is second
    assert len(created_with) == 1
    assert "verify" not in created_with[0]

    await market_data.close_http_client()
    assert first.is_closed is True
    assert market_data._http_client is None


@pytest.mark.asyncio
async def test_quote_returns_marked_demo_data_without_key(monkeypatch):
    monkeypatch.setattr(settings, "alpha_vantage_api_key", None)
    monkeypatch.setattr(settings, "demo_mode", True)

    quote = await AlphaVantageMarketDataAdapter().quote("amzn")

    assert quote["ticker"] == "AMZN"
    assert quote["source"] == "demo"
    assert quote["current"] > 0
    assert quote["previous"] > 0


@pytest.mark.asyncio
async def test_quote_requires_key_when_demo_disabled(monkeypatch):
    monkeypatch.setattr(settings, "alpha_vantage_api_key", None)
    monkeypatch.setattr(settings, "demo_mode", False)

    with pytest.raises(RuntimeError, match="ALPHA_VANTAGE_API_KEY"):
        await AlphaVantageMarketDataAdapter().quote("amzn")
