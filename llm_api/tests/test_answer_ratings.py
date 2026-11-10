"""Ratings door (docs/22): items, proposals that wait for a person, examples, the routes."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.auth import hash_key
from app.ratings import logic

KEY = {"Authorization": "Bearer itcs_webplacecc_x"}
GLOBAL = {"Authorization": "Bearer test-token"}


def _item(**kw):
    base = {"source_ref": "zap:log:1", "rating": "bad", "question": "Tem oficina?", "answer": "Tem sim."}
    base.update(kw)
    return base


def test_item_rules():
    assert logic.normalize_item({"source_ref": "zap:log:1", "rating": None}) == {"source_ref": "zap:log:1", "rating": None}
    for bad in ({"source_ref": "x y", "rating": "bad"}, _item(rating="ruim"), _item(answer="")):
        with pytest.raises(logic.ItemError):
            logic.normalize_item(bad)
    item = logic.normalize_item(_item(suggested_terms=["ok", "  prometo vaga  "]))
    assert item["suggested_terms"] == ["prometo vaga"]


def test_rejected_answer_proposes_the_links_the_model_never_saw_and_typed_terms():
    item = logic.normalize_item(_item(
        answer="Veja https://bikeanjo.org/belem e https://bikeanjo.org/eba",
        signals={"unsupported_links": ["https://bikeanjo.org/belem"]},
        suggested_terms=["garanto sua vaga"],
    ))
    assert logic.proposals_for(item) == [("forbidden_term", "bikeanjo.org/belem"), ("forbidden_term", "garanto sua vaga")]


def test_reason_about_a_link_without_signals_proposes_the_answer_links():
    item = logic.normalize_item(_item(answer="Veja https://x.org/a.", reason="Inventou link"))
    assert logic.proposals_for(item) == [("forbidden_term", "x.org/a")]


def test_good_answers_propose_nothing():
    item = logic.normalize_item(_item(rating="great", signals={"unsupported_links": ["https://x.org"]}))
    assert logic.proposals_for(item) == []


def test_examples_are_the_closest_approved_questions():
    rows = [
        {"question": "Quando é a próxima oficina em Curitiba?", "answer": "A1"},
        {"question": "Como faço meu cadastro?", "answer": "A2"},
    ]
    picked = logic.pick_examples("Tem oficina em Curitiba neste mês?", rows, 2)
    assert [r["answer"] for r in picked] == ["A1"]
    assert logic.pick_examples("Oi", rows, 2) == []
    block = logic.examples_block(picked)
    assert "Resposta aprovada: A1" in block and "trechos" in block


def test_approved_term_goes_to_the_list_the_guard_reads():
    cfg = logic.add_forbidden_term({"policies": {"forbidden_terms": ["Mobi"]}, "x": 1}, "bikeanjo.org/belem")
    assert cfg == {"policies": {"forbidden_terms": ["Mobi", "bikeanjo.org/belem"]}, "x": 1}
    assert logic.add_forbidden_term(cfg, "BIKEANJO.ORG/BELEM")["policies"]["forbidden_terms"] == ["Mobi", "bikeanjo.org/belem"]


@pytest.fixture
def _env():
    async def key_project(key_hash: str):
        return {hash_key("itcs_webplacecc_x"): "webplacecc"}.get(key_hash)

    async def project(pid: str):
        return {"project_id": pid, "config_json": {}} if pid in ("webplacecc", "other") else None

    with patch("app.config.settings.llm_api_token", "test-token"), patch(
        "app.auth.db_module.api_key_get_project_id", side_effect=key_project
    ), patch("app.ratings.routes.get_project", side_effect=project), patch(
        "app.ratings.store.save", new_callable=AsyncMock
    ) as save, patch("app.ratings.store.propose", new_callable=AsyncMock, return_value=True) as propose:
        yield save, propose


@pytest.mark.asyncio
async def test_post_ratings_stores_and_proposes_for_the_key_project(client, _env):
    save, propose = _env
    r = await client.post("/ratings", headers=KEY, json={"items": [
        _item(signals={"unsupported_links": ["https://x.org/a"]}),
        {"source_ref": "zap:log:2", "rating": None},
    ]})
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "stored": 1, "removed": 1, "new_proposals": 1}
    assert save.await_args_list[0].args[0] == "webplacecc"
    propose.assert_awaited_once_with("webplacecc", "forbidden_term", "x.org/a", "zap:log:1")


@pytest.mark.asyncio
async def test_post_ratings_refuses_bad_bodies_and_other_projects(client, _env):
    assert (await client.post("/ratings", headers=KEY, json={"items": []})).status_code == 400
    assert (await client.post("/ratings", headers=KEY, json={"items": [_item(rating="x")]})).status_code == 400
    assert (await client.post("/ratings", headers=KEY, json={"project_id": "other", "items": [_item()]})).status_code == 403
    assert (await client.post("/ratings", headers=GLOBAL, json={"items": [_item()]})).status_code == 400
    assert (await client.post("/ratings", headers=GLOBAL, json={"project_id": "other", "items": [_item()]})).status_code == 200


@pytest.mark.asyncio
async def test_decision_needs_a_pending_proposal(client, _env):
    with patch("app.ratings.store.decide", new_callable=AsyncMock, return_value=None):
        r = await client.post("/ratings/proposals/7/decision", headers=KEY, json={"decision": "approve"})
        assert r.status_code == 404
    with patch("app.ratings.store.decide", new_callable=AsyncMock, return_value={"id": 7, "status": "approved"}) as decide:
        r = await client.post("/ratings/proposals/7/decision", headers=KEY, json={"decision": "approve", "decided_by": "Ana"})
        assert r.json()["proposal"]["status"] == "approved"
        decide.assert_awaited_once_with("webplacecc", 7, True, "Ana")
    assert (await client.post("/ratings/proposals/7/decision", headers=KEY, json={"decision": "talvez"})).status_code == 400


@pytest.mark.asyncio
async def test_list_proposals(client, _env):
    with patch("app.ratings.store.list_proposals", new_callable=AsyncMock, return_value=[]) as lp:
        r = await client.get("/ratings/proposals", headers=KEY)
        assert r.json() == {"proposals": []}
        lp.assert_awaited_once_with("webplacecc", "pending")


@pytest.mark.asyncio
async def test_bike_anjo_contract_examples_go_through_the_route(client, _env):
    import json
    from pathlib import Path

    import jsonschema

    base = Path(__file__).resolve().parents[1] / "contracts" / "bikeanjo"
    schema = json.loads((base / "answer-ratings.schema.json").read_text(encoding="utf-8"))
    examples = json.loads((base / "answer-ratings.examples.json").read_text(encoding="utf-8"))
    for case in examples["cases"]:
        jsonschema.validate(case["request"], {**schema, "$ref": "#/$defs/request"})
        r = await client.post("/ratings", headers=KEY, json=case["request"])
        assert r.status_code == 200, case["name"]
        assert r.json() == case["response_ok"], case["name"]
