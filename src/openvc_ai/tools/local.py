"""Local tool registry used by the A2A orchestrator."""

from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any

from openvc_ai.domain.models import ToolInvocation, ToolResult, ToolSpec
from openvc_ai.tools.ports import ToolPort

ToolHandler = Callable[..., Any | Awaitable[Any]]


class LocalToolRegistry(ToolPort):
    """Registers local Python callables as agent-visible tools.

    Remote MCP/A2A tools can later be added behind the same ToolPort contract.
    """

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def list_tools(self) -> list[ToolSpec]:
        return sorted(self._specs.values(), key=lambda spec: spec.name)

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        start = time.perf_counter()
        handler = self._handlers.get(invocation.tool_name)
        if handler is None:
            return ToolResult(
                tool_name=invocation.tool_name,
                success=False,
                error=f"Unknown tool: {invocation.tool_name}",
                elapsed_ms=(time.perf_counter() - start) * 1000,
            )

        try:
            value = handler(**invocation.arguments)
            if inspect.isawaitable(value):
                value = await value
            return ToolResult(
                tool_name=invocation.tool_name,
                success=True,
                output=value,
                elapsed_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:
            return ToolResult(
                tool_name=invocation.tool_name,
                success=False,
                error=str(exc),
                elapsed_ms=(time.perf_counter() - start) * 1000,
            )
