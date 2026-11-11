"""Backup reader for NF / boleto when the local LLM is down; refused audio of unknown format."""
from unittest.mock import AsyncMock, patch

import pytest

from app.llm import doc_fallback as fb
from app.stt.audio_validate import sniff_format


def test_llm_reading_says_who_read():
    assert fb.llm_reading([]) == "local"
    assert fb.llm_reading(["LLM unavailable: timeout"]) == "unavailable"
    assert fb.llm_reading(["LLM unavailable: timeout", f"{fb.FALLBACK_OK_PREFIX} (anthropic)."]) == "fallback"


@pytest.mark.asyncio
async def test_without_a_backup_nothing_is_called():
    with patch("app.config.settings.doc_extract_fallback_provider", ""):
        out, w = await fb.read_with_fallback("nf_extract", [], {}, lambda t: {"x": 1}, ["LLM unavailable: x"])
    assert out == {} and w == ["LLM unavailable: x"]


@pytest.mark.asyncio
async def test_backup_reads_when_configured_and_says_so():
    provider = AsyncMock()
    provider.chat_with_metrics.return_value = ('{"amount": 10}', {"prompt_tokens": 5})
    with patch("app.config.settings.doc_extract_fallback_provider", "anthropic"), patch(
        "app.llm.factory.provider_by_name", return_value=provider
    ), patch("app.llm.doc_fallback.llm_metrics.record") as rec:
        out, w = await fb.read_with_fallback(
            "nf_extract", [{"role": "user", "content": "x"}], {"temperature": 0.1}, lambda t: {"amount": 10}, ["LLM unavailable: x"]
        )
    assert out == {"amount": 10}
    assert fb.llm_reading(w) == "fallback"
    assert rec.call_args.args[0] == "nf_extract_fallback"


@pytest.mark.asyncio
async def test_backup_failure_keeps_unavailable():
    provider = AsyncMock()
    provider.chat_with_metrics.side_effect = RuntimeError("quota")
    with patch("app.config.settings.doc_extract_fallback_provider", "openai"), patch(
        "app.llm.factory.provider_by_name", return_value=provider
    ):
        out, w = await fb.read_with_fallback("boleto_extract", [], {}, lambda t: {}, ["LLM unavailable: x"])
    assert out == {} and fb.llm_reading(w) == "unavailable"
    assert any("também falhou" in x for x in w)


def test_audio_signatures():
    pad = b"\x00" * 8
    assert sniff_format(b"\xff\xe3" + b"\x00" * 10) == "mp3"
    assert sniff_format(b"OggS" + pad) == "ogg"
    assert sniff_format(b"hello world!") is None
