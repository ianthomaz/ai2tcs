"""dest was written to disk before job_create ran. If job_create failed (DB down,
timeout, constraint), nothing removed the file — audio_temp_subdir accumulates
permanent orphans, since nothing in the repo reaps unreferenced files there.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def mock_token():
    with patch("app.config.settings.llm_api_token", "test-token"):
        yield


@pytest.mark.asyncio
async def test_orphan_temp_file_is_removed_when_job_create_fails(client, tmp_path):
    wav = b"RIFF" + b"\x00" * 32

    with patch.object(settings, "data_dir", tmp_path), \
        patch("app.api.audio.get_project", new_callable=AsyncMock) as mock_proj, \
        patch("app.api.audio.db_module.job_create", new_callable=AsyncMock) as mock_create:
        mock_proj.return_value = {"project_id": "p1", "sources": [], "config_json": {}}
        mock_create.side_effect = ConnectionError("db down")

        with pytest.raises(ConnectionError):
            await client.post(
                "/audio/transcribe",
                headers=HEADERS,
                data={"project_id": "p1"},
                files={"file": ("note.wav", wav, "audio/wav")},
            )

    audio_tmp = tmp_path / settings.audio_temp_subdir
    leftover = list(audio_tmp.glob("*")) if audio_tmp.exists() else []
    assert leftover == [], f"orphaned temp file(s) left behind: {leftover}"


@pytest.mark.asyncio
async def test_temp_file_exists_when_job_create_succeeds(client, tmp_path):
    """job_create receives the real path — the file must exist for the worker to read it."""
    wav = b"RIFF" + b"\x00" * 32
    seen_path = {}

    async def fake_create(*_a, **kw):
        seen_path["audio_path"] = kw["audio_path"]
        return kw["job_id"]

    with patch.object(settings, "data_dir", tmp_path), \
        patch("app.api.audio.get_project", new_callable=AsyncMock) as mock_proj, \
        patch("app.api.audio.db_module.job_create", side_effect=fake_create):
        mock_proj.return_value = {"project_id": "p1", "sources": [], "config_json": {}}
        response = await client.post(
            "/audio/transcribe",
            headers=HEADERS,
            data={"project_id": "p1"},
            files={"file": ("note.wav", wav, "audio/wav")},
        )

    assert response.status_code == 202
    from pathlib import Path

    assert Path(seen_path["audio_path"]).is_file()
