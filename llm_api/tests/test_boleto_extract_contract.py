"""Contract tests for boleto extraction heuristics and endpoint shape."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.boletoextract.parser import extract_from_text_heuristics, validate_digitable_line


def test_extract_boleto_labels_beneficiary_vs_payer() -> None:
    text = """
Beneficiário: EMPRESA COBRADORA LTDA
CPF/CNPJ: 00.000.000/0001-91

Sacado: CLIENTE PAGADOR SA
CPF/CNPJ: 60.746.948/0001-12

Vencimento: 15/07/2026
Valor do Documento: R$ 150,00
"""
    data = extract_from_text_heuristics(text)
    assert data.get("beneficiary_document") == "00000000000191"
    assert data.get("payer_document") == "60746948000112"
    assert data.get("beneficiary_document") != data.get("payer_document")
    assert data.get("due_date") == "15/07/2026"
    assert data.get("amount") == 150.0


def test_validate_digitable_line_rejects_short() -> None:
    assert validate_digitable_line("12345") is False


@pytest.mark.asyncio
async def test_boleto_extract_endpoint_shape(client) -> None:
    fake = {
        "status": "ok",
        "source_type": "upload",
        "document_type": "pdf",
        "file_name": "b.pdf",
        "beneficiary_name": "Co",
        "beneficiary_document": "00000000000191",
        "payer_name": "Cliente",
        "payer_document": "60746948000112",
        "digitable_line": None,
        "barcode": None,
        "due_date": "15/07/2026",
        "amount": 150.0,
        "bank_code": "341",
        "document_number": None,
        "confidence": 0.7,
        "confidence_by_field": {},
        "warnings": [],
        "errors": [],
        "raw_text_excerpt": None,
    }
    with patch("app.config.settings.llm_api_token", "test-token"), patch(
        "app.api.boleto_extract.run_boleto_extraction_pipeline",
        new_callable=AsyncMock,
        return_value=fake,
    ), patch("app.api.boleto_extract.log_sync_llm_job", new_callable=AsyncMock):
        files = {"file": ("b.pdf", b"%PDF-1.4", "application/pdf")}
        r = await client.post("/boletoExtract", files=files, headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200
    data = r.json()
    assert data["beneficiary_document"] == "00000000000191"
    assert data["payer_document"] == "60746948000112"
