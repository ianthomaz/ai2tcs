"""Answer signals: what the service knows about an answer, not what the model says about it.

The model's own confidence is an opinion (seen high on answers people rated bad). These come
from the pipeline: how close the best passage was, how many passed the threshold, whether the
sanitizer or a guard changed the text, and whether the prompt neared the context window.
Additive in the API (`signals`): clients that do not read it are unaffected.
"""
from __future__ import annotations

from typing import Any


def best_distance(chunks: list[dict]) -> float | None:
    values = [float(c["distance"]) for c in chunks if c.get("distance") is not None]
    return round(min(values), 3) if values else None


def build(
    *,
    chunks: list[dict],
    answer: str | None,
    sanitize_hit: bool = False,
    guard_hit: bool = False,
    metrics: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    m = metrics or {}
    out: dict[str, Any] = {
        "best_distance": best_distance(chunks),
        "chunks_kept": len(chunks),
        "sanitize_hit": sanitize_hit,
        "guard_hit": guard_hit,
        "answer_chars": len((answer or "").strip()),
        "prompt_tokens": m.get("prompt_tokens"),
        "near_ctx_limit": m.get("near_ctx_limit"),
    }
    out.update(extra)
    return out
