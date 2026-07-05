"""FastAPI application for OpenVC-AI with A2A-style ops endpoints."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from openvc_ai.adapters.market_data import AlphaVantageMarketDataAdapter, close_http_client
from openvc_ai.config.logging_config import configure_logging, get_logger
from openvc_ai.config.settings import settings
from openvc_ai.domain.models import A2ATaskRequest, BacktestRequest, ForecastRequest, ToolInvocation
from openvc_ai.runtime import AppRuntime

# Simple in-process rate limiter: max 20 chat requests per minute per IP
_rate_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = 20
_RATE_WINDOW = 60.0


def _check_rate_limit(client_ip: str) -> None:
    now = time.time()
    timestamps = _rate_store[client_ip]
    # Evict old entries
    _rate_store[client_ip] = [t for t in timestamps if now - t < _RATE_WINDOW]
    if len(_rate_store[client_ip]) >= _RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a minute.")
    _rate_store[client_ip].append(now)

logger = get_logger(__name__)

# Resolve the static directory relative to THIS file so it works regardless of CWD,
# whether running from source, an editable install, or inside Docker.
STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    runtime = AppRuntime()
    await runtime.boot()
    app.state.runtime = runtime
    try:
        yield
    finally:
        await close_http_client()
        logger.info("OpenVC-AI shutdown complete.")


app = FastAPI(
    title="OpenVC-AI",
    version="0.2.0",
    description="A2A-style multi-agent investment research platform.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def get_runtime(request: Request) -> AppRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Runtime not initialized")
    return runtime


@app.get("/", response_class=HTMLResponse)
async def index():
    if INDEX_FILE.is_file():
        return FileResponse(str(INDEX_FILE))
    return HTMLResponse("<h1>OpenVC-AI</h1><p>Frontend assets not found.</p>")


@app.get("/health")
async def health():
    """Lightweight liveness probe (no external calls)."""
    return {
        "status": "ok",
        "primary_llm_provider": settings.primary_llm_provider,
        "demo_mode": settings.demo_mode,
    }


@app.get("/status")
async def status(request: Request):
    """Aggregate system status: agents, tools, dependencies, uptime, memory, tasks."""
    runtime = get_runtime(request)
    return (await runtime.system_status()).model_dump(mode="json")


@app.get("/ready")
async def ready(request: Request):
    """Readiness probe: 200 when providers or demo-mode fallbacks are usable."""
    runtime = get_runtime(request)
    system = await runtime.system_status()
    if system.status == "unconfigured":
        return JSONResponse(
            status_code=503,
            content={"ready": False, "reason": "No providers configured", **system.model_dump(mode="json")},
        )
    return {"ready": True, "status": system.status, "demo_mode": settings.demo_mode}


@app.get("/cache/stats")
async def cache_stats(request: Request):
    return get_runtime(request).cache_stats()


@app.get("/config")
async def config():
    """Non-sensitive configuration summary (secrets shown only as booleans)."""
    return {
        "primary_llm_provider": settings.primary_llm_provider,
        "groq_model": settings.groq_model,
        "openai_model": settings.openai_model,
        "demo_mode": settings.demo_mode,
        "monte_carlo_simulations": settings.monte_carlo_simulations,
        "sample_paths": settings.sample_paths,
        "cache_ttl_seconds": settings.cache_ttl_seconds,
        "secrets_configured": settings.masked_summary(),
    }


@app.get("/a2a/card")
async def orchestrator_card(request: Request):
    runtime = get_runtime(request)
    card = runtime.registry.get("CentralA2AOrchestrator")
    if not card:
        raise HTTPException(status_code=404, detail="CentralA2AOrchestrator card not found")
    return card.model_dump(mode="json")


@app.get("/agents")
async def agents(request: Request, public_only: bool = False):
    runtime = get_runtime(request)
    return [card.model_dump(mode="json") for card in runtime.registry.list_cards(public_only=public_only)]


@app.get("/agents/discover")
async def discover_agents(
    request: Request,
    capability: str = Query(..., description="Capability/skill to search for."),
    ready_only: bool = False,
):
    runtime = get_runtime(request)
    cards = runtime.registry.find_by_capability(capability, ready_only=ready_only)
    return [card.model_dump(mode="json") for card in cards]


@app.get("/agents/by-name/{agent_name}")
async def agent_card(request: Request, agent_name: str):
    runtime = get_runtime(request)
    card = runtime.registry.get(agent_name)
    if not card:
        raise HTTPException(status_code=404, detail="Agent not found")
    return card.model_dump(mode="json")


@app.get("/tools")
async def tools(request: Request):
    runtime = get_runtime(request)
    return [tool.model_dump(mode="json") for tool in runtime.tools.list_tools()]


@app.post("/tools/execute")
async def execute_tool(request: Request, invocation: ToolInvocation):
    runtime = get_runtime(request)
    result = await runtime.tools.execute(invocation)
    status_code = 200 if result.success else 400
    return JSONResponse(status_code=status_code, content=result.model_dump(mode="json"))


@app.post("/tasks")
async def submit_task(request: Request, payload: A2ATaskRequest):
    runtime = get_runtime(request)
    result = await runtime.orchestrator.submit_task(payload)
    status_code = 200 if result.status.value == "succeeded" else 400
    return JSONResponse(status_code=status_code, content=result.model_dump(mode="json"))


@app.post("/a2a/execute")
async def a2a_execute(request: Request, payload: A2ATaskRequest):
    """Alias for A2A clients that post generic task envelopes."""
    runtime = get_runtime(request)
    result = await runtime.orchestrator.submit_task(payload)
    status_code = 200 if result.status.value == "succeeded" else 400
    return JSONResponse(status_code=status_code, content=result.model_dump(mode="json"))


@app.get("/tasks")
async def list_tasks(request: Request, limit: int = 50):
    runtime = get_runtime(request)
    return [task.model_dump(mode="json") for task in runtime.orchestrator.list_tasks(limit=limit)]


@app.get("/tasks/{task_id}")
async def get_task(request: Request, task_id: str):
    runtime = get_runtime(request)
    task = runtime.orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.model_dump(mode="json")


@app.get("/tasks/{task_id}/events")
async def get_task_events(request: Request, task_id: str):
    runtime = get_runtime(request)
    task = runtime.orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return [event.model_dump(mode="json") for event in task.events]


@app.post("/forecast")
async def forecast(request: Request, payload: ForecastRequest):
    runtime = get_runtime(request)
    try:
        result = await runtime.orchestrator.forecast_stock(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return result.model_dump(mode="json")


@app.post("/backtest")
async def backtest(request: Request, payload: BacktestRequest):
    """Run a walk-forward historical backtest for the quantitative forecast model."""
    runtime = get_runtime(request)
    try:
        result = await runtime.backtest_forecast_model(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return result.model_dump(mode="json")


@app.get("/quote")
async def quote(ticker: str):
    """Return a lightweight quote with data-source metadata."""
    adapter = AlphaVantageMarketDataAdapter()
    try:
        return await adapter.quote(ticker)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/chat")
async def chat(request: Request, payload: dict):
    """Non-streaming chat endpoint — returns the full response at once."""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)
    runtime = get_runtime(request)
    messages = payload.get("messages", [])
    context = payload.get("context", {})
    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")
    system_message = {
        "role": "system",
        "content": (
            f"You are an AI stock market analyst for OpenVC-AI. "
            f"Context: {context}. Be concise, professional, under 200 words."
        ),
    }
    full_messages = [system_message] + messages
    try:
        from openvc_ai.domain.models import ChatMessage, LLMRequest
        llm_messages = [ChatMessage(role=m["role"], content=m["content"]) for m in full_messages]
        llm_request = LLMRequest(messages=llm_messages, temperature=0.7, max_tokens=500)
        response = await runtime.llm_router.complete(llm_request)
        return {
            "role": "assistant",
            "content": response.content,
            "provider": response.provider,
            "model": response.model,
        }
    except Exception as exc:
        logger.exception("Chat completion failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"LLM completion failed: {str(exc)}")


@app.post("/chat/stream")
async def chat_stream(request: Request, payload: dict):
    """Real token-by-token SSE streaming via the LLM provider's native stream API."""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)
    runtime = get_runtime(request)
    messages = payload.get("messages", [])
    context = payload.get("context", {})
    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    system_content = (
        f"You are an AI stock market analyst for OpenVC-AI. "
        f"Context: {context}. Be concise, professional, under 200 words."
    )
    full_messages = [{"role": "system", "content": system_content}] + messages

    async def generate():
        from openvc_ai.domain.models import ChatMessage, LLMRequest
        llm_messages = [ChatMessage(role=m["role"], content=m["content"]) for m in full_messages]
        llm_request = LLMRequest(messages=llm_messages, temperature=0.7, max_tokens=500)
        stream_fn = getattr(runtime.llm_router, "stream_complete", None)
        try:
            if stream_fn is not None:
                async for token in stream_fn(llm_request):
                    yield f"data: {json.dumps({'token': token})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
            else:
                # Adapter doesn't support streaming — fall back to full response
                response = await runtime.llm_router.complete(llm_request)
                yield f"data: {json.dumps({'token': response.content})}\n\n"
                yield f"data: {json.dumps({'done': True, 'provider': response.provider, 'model': response.model})}\n\n"
        except Exception as exc:
            logger.exception("Chat stream failed: %s", exc)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/memory/long-term")
