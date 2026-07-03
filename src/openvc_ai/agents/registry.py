"""In-memory agent registry with A2A-style agent-card discovery."""

from __future__ import annotations

from openvc_ai.domain.models import AgentCapability, AgentCard, AgentStatus


class InMemoryAgentRegistry:
    """Capability-searchable agent-card registry.

    This is the local version of A2A discovery. In production, this can be
    replaced by a remote registry or card crawler while preserving the same API.
    """

    def __init__(self):
        self._cards: dict[str, AgentCard] = {}

    def register(self, card: AgentCard) -> None:
        if card.agent_id is None:
            card = card.model_copy(update={"agent_id": card.name})
        self._cards[card.name] = card

    def unregister(self, name: str) -> None:
        self._cards.pop(name, None)

    def set_status(self, name: str, status: AgentStatus) -> None:
        if name in self._cards:
            self._cards[name] = self._cards[name].model_copy(update={"status": status})

    def get(self, name: str) -> AgentCard | None:
        return self._cards.get(name)

    def list_cards(self, *, public_only: bool = False) -> list[AgentCard]:
        cards = list(self._cards.values())
        if public_only:
            cards = [card for card in cards if card.is_public]
        return sorted(cards, key=lambda card: card.name)

    def find_by_capability(self, capability: str, *, ready_only: bool = False) -> list[AgentCard]:
        needle = capability.lower()
        matches = [card for card in self._cards.values() if needle in card.capability_set()]
        if ready_only:
            matches = [card for card in matches if card.status == AgentStatus.READY]
        return sorted(matches, key=lambda card: card.name)

    def find_by_capabilities(
        self,
        capabilities: list[str],
        *,
        require_all: bool = False,
        ready_only: bool = False,
    ) -> list[AgentCard]:
        needles = {capability.lower() for capability in capabilities}
        if not needles:
            return self.list_cards()
        matches: list[AgentCard] = []
        for card in self._cards.values():
            card_caps = card.capability_set()
            ok = needles.issubset(card_caps) if require_all else bool(needles & card_caps)
            if ok and (not ready_only or card.status == AgentStatus.READY):
                matches.append(card)
        return sorted(matches, key=lambda card: card.name)

    def find_best_agent(
        self,
        capabilities: list[str],
        *,
        preferred_agent: str | None = None,
        ready_only: bool = False,
    ) -> AgentCard | None:
        if preferred_agent:
            preferred = self.get(preferred_agent)
            if preferred and all(cap.lower() in preferred.capability_set() for cap in capabilities):
                if not ready_only or preferred.status == AgentStatus.READY:
                    return preferred
        matches = self.find_by_capabilities(capabilities, require_all=True, ready_only=ready_only)
        if matches:
            return matches[0]
        partial = self.find_by_capabilities(capabilities, require_all=False, ready_only=ready_only)
        return partial[0] if partial else None


def _skill(name: str, description: str, tags: list[str] | None = None) -> AgentCapability:
    return AgentCapability(name=name, description=description, tags=tags or [])


def default_registry() -> InMemoryAgentRegistry:
    registry = InMemoryAgentRegistry()
    registry.register(
        AgentCard(
            name="CentralA2AOrchestrator",
            description="Plans and coordinates A2A-style tasks across local and remote-capable agents.",
            capabilities=["task_planning", "agent_routing", "task_lifecycle", "tool_orchestration"],
            protocol="http+json",
            endpoint_url="/a2a/execute",
            skills=[
                _skill("task_planning", "Builds execution plans from requested capabilities."),
                _skill("agent_routing", "Selects agents from registered agent cards."),
                _skill("task_lifecycle", "Tracks queued, running, succeeded, and failed tasks."),
            ],
            metadata={"role": "orchestrator"},
        )
    )
    registry.register(
        AgentCard(
            name="MarketDataAgent",
            description="Provides price-history and quote retrieval tools.",
            capabilities=["price_history", "quote", "market_data"],
            protocol="local-tool",
            endpoint_url="tool://price_history",
            skills=[
                _skill("price_history", "Fetches daily close history for a stock ticker."),
                _skill("quote", "Returns latest and previous close."),
            ],
        )
    )
    registry.register(
        AgentCard(
            name="MarketNewsAgent",
            description="Provides company-news retrieval tools.",
            capabilities=["company_news", "market_news"],
            protocol="local-tool",
            endpoint_url="tool://company_news",
            skills=[_skill("company_news", "Fetches recent company news for a ticker.")],
        )
    )
    registry.register(
        AgentCard(
            name="QuantForecastAgent",
            description="Runs historical-return and Monte Carlo based stock forecasts.",
            capabilities=["price_forecast", "volatility_estimation", "monte_carlo"],
            protocol="local",
            skills=[
                _skill("price_forecast", "Runs a Monte Carlo forecast over historical log returns."),
                _skill("volatility_estimation", "Estimates daily drift and volatility from historical prices."),
            ],
        )
    )
    registry.register(
        AgentCard(
            name="NewsAnalysisAgent",
            description="Summarizes recent market news and extracts bullish/bearish drivers.",
            capabilities=["news_summary", "sentiment_analysis", "risk_extraction"],
            protocol="local",
            skills=[
                _skill("news_summary", "Summarizes recent market-impact news."),
                _skill("sentiment_analysis", "Separates bullish, bearish, and unknown factors."),
            ],
        )
    )
    registry.register(
        AgentCard(
            name="InvestmentMemoAgent",
            description="Combines quantitative forecast and news analysis into a research memo.",
            capabilities=["memo_generation", "reasoning", "risk_disclosure"],
            protocol="local",
            skills=[_skill("memo_generation", "Writes cautious research memos with assumptions and risks.")],
        )
    )
    registry.register(
        AgentCard(
            name="MemoryAgent",
            description="Stores short-term session memory for prior tasks and research notes.",
            capabilities=["short_term_memory", "task_recall", "session_context"],
            protocol="local",
            skills=[_skill("short_term_memory", "Stores and retrieves recent task summaries by session.")],
        )
    )
    return registry
