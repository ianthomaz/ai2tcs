"""LLM call metrics: counts from Ollama, heavy / near-limit flags, stored next to the job."""
from __future__ import annotations

import asyncio
import logging
import re
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


@pytest.mark.asyncio
async def test_direct_ollama_door_records_and_bounds(caplog):
    from app.llm import direct

    with patch("ollama.chat", return_value=_OLLAMA), caplog.at_level(logging.INFO, logger="app.llm.metrics"):
        response = await direct.ollama_chat("edu_chat", None, model="m", messages=[])
    assert response is _OLLAMA
    assert any("kind=edu_chat" in r.getMessage() for r in caplog.records)

    async def slow(*_a, **_kw):
        await asyncio.sleep(1)

    with patch("app.llm.direct.asyncio.to_thread", side_effect=slow), pytest.raises(asyncio.TimeoutError):
        await direct.ollama_chat("edu_chat", None, timeout_s=0.01, model="m", messages=[])


def test_no_route_calls_ollama_chat_outside_the_doors():
    """Every model call is recorded: ollama.chat lives only in the provider and in app/llm/direct.py."""
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[1] / "app"
    allowed = {app_dir / "llm" / "direct.py", app_dir / "llm" / "ollama_provider.py"}
    call = re.compile(r"\bollama\.chat\s*[,(]")
    offenders = [
        f"{p.relative_to(app_dir)}:{n}"
        for p in app_dir.rglob("*.py")
        if p not in allowed
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if call.search(line) and not line.lstrip().startswith("#")
    ]
    assert offenders == []


# ---------------------------------------------------------------- L2: num_ctx per project


def test_num_ctx_comes_from_the_project_then_the_global_default():
    from app.registry import get_llm_config, get_num_ctx

    with_ctx = {"config_json": {"llm_options": {"num_ctx": 8192}}}
    without = {"config_json": {}}
    assert get_num_ctx(with_ctx) == 8192 and get_llm_config(with_ctx)["num_ctx"] == 8192
    assert get_num_ctx(without) is None and "num_ctx" not in get_llm_config(without)
    with patch("app.config.settings.ollama_num_ctx", 6144):
        assert get_num_ctx(without) == 6144
        assert get_num_ctx(with_ctx) == 8192


def test_near_limit_is_measured_against_the_window_actually_sent():
    assert metrics.flags({"prompt_tokens": 3900})["near_ctx_limit"] is True
    assert metrics.flags({"prompt_tokens": 3900}, ctx_tokens=8192)["near_ctx_limit"] is False
    assert metrics.record("ask", "p", "m", {"prompt_tokens": 3900}, 8192)["ctx_tokens"] == 8192


# ---------------------------------------------------------------- L1: answer signals


def test_signals_describe_the_pipeline_not_the_model():
    from app.llm import signals

    out = signals.build(
        chunks=[{"distance": 0.62}, {"distance": 0.41}, {"distance": None}],
        answer=" Oi! ",
        guard_hit=True,
        metrics={"prompt_tokens": 2100, "near_ctx_limit": False},
    )
    assert out == {
        "best_distance": 0.41,
        "chunks_kept": 3,
        "sanitize_hit": False,
        "guard_hit": True,
        "answer_chars": 3,
        "prompt_tokens": 2100,
        "near_ctx_limit": False,
    }
    assert signals.build(chunks=[], answer=None)["best_distance"] is None


@pytest.mark.asyncio
async def test_ask_job_stores_signals_and_result_returns_them(client):
    project = {
        "project_id": "p1",
        "name": "P1",
        "sources": [],
        "config_json": {"rag_mode": "disabled", "llm_options": {"num_ctx": 8192}},
    }
    sent: dict = {}

    class _P(LLMProvider):
        async def chat(self, model, messages, options):
            return "texto"

        async def chat_with_metrics(self, model, messages, options):
            sent.update(options)
            return "texto", {"prompt_tokens": 120}

    with patch("app.jobs.worker.get_project", new_callable=AsyncMock, return_value=project), patch(
        "app.jobs.worker.get_rag_mode", return_value="disabled"
    ), patch("app.jobs.worker.get_provider", return_value=_P()), patch(
        "app.jobs.worker.db_module.job_update_status", new_callable=AsyncMock
    ), patch(
        "app.jobs.worker.db_module.job_merge_user_context", new_callable=AsyncMock
    ) as merge:
        await worker.run_rag_job("job-1", "p1", "oi?")
    assert sent["num_ctx"] == 8192
    stored = merge.await_args.args[1]
    assert stored["__signals"]["chunks_kept"] == 0 and stored["__signals"]["answer_chars"] == 5
    assert stored["__metrics"]["ctx_tokens"] == 8192

    job = {"id": "job-1", "status": "done", "answer": "texto", "sources": [], "signals": stored["__signals"]}
    with patch("app.config.settings.llm_api_token", "test-token"), patch(
        "app.api.ask.db_module.job_get", new_callable=AsyncMock, return_value=job
    ):
        r = await client.get("/result/job-1", headers={"Authorization": "Bearer test-token"})
    assert r.json()["signals"]["answer_chars"] == 5


@pytest.mark.asyncio
async def test_router_returns_signals_and_sends_the_project_window(client):
    sent: dict = {}

    class _P(LLMProvider):
        async def chat(self, model, messages, options):
            return ""

        async def chat_with_metrics(self, model, messages, options):
            sent.update(options)
            return '{"action":"answer_now","suggested_route":"ask","answer":"Oi.","confidence":0.9}', {
                "prompt_tokens": 900
            }

    project = {"project_id": "p1", "name": "P1", "sources": [], "config_json": {"llm_options": {"num_ctx": 8192}}}
    chunks = [{"path": "a.md", "snippet": "x", "distance": 0.3}]
    with patch("app.config.settings.llm_api_token", "test-token"), patch(
        "app.api.message_router.get_project", new_callable=AsyncMock, return_value=project
    ), patch("app.api.message_router.retrieve", new_callable=AsyncMock, return_value=chunks), patch(
        "app.api.message_router.get_provider", return_value=_P()
    ), patch("app.api.message_router.log_sync_llm_job", new_callable=AsyncMock):
        r = await client.post(
            "/router", json={"message": "oi?", "project_id": "p1"}, headers={"Authorization": "Bearer test-token"}
        )
    body = r.json()
    assert sent["num_ctx"] == 8192
    assert body["signals"]["best_distance"] == 0.3 and body["signals"]["chunks_kept"] == 1
    assert body["signals"]["prompt_tokens"] == 900 and body["confidence"] == 0.9
