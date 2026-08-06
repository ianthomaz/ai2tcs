"""amount / amount_tax / amount_deposit are float | None on NFExtractResponse and
BoletoExtractResponse. The LLM merge step passed a string straight through when it
wasn't a recognized placeholder — a BR-formatted amount ("1.234,56") or a currency-
prefixed one ("R$ 10,00") from the LLM reached Response(**result) unconverted and
pydantic raised ValidationError with nothing catching it: a 500 instead of a usable
response, on a pipeline whose whole job is turning a document into structured data.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.boletoextract.parser import run_boleto_extraction_pipeline
from app.models import BoletoExtractResponse, NFExtractResponse
from app.nfextract.parser import _to_float, run_extraction_pipeline


def test_to_float_strips_currency_prefix():
    assert _to_float("R$ 10,00") == 10.0
    assert _to_float("r$1.234,56") == 1234.56


def test_to_float_still_handles_plain_br_format():
    assert _to_float("1.234,56") == 1234.56


def test_to_float_degrades_to_none_on_garbage_not_raises():
    assert _to_float("aproximadamente 123 ou 124") is None


@pytest.mark.asyncio
async def test_nf_br_formatted_llm_amount_no_longer_crashes_response_construction():
    with patch("app.nfextract.parser.enrich_with_local_llm", new_callable=AsyncMock) as m:
        m.return_value = ({"amount": "1.234,56", "amount_tax": "R$ 10,00"}, [])
        result = await run_extraction_pipeline(
            source_type="upload", file_name="x.xml", raw_bytes=b"<nfe></nfe>",
            ollama_host="http://x", ollama_model="m",
        )

    assert result["amount"] == 1234.56
    assert result["amount_tax"] == 10.0
    response = NFExtractResponse(**result)  # must not raise ValidationError
    assert response.status == "ok"


@pytest.mark.asyncio
async def test_nf_unparseable_llm_amount_degrades_to_none_not_a_crash():
    with patch("app.nfextract.parser.enrich_with_local_llm", new_callable=AsyncMock) as m:
        m.return_value = ({"amount": "aproximadamente 123 ou 124"}, [])
        result = await run_extraction_pipeline(
            source_type="upload", file_name="x.xml", raw_bytes=b"<nfe></nfe>",
            ollama_host="http://x", ollama_model="m",
        )

    assert result["amount"] is None
    NFExtractResponse(**result)  # must not raise


@pytest.mark.asyncio
async def test_nf_numeric_llm_amount_still_accepted():
    """The LLM can also answer with a real number (not a string) — must pass through."""
    with patch("app.nfextract.parser.enrich_with_local_llm", new_callable=AsyncMock) as m:
        m.return_value = ({"amount": 250.5}, [])
        result = await run_extraction_pipeline(
            source_type="upload", file_name="x.xml", raw_bytes=b"<nfe></nfe>",
            ollama_host="http://x", ollama_model="m",
        )

    assert result["amount"] == 250.5


@pytest.mark.asyncio
async def test_boleto_currency_prefixed_llm_amount_no_longer_crashes_response_construction():
    with patch("app.boletoextract.parser.extract_pdf_text_with_fallbacks", return_value=("texto do boleto", [])), \
        patch("app.boletoextract.parser.enrich_boleto_with_local_llm", new_callable=AsyncMock) as m:
        m.return_value = ({"amount": "R$ 1.234,56"}, [])
        result = await run_boleto_extraction_pipeline(
            source_type="upload", file_name="x.pdf", raw_bytes=b"%PDF-1.4",
            ollama_host="http://x", ollama_model="m",
        )

    assert result["amount"] == 1234.56
    response = BoletoExtractResponse(**result)  # must not raise ValidationError
    assert response.status == "ok"


@pytest.mark.asyncio
async def test_boleto_unparseable_llm_amount_degrades_to_none_not_a_crash():
    with patch("app.boletoextract.parser.extract_pdf_text_with_fallbacks", return_value=("texto do boleto", [])), \
        patch("app.boletoextract.parser.enrich_boleto_with_local_llm", new_callable=AsyncMock) as m:
        m.return_value = ({"amount": "valor não localizado com clareza"}, [])
        result = await run_boleto_extraction_pipeline(
            source_type="upload", file_name="x.pdf", raw_bytes=b"%PDF-1.4",
            ollama_host="http://x", ollama_model="m",
        )

    assert result["amount"] is None
    BoletoExtractResponse(**result)  # must not raise
