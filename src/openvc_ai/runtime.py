"""Application runtime: singletons, agent bootup, tools, memory, and status checks."""

from __future__ import annotations

import asyncio
import time
from datetime import date, timedelta
from typing import Any

from openvc_ai import __version__
from openvc_ai.adapters.market_data import (
    AlphaVantageMarketDataAdapter,
    FinnhubNewsAdapter,
    price_points_to_frame,
)
from openvc_ai.a2a.planner import CapabilityPlanner
from openvc_ai.a2a.tasks import InMemoryTaskStore
from openvc_ai.agents.forecasting import QuantForecastAgent
from openvc_ai.agents.memo import InvestmentMemoAgent
from openvc_ai.agents.news import NewsAnalysisAgent
from openvc_ai.agents.orchestrator import CentralA2AOrchestrator
from openvc_ai.agents.registry import InMemoryAgentRegistry, default_registry
from openvc_ai.config.logging_config import get_logger
from openvc_ai.config.settings import settings
from openvc_ai.domain.models import (
    AgentStatus,
    DependencyHealth,
    ForecastResult,
    BacktestRequest,
    BacktestResult,
    NewsItem,
    PricePoint,
    ProviderStatus,
    SystemStatus,
    ToolSpec,
)
from openvc_ai.llm.adapters import (
    FallbackLLMRouter,
    GroqLLMAdapter,
    MockLLMAdapter,
    OpenAILLMAdapter,
)
from openvc_ai.evaluation.backtesting import ForecastBacktester
from openvc_ai.memory.in_memory import InMemoryMemoryStore
from openvc_ai.memory.postgres_store import PostgresMemoryStore
from openvc_ai.memory.sqlite_store import SQLiteMemoryStore
from openvc_ai.tools.local import LocalToolRegistry

logger = get_logger(__name__)


