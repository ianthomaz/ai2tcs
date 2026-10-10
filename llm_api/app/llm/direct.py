"""Direct Ollama chat for routes that pass Ollama-only arguments (format, think, …).

The one door for `ollama.chat` outside the provider: every call is bounded and recorded
(app/llm/metrics.py). Routes that only need text go through `get_provider(project)`.
"""
from __future__ import annotations

import asyncio
from typing import Any

import ollama

from app.config import settings
from app.llm import metrics as llm_metrics


async def ollama_chat(kind: str, project_id: str | None, *, timeout_s: float | None = None, **kwargs: Any) -> Any:
    """`ollama.chat(**kwargs)` in a thread, bounded by `timeout_s` (default LLM_CHAT_TIMEOUT_S).

    Raises asyncio.TimeoutError on the bound; the caller keeps its own failure path.
    """
    if settings.ollama_keep_alive and "keep_alive" not in kwargs:
        kwargs["keep_alive"] = settings.ollama_keep_alive
    response = await asyncio.wait_for(
        asyncio.to_thread(ollama.chat, **kwargs),
        timeout=timeout_s if timeout_s is not None else settings.llm_chat_timeout_s,
    )
    llm_metrics.record(kind, project_id, str(kwargs.get("model") or ""), llm_metrics.from_ollama(response))
    return response
