"""Smoke tests for /audio routes (no real Whisper or DB)."""

import pytest
from unittest.mock import AsyncMock, patch

from app.config import settings

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def mock_token():
    with patch("app.config.settings.llm_api_token", "test-token"):
        yield


@pytest.mark.asyncio
async def test_openapi_includes_audio_paths(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json().get("paths", {})
    assert "/audio/transcribe" in paths
    assert "/audio/ask" in paths


@pytest.mark.asyncio
async def test_audio_transcribe_requires_multipart(client):
    """Wrong content-type should fail validation before DB."""
    response = await client.post("/audio/transcribe", headers=HEADERS, json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_audio_transcribe_enqueue(client, tmp_path):
    wav = b"RIFF" + b"\x00" * 32

    with patch.object(settings, "data_dir", tmp_path), \
         patch("app.api.audio.get_project", new_callable=AsyncMock) as mock_proj, \
         patch("app.api.audio.db_module.job_create", new_callable=AsyncMock) as mock_create:
        mock_proj.return_value = {"project_id": "p1", "sources": [], "config_json": {}}
        response = await client.post(
            "/audio/transcribe",
            headers=HEADERS,
            data={"project_id": "p1"},
            files={"file": ("note.wav", wav, "audio/wav")},
        )

    assert response.status_code == 202
    body = response.json()
    assert len(body["job_id"]) == 36
    assert "/status/" in body["status_url"]
    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs.get("job_kind") == "audio_transcribe"
