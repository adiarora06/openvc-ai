"""LLM provider adapters with shared client, latency tracking, and fallback routing."""

import json
import time
from typing import AsyncIterator

import httpx

from openvc_ai.adapters.market_data import get_http_client
from openvc_ai.config.logging_config import get_logger
from openvc_ai.config.settings import settings
from openvc_ai.domain.models import DependencyHealth, LLMRequest, LLMResponse, ProviderStatus
from openvc_ai.llm.ports import LLMPort

logger = get_logger(__name__)


async def _chat_completion(url: str, api_key: str, model: str, request: LLMRequest) -> dict:
    payload = {
        "model": model,
        "messages": [m.model_dump() for m in request.messages],
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    client = await get_http_client()
    response = await client.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


async def _chat_completion_stream(
    url: str, api_key: str, model: str, request: LLMRequest
) -> AsyncIterator[str]:
    """Stream tokens from an OpenAI-compatible SSE endpoint."""
    payload = {
        "model": model,
        "messages": [m.model_dump() for m in request.messages],
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "stream": True,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "text/event-stream"}
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw.strip() == "[DONE]":
                    return
                try:
                    chunk = json.loads(raw)
                    delta = chunk["choices"][0].get("delta", {})
                    token = delta.get("content")
                    if token:
                        yield token
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


class GroqLLMAdapter(LLMPort):
    name = "groq"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.groq_api_key
        self.model = model or settings.groq_model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        start = time.perf_counter()
        data = await _chat_completion(
            "https://api.groq.com/openai/v1/chat/completions",
            self.api_key,
            self.model,
            request,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        return LLMResponse(
            provider="groq",
            model=self.model,
            content=data["choices"][0]["message"]["content"],
            latency_ms=latency_ms,
        )

    async def stream_complete(self, request: LLMRequest) -> AsyncIterator[str]:
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        async for token in _chat_completion_stream(
            "https://api.groq.com/openai/v1/chat/completions",
            self.api_key,
            self.model,
            request,
        ):
            yield token

    def health(self) -> DependencyHealth:
        status = ProviderStatus.OK if self.api_key else ProviderStatus.NOT_CONFIGURED
        return DependencyHealth(
            name="groq",
            status=status,
            detail=None if self.api_key else "GROQ_API_KEY missing",
        )


class OpenAILLMAdapter(LLMPort):
    name = "openai"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        start = time.perf_counter()
        data = await _chat_completion(
            "https://api.openai.com/v1/chat/completions",
            self.api_key,
            self.model,
            request,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        return LLMResponse(
            provider="openai",
            model=self.model,
            content=data["choices"][0]["message"]["content"],
            latency_ms=latency_ms,
        )

    async def stream_complete(self, request: LLMRequest) -> AsyncIterator[str]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        async for token in _chat_completion_stream(
            "https://api.openai.com/v1/chat/completions",
            self.api_key,
            self.model,
            request,
        ):
            yield token

    def health(self) -> DependencyHealth:
        status = ProviderStatus.OK if self.api_key else ProviderStatus.NOT_CONFIGURED
        return DependencyHealth(
            name="openai",
            status=status,
            detail=None if self.api_key else "OPENAI_API_KEY missing",
        )


class MockLLMAdapter(LLMPort):
    """Deterministic local LLM replacement for demo/offline mode."""

    name = "mock"

    def __init__(self, model: str = "openvc-demo-llm"):
        self.model = model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        start = time.perf_counter()
        user_text = "\n".join(
            message.content for message in request.messages if message.role == "user"
        )
        content = (
            "Demo-mode analysis: no external LLM key is configured, so this response "
            "is generated locally. Bullish factors include constructive momentum in the "
            "provided inputs and stable trend assumptions. Bearish factors include model "
            "risk, valuation sensitivity, and the possibility that synthetic/demo news does "
            "not reflect real market events. Unknown factors include earnings surprises, "
            "macro shocks, rates, liquidity, and regulatory changes.\n\n"
            f"Input reviewed: {user_text[:700]}"
        )
        return LLMResponse(
            provider="mock",
            model=self.model,
            content=content,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    async def stream_complete(self, request: LLMRequest) -> AsyncIterator[str]:
        """Yield the mock response word-by-word for a consistent streaming interface."""
        response = await self.complete(request)
        for word in response.content.split(" "):
            yield word + " "

    def health(self) -> DependencyHealth:
        return DependencyHealth(
            name="mock_llm",
            status=ProviderStatus.OK,
            detail="Demo mode: local deterministic LLM response is enabled",
        )


class FallbackLLMRouter(LLMPort):
    name = "fallback-router"

    def __init__(self, primary: LLMPort, fallback: LLMPort | None = None):
        self.primary = primary
        self.fallback = fallback

    async def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            return await self.primary.complete(request)
        except Exception as primary_error:
            logger.warning("Primary LLM failed: %s", primary_error)
            if not self.fallback:
                if settings.demo_mode:
                    logger.info("Falling back to mock LLM because demo mode is enabled")
                    return await MockLLMAdapter().complete(request)
                raise primary_error
            try:
                logger.info("Falling back to secondary LLM provider")
                return await self.fallback.complete(request)
            except Exception as fallback_error:
                logger.error("Fallback LLM also failed: %s", fallback_error)
                if settings.demo_mode:
                    logger.info("Falling back to mock LLM because demo mode is enabled")
                    return await MockLLMAdapter().complete(request)
                raise primary_error from fallback_error

    async def stream_complete(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream tokens with automatic fallback to secondary provider then mock."""
        primary_stream = getattr(self.primary, "stream_complete", None)
        if primary_stream is None:
            response = await self.complete(request)
            yield response.content
            return
        try:
            async for token in primary_stream(request):
                yield token
            return
        except Exception as primary_error:
            logger.warning("Primary LLM stream failed: %s", primary_error)

        # Try fallback adapter's stream
        fallback_stream = getattr(self.fallback, "stream_complete", None) if self.fallback else None
        if fallback_stream:
            try:
                async for token in fallback_stream(request):
                    yield token
                return
            except Exception as fallback_error:
                logger.error("Fallback LLM stream also failed: %s", fallback_error)

        if settings.demo_mode:
            async for token in MockLLMAdapter().stream_complete(request):
                yield token
        else:
            yield "Error: LLM providers unavailable."

    def health(self) -> list[DependencyHealth]:
        checks: list[DependencyHealth] = []
        for adapter in (self.primary, self.fallback):
            if adapter is None:
                continue
            check = getattr(adapter, "health", None)
            if callable(check):
                result = check()
                if isinstance(result, DependencyHealth):
                    checks.append(result)
        return checks