async def long_term_memory(request: Request, limit: int = 50, query: str = ""):
    import asyncio
    runtime = get_runtime(request)
    if query:
        records = await asyncio.to_thread(runtime.memory.search_long_term, query, limit)
    else:
        records = await asyncio.to_thread(runtime.memory.long_term_recent, limit)
    return [record.model_dump(mode="json") for record in records]


@app.post("/memory/long-term")
async def add_long_term_memory(request: Request, payload: dict):
    import asyncio
    runtime = get_runtime(request)
    kind = payload.get("kind", "insight")
    content = payload.get("content", "")
    metadata = payload.get("metadata", {})
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    record = await asyncio.to_thread(runtime.memory.add_long_term, kind, content, metadata)
    return record.model_dump(mode="json")


@app.get("/memory/stats")
async def memory_stats(request: Request):
    import asyncio
    runtime = get_runtime(request)
    short = await asyncio.to_thread(runtime.memory.count)
    long  = await asyncio.to_thread(runtime.memory.long_term_count)
    sess  = await asyncio.to_thread(runtime.memory.sessions)
    return {"short_term_records": short, "long_term_records": long, "sessions": sess}


@app.get("/memory/{session_id}")
async def session_memory(request: Request, session_id: str, limit: int = 10):
    import asyncio
    runtime = get_runtime(request)
    records = await asyncio.to_thread(runtime.memory.recent, session_id, limit)
    return [record.model_dump(mode="json") for record in records]


@app.post("/memory/{session_id}")
async def add_memory(request: Request, session_id: str, payload: dict):
    import asyncio
    runtime = get_runtime(request)
    kind     = payload.get("kind", "chat_message")
    content  = payload.get("content", "")
    metadata = payload.get("metadata", {})
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    record = await asyncio.to_thread(runtime.memory.add, session_id, kind, content, metadata)
    return record.model_dump(mode="json")
