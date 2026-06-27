"""Contract: every REST API path (except public health/metrics) requires Bearer when global token is unset."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings


class _MockAcquireCM:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_args):
        return False


@pytest.fixture
def clear_global_token():
    with patch.object(settings, "llm_api_token", ""):
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        ("POST", "/ask", {"json": {"project_id": "p", "question": "q"}}),
        ("GET", "/status/00000000-0000-0000-0000-000000000001", {}),
        ("GET", "/result/00000000-0000-0000-0000-000000000001", {}),
        ("POST", "/ingest", {"json": {"project_id": "p", "incremental": False}}),
        ("POST", "/router", {"json": {"message": "hi", "project_id": "p"}}),
        ("POST", "/extract", {"json": {"project_id": "p", "field": "name", "message": "x"}}),
        ("POST", "/extract-multi", {"json": {"project_id": "p", "message": "x", "fields": ["name"]}}),
        ("POST", "/nfExtract", {}),
        ("POST", "/boletoExtract", {}),
        ("POST", "/nabilvideomap/qualify-caption", {"json": {"project_id": "p", "text": "caption"}}),
        ("POST", "/audio/transcribe", {"files": {"file": ("x.wav", b"RIFF", "audio/wav")}}),
        ("POST", "/audio/ask", {"files": {"file": ("x.wav", b"RIFF", "audio/wav")}}),
        ("GET", "/projects", {}),
        ("GET", "/projects/p", {}),
        ("POST", "/projects", {"json": {"project_id": "newp", "sources": ["/tmp"]}}),
        ("PUT", "/projects/p", {"json": {"name": "n"}}),
        ("DELETE", "/projects/p", {}),
        ("GET", "/jobs", {}),
        ("GET", "/jobs/stats", {}),
        ("POST", "/jobs/00000000-0000-0000-0000-000000000001/cancel", {}),
        ("POST", "/edu/chat", {"json": {"project_id": "p", "message": "hi"}}),
        ("POST", "/edu/exercise", {"json": {"project_id": "p", "level": "A1"}}),
        ("GET", "/edu/vocabulary", {"params": {"language": "pt", "level": "A1"}}),
        ("POST", "/edu/vocabulary", {"json": {"language": "pt", "level": "A1", "word": "w", "translation": "t"}}),
        ("GET", "/edu/grammar", {"params": {"language": "pt", "level": "A1"}}),
        ("POST", "/edu/grammar", {"json": {"language": "pt", "level": "A1", "topic": "t", "explanation": "e"}}),
        ("POST", "/edu/progress", {"json": {"project_id": "p", "user_id": "u", "activity": "x"}}),
        ("PUT", "/users/profile", {"json": {"user_id": "u", "project_id": "p"}}),
        ("GET", "/users/profile/p/u", {}),
        ("DELETE", "/users/profile/p/u", {}),
        ("POST", "/users/conversation/reset", {"json": {"user_id": "u", "project_id": "p"}}),
        ("POST", "/users/conversation/maintenance", {}),
    ],
)
async def test_route_requires_bearer_when_no_global_token(client, clear_global_token, method, path, kwargs):
    call = getattr(client, method.lower())
    r = await call(path, **kwargs)
    assert r.status_code == 401, f"{method} {path} -> {r.status_code} {r.text[:200]}"


@pytest.mark.asyncio
async def test_health_no_auth_ok(client, clear_global_token):
    with patch("app.api.health.httpx.AsyncClient") as mock_httpx, patch("app.api.health.db_module.get_pool") as mock_pool:
        mock_httpx.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(get=AsyncMock(side_effect=Exception("down")))
        )
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)
        mock_pool_obj = MagicMock()
        mock_pool_obj.acquire = MagicMock(return_value=_MockAcquireCM(mock_conn))
        mock_pool.return_value = mock_pool_obj
        r = await client.get("/health")
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_metrics_no_auth_ok(client, clear_global_token):
    with patch("app.api.health.db_module.job_stats", new_callable=AsyncMock) as mock_stats:
        mock_stats.return_value = {
            "total": 0,
            "last_24h": 0,
            "by_status": {},
            "by_project": {},
            "avg_duration_seconds": 0.0,
        }
        r = await client.get("/metrics")
        assert r.status_code == 200
        assert "llm_api_ready" in r.text


@pytest.mark.asyncio
async def test_dashboard_root_redirects_without_session(client, clear_global_token):
    r = await client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 302
    assert "/dashboard/login" in (r.headers.get("location") or "")


@pytest.mark.asyncio
async def test_global_token_allows_ask_with_mocks(client, mock_pool):
    with patch.object(settings, "llm_api_token", "matrix-token"), patch(
        "app.api.ask.get_project", new_callable=AsyncMock
    ) as gp, patch("app.api.ask.db_module.job_find_recent_duplicate", new_callable=AsyncMock) as dup, patch(
        "app.api.ask.db_module.job_create", new_callable=AsyncMock
    ) as jc:
        gp.return_value = {"project_id": "p1"}
        dup.return_value = None
        jc.return_value = str(uuid.uuid4())
        r = await client.post(
            "/ask",
            headers={"Authorization": "Bearer matrix-token"},
            json={"project_id": "p1", "question": "unique question for matrix test"},
        )
        assert r.status_code == 202
        assert "job_id" in r.json()
