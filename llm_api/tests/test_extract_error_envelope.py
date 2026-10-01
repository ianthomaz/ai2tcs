"""HTTP error envelope for /nfExtract and /boletoExtract (errors[] + error.message)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.extract_envelope import classify_extract_error_code, extract_error_dict
from app.models import BoletoExtractResponse, DocumentExtractError, NFExtractResponse


def test_classify_timeout_and_model_errors():
    assert classify_extract_error_code("LLM unavailable: ReadTimeout") == "timeout"
    assert classify_extract_error_code("O modelo não respondeu a tempo") == "timeout"
    assert classify_extract_error_code("ollama connection refused") == "model_error"
    assert classify_extract_error_code("Send exactly one source") == "invalid_request"


def test_nf_model_fills_error_from_errors_list():
    r = NFExtractResponse(status="error", errors=["Send exactly one source: file OR url."])
    assert r.error is not None
    assert r.error.code == "invalid_request"
    assert r.error.message.startswith("Send exactly one source")


def test_boleto_model_keeps_explicit_error_code():
    r = BoletoExtractResponse(
        status="error",
        errors=["LLM unavailable: ReadTimeout"],
        error=DocumentExtractError(code="timeout", message="O modelo não respondeu a tempo."),
    )
    assert r.error is not None
    assert r.error.code == "timeout"
    assert r.errors[0].startswith("LLM unavailable")


def test_extract_error_dict_empty():
    assert extract_error_dict([]) is None


@pytest.mark.asyncio
async def test_nf_extract_http_returns_error_envelope(client) -> None:
    with patch("app.config.settings.llm_api_token", "test-token"), patch(
        "app.api.nf_extract.log_sync_llm_job", new_callable=AsyncMock
    ):
        r = await client.post("/nfExtract", headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "error"
    assert data["errors"]
    assert data["error"]["message"] == data["errors"][0]
    assert data["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_boleto_extract_http_returns_error_envelope(client) -> None:
    with patch("app.config.settings.llm_api_token", "test-token"), patch(
        "app.api.boleto_extract.log_sync_llm_job", new_callable=AsyncMock
    ):
        r = await client.post("/boletoExtract", headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "error"
    assert data["errors"]
    assert data["error"]["message"] == data["errors"][0]
    assert data["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_nf_pipeline_error_survives_response_model(client) -> None:
    fake = {
        "status": "error",
        "source_type": "upload",
        "document_type": "pdf",
        "file_name": "x.pdf",
        "errors": ["LLM unavailable: ReadTimeout"],
        "error": {"code": "timeout", "message": "O modelo não respondeu a tempo."},
        "warnings": [],
        "confidence": 0.0,
        "confidence_by_field": {},
    }
    with patch("app.config.settings.llm_api_token", "test-token"), patch(
        "app.api.nf_extract.run_extraction_pipeline",
        new_callable=AsyncMock,
        return_value=fake,
    ), patch("app.api.nf_extract.log_sync_llm_job", new_callable=AsyncMock):
        files = {"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}
        r = await client.post("/nfExtract", files=files, headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200
    data = r.json()
    assert data["error"]["code"] == "timeout"
    assert data["error"]["message"]
    assert data["errors"][0].startswith("LLM unavailable")
