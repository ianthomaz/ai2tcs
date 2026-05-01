"""Ollama provider: local inference via the ollama Python library."""
import asyncio
import logging

import ollama

from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    async def chat(self, model: str, messages: list[dict], options: dict) -> str:
        # Strip non-Ollama keys before passing options (e.g. tone_of_voice, message_size)
        ollama_options = {
            k: v for k, v in options.items()
            if k in {"temperature", "top_k", "top_p", "repeat_penalty", "num_predict", "num_ctx", "seed"}
        }
        response = await asyncio.to_thread(
            ollama.chat,
            model=model,
            messages=messages,
            options=ollama_options,
        )
        return (response.get("message") or {}).get("content") or ""
