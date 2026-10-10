"""POST /task/{task_id}: one door for text tasks of every project."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.auth import hash_key
from app.llm.base import LLMProvider
from app.tasks import executor
from app.tasks.registry import file_task, project_task_config
from app.db import _parse_config_json

GLOBAL = {"Authorization": "Bearer test-token"}
WEB_KEY = {"Authorization": "Bearer itcs_webplacecc_x"}
BA_KEY = {"Authorization": "Bearer itcs_bikeanjoall_2026_x"}

CATEGORIES = ["parceria", "suporte", "imprensa", "outro"]
_WEB = {"project_id": "webplacecc", "config_json": {"tasks": {"text_triage": {"categories": CATEGORIES}}}}
_OFF = {"project_id": "estudosmobi", "config_json": {}}

_GOOD = {
    "urgency": "watch",
    "priority": 4,
    "category": "parceria",
    "summary": "Empresa quer patrocinar a próxima ação.",
    "needs_reply": True,
    "suggested_project": None,
    "confidence": 0.8,
}


@pytest.fixture(autouse=True)
def _env():
    async def key_project(key_hash: str):
        return {
            hash_key("itcs_webplacecc_x"): "webplacecc",
            hash_key("itcs_bikeanjoall_2026_x"): "bikeanjoall_2026",
        }.get(key_hash)

    async def project(pid: str):
        return {"webplacecc": _WEB, "estudosmobi": _OFF, "bikeanjoall_2026": {"project_id": "bikeanjoall_2026", "config_json": {}}}.get(pid)

    with patch("app.config.settings.llm_api_token", "test-token"), patch(
        "app.auth.db_module.api_key_get_project_id", side_effect=key_project
    ), patch("app.tasks.routes.get_project", side_effect=project), patch(
        "app.tasks.routes.log_sync_llm_job", new_callable=AsyncMock
    ):
        yield


def _model_says(*answers: dict):
    seen: list[dict] = []
    replies = iter(answers)

    class _P(LLMProvider):
        async def chat(self, model, messages, options):
            return ""

        async def chat_with_metrics(self, model, messages, options):
            seen.append({"messages": messages, "options": options})
            return json.dumps(next(replies), ensure_ascii=False), {"prompt_tokens": 300}

    return patch("app.tasks.engine.get_provider", return_value=_P()), seen


def test_parse_config_json_accepts_dict_or_json_string():
    """asyncpg often returns jsonb as a string; /task must still see tasks.*."""
    assert _parse_config_json({"tasks": {"text_triage": {}}}) == {"tasks": {"text_triage": {}}}
    assert _parse_config_json('{"tasks": {"text_triage": {"categories": ["a"]}}}') == {
        "tasks": {"text_triage": {"categories": ["a"]}}
    }
    assert _parse_config_json(None) is None
    assert _parse_config_json("not-json") is None


def test_project_task_config_reads_string_config_json():
    entry = {"categories": ["parceria"]}
    as_dict = {"config_json": {"tasks": {"text_triage": entry}}}
    as_str = {"config_json": json.dumps({"tasks": {"text_triage": entry}})}
    assert project_task_config(as_dict, "text_triage") == entry
    assert project_task_config(as_str, "text_triage") == entry
    assert project_task_config({"config_json": {}}, "text_triage") is None


def test_text_triage_spec_examples_validate():
    spec = file_task("text_triage")
    assert spec and spec["prompt_version"] == "text-triage-v1"
    schema = executor.output_schema_for(spec, _WEB, {"text": "oi"})
    assert schema["properties"]["category"] == {"enum": CATEGORIES}
    assert executor._errors(schema, _GOOD) == []
    assert executor._errors(schema, {**_GOOD, "category": "inventada"})


_BA_CONTRACT = Path(__file__).resolve().parents[1] / "contracts" / "bikeanjo"
_ENVELOPE = {"status", "model", "prompt_version", "warnings"}


def test_bike_anjo_text_triage_contract_matches_the_task_and_the_seed():
    """The Bike Anjo contract (copied from bikeanjo2026all) fits the generic task as is."""
    spec = file_task("text_triage")
    contract = json.loads((_BA_CONTRACT / "text-triage.schema.json").read_text(encoding="utf-8"))
    categories = contract["$defs"]["category"]["enum"]
    seed = (Path(__file__).resolve().parents[1] / "scripts" / "seed_bikeanjoall.py").read_text(encoding="utf-8")
    for c in categories:
        assert f'"{c}"' in seed, c
    project = {"project_id": "bikeanjoall_2026", "config_json": {"tasks": {"text_triage": {"categories": categories}}}}
    examples = json.loads((_BA_CONTRACT / "text-triage.examples.json").read_text(encoding="utf-8"))
    for case in examples["cases"]:
        assert executor._errors(spec["input_schema"], case["request"]) == [], case["name"]
        out = {k: v for k, v in case["response_ok"].items() if k not in _ENVELOPE}
        assert executor._errors(executor.output_schema_for(spec, project, case["request"]), out) == [], case["name"]
        assert case["response_ok"]["prompt_version"] == spec["prompt_version"]


@pytest.mark.asyncio
async def test_project_key_runs_an_enabled_file_task_with_its_vocabulary(client):
    p, seen = _model_says(_GOOD)
    with p:
        r = await client.post("/task/text_triage", json={"text": "Queremos patrocinar", "channel": "email"}, headers=WEB_KEY)
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ok"
    assert body["category"] == "parceria" and body["prompt_version"] == "text-triage-v1"
    system = seen[0]["messages"][0]["content"]
    assert "- category: parceria, suporte, imprensa, outro" in system
    assert seen[0]["options"]["format"] == "json"


@pytest.mark.asyncio
async def test_value_outside_the_project_list_is_asked_again_then_fails(client):
    p, seen = _model_says({**_GOOD, "category": "inventada"}, {**_GOOD, "category": "inventada"})
    with p:
        r = await client.post("/task/text_triage", json={"text": "oi"}, headers=WEB_KEY)
    assert r.json()["error"]["code"] == "model_error"
    assert len(seen) == 2 and "category" in seen[1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_project_that_did_not_enable_the_task_is_forbidden(client):
    r = await client.post("/task/text_triage", json={"project_id": "estudosmobi", "text": "oi"}, headers=GLOBAL)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_operator_token_needs_a_project_and_can_suggest_among_candidates(client):
    r = await client.post("/task/text_triage", json={"text": "oi"}, headers=GLOBAL)
    assert r.json()["error"]["code"] == "invalid_request"
    p, seen = _model_says({**_GOOD, "suggested_project": "bikeanjoall_2026"})
    with p:
        r = await client.post(
            "/task/text_triage",
            json={"project_id": "webplacecc", "text": "Quero aprender a pedalar", "candidate_projects": ["webplacecc", "bikeanjoall_2026"]},
            headers=GLOBAL,
        )
    assert r.json()["suggested_project"] == "bikeanjoall_2026"
    assert "- suggested_project: webplacecc, bikeanjoall_2026, null" in seen[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_invalid_input_and_unknown_task(client):
    r = await client.post("/task/text_triage", json={"text": ""}, headers=WEB_KEY)
    assert r.json()["error"]["code"] == "invalid_request"
    assert (await client.post("/task/nao_existe", json={}, headers=WEB_KEY)).status_code == 404
    assert (await client.post("/task/../etc", json={}, headers=WEB_KEY)).status_code == 404


@pytest.mark.asyncio
async def test_bike_anjo_code_task_through_the_same_door(client):
    examples = Path(__file__).resolve().parents[1] / "contracts" / "bikeanjo" / "health-normalize.examples.json"
    case = json.loads(examples.read_text(encoding="utf-8"))["cases"][0]
    model_out = {k: v for k, v in case["response_ok"].items() if k not in {"status", "model", "prompt_version", "warnings"}}
    with patch("app.bikeanjo.health_normalize.chat_json", new_callable=AsyncMock, return_value=(model_out, "m")):
        r = await client.post("/task/health_normalize", json=case["request"], headers=BA_KEY)
        other = await client.post("/task/health_normalize", json=case["request"], headers=WEB_KEY)
    assert r.json()["status"] == "ok" and r.json()["prompt_version"] == case["response_ok"]["prompt_version"]
    assert other.status_code == 403


@pytest.mark.asyncio
async def test_task_list_is_the_callers_view(client):
    web = (await client.get("/tasks", headers=WEB_KEY)).json()["tasks"]
    ba = (await client.get("/tasks", headers=BA_KEY)).json()["tasks"]
    op = (await client.get("/tasks", headers=GLOBAL)).json()["tasks"]
    assert [t["task_id"] for t in web] == ["text_triage"]
    assert {t["task_id"] for t in ba} == {"feedback_triage", "health_normalize", "reply_suggest"}
    assert len(op) == 4
