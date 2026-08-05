"""Tests for zapzap-oriented API fields (client_status, ask body shape)."""
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.api import extract as extract_module

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def mock_token():
    with patch("app.config.settings.llm_api_token", "test-token"):
        yield


@pytest.mark.asyncio
async def test_status_includes_client_status_processing(client):
    with patch("app.api.ask.db_module.job_get", new_callable=AsyncMock) as m:
        m.return_value = {
            "id": "job-uuid",
            "status": "working",
            "progress": "generating",
            "created_at": datetime(2026, 1, 1, 12, 0, 0),
        }
        r = await client.get("/status/job-uuid", headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "working"
        assert data["client_status"] == "processing"


@pytest.mark.asyncio
async def test_status_client_status_done_matches(client):
    with patch("app.api.ask.db_module.job_get", new_callable=AsyncMock) as m:
        m.return_value = {
            "id": "job-uuid",
            "status": "done",
            "progress": "complete",
            "created_at": datetime(2026, 1, 1, 12, 0, 0),
        }
        r = await client.get("/status/job-uuid", headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert data["client_status"] == "done"


@pytest.mark.asyncio
async def test_extract_multi_rejects_empty_fields(client):
    body = {"task": "extract_multi", "userReply": "oi", "fields": []}
    r = await client.post("/extract-multi", json=body, headers=HEADERS)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_extract_payment_nf_confirmation_returns_json_string(client):
    async def fake_to_thread(_func, *_a, **_kw):
        return {"message": {"content": '{"supplier_name": "Padaria LTDA", "payment_freeform": "copiar: fin@bikeanjo.org"}'}}

    with patch.object(extract_module.asyncio, "to_thread", side_effect=fake_to_thread), patch(
        "app.api.extract.log_sync_llm_job", new_callable=AsyncMock
    ):
        r = await client.post(
            "/extract",
            json={
                "task": "extract",
                "step": "payment_nf_confirmation",
                "question": "Current_nf JSON: {}",
                "userReply": "o emissor é Padaria LTDA copiar: fin@bikeanjo.org",
            },
            headers=HEADERS,
        )
    assert r.status_code == 200
    data = r.json()
    assert data["extracted"] is not None
    assert "Padaria LTDA" in data["extracted"]
    assert "fin@bikeanjo.org" in data["extracted"]


@pytest.mark.asyncio
async def test_extract_unknown_step_returns_null(client):
    with patch("app.api.extract.log_sync_llm_job", new_callable=AsyncMock):
        r = await client.post(
            "/extract",
            json={
                "task": "extract",
                "step": "step_inexistente_xyz",
                "question": "?",
                "userReply": "oi",
            },
            headers=HEADERS,
        )
    assert r.status_code == 200
    assert r.json()["extracted"] is None


@pytest.mark.asyncio
async def test_extract_multi_accepts_payment_context_and_extra_keys(client):
    async def fake_to_thread(_func, *_a, **_kw):
        return {"message": {"content": '{"supplier_name": "Novo Emissor SA"}'}}

    with patch.object(extract_module.asyncio, "to_thread", side_effect=fake_to_thread), patch(
        "app.api.extract.log_sync_llm_job", new_callable=AsyncMock
    ):
        r = await client.post(
            "/extract-multi",
            json={
                "task": "extract_multi",
                "userReply": "corrigindo o emissor para Novo Emissor SA",
                "fields": [
                    {"id": "supplier_name", "label": "Nome do emissor na NF", "example": "ACME"},
                ],
                "context": {
                    "step": "payment_nf_confirmation",
                    "current_nf": {"supplier_name": "Errado LTDA", "amount": 10},
                    "instruction": "fill corrections",
                },
            },
            headers=HEADERS,
        )
    assert r.status_code == 200
    data = r.json()
    assert data["extracted"].get("supplier_name") == "Novo Emissor SA"


@pytest.mark.asyncio
async def test_router_injects_rich_context_into_llm_prompt(client):
    """§1.1: city/journey/next_event reach the user prompt; clearance stays out of it."""
    raw = (
        '{"action": "escalate", "suggested_route": "ask", "escalate_to": "smart", '
        '"confidence": 0.7}'
    )
    with patch("app.api.message_router.get_project", new_callable=AsyncMock) as mock_project, \
         patch("app.api.message_router.retrieve", new_callable=AsyncMock) as mock_retrieve, \
         patch("app.api.message_router.log_sync_llm_job", new_callable=AsyncMock), \
         patch("ollama.chat", return_value={"message": {"content": raw}}) as mock_ollama:
        mock_project.return_value = {"project_id": "bikeanjoall_2026", "config_json": {}}
        mock_retrieve.return_value = []

        r = await client.post(
            "/router",
            json={
                "message": "quero ir no evento",
                "project_id": "bikeanjoall_2026",
                "city": "São Paulo",
                "state": "SP",
                "clearance": "O",
                "intended_clearance": "I",
                "interesse": "aprender_a_pedalar",
                "journey_kind": "event_signup",
                "journey_destination": "/eixo/event-abc",
                "next_event_name": "EBA Centro",
                "next_event_at": "2026-08-01T14:00:00-03:00",
                "unknown_future_field": "ignored",
            },
            headers=HEADERS,
        )
        assert r.status_code == 200
        mock_ollama.assert_called_once()
        messages = mock_ollama.call_args.kwargs["messages"]
        user_content = next(m["content"] for m in messages if m["role"] == "user")
        assert "Cidade: São Paulo" in user_content
        assert "Estado: SP" in user_content
        # Authorization tier (NOIA) is accepted on the wire but never shown to the model.
        assert "Clearance" not in user_content
        assert "Interesse: aprender_a_pedalar" in user_content
        assert "Jornada: event_signup" in user_content
        # Internal reference, not a link: the model never sees it.
        assert "/eixo/event-abc" not in user_content
        assert "Próximo evento: EBA Centro" in user_content
        assert "Data do próximo evento: 2026-08-01T14:00:00-03:00" in user_content
        assert "ignored" not in user_content


@pytest.mark.asyncio
async def test_ask_stores_rich_user_context_fields(client):
    """§1.1: clearance/journey/next_event/current_time survive AskRequest → job payload."""
    with patch("app.api.ask.get_project", new_callable=AsyncMock) as mock_project, \
         patch("app.api.ask.db_module.job_find_recent_duplicate", new_callable=AsyncMock, return_value=None), \
         patch("app.api.ask.db_module.job_create", new_callable=AsyncMock) as mock_create:
        mock_project.return_value = {"project_id": "bikeanjoall_2026", "config_json": {}}
        mock_create.return_value = "job-rich-ctx"
        r = await client.post(
            "/ask",
            json={
                "project_id": "bikeanjoall_2026",
                "question": "onde fica o EBA?",
                "user_context": {
                    "name": "Ana",
                    "city": "Campinas",
                    "clearance": "N",
                    "intended_clearance": "O",
                    "journey_kind": "onboarding",
                    "journey_destination": "/eixo/cadastro",
                    "next_event_name": "Pedal Noturno",
                    "next_event_at": "2026-09-10T19:00:00-03:00",
                    "current_time": "2026-07-29T23:00:00-03:00",
                    "interesse": "passeio",
                    "future_ignored": "x",
                },
            },
            headers=HEADERS,
        )
    assert r.status_code == 202
    mock_create.assert_called_once()
    _args, kwargs = mock_create.call_args
    ctx = kwargs.get("user_context") or {}
    assert ctx.get("clearance") == "N"
    assert ctx.get("intended_clearance") == "O"
    assert ctx.get("journey_kind") == "onboarding"
    assert ctx.get("journey_destination") == "/eixo/cadastro"
    assert ctx.get("next_event_name") == "Pedal Noturno"
    assert ctx.get("next_event_at") == "2026-09-10T19:00:00-03:00"
    assert ctx.get("current_time") == "2026-07-29T23:00:00-03:00"
    assert ctx.get("interesse") == "passeio"
    assert "future_ignored" not in ctx
