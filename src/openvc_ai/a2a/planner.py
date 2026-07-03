"""Capability-based planning for A2A tasks."""

from __future__ import annotations

from openvc_ai.agents.registry import InMemoryAgentRegistry
from openvc_ai.domain.models import ForecastRequest, TaskPlan, TaskPlanStep
from openvc_ai.tools.local import LocalToolRegistry


class CapabilityPlanner:
    """Builds simple executable task plans from requested capabilities.

    This is intentionally deterministic: it gives the starter kit a clear place
    to swap in an LLM planner later without changing the orchestrator contract.
    """

    def __init__(self, registry: InMemoryAgentRegistry, tools: LocalToolRegistry | None = None):
        self.registry = registry
        self.tools = tools

    def build_forecast_plan(self, request: ForecastRequest) -> TaskPlan:
        steps: list[TaskPlanStep] = [
            TaskPlanStep(
                step_id="fetch_prices",
                description=f"Fetch daily historical prices for {request.ticker}.",
                required_capability="price_history",
                preferred_agent="MarketDataAgent",
                tool_name="price_history",
            ),
            TaskPlanStep(
                step_id="run_quant_forecast",
                description=f"Run Monte Carlo forecast for {request.ticker}.",
                required_capability="price_forecast",
                preferred_agent="QuantForecastAgent",
                tool_name="quant_forecast",
                depends_on=["fetch_prices"],
            ),
        ]

        if request.include_news:
            steps.extend(
                [
                    TaskPlanStep(
                        step_id="fetch_news",
                        description=f"Fetch recent company news for {request.ticker}.",
                        required_capability="company_news",
                        preferred_agent="MarketNewsAgent",
                        tool_name="company_news",
                    ),
                    TaskPlanStep(
                        step_id="analyze_news",
                        description=f"Summarize bullish, bearish, and unknown news drivers for {request.ticker}.",
                        required_capability="news_summary",
                        preferred_agent="NewsAnalysisAgent",
                        tool_name="news_analysis",
                        depends_on=["fetch_news"],
                    ),
                ]
            )

        if request.include_memo:
            steps.append(
                TaskPlanStep(
                    step_id="write_memo",
                    description=f"Write a cautious investment memo for {request.ticker}.",
                    required_capability="memo_generation",
                    preferred_agent="InvestmentMemoAgent",
                    tool_name="investment_memo",
                    depends_on=["run_quant_forecast", "analyze_news"] if request.include_news else ["run_quant_forecast"],
                )
            )

        selected = []
        for step in steps:
            agent = self.registry.find_best_agent(
                [step.required_capability], preferred_agent=step.preferred_agent
            )
            if agent and agent.name not in selected:
                selected.append(agent.name)

        return TaskPlan(
            task_type="forecast_stock",
            strategy="capability_registry_v1",
            steps=steps,
            selected_agents=selected,
        )

    def build_generic_plan(self, task_type: str, required_capabilities: list[str]) -> TaskPlan:
        steps = []
        selected = []
        for index, capability in enumerate(required_capabilities, start=1):
            agent = self.registry.find_best_agent([capability])
            agent_name = agent.name if agent else None
            if agent_name and agent_name not in selected:
                selected.append(agent_name)
            steps.append(
                TaskPlanStep(
                    step_id=f"step_{index}",
                    description=f"Handle capability: {capability}",
                    required_capability=capability,
                    preferred_agent=agent_name,
                )
            )
        return TaskPlan(
            task_type=task_type,
            strategy="capability_registry_v1",
            steps=steps,
            selected_agents=selected,
        )
