"""Central A2A-style orchestrator coordinating agents, tools, tasks, and memory."""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta

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
from openvc_ai.agents.registry import InMemoryAgentRegistry
from openvc_ai.config.logging_config import get_logger
from openvc_ai.domain.models import (
    A2ATask,
    A2ATaskRequest,
    A2ATaskResult,
    ForecastRequest,
    ForecastResult,
    NewsItem,
    PricePoint,
    TaskPlan,
    TaskStatus,
)
from openvc_ai.memory.in_memory import InMemoryMemoryStore
from openvc_ai.tools.local import LocalToolRegistry

logger = get_logger(__name__)


class CentralA2AOrchestrator:
    """
    A2A-style central coordinator.

    The project now has the local pieces needed for A2A-style execution:
    - agent cards and capability-based discovery
    - a deterministic planner
    - a task lifecycle store
    - a tool registry
    - short-term session memory

    The underlying agents still run in-process by default, but the orchestration
    contract is ready to swap individual steps for remote A2A agents later.
    """

    def __init__(
        self,
        market_data: AlphaVantageMarketDataAdapter,
        news_data: FinnhubNewsAdapter,
        quant_agent: QuantForecastAgent,
        news_agent: NewsAnalysisAgent,
        memo_agent: InvestmentMemoAgent | None = None,
        *,
        registry: InMemoryAgentRegistry | None = None,
        tools: LocalToolRegistry | None = None,
        planner: CapabilityPlanner | None = None,
        task_store: InMemoryTaskStore | None = None,
        memory: InMemoryMemoryStore | None = None,
    ):
        self.market_data = market_data
        self.news_data = news_data
        self.quant_agent = quant_agent
        self.news_agent = news_agent
        self.memo_agent = memo_agent
        self.registry = registry
        self.tools = tools
        self.planner = planner or (CapabilityPlanner(registry, tools) if registry else None)
        self.task_store = task_store or InMemoryTaskStore()
        self.memory = memory

    async def submit_task(self, request: A2ATaskRequest) -> A2ATaskResult:
        """Execute a generic A2A-style task and return its result."""
        start = time.perf_counter()
        task = self.task_store.create(request)
        try:
            if request.task_type != "forecast_stock":
                plan = self._build_generic_plan(request)
                self.task_store.set_plan(task.task_id, plan)
                msg = f"Unsupported task_type '{request.task_type}'. Registered plan only."
                self.task_store.update_status(task.task_id, TaskStatus.FAILED, msg)
                final = self.task_store.get(task.task_id)
                assert final is not None
                return A2ATaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    error=msg,
                    events=final.events,
                    elapsed_ms=(time.perf_counter() - start) * 1000,
                    plan=final.plan,
                )

            forecast_request = ForecastRequest(**request.input)
            plan = self._build_forecast_plan(forecast_request)
            task = self.task_store.set_plan(task.task_id, plan)
            assigned = plan.selected_agents[0] if plan.selected_agents else "CentralA2AOrchestrator"
            self.task_store.update_status(
                task.task_id,
                TaskStatus.RUNNING,
                "Executing forecast task through local A2A orchestration.",
                assigned_agent=assigned,
                agent="CentralA2AOrchestrator",
            )

            result = await self.forecast_stock(forecast_request, task_id=task.task_id, plan=plan)
            payload = result.model_dump(mode="json")
            self.task_store.update_status(
                task.task_id,
                TaskStatus.SUCCEEDED,
                "Task completed successfully.",
                agent="CentralA2AOrchestrator",
                payload={"ticker": result.ticker, "expected_price": result.expected_price},
            )
            final = self.task_store.get(task.task_id)
            assert final is not None
            return A2ATaskResult(
                task_id=task.task_id,
                status=TaskStatus.SUCCEEDED,
                output=payload,
                events=final.events,
                elapsed_ms=(time.perf_counter() - start) * 1000,
                assigned_agent=final.assigned_agent,
                plan=final.plan,
            )
        except Exception as exc:
            logger.exception("A2A task failed: %s", exc)
            self.task_store.update_status(
                task.task_id,
                TaskStatus.FAILED,
                f"Task failed: {exc}",
                agent="CentralA2AOrchestrator",
            )
            final = self.task_store.get(task.task_id)
            assert final is not None
            return A2ATaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error=str(exc),
                events=final.events,
                elapsed_ms=(time.perf_counter() - start) * 1000,
                assigned_agent=final.assigned_agent,
                plan=final.plan,
            )

    def get_task(self, task_id: str) -> A2ATask | None:
        return self.task_store.get(task_id)

    def list_tasks(self, limit: int = 50) -> list[A2ATask]:
        return self.task_store.list(limit=limit)

    async def forecast_stock(
        self,
        request: ForecastRequest,
        *,
        task_id: str | None = None,
        plan: TaskPlan | None = None,
    ) -> ForecastResult:
        start = time.perf_counter()
        notes: list[str] = []
        plan = plan or self._build_forecast_plan(request)

        if task_id:
            self.task_store.add_event(
                task_id, TaskStatus.RUNNING,
                "SEND → MarketDataAgent: fetch price history",
                agent="CentralA2AOrchestrator",
            )

        # Kick off price and news retrieval concurrently.
        prices_task = asyncio.create_task(self._get_prices(request.ticker))
        news_task: asyncio.Task[list[NewsItem]] | None = None
        if request.include_news:
            if task_id:
                self.task_store.add_event(
                    task_id, TaskStatus.RUNNING,
                    "SEND → MarketNewsAgent: fetch company news",
                    agent="CentralA2AOrchestrator",
                )
            news_task = asyncio.create_task(self._get_news(request.ticker))

        # Prices are required; surface failures clearly.
        try:
            prices = await prices_task
            if task_id:
                self.task_store.add_event(
                    task_id, TaskStatus.RUNNING,
                    f"RECV ← MarketDataAgent: {len(prices)} price points",
                    agent="MarketDataAgent",
                )
        except Exception as exc:
            if news_task is not None:
                news_task.cancel()
            logger.error("Price retrieval failed for %s: %s", request.ticker, exc)
            raise

        price_frame = price_points_to_frame(prices)

        if task_id:
            self.task_store.add_event(
                task_id, TaskStatus.RUNNING,
                "SEND → QuantForecastAgent: run Monte Carlo simulation",
                agent="CentralA2AOrchestrator",
            )
        # CPU-bound Monte Carlo runs off the event loop.
        quant = await asyncio.to_thread(
            self.quant_agent.forecast, price_frame, request.horizon_days
        )
        if task_id:
            self.task_store.add_event(
                task_id, TaskStatus.RUNNING,
                f"RECV ← QuantForecastAgent: drift={quant['drift']:.4f} vol={quant['volatility']:.4f}",
                agent="QuantForecastAgent",
            )

        forecast_series = self._build_forecast_series(price_frame, quant)
        forecast_paths = quant.get("sample_paths") or None

        news_items: list[NewsItem] = []
        news_analysis: str | None = None
        if request.include_news and news_task is not None:
            try:
                news_items = await news_task
                if task_id:
                    self.task_store.add_event(
                        task_id, TaskStatus.RUNNING,
                        f"RECV ← MarketNewsAgent: {len(news_items)} news items",
                        agent="MarketNewsAgent",
                    )
                if task_id:
                    self.task_store.add_event(
                        task_id, TaskStatus.RUNNING,
                        "SEND → NewsAnalysisAgent: analyse sentiment",
                        agent="CentralA2AOrchestrator",
                    )
                news_analysis = await self.news_agent.analyze(request.ticker, news_items)
                if task_id:
                    self.task_store.add_event(
                        task_id, TaskStatus.RUNNING,
                        "RECV ← NewsAnalysisAgent: sentiment analysis complete",
                        agent="NewsAnalysisAgent",
                    )
            except Exception as exc:
                notes.append(f"News analysis unavailable: {exc}")
                logger.warning("News analysis failed for %s: %s", request.ticker, exc)
        elif not request.include_news:
            news_analysis = "News analysis was not requested."

        explanation = (
            f"Baseline forecast uses historical daily log returns and Monte Carlo simulation. "
            f"Estimated daily drift: {quant['drift']:.6f}; "
            f"daily volatility: {quant['volatility']:.6f}.\n\n"
            f"Recent-news interpretation:\n{news_analysis or 'Not available.'}"
        )

        risks = [
            "This is a statistical forecast, not a guaranteed prediction.",
            "Historical returns may not represent future behavior.",
            "News APIs may miss relevant events or include noisy information.",
            "Earnings, macro shocks, liquidity, and regulatory events can dominate model outputs.",
        ]
        if not news_items and request.include_news:
            risks.append("No recent news items were available or news retrieval failed.")

        result = ForecastResult(
            ticker=request.ticker.upper(),
            horizon_days=request.horizon_days,
            current_price=quant["current_price"],
            expected_price=quant["expected_price"],
            lower_bound=quant["lower_bound"],
            upper_bound=quant["upper_bound"],
            confidence=quant["confidence"],
            explanation=explanation,
            risks=risks,
            data_notes=notes,
            news_analysis=news_analysis,
            price_history=prices,
            forecast_series=forecast_series,
            forecast_paths=forecast_paths,
            task_id=task_id,
            plan=plan.model_dump(mode="json") if plan else None,
            assigned_agents=plan.selected_agents if plan else [],
        )

        # Optional investment memo synthesizes quant + news (extra LLM call).
        if request.include_memo and self.memo_agent is not None:
            try:
                if task_id:
                    self.task_store.add_event(
                        task_id, TaskStatus.RUNNING,
                        "SEND → InvestmentMemoAgent: synthesise quant + news into memo",
                        agent="CentralA2AOrchestrator",
                    )
                result.investment_memo = await self.memo_agent.write_memo(
                    result, news_analysis or "No news analysis available."
                )
                if task_id:
                    self.task_store.add_event(
                        task_id, TaskStatus.RUNNING,
                        "RECV ← InvestmentMemoAgent: investment memo written",
                        agent="InvestmentMemoAgent",
                    )
            except Exception as exc:
                notes.append(f"Investment memo unavailable: {exc}")
                logger.warning("Memo generation failed for %s: %s", request.ticker, exc)

        result.elapsed_ms = (time.perf_counter() - start) * 1000
        self._remember_forecast(request, result)
        logger.info(
            "Forecast complete for %s (%dd) in %.0fms",
            request.ticker,
            request.horizon_days,
            result.elapsed_ms,
        )
        return result

    async def _get_prices(self, ticker: str) -> list[PricePoint]:
        if self.tools and self.tools.get("price_history"):
            from openvc_ai.domain.models import ToolInvocation

            tool_result = await self.tools.execute(
                ToolInvocation(tool_name="price_history", arguments={"ticker": ticker, "outputsize": "compact"})
            )
            if tool_result.success:
                return [PricePoint(**item) for item in tool_result.output]
            raise RuntimeError(tool_result.error or "price_history tool failed")
        return await self.market_data.daily_prices(ticker, outputsize="compact")

    async def _get_news(self, ticker: str) -> list[NewsItem]:
        if self.tools and self.tools.get("company_news"):
            from openvc_ai.domain.models import ToolInvocation

            tool_result = await self.tools.execute(
                ToolInvocation(tool_name="company_news", arguments={"ticker": ticker})
            )
            if tool_result.success:
                return [NewsItem(**item) for item in tool_result.output]
            raise RuntimeError(tool_result.error or "company_news tool failed")
        return await self.news_data.company_news(ticker)

    def _build_forecast_plan(self, request: ForecastRequest) -> TaskPlan:
        if self.planner:
            return self.planner.build_forecast_plan(request)
        steps = []
        selected = ["QuantForecastAgent"]
        if request.include_news:
            selected.append("NewsAnalysisAgent")
        if request.include_memo:
            selected.append("InvestmentMemoAgent")
        return TaskPlan(task_type="forecast_stock", strategy="static_fallback", steps=steps, selected_agents=selected)

    def _build_generic_plan(self, request: A2ATaskRequest) -> TaskPlan:
        if self.planner:
            return self.planner.build_generic_plan(request.task_type, request.required_capabilities)
        return TaskPlan(task_type=request.task_type, strategy="static_fallback", steps=[])

    def _remember_forecast(self, request: ForecastRequest, result: ForecastResult) -> None:
        if not self.memory or not request.use_memory:
            return
        session_id = request.session_id or "default"
        summary = (
            f"{result.ticker} {result.horizon_days}d forecast: "
            f"current={result.current_price}, expected={result.expected_price}, "
            f"range=({result.lower_bound}, {result.upper_bound}), confidence={result.confidence:.2f}."
        )
        try:
            self.memory.add(
                session_id=session_id,
                kind="forecast_result",
                content=summary,
                metadata={
                    "ticker": result.ticker,
                    "horizon_days": result.horizon_days,
                    "task_id": result.task_id,
                    "expected_price": result.expected_price,
                },
            )
        except Exception as exc:
            logger.warning("Failed to persist forecast memory: %s", exc)

    @staticmethod
    def _build_forecast_series(price_frame, quant: dict) -> list[dict] | None:
        try:
            last_date = price_frame["date"].iloc[-1]
        except Exception:
            return None

        per_day = quant.get("per_day_percentiles")
        if not per_day:
            return None

        series: list[dict] = []
        for i, p in enumerate(per_day, start=1):
            d = last_date + timedelta(days=i)
            series.append(
                {
                    "date": d.isoformat(),
                    "p10": p.get("p10"),
                    "p50": p.get("p50"),
                    "p90": p.get("p90"),
                }
            )
        return series
