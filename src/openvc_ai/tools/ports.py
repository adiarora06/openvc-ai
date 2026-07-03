"""Abstract contract for local and remote tools."""

from __future__ import annotations

from abc import ABC, abstractmethod

from openvc_ai.domain.models import ToolInvocation, ToolResult, ToolSpec


class ToolPort(ABC):
    """Interface for registries that expose executable tools to agents."""

    @abstractmethod
    def list_tools(self) -> list[ToolSpec]:
        """Return available tool specifications."""

    @abstractmethod
    def get(self, name: str) -> ToolSpec | None:
        """Return a tool specification by name, if present."""

    @abstractmethod
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        """Execute a tool invocation."""
