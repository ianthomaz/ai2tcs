"""Tests for /projects CRUD endpoints."""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime


MOCK_PROJECT = {
    "id": "cuid123",
    "project_id": "test_project",
    "name": "Test Project",
    "sources": ["/path/to/content"],
    "config_json": {"chunking": {"chunk_size": 512}},
    "created_at": datetime(2026, 1, 1),
    "updated_at": datetime(2026, 1, 1),
}

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def mock_token():
    with patch("app.config.settings.llm_api_token", "test-token"):
        yield


@pytest.mark.asyncio
async def test_list_projects(client):
    with patch("app.db.project_list_all", new_callable=AsyncMock) as mock_list, \
         patch("app.db.project_get_themes", new_callable=AsyncMock) as mock_themes:
        mock_list.return_value = [MOCK_PROJECT]
        mock_themes.return_value = ["saude"]
        response = await client.get("/projects", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["projects"][0]["project_id"] == "test_project"
        assert data["projects"][0]["themes"] == ["saude"]


@pytest.mark.asyncio
async def test_create_project(client):
    with patch("app.db.project_get", new_callable=AsyncMock) as mock_get, \
         patch("app.db.project_create", new_callable=AsyncMock) as mock_create, \
         patch("app.db.project_themes_set", new_callable=AsyncMock), \
         patch("app.db.project_get_themes", new_callable=AsyncMock) as mock_themes:
        mock_get.return_value = None  # no existing
        mock_create.return_value = MOCK_PROJECT
        mock_themes.return_value = ["saude"]
        response = await client.post("/projects", headers=HEADERS, json={
            "project_id": "test_project",
            "name": "Test Project",
            "sources": ["/path/to/content"],
            "themes": ["saude"],
        })
        assert response.status_code == 201
        assert response.json()["project_id"] == "test_project"


@pytest.mark.asyncio
async def test_create_duplicate_project(client):
    with patch("app.db.project_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MOCK_PROJECT  # already exists
        response = await client.post("/projects", headers=HEADERS, json={
            "project_id": "test_project",
        })
        assert response.status_code == 409


@pytest.mark.asyncio
async def test_get_project_not_found(client):
    with patch("app.db.project_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        response = await client.get("/projects/nonexistent", headers=HEADERS)
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_project(client):
    with patch("app.db.project_get", new_callable=AsyncMock) as mock_get, \
         patch("app.db.project_delete", new_callable=AsyncMock):
        mock_get.return_value = MOCK_PROJECT
        response = await client.delete("/projects/test_project", headers=HEADERS)
        assert response.status_code == 204


@pytest.mark.asyncio
async def test_unauthorized(client):
    response = await client.get("/projects")
    assert response.status_code == 401
