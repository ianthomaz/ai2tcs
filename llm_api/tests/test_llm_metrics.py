"""LLM call metrics: counts from Ollama, heavy / near-limit flags, stored next to the job."""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.jobs import worker
from app.llm import metrics
from app.llm.base import LLMProvider

_OLLAMA = {
    "message": {"content": "ok"},
    "prompt_eval_count": 3900,
    "eval_count": 42,
    "total_duration": 2_500_000_000,
    "load_duration": 300_000_000,
    "prompt_eval_duration": 1_000_000_000,
    "eval_duration": 1_200_000_000,
}


def test_from_ollama_reads_counts_and_times():
    m = metrics.from_ollama(_OLLAMA)
    assert m == {
        "prompt_tokens": 3900,
        "output_tokens": 42,
        "total_ms": 2500,
        "load_ms": 300,
        "prompt_ms": 1000,
        "output_ms": 1200,
    }


def test_flags_mark_heavy_and_near_the_context_limit():
    assert metrics.flags({"prompt_tokens": 3900}) == {"heavy": True, "near_ctx_limit": True}
    assert metrics.flags({"prompt_tokens": 3600}) == {"heavy": True, "near_ctx_limit": False}
    assert metrics.flags({"prompt_tokens": 800}) == {"heavy": False, "near_ctx_limit": False}


def test_record_logs_heavy_calls_at_warning_and_never_text(caplog):
    with caplog.at_level(logging.INFO, logger="app.llm.metrics"):
        out = metrics.record("ask", "bikeanjoall_2026", "gemma3:12b", metrics.from_ollama(_OLLAMA))
    assert out["heavy"] and out["model"] == "gemma3:12b"
    heavy = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert heavy and "llm_heavy" in heavy[0].getMessage()
    assert "ok" not in heavy[0].getMessage().split("model=")[0]


def test_record_without_metrics_is_silent(caplog):
    with caplog.at_level(logging.INFO, logger="app.llm.metrics"):
        assert metrics.record("ask", "p", "m", {}) == {}
    assert not caplog.records


class _Provider(LLMProvider):
    async def chat(self, model, messages, options):
        return "texto"

    async def chat_with_metrics(self, model, messages, options):
        return "texto", {"prompt_tokens": 120, "output_tokens": 8}


class _PlainProvider:
    async def chat(self, model, messages, options):
        return "texto"


@pytest.mark.asyncio
async def test_worker_call_returns_metrics_and_tolerates_plain_providers():
    assert await worker._chat_with_metrics_or_timeout(_Provider(), model="m", messages=[], options={}) == (
        "texto",
        {"prompt_tokens": 120, "output_tokens": 8},
    )
    assert await worker._chat_with_metrics_or_timeout(_PlainProvider(), model="m", messages=[], options={}) == (
        "texto",
        {},
    )


@pytest.mark.asyncio
async def test_ask_job_stores_metrics_on_the_job():
    project = {"project_id": "p1", "name": "P1", "sources": [], "config_json": {"rag_mode": "disabled"}}
    with patch("app.jobs.worker.get_project", new_callable=AsyncMock, return_value=project), patch(
        "app.jobs.worker.get_rag_mode", return_value="disabled"
    ), patch("app.jobs.worker.get_provider", return_value=_Provider()), patch(
        "app.jobs.worker.db_module.job_update_status", new_callable=AsyncMock
    ), patch(
        "app.jobs.worker.db_module.job_merge_user_context", new_callable=AsyncMock
    ) as merge:
        await worker.run_rag_job("job-1", "p1", "oi?")
    merge.assert_awaited_once()
    job_id, extra = merge.await_args.args
    assert job_id == "job-1"
    assert extra["__metrics"]["prompt_tokens"] == 120 and extra["__metrics"]["heavy"] is False


@pytest.mark.asyncio
async def test_router_model_timeout_escalates(client):
    class _Slow(LLMProvider):
        async def chat(self, model, messages, options):
            return ""

        async def chat_with_metrics(self, model, messages, options):
            await asyncio.sleep(1)
            return "", {}

    project = {"project_id": "p1", "name": "P1", "sources": [], "config_json": {}}
    with patch("app.config.settings.llm_api_token", "test-token"), patch(
        "app.config.settings.router_timeout_s", 0.01
    ), patch("app.api.message_router.get_project", new_callable=AsyncMock, return_value=project), patch(
        "app.api.message_router.retrieve", new_callable=AsyncMock, return_value=[]
    ), patch("app.api.message_router.get_provider", return_value=_Slow()), patch(
        "app.api.message_router.log_sync_llm_job", new_callable=AsyncMock
    ) as audit:
        r = await client.post(
            "/router",
            json={"message": "oi", "project_id": "p1"},
            headers={"Authorization": "Bearer test-token"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "escalate" and "timed out" in (body["obs"] or "")
    assert audit.await_args.kwargs["status"] == "failed"
