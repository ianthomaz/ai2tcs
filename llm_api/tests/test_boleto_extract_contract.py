"""Contract tests for boleto extraction heuristics and endpoint shape."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.boletoextract.parser import (
    BIKE_ANJO_CNPJ,
    apply_guia_roles,
    extract_from_text_heuristics,
    is_guia_arrecadacao,
    validate_digitable_line,
)


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


def test_validate_arrecadacao_line_starts_with_8() -> None:
    # 48 digits starting with 8 (federal collection) — accepted by length/prefix rule
    line = "858800000300620403852628680716262513980235235038"
    assert len(line) == 48
    assert validate_digitable_line(line) is True


def test_cofins_darf_guia_roles() -> None:
    text = """
Documento de Arrecadação de Receitas Federais
19.515.100/0001-89 ASSOCIACAO BIKE ANJO
Valor Total do Documento
3.062,04
5856 COFINS NAO-CUMULATIVA 3.062,04
Pagar até: 25/09/2026
Número: 07.16.26251.9802352-3
85880000030 0 62040385262 8 68071626251 3 98023523503 8
"""
    assert is_guia_arrecadacao(text, "BIKE ANJO - COFINS 08.2026.pdf")
    data = extract_from_text_heuristics(text, "BIKE ANJO - COFINS 08.2026.pdf")
    assert data.get("amount") == 3062.04
    assert data.get("payer_document") == BIKE_ANJO_CNPJ
    assert data.get("beneficiary_document") != BIKE_ANJO_CNPJ
    assert data.get("beneficiary_document") is None
    assert data.get("beneficiary_name") and "Receita" in data["beneficiary_name"]
    assert data.get("digitable_line", "").startswith("8588")
    assert data.get("document_number")


def test_iss_guia_filename_and_amount() -> None:
    text = """
SAOPAULO ISS 08/2026
19.515.100/0001-89
Valor Total do Documento 2.014,50
"""
    assert is_guia_arrecadacao(text, "BIKE ANJO - ISS 08.2026.pdf")
    data = extract_from_text_heuristics(text, "BIKE ANJO - ISS 08.2026.pdf")
    assert data.get("amount") == 2014.5
    assert data.get("payer_document") == BIKE_ANJO_CNPJ
    assert "ISS" in (data.get("beneficiary_name") or "")


def test_apply_guia_roles_clears_ba_beneficiary() -> None:
    out = apply_guia_roles(
        {
            "beneficiary_name": "ASSOCIACAO BIKE ANJO",
            "beneficiary_document": BIKE_ANJO_CNPJ,
            "payer_name": None,
            "payer_document": None,
        },
        "Documento de Arrecadação COFINS",
    )
    assert out["payer_document"] == BIKE_ANJO_CNPJ
    assert out["beneficiary_document"] is None
    assert "Receita" in (out["beneficiary_name"] or "")


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
