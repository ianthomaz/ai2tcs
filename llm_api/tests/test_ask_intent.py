"""Tests for /ask semantic intent cut (2nd router)."""
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.rag.ask_intent import action_codes, build_classify_system, normalize_intent
from app.registry import get_ask_intent_config

HEADERS = {"Authorization": "Bearer test-token"}

BA_ACTIONS = {
    "enabled": True,
    "actions": [
        {
            "code": "event_interest_lookup",
            "meaning": "Pergunta se já tem inscrição/interesse ou se o canal 'consegue ver' o status.",
        },
        {"code": "registration_completeness_lookup", "meaning": "Reservado."},
        {"code": "city_event_lookup", "meaning": "Reservado."},
    ],
}

CASES_PATH = Path(__file__).parent / "eval" / "ask_intent_cases.json"


@pytest.fixture(autouse=True)
def mock_token():
    with patch("app.config.settings.llm_api_token", "test-token"):
        yield


def test_get_ask_intent_config_disabled_or_empty():
    assert get_ask_intent_config({"config_json": {}}) is None
    assert get_ask_intent_config({"config_json": {"ask_intent": {"enabled": False, "actions": []}}}) is None
    assert get_ask_intent_config({"config_json": {"ask_intent": {"enabled": True, "actions": []}}}) is None


def test_get_ask_intent_config_accepts_code_meaning():
    cfg = get_ask_intent_config({"config_json": {"ask_intent": BA_ACTIONS}})
    assert cfg is not None
    assert cfg["enabled"] is True
    assert "event_interest_lookup" in action_codes(cfg)
    assert "Closed action list" in build_classify_system(cfg)


def test_normalize_intent_closed_list():
    cfg = BA_ACTIONS
    assert normalize_intent(
        {"knowledge_kind": "user_system", "action": "event_interest_lookup"}, cfg
    ) == {
        "knowledge_kind": "user_system",
        "action": "event_interest_lookup",
        "action_payload": None,
    }
    # Invented action → unknown
    assert normalize_intent(
        {"knowledge_kind": "user_system", "action": "invented_lookup"}, cfg
    )["knowledge_kind"] == "unknown"
    # org_general forces action null
    assert normalize_intent(
        {"knowledge_kind": "org_general", "action": "event_interest_lookup"}, cfg
    ) == {"knowledge_kind": "org_general", "action": None, "action_payload": None}


def test_eval_cases_file_has_six():
    import json

    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    assert len(data["cases"]) == 6
    ids = {c["id"] for c in data["cases"]}
    assert ids == {1, 2, 3, 4, 5, 6}


@pytest.mark.asyncio
async def test_worker_user_system_skips_rag():
    from app.jobs.worker import run_rag_job

    project = {
        "project_id": "bikeanjoall_2026",
        "config_json": {
            "ask_intent": BA_ACTIONS,
            "policies": {"when_no_answer": "no_answer"},
        },
    }
    classified = {
        "knowledge_kind": "user_system",
        "action": "event_interest_lookup",
        "action_payload": {"event_name": "EBA Centro"},
    }
    with patch("app.jobs.worker.get_project", new_callable=AsyncMock, return_value=project), \
         patch("app.jobs.worker.classify_ask_intent", new_callable=AsyncMock, return_value=classified), \
         patch("app.jobs.worker.retrieve", new_callable=AsyncMock) as mock_retrieve, \
         patch("app.jobs.worker.db_module.job_update_status", new_callable=AsyncMock) as mock_status, \
         patch("app.jobs.worker.db_module.job_merge_user_context", new_callable=AsyncMock) as mock_merge, \
         patch("app.jobs.worker.db_module.conversation_append", new_callable=AsyncMock), \
         patch("app.jobs.worker.db_module.conversation_get_recent", new_callable=AsyncMock, return_value=[]):
        await run_rag_job("job-1", "bikeanjoall_2026", "já me inscrevi?")

    mock_retrieve.assert_not_called()
    mock_merge.assert_awaited()
    merge_extra = mock_merge.await_args.args[1]
    assert merge_extra["__intent"]["action"] == "event_interest_lookup"
    final = [c for c in mock_status.await_args_list if c.kwargs.get("progress") == "complete" or (len(c.args) > 1 and c.args[1] == "done")]
    # Last status update should be done with empty answer
    last = mock_status.await_args_list[-1]
    assert last.args[1] == "done"
    assert last.kwargs.get("answer") is None


