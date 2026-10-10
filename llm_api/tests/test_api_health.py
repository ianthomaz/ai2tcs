"""Tests for /health and /metrics endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class _MockAcquireCM:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Health endpoint should return status even with mocked deps."""
    with patch("app.api.health.httpx.AsyncClient") as mock_httpx, \
         patch("app.api.health.db_module.get_pool") as mock_pool:
        # Mock Ollama unreachable
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
            get=AsyncMock(side_effect=Exception("connection refused"))
        ))
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)
        # Mock PostgreSQL OK
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)
        mock_pool_obj = MagicMock()
        mock_pool_obj.acquire = MagicMock(return_value=_MockAcquireCM(mock_conn))
        mock_pool.return_value = mock_pool_obj

        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert "uptime_seconds" in data


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    """Metrics endpoint should return prometheus-like text."""
    with patch("app.api.health.db_module.job_stats", new_callable=AsyncMock) as mock_stats:
        mock_stats.return_value = {
            "total": 42,
            "last_24h": 5,
            "by_status": {"done": 30, "failed": 2},
            "by_project": {"bikeanjoall_2026": 40},
            "avg_duration_seconds": 3.5,
        }
        response = await client.get("/metrics")
        assert response.status_code == 200
        text = response.text
        assert "llm_api_ready 1" in text
        assert "llm_jobs_total 42" in text
        assert "llm_jobs_last_24h 5" in text


@pytest.mark.asyncio
async def test_metrics_lists_heavy_llm_calls(client):
    with patch("app.api.health.db_module.job_stats", new_callable=AsyncMock) as mock_stats, patch(
        "app.api.health.db_module.llm_heavy_counts_24h", new_callable=AsyncMock
    ) as heavy:
        mock_stats.return_value = {"total": 1, "last_24h": 1, "by_status": {}, "by_project": {}}
        heavy.return_value = {"bikeanjoall_2026": {"heavy": 3, "near_limit": 1}}
        text = (await client.get("/metrics")).text
    assert 'llm_calls_heavy_24h{project="bikeanjoall_2026"} 3' in text
    assert 'llm_calls_near_ctx_limit_24h{project="bikeanjoall_2026"} 1' in text


@pytest.mark.asyncio
async def test_metrics_is_plain_text(client):
    with patch("app.api.health.db_module.job_stats", new_callable=AsyncMock) as mock_stats:
        mock_stats.return_value = {"total": 1, "last_24h": 1, "by_status": {}, "by_project": {}}
        r = await client.get("/metrics")
    assert r.headers["content-type"].startswith("text/plain")
    assert r.text.startswith("llm_api_ready 1\n")
