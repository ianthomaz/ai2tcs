"""Test fixtures: async client, mocked DB, mocked Ollama."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_pool():
    """Mock the database pool so tests don't need a real PostgreSQL."""
    mock = AsyncMock()
    with patch("app.db._pool", mock), patch("app.db.get_pool", return_value=mock):
        yield mock


@pytest.fixture
async def client(mock_pool):
    """Async test client with mocked lifespan (no real DB/worker)."""
    with patch("app.main.get_pool", new_callable=AsyncMock), \
         patch("app.main.close_pool", new_callable=AsyncMock), \
         patch("app.main.job_worker._worker_coro", new_callable=AsyncMock):
        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