@pytest.mark.asyncio
async def test_worker_unknown_is_no_answer():
    from app.jobs.worker import run_rag_job

    project = {
        "project_id": "bikeanjoall_2026",
        "config_json": {
            "ask_intent": BA_ACTIONS,
            "policies": {"when_no_answer": "no_answer"},
        },
    }
    classified = {"knowledge_kind": "unknown", "action": None, "action_payload": None}
    with patch("app.jobs.worker.get_project", new_callable=AsyncMock, return_value=project), \
         patch("app.jobs.worker.classify_ask_intent", new_callable=AsyncMock, return_value=classified), \
         patch("app.jobs.worker.retrieve", new_callable=AsyncMock) as mock_retrieve, \
         patch("app.jobs.worker.db_module.job_update_status", new_callable=AsyncMock) as mock_status, \
         patch("app.jobs.worker.db_module.job_merge_user_context", new_callable=AsyncMock), \
         patch("app.jobs.worker.db_module.conversation_append", new_callable=AsyncMock), \
         patch("app.jobs.worker.db_module.conversation_get_recent", new_callable=AsyncMock, return_value=[]):
        await run_rag_job("job-2", "bikeanjoall_2026", "obrigado")

    mock_retrieve.assert_not_called()
    last = mock_status.await_args_list[-1]
    assert last.args[1] == "no_answer"


@pytest.mark.asyncio
async def test_worker_org_general_continues_rag_and_stores_intent():
    from app.jobs.worker import run_rag_job

    project = {
        "project_id": "bikeanjoall_2026",
        "name": "BA",
        "config_json": {
            "ask_intent": BA_ACTIONS,
            "policies": {"when_no_answer": "no_answer", "max_chunks_to_retrieve": 3},
            "system_instruction": "Responda curto.",
        },
    }
    classified = {"knowledge_kind": "org_general", "action": None, "action_payload": None}
    fake_provider = AsyncMock()
    fake_provider.chat_with_metrics = AsyncMock(return_value=("A Bike Anjo é uma rede de voluntários.", {}))

    with patch("app.jobs.worker.get_project", new_callable=AsyncMock, return_value=project), \
         patch("app.jobs.worker.classify_ask_intent", new_callable=AsyncMock, return_value=classified), \
         patch("app.jobs.worker.retrieve", new_callable=AsyncMock, return_value=[
             {"id": "c1", "path": "a.md", "snippet": "Bike Anjo é voluntariado.", "distance": 0.2, "url": None}
         ]), \
         patch("app.jobs.worker.get_provider", return_value=fake_provider), \
         patch("app.jobs.worker.db_module.job_update_status", new_callable=AsyncMock), \
         patch("app.jobs.worker.db_module.job_merge_user_context", new_callable=AsyncMock) as mock_merge, \
         patch("app.jobs.worker.db_module.conversation_append", new_callable=AsyncMock), \
         patch("app.jobs.worker.db_module.conversation_get_recent", new_callable=AsyncMock, return_value=[]), \
         patch("app.jobs.worker.db_module.user_profile_get", new_callable=AsyncMock, return_value=None), \
         patch("app.jobs.worker.db_module.summary_get_recent", new_callable=AsyncMock, return_value=[]):
        await run_rag_job("job-3", "bikeanjoall_2026", "o que é a Bike Anjo?")

    merge_extra = mock_merge.await_args.args[1]
    assert merge_extra["__intent"]["knowledge_kind"] == "org_general"
    assert merge_extra["__intent"]["action"] is None
    fake_provider.chat_with_metrics.assert_awaited()


@pytest.mark.asyncio
async def test_result_exposes_intent(client):
    with patch("app.api.ask.db_module.job_get", new_callable=AsyncMock) as m:
        m.return_value = {
            "id": "job-intent",
            "status": "done",
            "answer": None,
            "sources": [],
            "confidence": "high",
            "created_at": datetime(2026, 10, 30, 12, 0, 0),
            "transcript": None,
            "stt_metadata": None,
            "signals": None,
            "intent": {
                "knowledge_kind": "user_system",
                "action": "event_interest_lookup",
                "action_payload": {"event_name": "EBA"},
            },
        }
        with patch("app.api.ask.ensure_job_visible", side_effect=lambda _req, job: job):
            r = await client.get("/result/job-intent", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["intent"]["knowledge_kind"] == "user_system"
    assert data["intent"]["action"] == "event_interest_lookup"
    assert data["intent"]["action_payload"]["event_name"] == "EBA"


def test_eval_case_expectations_match_normalize_rules():
    """Static pass/fail for the 6 contract cases against normalize_intent (no LLM)."""
    import json

    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    # Simulated model outputs aligned with expected labels (offline gate).
    simulated = {
        1: {"knowledge_kind": "user_system", "action": "event_interest_lookup"},
        2: {"knowledge_kind": "user_system", "action": "event_interest_lookup"},
        3: {"knowledge_kind": "org_general", "action": None},
        4: {"knowledge_kind": "org_general", "action": None},
        5: {"knowledge_kind": "unknown", "action": None},
        6: {"knowledge_kind": "org_general", "action": None},
    }
    for case in data["cases"]:
        out = normalize_intent(simulated[case["id"]], BA_ACTIONS)
        exp = case["expected"]
        assert out["knowledge_kind"] == exp["knowledge_kind"], case["name"]
        if "action" in exp:
            assert out["action"] == exp["action"], case["name"]
        if exp.get("forbid_action"):
            assert out["action"] != exp["forbid_action"], case["name"]