class AppRuntime:
    """Holds shared singletons and performs parallel bootup of all agents."""

    def __init__(self) -> None:
        self.started_at: float = time.monotonic()
        self.registry: InMemoryAgentRegistry = default_registry()
        self.memory = self._build_memory_store()
        self.task_store = InMemoryTaskStore()

        # LLM routing. Real providers are used when configured; otherwise the app
        # can run locally with MockLLMAdapter while demo_mode is enabled.
        self.llm_router = self._build_llm_router()

        # Data adapters (shared, cached, demo-capable when no keys are configured).
        self.market_data = AlphaVantageMarketDataAdapter()
        self.news_data = FinnhubNewsAdapter()

        # Agents.
        self.quant_agent = QuantForecastAgent()
        self.backtester = ForecastBacktester(self.quant_agent)
        self.news_agent = NewsAnalysisAgent(self.llm_router)
        self.memo_agent = InvestmentMemoAgent(self.llm_router)

        # Tools and planner.
        self.tools = LocalToolRegistry()
        self._register_tools()
        self.planner = CapabilityPlanner(self.registry, self.tools)

        # Orchestrator wires everything together.
        self.orchestrator = CentralA2AOrchestrator(
            market_data=self.market_data,
            news_data=self.news_data,
            quant_agent=self.quant_agent,
            news_agent=self.news_agent,
            memo_agent=self.memo_agent,
            registry=self.registry,
            tools=self.tools,
            planner=self.planner,
            task_store=self.task_store,
            memory=self.memory,
        )

    def _build_memory_store(self):
        if settings.database_url:
            try:
                logger.info("Using Postgres memory store")
                return PostgresMemoryStore(settings.database_url)
            except Exception:
                logger.exception("Postgres memory store unavailable, falling back to SQLite")

        try:
            logger.info("Using SQLite memory store")
            return SQLiteMemoryStore()
        except Exception:
            logger.warning("SQLite memory store unavailable, using in-memory fallback")
            return InMemoryMemoryStore()

    def _build_llm_router(self) -> FallbackLLMRouter:
        if settings.groq_api_key:
            primary = GroqLLMAdapter()
            fallback = OpenAILLMAdapter() if settings.openai_api_key else None
        elif settings.openai_api_key:
            primary = OpenAILLMAdapter()
            fallback = None
        elif settings.demo_mode:
            primary = MockLLMAdapter()
            fallback = None
        else:
            primary = GroqLLMAdapter()
            fallback = OpenAILLMAdapter() if settings.openai_api_key else None
        return FallbackLLMRouter(primary=primary, fallback=fallback)

    def _register_tools(self) -> None:
        self.tools.register(
            ToolSpec(
                name="price_history",
                description="Fetch daily historical close prices for a ticker.",
                capabilities=["price_history", "market_data"],
                input_schema={"ticker": "str", "outputsize": "compact|full"},
                output_schema={"points": "list[{timestamp, close}]"},
            ),
            self._price_history_tool,
        )
        self.tools.register(
            ToolSpec(
                name="company_news",
                description="Fetch recent company news for a ticker.",
                capabilities=["company_news", "market_news"],
                input_schema={"ticker": "str", "days_back": "int"},
                output_schema={"items": "list[NewsItem]"},
            ),
            self._company_news_tool,
        )
        self.tools.register(
            ToolSpec(
                name="quant_forecast",
                description="Run a Monte Carlo forecast using provided price history.",
                capabilities=["price_forecast", "monte_carlo"],
                input_schema={"prices": "list[PricePoint]", "horizon_days": "int"},
                output_schema={"forecast": "dict"},
            ),
            self._quant_forecast_tool,
        )
        self.tools.register(
            ToolSpec(
                name="news_analysis",
                description="Summarize bullish, bearish, and unknown market-impact factors.",
                capabilities=["news_summary", "sentiment_analysis", "risk_extraction"],
                input_schema={"ticker": "str", "news": "list[NewsItem]"},
                output_schema={"analysis": "str"},
            ),
            self._news_analysis_tool,
        )
        self.tools.register(
            ToolSpec(
                name="investment_memo",
                description="Write a cautious investment memo from a forecast and news analysis.",
                capabilities=["memo_generation", "risk_disclosure"],
                input_schema={"forecast": "ForecastResult", "news_analysis": "str"},
                output_schema={"memo": "str"},
            ),
            self._investment_memo_tool,
        )

    async def _price_history_tool(self, ticker: str, outputsize: str = "compact") -> list[dict]:
        points = await self.market_data.daily_prices(ticker, outputsize=outputsize)
        return [point.model_dump(mode="json") for point in points]

    async def backtest_forecast_model(self, request: BacktestRequest) -> BacktestResult:
        start_date: date | None = None
        end_date: date | None = None
        if request.start_date or request.end_date:
            eval_start = request.start_date or (date.today() - timedelta(days=180))
            eval_end = request.end_date or date.today()
            start_date = eval_start - timedelta(days=max(request.training_window_days * 3, 120))
            end_date = eval_end + timedelta(days=max(request.horizon_days * 3, 14))
        points = await self.market_data.historical_prices(request.ticker, start_date, end_date)
        frame = price_points_to_frame(points)
        return await asyncio.to_thread(self.backtester.run, frame, request)

    async def _company_news_tool(self, ticker: str, days_back: int = 14) -> list[dict]:
        items = await self.news_data.company_news(ticker, days_back=days_back)
        return [item.model_dump(mode="json") for item in items]

    async def _quant_forecast_tool(self, prices: list[dict], horizon_days: int) -> dict[str, Any]:
        points = [PricePoint(**point) for point in prices]
        frame = price_points_to_frame(points)
        return await asyncio.to_thread(self.quant_agent.forecast, frame, horizon_days)

    async def _news_analysis_tool(self, ticker: str, news: list[dict]) -> str:
        items = [NewsItem(**item) for item in news]
        return await self.news_agent.analyze(ticker, items)

    async def _investment_memo_tool(self, forecast: dict, news_analysis: str) -> str:
        return await self.memo_agent.write_memo(ForecastResult(**forecast), news_analysis)

    async def boot(self) -> None:
        """Bring all agents online in parallel and record their status."""
        logger.info("Booting OpenVC-AI runtime v%s ...", __version__)

        async def boot_agent(name: str) -> None:
            # Each agent is lightweight to construct; readiness is based on whether
            # its required dependencies are configured or demo mode covers them.
            ready = True
            if name in {"MarketDataAgent", "QuantForecastAgent"}:
                ready = bool(settings.alpha_vantage_api_key or settings.demo_mode)
            elif name in {"MarketNewsAgent", "NewsAnalysisAgent"}:
                ready = bool(settings.finnhub_api_key or settings.demo_mode) and self._any_llm_configured()
            elif name == "InvestmentMemoAgent":
                ready = self._any_llm_configured()
            status = AgentStatus.READY if ready else AgentStatus.DEGRADED
            self.registry.set_status(name, status)
            logger.info("Agent %-24s -> %s", name, status.value)

        await asyncio.gather(*(boot_agent(card.name) for card in self.registry.list_cards()))
        logger.info("Runtime boot complete.")

    def _any_llm_configured(self) -> bool:
        return bool(settings.groq_api_key or settings.openai_api_key or settings.demo_mode)

    async def system_status(self) -> SystemStatus:
        """Aggregate dependency + agent health for dashboards."""
        dependencies: list[DependencyHealth] = []

        # Data adapters.
        dependencies.append(await self.market_data.health())
        dependencies.append(await self.news_data.health())

        # LLM providers via router.
        llm_health = self.llm_router.health()
        if isinstance(llm_health, list):
            dependencies.extend(llm_health)

        overall = "ok"
        if any(d.status == ProviderStatus.ERROR for d in dependencies):
            overall = "degraded"
        elif all(d.status == ProviderStatus.NOT_CONFIGURED for d in dependencies):
            overall = "unconfigured"

        return SystemStatus(
            status=overall,
            version=__version__,
            uptime_seconds=round(time.monotonic() - self.started_at, 2),
            primary_llm_provider=settings.primary_llm_provider,
            agents=self.registry.list_cards(),
            dependencies=dependencies,
            tools=self.tools.list_tools(),
            active_tasks=self.task_store.active_count(),
            memory_records=self.memory.count(),
        )

    def cache_stats(self) -> dict:
        return {
            "market_data": AlphaVantageMarketDataAdapter._cache.stats(),
            "news": FinnhubNewsAdapter._cache.stats(),
        }
