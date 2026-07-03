from abc import ABC, abstractmethod

from openvc_ai.domain.models import LLMRequest, LLMResponse


class LLMPort(ABC):
    """Abstract contract for LLM providers.

    Implementations may optionally expose a synchronous ``health()`` method
    returning a ``DependencyHealth`` (used by the status subsystem).
    """

    name: str = "llm"

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Generate a response from an LLM provider."""
