"""Content-Length is checked before body parsing runs. /audio/* only checked
audio_max_bytes after Starlette's multipart parser had already spooled the whole
upload, and /ingest/upload had no size check of any kind.
"""
from unittest.mock import patch

import pytest

from app.config import settings

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def mock_token():
    with patch("app.config.settings.llm_api_token", "test-token"):
        yield


@pytest.mark.asyncio
async def test_declared_oversized_body_rejected_before_route_runs(client):
    """Lying about a huge Content-Length must 413 without ever hitting auth/routing logic."""
    r = await client.post(
        "/router",
        content=b"{}",
        headers={**HEADERS, "content-length": str(settings.max_request_body_bytes + 1)},
    )
    assert r.status_code == 413
    assert "too large" in r.json()["detail"]


@pytest.mark.asyncio
async def test_normal_sized_request_is_unaffected(client):
    r = await client.get("/openapi.json")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_malformed_content_length_does_not_crash(client):
    r = await client.get("/openapi.json", headers={"content-length": "not-a-number"})
    assert r.status_code == 200
