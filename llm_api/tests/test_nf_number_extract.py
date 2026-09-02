"""Regression: NFS-e série must not be returned as nf_number."""
from app.nfextract.parser import _extract_nf_number_from_text, _sanitize_nf_number_field


def test_prefers_numero_da_nota_over_serie():
    text = "NFS-e Série: 1 Número da Nota: 00000008 Prestador RAIRA"
    assert _extract_nf_number_from_text(text) == "8"


def test_numero_nfs_e_label():
    text = "Nota Fiscal de Serviço Eletrônica Número da NFS-e 31 Série 1"
    assert _extract_nf_number_from_text(text) == "31"


def test_sanitize_replaces_serie_one():
    base = {"nf_number": "1"}
    warnings: list[str] = []
    text = "NFS-e Série 1 Número da Nota 8 Emitente AMAZONAS"
    _sanitize_nf_number_field(base, text, warnings)
    assert base["nf_number"] == "8"
    assert warnings


def test_keeps_real_single_digit_when_labeled():
    text = "Número da Nota: 7 Valor dos Serviços R$ 100,00"
    assert _extract_nf_number_from_text(text) == "7"


def test_sp_nfse_columnar_layout_zero_padded():
    text = """NOTA FISCAL ELETRÔNICA DE SERVIÇOS - NFS-e
Número da Nota
Data e Hora de Emissão
Código de Verificação
20260902u65998990000144
00000005
02/09/2026 12:32:38
UBMG-ABWU
PRESTADOR DE SERVIÇOS
ITCS WEBPLACE LTDA
"""
    assert _extract_nf_number_from_text(text) == "5"


def test_sanitize_prefers_heuristic_over_wrong_llm():
    text = """Número da Nota
Data e Hora de Emissão
Código de Verificação
00000005
02/09/2026
"""
    base = {"nf_number": "14"}
    warnings: list[str] = []
    _sanitize_nf_number_field(base, text, warnings)
    assert base["nf_number"] == "5"
    assert warnings
