"""Ollama provider: local inference via the ollama Python library."""
import asyncio
import logging

import ollama

from app.config import settings
from app.llm.base import LLMProvider
from app.llm.metrics import from_ollama

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    async def chat(self, model: str, messages: list[dict], options: dict) -> str:
        text, _ = await self.chat_with_metrics(model=model, messages=messages, options=options)
        return text

    async def chat_with_metrics(self, model: str, messages: list[dict], options: dict) -> tuple[str, dict]:
        # Strip non-Ollama keys before passing options (e.g. tone_of_voice, message_size)
        ollama_options = {
            k: v for k, v in options.items()
            if k in {"temperature", "top_k", "top_p", "repeat_penalty", "num_predict", "num_ctx", "seed"}
        }
        # "format": "json" makes Ollama constrain decoding to a JSON value.
        extra = {"format": options["format"]} if options.get("format") else {}
        if settings.ollama_keep_alive:
            extra["keep_alive"] = settings.ollama_keep_alive
        response = await asyncio.to_thread(
            ollama.chat,
            model=model,
            messages=messages,
            options=ollama_options,
            **extra,
        )
        message = response.get("message") if hasattr(response, "get") else getattr(response, "message", None)
        content = (message.get("content") if hasattr(message, "get") else getattr(message, "content", "")) or ""
        return content, from_ollama(response)
