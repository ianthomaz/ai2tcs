"""Contract-style tests for NF extract postprocess and XML prestador/tomador."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.nfextract.parser import (
    apply_nf_extract_postprocess,
    extract_from_xml,
    extract_from_text_heuristics,
    _extract_nfs_e_discriminacao_clean,
)


def test_extract_from_xml_splits_prestador_tomador() -> None:
    # Valid check-digit CNPJs; prestador vs tomador must not swap.
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <root>
      <PrestadorServico>
        <RazaoSocial>ACME Servicos Ltda</RazaoSocial>
        <CpfCnpj><Cnpj>00000000000191</Cnpj></CpfCnpj>
      </PrestadorServico>
      <TomadorServico>
        <CpfCnpj><Cnpj>60746948000112</Cnpj></CpfCnpj>
      </TomadorServico>
      <Numero>1042</Numero>
      <DataEmissao>2026-03-05</DataEmissao>
      <ValorServicos>1500,00</ValorServicos>
    </root>"""
    data, _text = extract_from_xml(xml)
    assert data["supplier_name"] == "ACME Servicos Ltda"
    assert data["supplier_code"] == "00000000000191"
    assert data["service_recipient_code"] == "60746948000112"
    assert data["nf_number"] == "1042"


def test_apply_nf_extract_postprocess_description_prefix() -> None:
    base: dict = {
        "issue_date": "2026-03-05",
        "description": "Consultoria em gestão",
        "payment_pixCode": None,
        "payment_bank": None,
        "payment_bank_agency": None,
        "payment_bank_account": None,
        "service_recipient_code": None,
        "payment_type": None,
        "amount_type": "unknown",
        "amount": 100.0,
    }
    apply_nf_extract_postprocess(base, "")
    assert base["description"].startswith("NF emitida 05/mar/2026\n")
    assert "Consultoria" in base["description"]
    assert base["amount_type"] == "total"


def test_apply_nf_extract_postprocess_payment_type_pix() -> None:
    base: dict = {
        "issue_date": None,
        "description": None,
        "payment_pixCode": "pix@example.com",
        "payment_bank": None,
        "payment_bank_agency": None,
        "payment_bank_account": None,
        "service_recipient_code": None,
        "payment_type": None,
        "amount_type": "total",
        "amount": 10.0,
    }
    apply_nf_extract_postprocess(base, "")
    assert base["payment_type"] == "pix"


def test_extract_nfs_e_discriminacao_stops_before_valor_total() -> None:
    ocr = """DISCRIMINACAO DOS SERVICOS
SERVICOS DE CONTABILIDADE PRESTADOS NO MBS DE ABRIL DE 2026.

VALOR TOTAL DO SERVICO = R$ 1.138,62
INSS (R$) OUTRAS INFORMACOES
"""
    disc = _extract_nfs_e_discriminacao_clean(ocr)
    assert disc is not None
    assert "VALOR TOTAL" not in disc
    assert "INSS" not in disc
    assert "MÊS" in disc
    assert disc.startswith("DISCRIMINAÇÃO DOS SERVIÇOS")
    assert "SERVIÇOS DE CONTABILIDADE" in disc


def test_extract_from_text_prestador_supplier_not_tomador_cnpj() -> None:
    text = """
PRESTADOR DE SERVICOS
CPF/CNPJ: §3.796.095/0001-68 Inserigéo Municipal: 7.976.604-8
Nome/Razéo Social: GBA SERVICOS ESPECIALIZADOS LTDA
Enderego: R X

TOMADOR DE SERVICOS
CPF/CNPJ: 60.746.948/0001-12
Nome/Razão Social: ASSOCIACAO BIKE ANJO

DISCRIMINACAO DOS SERVICOS
SERVICOS DE ALGO NO MBS DE 2026.

VALOR TOTAL DO SERVICO = R$ 10,00
"""
    data = extract_from_text_heuristics(text)
    assert data.get("supplier_name") == "GBA SERVICOS ESPECIALIZADOS LTDA"
    assert data.get("supplier_code") is not None
    assert data.get("supplier_code") != "60746948000112"


def test_apply_nf_extract_postprocess_payment_type_boleto_from_text() -> None:
    base: dict = {
        "issue_date": None,
        "description": None,
        "payment_pixCode": None,
        "payment_bank": None,
        "payment_bank_agency": None,
        "payment_bank_account": None,
        "service_recipient_code": None,
        "payment_type": None,
        "amount_type": "total",
        "amount": 10.0,
    }
    apply_nf_extract_postprocess(base, "Pagamento via boleto bancário")
    assert base["payment_type"] == "boleto"


@pytest.mark.asyncio
async def test_nf_extract_endpoint_accepts_new_fields(client) -> None:
    """Response model includes service_recipient_code and payment_type keys."""
    fake_pipeline = {
        "status": "ok",
        "source_type": "upload",
        "document_type": "pdf",
        "file_name": "x.pdf",
        "supplier_name": "Co",
        "supplier_code": "00000000000191",
        "nf_number": "1",
        "issue_date": "2026-01-02",
        "amount": 10.0,
        "amount_type": "total",
        "amount_deposit": None,
        "amount_tax": None,
        "description": "NF emitida 02/jan/2026\nTeste",
        "payment_pixCode": None,
        "payment_bank": None,
        "payment_bank_agency": None,
        "payment_bank_account": None,
        "payment_bank_account_type": "unknown",
        "payment_receiver_name": None,
        "payment_receiver_document": None,
        "service_recipient_code": "60746948000112",
        "payment_type": "transferencia",
        "confidence": 0.5,
        "confidence_by_field": {},
        "warnings": [],
        "errors": [],
        "raw_text_excerpt": None,
    }
    with patch("app.config.settings.llm_api_token", "test-token"), patch(
        "app.api.nf_extract.run_extraction_pipeline",
        new_callable=AsyncMock,
        return_value=fake_pipeline,
    ):
        files = {"file": ("x.pdf", b"%PDF-1.4 minimal", "application/pdf")}
        r = await client.post("/nfExtract", files=files, headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200
    data = r.json()
    assert data["service_recipient_code"] == "60746948000112"
    assert data["payment_type"] == "transferencia"
