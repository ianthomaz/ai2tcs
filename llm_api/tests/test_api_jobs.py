"""Tests for /jobs endpoints."""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime


HEADERS = {"Authorization": "Bearer test-token"}

MOCK_JOB = {
    "id": "job-123",
    "project_id": "test_project",
    "question": "O que e fitness?",
    "question_hash": "abc123",
    "status": "done",
    "progress": "completed",
    "answer": "Fitness e a pratica de exercicios fisicos.",
    "sources": [{"id": "1", "path": "doc.md", "snippet": "trecho"}],
    "confidence": "high",
    "error_message": None,
    "created_at": datetime(2026, 1, 1, 10, 0),
    "updated_at": datetime(2026, 1, 1, 10, 5),
}


@pytest.fixture(autouse=True)
def mock_token():
    with patch("app.config.settings.llm_api_token", "test-token"):
        yield


@pytest.mark.asyncio
async def test_list_jobs(client):
    with patch("app.db.job_list", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = ([MOCK_JOB], 1)
        response = await client.get("/jobs", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["jobs"][0]["job_id"] == "job-123"


@pytest.mark.asyncio
async def test_job_stats(client):
    with patch("app.db.job_stats", new_callable=AsyncMock) as mock_stats:
        mock_stats.return_value = {
            "total": 100,
            "by_status": {"done": 80, "failed": 5},
            "by_project": {"test_project": 100},
            "last_24h": 10,
            "avg_duration_seconds": 4.2,
        }
        response = await client.get("/jobs/stats", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 100
        assert data["last_24h"] == 10


@pytest.mark.asyncio
async def test_cancel_queued_job(client):
    queued_job = {**MOCK_JOB, "status": "queued"}
    with patch("app.db.job_get", new_callable=AsyncMock) as mock_get, \
         patch("app.db.job_cancel", new_callable=AsyncMock) as mock_cancel:
        mock_get.return_value = queued_job
        response = await client.post("/jobs/job-123/cancel", headers=HEADERS)
        assert response.status_code == 200
        mock_cancel.assert_called_once_with("job-123")


@pytest.mark.asyncio
async def test_cancel_done_job_fails(client):
    with patch("app.db.job_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MOCK_JOB  # status = done
        response = await client.post("/jobs/job-123/cancel", headers=HEADERS)
        assert response.status_code == 409


@pytest.mark.asyncio
async def test_cancel_nonexistent_job(client):
    with patch("app.db.job_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        response = await client.post("/jobs/nonexistent/cancel", headers=HEADERS)
        assert response.status_code == 404
