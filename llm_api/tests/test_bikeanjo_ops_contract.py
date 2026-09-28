"""Contract tests for the Bike Anjo ops ports against contracts/bikeanjo/ (no Ollama, no DB).

Every `request` in the examples is accepted; every success validates `response_ok`; every
content error validates the common error envelope; only the Bike Anjo key gets in.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app.bikeanjo.common import CONTRACTS_DIR, PortError

GLOBAL = {"Authorization": "Bearer test-token"}
BA_KEY = {"Authorization": "Bearer itcs_bikeanjoall_2026_x"}
OTHER_KEY = {"Authorization": "Bearer itcs_webplacecc_x"}

PORTS = {
    "/feedbackTriage": "feedback-triage",
    "/healthNormalize": "health-normalize",
    "/replySuggest": "reply-suggest",
}
# Keys the service adds around the model output.
SERVICE_KEYS = {"status", "model", "prompt_version", "warnings"}

_PROJECT = {"project_id": "bikeanjoall_2026", "sources": [], "config_json": {}}


def _load(name: str) -> dict:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


def _registry() -> Registry:
    reg = Registry()
    for path in CONTRACTS_DIR.glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        res = Resource.from_contents(schema)
        reg = reg.with_resource(path.name, res).with_resource(schema["$id"], res)
    return reg


def _validator(schema_name: str, part: str) -> Draft202012Validator:
    schema = _load(f"{schema_name}.schema.json")
    sub = {"$schema": schema["$schema"], "$ref": f"{schema_name}.schema.json#/$defs/{part}"}
    return Draft202012Validator(sub, registry=_registry())


def _cases(stem: str) -> list[dict]:
    return _load(f"{stem}.examples.json")["cases"]


def _model_output(response_ok: dict) -> str:
    return json.dumps({k: v for k, v in response_ok.items() if k not in SERVICE_KEYS}, ensure_ascii=False)


@pytest.fixture(autouse=True)
def _env():
    async def key_project(key_hash: str):
        from app.auth import hash_key

        return {
            hash_key("itcs_bikeanjoall_2026_x"): "bikeanjoall_2026",
            hash_key("itcs_webplacecc_x"): "webplacecc",
        }.get(key_hash)

    with patch("app.config.settings.llm_api_token", "test-token"), patch(
        "app.auth.db_module.api_key_get_project_id", side_effect=key_project
    ), patch("app.bikeanjo.routes.log_sync_llm_job", new_callable=AsyncMock), patch(
        "app.bikeanjo.routes.get_project", new_callable=AsyncMock, return_value=_PROJECT
    ):
        yield


def _fake_chat(content: str):
    class _P:
        async def chat(self, model, messages, options):
            assert options.get("format") == "json"
            return content

    return patch("app.bikeanjo.common.get_provider", return_value=_P())


def _fake_retrieve(names: list[str]):
    chunks = [
        {"id": str(i), "path": f"bibliotecaConteudoLLM/{n}.md", "snippet": f"trecho {n}", "distance": 0.4}
        for i, n in enumerate(names)
    ]
    return patch("app.bikeanjo.reply_suggest.retrieve", new_callable=AsyncMock, return_value=chunks)


# ---------------------------------------------------------------- the package itself


@pytest.mark.parametrize("stem", ["feedback-triage", "health-normalize", "reply-suggest"])
def test_examples_match_their_own_schema(stem):
    req_v, ok_v = _validator(stem, "request"), _validator(stem, "response_ok")
    for case in _cases(stem):
        req_v.validate(case["request"])
        ok_v.validate(case["response_ok"])


def test_prompts_load_without_the_paste_notes():
    from app.bikeanjo.common import load_prompt

    body = load_prompt("feedback-triage-v1.md")
    assert not body.startswith("# System prompt")
    assert "grave" in body and "Colar no ai2tcs" not in body


# ---------------------------------------------------------------- examples through the routes


@pytest.mark.asyncio
@pytest.mark.parametrize("stem", ["feedback-triage", "health-normalize"])
async def test_every_example_request_is_accepted(client, stem):
    route = next(r for r, s in PORTS.items() if s == stem)
    ok_v = _validator(stem, "response_ok")
    for case in _cases(stem):
        with _fake_chat(_model_output(case["response_ok"])):
            r = await client.post(route, json=case["request"], headers=BA_KEY)
        assert r.status_code == 200, r.text
        body = r.json()
        ok_v.validate(body)
        assert body["prompt_version"] == case["response_ok"]["prompt_version"]


@pytest.mark.asyncio
async def test_reply_examples_are_accepted(client):
    ok_v = _validator("reply-suggest", "response_ok")
    for case in _cases("reply-suggest"):
        expected = case["response_ok"]
        with _fake_chat(_model_output(expected)), _fake_retrieve(expected["sources"] or ["34_suporte_chamados_rascunho"]):
            r = await client.post("/replySuggest", json=case["request"], headers=BA_KEY)
        assert r.status_code == 200, r.text
        body = r.json()
        ok_v.validate(body)
        assert body["no_answer"] == expected["no_answer"]
        if not expected["no_answer"]:
            assert body["sources"] == expected["sources"]


@pytest.mark.asyncio
async def test_unknown_fields_are_ignored(client):
    req = {**_cases("feedback-triage")[0]["request"], "extra_field": {"x": 1}}
    with _fake_chat(_model_output(_cases("feedback-triage")[0]["response_ok"])):
        r = await client.post("/feedbackTriage", json=req, headers=BA_KEY)
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------- error envelope


@pytest.mark.asyncio
@pytest.mark.parametrize("route", list(PORTS))
async def test_invalid_body_is_http_200_with_error_envelope(client, route):
    r = await client.post(route, json={"source": "nope"}, headers=BA_KEY)
    assert r.status_code == 200
    body = r.json()
    _validator(PORTS[route], "response_error").validate(body)
    assert body["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_model_timeout_maps_to_timeout_code(client):
    req = _cases("health-normalize")[0]["request"]
    with patch("app.bikeanjo.health_normalize.chat_json", side_effect=PortError("timeout", "x")):
        r = await client.post("/healthNormalize", json=req, headers=BA_KEY)
    assert r.status_code == 200
    assert r.json() == {"status": "error", "error": {"code": "timeout", "message": "x"}}


@pytest.mark.asyncio
async def test_non_json_model_answer_is_model_error_after_retry(client):
    req = _cases("feedback-triage")[0]["request"]
    with _fake_chat("não sei responder isso"):
        r = await client.post("/feedbackTriage", json=req, headers=BA_KEY)
    assert r.json()["error"]["code"] == "model_error"


# ---------------------------------------------------------------- access: Bike Anjo only


@pytest.mark.asyncio
@pytest.mark.parametrize("route", list(PORTS))
async def test_other_project_key_is_forbidden(client, route):
    r = await client.post(route, json={}, headers=OTHER_KEY)
    assert r.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("route", list(PORTS))
async def test_missing_token_is_401(client, route):
    r = await client.post(route, json={})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_global_token_runs_as_bikeanjo(client):
    case = _cases("health-normalize")[0]
    with _fake_chat(_model_output(case["response_ok"])):
        r = await client.post("/healthNormalize", json=case["request"], headers=GLOBAL)
    assert r.status_code == 200 and r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_global_token_can_be_turned_off(client):
    with patch("app.config.settings.bikeanjo_ops_allow_global_token", False):
        r = await client.post("/healthNormalize", json={}, headers=GLOBAL)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_body_project_id_of_another_project_is_forbidden(client):
    req = {**_cases("health-normalize")[0]["request"], "project_id": "webplacecc"}
    r = await client.post("/healthNormalize", json=req, headers=BA_KEY)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_database_down_still_answers_with_the_envelope(client):
    case = _cases("health-normalize")[0]
    with patch("app.bikeanjo.routes.get_project", side_effect=RuntimeError("db down")), _fake_chat(
        _model_output(case["response_ok"])
    ):
        r = await client.post("/healthNormalize", json=case["request"], headers=BA_KEY)
    assert r.status_code == 200 and r.json()["status"] == "ok"
    with patch("app.bikeanjo.routes.get_project", side_effect=RuntimeError("db down")):
        r = await client.post("/replySuggest", json=_cases("reply-suggest")[0]["request"], headers=BA_KEY)
    assert r.json()["error"]["code"] == "model_error"
