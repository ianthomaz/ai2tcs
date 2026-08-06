"""provider.chat() had no timeout at all, and an empty answer was reported as
status="done" as long as chunks existed. Both are pure-logic pieces of run_rag_job,
tested in isolation rather than through the full pipeline.
"""
import asyncio
from unittest.mock import patch

import pytest

from app.jobs.worker import _chat_or_timeout, _final_job_status


class _SlowProvider:
    async def chat(self, *, model, messages, options):
        await asyncio.sleep(10)
        return "too late"


class _FastProvider:
    async def chat(self, *, model, messages, options):
        return "resposta"


class _FailingProvider:
    async def chat(self, *, model, messages, options):
        raise ConnectionError("network down")


@pytest.mark.asyncio
async def test_chat_or_timeout_bounds_a_hung_provider():
    with patch("app.jobs.worker.settings.llm_chat_timeout_s", 0.05):
        with pytest.raises(RuntimeError, match="timed out"):
            await _chat_or_timeout(_SlowProvider(), model="m", messages=[], options={})


@pytest.mark.asyncio
async def test_chat_or_timeout_returns_the_answer_on_success():
    answer = await _chat_or_timeout(_FastProvider(), model="m", messages=[], options={})
    assert answer == "resposta"


@pytest.mark.asyncio
async def test_chat_or_timeout_lets_other_errors_through_unwrapped():
    """Only a timeout gets converted; a real provider error keeps its own message."""
    with pytest.raises(ConnectionError, match="network down"):
        await _chat_or_timeout(_FailingProvider(), model="m", messages=[], options={})


def test_empty_answer_never_reports_done():
    for blank in ("", "   ", None):
        status = _final_job_status(blank, chunks=[{"id": "c1"}], rag_mode="optional", policies={})
        assert status == "no_answer"


def test_empty_answer_respects_project_when_no_answer_override():
    status = _final_job_status("", chunks=[{"id": "c1"}], rag_mode="optional", policies={"when_no_answer": "need_more_info"})
    assert status == "need_more_info"


def test_real_answer_with_chunks_is_done():
    status = _final_job_status("resposta real", chunks=[{"id": "c1"}], rag_mode="required", policies={})
    assert status == "done"


def test_real_answer_without_chunks_in_required_mode_is_no_answer():
    """Unchanged behaviour: required mode with zero chunks was already no_answer."""
    status = _final_job_status("resposta real", chunks=[], rag_mode="required", policies={})
    assert status == "no_answer"


def test_real_answer_without_chunks_in_optional_mode_is_still_done():
    status = _final_job_status("resposta real", chunks=[], rag_mode="optional", policies={})
    assert status == "done"
