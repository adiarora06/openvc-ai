from datetime import date, timedelta

import pytest

from openvc_ai.agents.forecasting import QuantForecastAgent
from openvc_ai.agents.orchestrator import CentralA2AOrchestrator
from openvc_ai.domain.models import ForecastRequest, NewsItem, PricePoint


class FakeMarketData:
    async def daily_prices(self, ticker, outputsize="compact"):
        start = date(2024, 1, 1)
        return [PricePoint(timestamp=start + timedelta(days=i), close=100 + i * 0.5) for i in range(60)]


class FailingMarketData:
    async def daily_prices(self, ticker, outputsize="compact"):
        raise RuntimeError("upstream down")


class FakeNews:
    async def company_news(self, ticker, days_back=14):
        return [NewsItem(headline="Company beats earnings", summary="Strong quarter")]


class FailingNews:
    async def company_news(self, ticker, days_back=14):
        raise RuntimeError("news provider down")


class FakeNewsAgent:
    async def analyze(self, ticker, news):
        return "Bullish: earnings beat. Bearish: none. Unknown: macro."


class FakeMemoAgent:
    async def write_memo(self, forecast, news_analysis):
        return "MEMO: cautious optimism."


def _orchestrator(market=None, news=None, memo=None):
    return CentralA2AOrchestrator(
        market_data=market or FakeMarketData(),
        news_data=news or FakeNews(),
        quant_agent=QuantForecastAgent(),
        news_agent=FakeNewsAgent(),
        memo_agent=memo,
    )


@pytest.mark.asyncio
async def test_forecast_happy_path():
    orch = _orchestrator()
    result = await orch.forecast_stock(ForecastRequest(ticker="NVDA", horizon_days=10))
    assert result.ticker == "NVDA"
    assert result.current_price > 0
    assert result.news_analysis is not None
    assert result.forecast_series and len(result.forecast_series) == 10
    assert result.elapsed_ms is not None


@pytest.mark.asyncio
async def test_news_failure_does_not_block_forecast():
    orch = _orchestrator(news=FailingNews())
    result = await orch.forecast_stock(ForecastRequest(ticker="NVDA", horizon_days=5))
    assert result.current_price > 0
    assert any("News analysis unavailable" in n for n in result.data_notes)


@pytest.mark.asyncio
async def test_price_failure_raises():
    orch = _orchestrator(market=FailingMarketData())
    with pytest.raises(RuntimeError):
        await orch.forecast_stock(ForecastRequest(ticker="NVDA", horizon_days=5))


@pytest.mark.asyncio
async def test_memo_included_when_requested():
    orch = _orchestrator(memo=FakeMemoAgent())
    result = await orch.forecast_stock(
        ForecastRequest(ticker="NVDA", horizon_days=5, include_memo=True)
    )
    assert result.investment_memo == "MEMO: cautious optimism."


@pytest.mark.asyncio
async def test_news_skipped_when_disabled():
    orch = _orchestrator()
    result = await orch.forecast_stock(
        ForecastRequest(ticker="NVDA", horizon_days=5, include_news=False)
    )
    assert result.news_analysis == "News analysis was not requested."
