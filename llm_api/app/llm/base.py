"""Abstract base for LLM providers."""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, model: str, messages: list[dict], options: dict) -> str:
        """Send messages and return the assistant text response."""
        ...
