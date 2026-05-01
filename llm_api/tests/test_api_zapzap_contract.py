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
