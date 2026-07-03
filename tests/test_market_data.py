import pytest

from openvc_ai.adapters.market_data import AlphaVantageMarketDataAdapter
from openvc_ai.config.settings import settings


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
