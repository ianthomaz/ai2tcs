"""Tests for Dual LLM strategy (fast/smart models)."""
from unittest.mock import AsyncMock, patch
import pytest

HEADERS = {"Authorization": "Bearer test-token"}

@pytest.fixture(autouse=True)
def mock_token():
    with patch("app.config.settings.llm_api_token", "test-token"):
        yield

@pytest.mark.asyncio
async def test_router_uses_fast_model_by_default(client):
    with patch("app.api.message_router.get_project", new_callable=AsyncMock) as mock_project, \
         patch("app.api.message_router.retrieve", new_callable=AsyncMock) as mock_retrieve, \
         patch("ollama.chat", return_value={"message": {"content": '{"action": "escalate", "suggested_route": "ask", "escalate_to": "smart"}'}}) as mock_ollama:

        mock_project.return_value = {"project_id": "p1", "config_json": {}}
        mock_retrieve.return_value = []

        body = {"message": "oi", "project_id": "p1"}
        r = await client.post("/router", json=body, headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["action"] == "escalate"

        # Should use llama3:8b (fast)
        mock_ollama.assert_called_once()
        args, kwargs = mock_ollama.call_args
        assert kwargs["model"] == "llama3:8b"

@pytest.mark.asyncio
async def test_router_uses_explicit_model(client):
    with patch("app.api.message_router.get_project", new_callable=AsyncMock) as mock_project, \
         patch("app.api.message_router.retrieve", new_callable=AsyncMock) as mock_retrieve, \
         patch("ollama.chat", return_value={"message": {"content": '{"action": "escalate", "suggested_route": "ask", "escalate_to": "smart"}'}}) as mock_ollama:

        mock_project.return_value = {"project_id": "p1", "config_json": {}}
        mock_retrieve.return_value = []

        body = {"message": "oi", "project_id": "p1", "model": "smart"}
        r = await client.post("/router", json=body, headers=HEADERS)
        assert r.status_code == 200

        # Should use qwen2.5:14b-instruct (smart)
        mock_ollama.assert_called_once()
        args, kwargs = mock_ollama.call_args
        assert kwargs["model"] == "qwen2.5:14b-instruct"

@pytest.mark.asyncio
async def test_router_uses_compact_model(client):
    with patch("app.api.message_router.get_project", new_callable=AsyncMock) as mock_project, \
         patch("app.api.message_router.retrieve", new_callable=AsyncMock) as mock_retrieve, \
         patch("ollama.chat", return_value={"message": {"content": '{"action": "escalate", "suggested_route": "ask", "escalate_to": "smart"}'}}) as mock_ollama:

        mock_project.return_value = {"project_id": "p1", "config_json": {}}
        mock_retrieve.return_value = []

        body = {"message": "oi", "project_id": "p1", "model": "compact"}
        r = await client.post("/router", json=body, headers=HEADERS)
        assert r.status_code == 200

        # Should use qwen2.5:7b-instruct (compact)
        mock_ollama.assert_called_once()
        args, kwargs = mock_ollama.call_args
        assert kwargs["model"] == "qwen2.5:7b-instruct"

@pytest.mark.asyncio
async def test_router_uses_reasoner_model(client):
    with patch("app.api.message_router.get_project", new_callable=AsyncMock) as mock_project, \
         patch("app.api.message_router.retrieve", new_callable=AsyncMock) as mock_retrieve, \
         patch("ollama.chat", return_value={"message": {"content": '{"action": "escalate", "suggested_route": "ask", "escalate_to": "smart"}'}}) as mock_ollama:

        mock_project.return_value = {"project_id": "p1", "config_json": {}}
        mock_retrieve.return_value = []

        body = {"message": "oi", "project_id": "p1", "model": "reasoner"}
        r = await client.post("/router", json=body, headers=HEADERS)
        assert r.status_code == 200

        # Should use deepseek-r1:8b (reasoner)
        mock_ollama.assert_called_once()
        args, kwargs = mock_ollama.call_args
        assert kwargs["model"] == "deepseek-r1:8b"

@pytest.mark.asyncio
async def test_router_accepts_legacy_confidence_string_and_extra_keys(client):
    """LLM noise (extra keys, high/medium/low) must not 500 the endpoint."""
    raw = (
        '{"action": "escalate", "suggested_route": "ask", "escalate_to": "smart", '
        '"confidence": "high", "reason": "legacy noise", "foo": 1}'
    )
    with patch("app.api.message_router.get_project", new_callable=AsyncMock) as mock_project, \
         patch("app.api.message_router.retrieve", new_callable=AsyncMock) as mock_retrieve, \
         patch("ollama.chat", return_value={"message": {"content": raw}}):

        mock_project.return_value = {"project_id": "p1", "config_json": {}}
        mock_retrieve.return_value = []

        r = await client.post(
            "/router",
            json={"message": "oi", "project_id": "p1"},
            headers=HEADERS,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["confidence"] == 0.85
        assert "reason" not in body


@pytest.mark.asyncio
async def test_router_empty_answer_now_resolves_escalate_alias(client):
    """answer_now with blank answer is coerced to escalate and still gets a concrete escalate_to."""
    raw = '{"action": "answer_now", "suggested_route": "saudacao", "answer": "   ", "escalate_to": null}'
    with patch("app.api.message_router.get_project", new_callable=AsyncMock) as mock_project, \
         patch("app.api.message_router.retrieve", new_callable=AsyncMock) as mock_retrieve, \
         patch("ollama.chat", return_value={"message": {"content": raw}}), \
         patch("app.jobs.worker.speculative_warmup", new_callable=AsyncMock):
        mock_project.return_value = {"project_id": "p1", "config_json": {}}
        mock_retrieve.return_value = []

        r = await client.post(
            "/router",
            json={"message": "oi", "project_id": "p1"},
            headers=HEADERS,
        )
        assert r.status_code == 200
        out = r.json()
        assert out["action"] == "escalate"
        assert out["escalate_to"] in ("compact", "smart", "reasoner")
        assert out["answer"] is None


@pytest.mark.asyncio
async def test_ask_records_model_choice(client):
    with patch("app.api.ask.get_project", new_callable=AsyncMock) as mock_project, \
         patch("app.api.ask.db_module.job_find_recent_duplicate", return_value=None), \
         patch("app.api.ask.db_module.job_create", new_callable=AsyncMock) as mock_create:

        mock_project.return_value = {"project_id": "p1"}
        mock_create.return_value = "job-123"

        body = {"project_id": "p1", "question": "test?", "model": "fast"}
        r = await client.post("/ask", json=body, headers=HEADERS)
        assert r.status_code == 202

        mock_create.assert_called_once()
        args, kwargs = mock_create.call_args
        # user_context should contain __llm_model
        assert kwargs["user_context"]["__llm_model"] == "fast"
