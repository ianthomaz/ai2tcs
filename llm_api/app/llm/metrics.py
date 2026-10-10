"""Per-call LLM metrics: tokens and time, and the flag for calls near the context limit.

Ollama returns prompt_eval_count / eval_count and durations (ns) with every chat; the text
alone hides whether the prompt fit. Every call logs one `llm_call` line; a call whose prompt
reaches LLM_HEAVY_PROMPT_TOKENS also logs `llm_heavy` at WARNING, and one that reaches 90% of
LLM_CONTEXT_REFERENCE_TOKENS is flagged `near_ctx_limit` — Ollama may have cut the prompt.
Only counts and times are logged, never prompt or answer text.
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger("app.llm.metrics")

_NS_PER_MS = 1_000_000


def _ms(raw: object) -> int | None:
    try:
        return int(raw) // _NS_PER_MS  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _int(raw: object) -> int | None:
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def from_ollama(response: Any) -> dict[str, Any]:
    """Metrics from an ollama.chat response (dict or ChatResponse)."""
    get = response.get if hasattr(response, "get") else (lambda k, d=None: getattr(response, k, d))
    out = {
        "prompt_tokens": _int(get("prompt_eval_count")),
        "output_tokens": _int(get("eval_count")),
        "total_ms": _ms(get("total_duration")),
        "load_ms": _ms(get("load_duration")),
        "prompt_ms": _ms(get("prompt_eval_duration")),
        "output_ms": _ms(get("eval_duration")),
    }
    return {k: v for k, v in out.items() if v is not None}


def flags(metrics: dict[str, Any], ctx_tokens: int | None = None) -> dict[str, bool]:
    """`ctx_tokens` is the num_ctx the call sent; without it, Ollama's default is assumed."""
    prompt = metrics.get("prompt_tokens") or 0
    window = ctx_tokens or settings.llm_context_reference_tokens
    return {
        "heavy": prompt >= settings.llm_heavy_prompt_tokens,
        "near_ctx_limit": prompt >= int(window * 0.9),
    }


def record(
    kind: str,
    project_id: str | None,
    model: str,
    metrics: dict[str, Any],
    ctx_tokens: int | None = None,
) -> dict[str, Any]:
    """Log the call; return metrics + flags, ready to store next to the job."""
    if not metrics:
        return {}
    out = {**metrics, **flags(metrics, ctx_tokens), "model": model}
    if ctx_tokens:
        out["ctx_tokens"] = ctx_tokens
    line = (
        "kind=%s project=%s model=%s prompt_tokens=%s output_tokens=%s total_ms=%s load_ms=%s "
        "heavy=%s near_ctx_limit=%s"
    )
    args = (
        kind,
        project_id or "-",
        model,
        out.get("prompt_tokens"),
        out.get("output_tokens"),
        out.get("total_ms"),
        out.get("load_ms"),
        out["heavy"],
        out["near_ctx_limit"],
    )
    logger.info("llm_call " + line, *args)
    if out["heavy"] or out["near_ctx_limit"]:
        logger.warning("llm_heavy " + line, *args)
    return out
