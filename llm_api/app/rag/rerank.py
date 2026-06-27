"""Semantic reranking of retrieved RAG chunks (opt-in via RAG_RERANK_ENABLED)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_reranker = None
_reranker_load_failed = False


def _get_reranker():
    global _reranker, _reranker_load_failed
    if _reranker_load_failed:
        return None
    if _reranker is not None:
        return _reranker
    try:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        return _reranker
    except Exception as exc:
        logger.warning("RAG reranker unavailable: %s", exc)
        _reranker_load_failed = True
        return None


def rerank_chunks(query: str, chunks: list[dict], top_k: int | None = None) -> list[dict]:
    """Re-score chunks by (query, snippet) relevance. Returns chunks sorted best-first."""
    if not chunks:
        return chunks
    model = _get_reranker()
    if model is None:
        return chunks

    pairs = [(query, (c.get("snippet") or "")[:2000]) for c in chunks]
    try:
        scores = model.predict(pairs)
    except Exception as exc:
        logger.warning("RAG rerank predict failed: %s", exc)
        return chunks

    scored = list(zip(scores, chunks))
    scored.sort(key=lambda x: float(x[0]), reverse=True)
    ranked = [c for _, c in scored]
    if top_k is not None:
        return ranked[:top_k]
    return ranked
