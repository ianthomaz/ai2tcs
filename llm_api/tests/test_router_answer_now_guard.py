"""answer_now text used to skip both _sanitize_answer and guard_answer_for_profile —
the two nets /ask always runs an answer through. A router-generated reply could leak
a banned meta-phrase or a project's forbidden term with no net at all.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.api import message_router

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def mock_token():
    with patch("app.config.settings.llm_api_token", "test-token"):
        yield


async def _post_router(client, *, project, llm_json):
    async def fake_to_thread(_func, *_a, **_kw):
        return {"message": {"content": llm_json}}

    with patch.object(message_router.asyncio, "to_thread", side_effect=fake_to_thread), \
        patch("app.api.message_router.get_project", new_callable=AsyncMock) as gp, \
        patch("app.api.message_router.get_rag_policies", return_value={}), \
        patch("app.api.message_router.get_router_config", return_value={}), \
        patch("app.api.message_router.retrieve", new_callable=AsyncMock, return_value=[]), \
        patch("app.api.message_router.log_sync_llm_job", new_callable=AsyncMock):
        gp.return_value = project
        return await client.post(
            "/router",
            json={"message": "oi", "project_id": project["project_id"]},
            headers=HEADERS,
        )


@pytest.mark.asyncio
async def test_answer_now_strips_banned_meta_phrase(client):
    project = {"project_id": "p1", "config_json": {}}
    llm_json = (
        '{"action": "answer_now", "suggested_route": "ask", "confidence": 0.8, '
        '"answer": "Com base no contexto fornecido, o evento é sábado."}'
    )
    r = await _post_router(client, project=project, llm_json=llm_json)
    assert r.status_code == 200
    answer = r.json()["answer"]
    assert "com base no contexto fornecido" not in answer.lower()
    assert "sábado" in answer


@pytest.mark.asyncio
async def test_answer_now_blocked_by_project_forbidden_terms(client):
    project = {
        "project_id": "p1",
        "config_json": {
            "no_answer_fallback": "Fale com a equipe.",
            "policies": {"forbidden_terms": ["concorrente xpto"]},
        },
    }
    llm_json = (
        '{"action": "answer_now", "suggested_route": "ask", "confidence": 0.8, '
        '"answer": "Recomendo procurar o concorrente XPTO para isso."}'
    )
    r = await _post_router(client, project=project, llm_json=llm_json)
    assert r.status_code == 200
    assert r.json()["answer"] == "Fale com a equipe."


@pytest.mark.asyncio
async def test_answer_now_clean_answer_is_untouched(client):
    project = {"project_id": "p1", "config_json": {}}
    llm_json = (
        '{"action": "answer_now", "suggested_route": "ask", "confidence": 0.9, '
        '"answer": "O evento é sábado às 9h."}'
    )
    r = await _post_router(client, project=project, llm_json=llm_json)
    assert r.status_code == 200
    assert r.json()["answer"] == "O evento é sábado às 9h."


@pytest.mark.asyncio
async def test_escalate_path_is_not_touched_by_the_guard(client):
    """The guard only runs for answer_now; escalate keeps its existing shape."""
    project = {"project_id": "p1", "config_json": {}}
    llm_json = '{"action": "escalate", "suggested_route": "ask", "escalate_to": "smart", "confidence": 0.5}'
    r = await _post_router(client, project=project, llm_json=llm_json)
    assert r.status_code == 200
    data = r.json()
    assert data["action"] == "escalate"
    assert data["answer"] is None
