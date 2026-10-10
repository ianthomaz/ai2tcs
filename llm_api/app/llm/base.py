"""Abstract base for LLM providers."""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, model: str, messages: list[dict], options: dict) -> str:
        """Send messages and return the assistant text response."""
        ...

    async def chat_with_metrics(self, model: str, messages: list[dict], options: dict) -> tuple[str, dict]:
        """Text plus call metrics (app/llm/metrics.py). Providers without metrics return {}."""
        return await self.chat(model=model, messages=messages, options=options), {}
