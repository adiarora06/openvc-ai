"""Domain models shared by the API, agents, tools, registry, and runtime."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class AgentStatus(str, Enum):
    """Lifecycle state of an agent."""

    UNINITIALIZED = "uninitialized"
    READY = "ready"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class ProviderStatus(str, Enum):
    """Health state of an external provider/dependency."""

    OK = "ok"
    NOT_CONFIGURED = "not_configured"
    ERROR = "error"
    UNKNOWN = "unknown"


class TaskStatus(str, Enum):
    """Lifecycle state for an A2A-style task."""

    QUEUED = "queued"
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentCapability(BaseModel):
    """Structured skill/capability advertised by an agent card."""

    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class AgentCard(BaseModel):
    """A2A-style agent card.

    The original project only had name/description/capabilities. This richer card
    keeps those fields for compatibility and adds the metadata needed for local
    discovery now and remote discovery later.
    """

    name: str
    description: str
    capabilities: list[str]
    version: str = "0.1.0"
    status: AgentStatus = AgentStatus.READY
    agent_id: str | None = None
    protocol: str = "local"
    endpoint_url: str | None = None
    input_modes: list[str] = Field(default_factory=lambda: ["application/json"])
    output_modes: list[str] = Field(default_factory=lambda: ["application/json"])
    skills: list[AgentCapability] = Field(default_factory=list)
    auth: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_public: bool = True

    def capability_set(self) -> set[str]:
        return {cap.lower() for cap in self.capabilities}


class ChatMessage(BaseModel):
    role: str
    content: str


class LLMRequest(BaseModel):
    messages: list[ChatMessage]
    temperature: float = 0.2
    max_tokens: int = 1200


class LLMResponse(BaseModel):
    provider: str
    model: str
    content: str
    latency_ms: float | None = None


class PricePoint(BaseModel):
    timestamp: date
    close: float


class NewsItem(BaseModel):
    headline: str
    summary: str | None = None
    source: str | None = None
    url: str | None = None
    published_at: datetime | None = None


class ForecastRequest(BaseModel):
    ticker: str = Field(..., examples=["NVDA"], min_length=1, max_length=12)
    horizon_days: int = Field(30, ge=1, le=3650)
    include_news: bool = True
    include_memo: bool = False
    session_id: str | None = Field(default=None, description="Optional memory/session id.")
    use_memory: bool = True

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned.replace(".", "").replace("-", "").isalnum():
            raise ValueError("Ticker may only contain letters, numbers, '.' and '-'.")
        return cleaned


class ForecastResult(BaseModel):
    ticker: str
    horizon_days: int
    current_price: float | None
    expected_price: float | None
    lower_bound: float | None
    upper_bound: float | None
    confidence: float
    explanation: str
    risks: list[str]
    data_notes: list[str]
    news_analysis: str | None = None
    investment_memo: str | None = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    elapsed_ms: float | None = None
    # Optional series data used by the frontend dashboard
    price_history: list[PricePoint] | None = None
    # forecast_series is a list of dicts with keys: date (ISO), p10, p50, p90
    forecast_series: list[dict] | None = None
    # sampled simulation paths for visualization: list of lists (prices for days 1..horizon)
    forecast_paths: list[list[float]] | None = None
    # A2A execution metadata
    task_id: str | None = None
    plan: dict[str, Any] | None = None
    assigned_agents: list[str] = Field(default_factory=list)


class BacktestRequest(BaseModel):
    ticker: str = Field(..., examples=["NVDA"], min_length=1, max_length=12)
    horizon_days: int = Field(10, ge=1, le=252)
    training_window_days: int = Field(60, ge=30, le=1500)
    stride_days: int = Field(10, ge=1, le=252)
    max_windows: int = Field(12, ge=1, le=100)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned.replace(".", "").replace("-", "").isalnum():
            raise ValueError("Ticker may only contain letters, numbers, '.' and '-'.")
        return cleaned


class BacktestWindowResult(BaseModel):
    train_start: date
    forecast_date: date
    target_date: date
    start_price: float
    predicted_price: float
    actual_price: float
    lower_bound: float
    upper_bound: float
    absolute_error: float
    percentage_error: float
    predicted_return: float
    actual_return: float
    direction_correct: bool
    interval_hit: bool


class BacktestResult(BaseModel):
    ticker: str
    horizon_days: int
    training_window_days: int
    stride_days: int
    windows: int
    mae: float
    rmse: float
    mape: float
    directional_accuracy: float
    interval_coverage: float
    average_predicted_return: float
    average_actual_return: float
    data_points: int
    first_forecast_date: date | None = None
    last_forecast_date: date | None = None
    window_results: list[BacktestWindowResult] = Field(default_factory=list)


class DependencyHealth(BaseModel):
    name: str
    status: ProviderStatus
    detail: str | None = None
    latency_ms: float | None = None


class ToolSpec(BaseModel):
    """Tool metadata exposed to agents and planners."""

    name: str
    description: str
    capabilities: list[str]
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    agent_visible: bool = True


class ToolInvocation(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    output: Any = None
    error: str | None = None
    elapsed_ms: float | None = None


class TaskPlanStep(BaseModel):
    step_id: str
    description: str
    required_capability: str
    preferred_agent: str | None = None
    tool_name: str | None = None
    depends_on: list[str] = Field(default_factory=list)


class TaskPlan(BaseModel):
    task_type: str
    strategy: str
    steps: list[TaskPlanStep]
    selected_agents: list[str] = Field(default_factory=list)


class A2ATaskRequest(BaseModel):
    """Generic task envelope for A2A-style execution."""

    task_type: str = "forecast_stock"
    input: dict[str, Any] = Field(default_factory=dict)
    required_capabilities: list[str] = Field(default_factory=list)
    preferred_agent: str | None = None
    session_id: str | None = None
    stream: bool = False


class A2ATaskEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    status: TaskStatus
    message: str
    agent: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class A2ATask(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    task_type: str
    input: dict[str, Any] = Field(default_factory=dict)
    required_capabilities: list[str] = Field(default_factory=list)
    preferred_agent: str | None = None
    session_id: str | None = None
    status: TaskStatus = TaskStatus.QUEUED
    assigned_agent: str | None = None
    plan: TaskPlan | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    events: list[A2ATaskEvent] = Field(default_factory=list)


class A2ATaskResult(BaseModel):
    task_id: str
    status: TaskStatus
    output: dict[str, Any] | None = None
    error: str | None = None
    events: list[A2ATaskEvent] = Field(default_factory=list)
    elapsed_ms: float | None = None
    assigned_agent: str | None = None
    plan: TaskPlan | None = None


class MemoryRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    kind: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SystemStatus(BaseModel):
    """Aggregate system status used by the dashboard and ops tooling."""

    status: str
    version: str
    uptime_seconds: float
    primary_llm_provider: str
    agents: list[AgentCard]
    dependencies: list[DependencyHealth]
    tools: list[ToolSpec] = Field(default_factory=list)
    active_tasks: int = 0
    memory_records: int = 0
    checked_at: datetime = Field(default_factory=datetime.utcnow)
