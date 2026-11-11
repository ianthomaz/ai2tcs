"""Backup reader for document extraction (NF, boleto) when the local LLM is down.

Off unless DOC_EXTRACT_FALLBACK_PROVIDER names an external provider (openai, anthropic,
gemini) with its key in .env. Only document reading uses it: the text of the document goes
to that provider, so turning it on is the owner's decision. Every call is recorded like
any other (`llm_call`, kind `<kind>_fallback`).

`llm_reading(warnings)` tells the response who read the document: local, fallback or
unavailable (nobody: only the heuristic fields came back).
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from app.config import settings
from app.llm import metrics as llm_metrics

logger = logging.getLogger(__name__)

UNAVAILABLE_PREFIX = "LLM unavailable"
FALLBACK_OK_PREFIX = "LLM local indisponível; leitura feita pelo provedor de reserva"
FALLBACK_FAILED_PREFIX = "Provedor de reserva"


async def read_with_fallback(
    kind: str,
    messages: list[dict],
    options: dict,
    parse: Callable[[str], dict[str, Any]],
    warnings: list[str],
) -> tuple[dict[str, Any], list[str]]:
    """Called after the local LLM gave up. Returns ({}, warnings) when there is no backup."""
    name = (settings.doc_extract_fallback_provider or "").strip().lower()
    if not name or name == "ollama":
        return {}, warnings
    from app.llm.factory import provider_by_name

    model = (settings.doc_extract_fallback_model or "").strip()
    try:
        provider = provider_by_name(name)
        text, metrics = await provider.chat_with_metrics(model=model, messages=messages, options=options)
        llm_metrics.record(f"{kind}_fallback", None, model or name, metrics)
    except Exception as exc:  # noqa: BLE001
        logger.warning("doc fallback %s failed for %s: %s", name, kind, exc)
        warnings.append(f"{FALLBACK_FAILED_PREFIX} ({name}) também falhou: {str(exc)[:200]}")
        return {}, warnings
    parsed = parse(text or "")
    warnings.append(f"{FALLBACK_OK_PREFIX} ({name}).")
    if not parsed:
        warnings.append("LLM returned non-JSON content; kept Python extraction.")
    return parsed, warnings


def llm_reading(warnings: list[str]) -> str:
    """local · fallback · unavailable, from the warnings the readers append."""
    if any(w.startswith(FALLBACK_OK_PREFIX) for w in warnings):
        return "fallback"
    if any(w.startswith(UNAVAILABLE_PREFIX) for w in warnings):
        return "unavailable"
    return "local"
