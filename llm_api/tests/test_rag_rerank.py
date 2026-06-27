"""Tests for RAG rerank helper (mocked, no model download)."""
from unittest.mock import MagicMock, patch

from app.rag.rerank import rerank_chunks


def test_rerank_chunks_no_model_returns_unchanged() -> None:
    chunks = [{"snippet": "alpha", "id": "1"}, {"snippet": "beta", "id": "2"}]
    with patch("app.rag.rerank._get_reranker", return_value=None):
        out = rerank_chunks("query", chunks, top_k=2)
    assert out == chunks


def test_rerank_chunks_reorders_by_score() -> None:
    chunks = [{"snippet": "low", "id": "1"}, {"snippet": "high", "id": "2"}]
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.1, 0.9]
    with patch("app.rag.rerank._get_reranker", return_value=mock_model):
        out = rerank_chunks("query", chunks, top_k=2)
    assert out[0]["id"] == "2"
