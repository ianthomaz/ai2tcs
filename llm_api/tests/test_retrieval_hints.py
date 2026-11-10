"""Retrieval: project hints reorder the pool, the threshold still reads the raw distance."""
from unittest.mock import AsyncMock, patch

import pytest

from app.rag import hints


def _c(path, d):
    return {"id": path, "path": f"/x/{path}.md", "snippet": "", "distance": d}


HINTS = {
    "port": {
        "boost_path_substrings": ["24_instrucoes"],
        "downrank_path_substrings": ["22_estatuto"],
        "exclude_path_substrings": ["rascunho"],
    },
    "intent_clusters": {
        "governanca": {"keywords": ["Estatuto", "assembleia"], "boost_path_substrings": ["22_estatuto"]},
        "local": {"keywords": ["quero pedalar"], "boost_path_substrings": ["04_mapa"], "extra_downrank": ["19_sobre"]},
    },
}


def test_boost_downrank_and_exclude():
    out = hints.apply([_c("22_estatuto", 0.30), _c("24_instrucoes", 0.34), _c("rascunho", 0.1), _c("19_sobre", 0.33)], HINTS, "tem oficina?")
    assert [c["id"] for c in out] == ["24_instrucoes", "19_sobre", "22_estatuto"]
    assert out[0]["distance"] == 0.34 and out[0]["adjusted_distance"] == 0.29


def test_cluster_lifts_its_files_even_over_the_general_downrank():
    out = hints.apply([_c("24_instrucoes", 0.30), _c("22_estatuto", 0.32)], HINTS, "O que diz o estatuto?")
    assert out[0]["id"] == "22_estatuto"
    out = hints.apply([_c("04_mapa", 0.36), _c("19_sobre", 0.30)], HINTS, "Quero pedalar em Curitiba")
    assert [c["id"] for c in out] == ["04_mapa", "19_sobre"]


def test_project_without_hints_keeps_the_order():
    chunks = [_c("b", 0.2), _c("a", 0.1)]
    assert hints.apply(chunks, None) is chunks
    assert hints.project_hints({"config_json": {}}, "ask") is None
    assert hints.project_hints({"config_json": {"retrieval_hints": {"ports": {"ask": {"boost_path_substrings": ["x"]}}}}}, "ask")["port"]


@pytest.mark.asyncio
async def test_retrieve_fetches_a_pool_applies_hints_and_the_query_instruction():
    from app.rag import retrieve as r

    project = {"project_id": "p", "config_json": {
        "retrieval_hints": {"ports": {"ask": HINTS["port"]}},
        "policies": {"embedding_query_instruction": True},
    }}
    pool = [_c("22_estatuto", 0.30), _c("19_sobre", 0.31), _c("24_instrucoes", 0.34)]
    with patch("app.registry.get_project", AsyncMock(return_value=project)), patch.object(
        r, "get_embedding_async", AsyncMock(return_value=[0.1])
    ) as emb, patch.object(r, "_retrieve_from_path", AsyncMock(return_value=pool)) as fetch:
        out = await r.retrieve("p", "Tem oficina?", top_k=2, port="ask")
    assert fetch.await_args.kwargs["top_k"] == 4
    assert emb.await_args.args[0].startswith("Represent this sentence")
    assert [c["id"] for c in out] == ["24_instrucoes", "19_sobre"]


@pytest.mark.asyncio
async def test_retrieve_without_port_or_flags_is_the_plain_top_k():
    from app.rag import retrieve as r

    pool = [_c("b", 0.2), _c("a", 0.1), _c("c", 0.3)]
    with patch("app.registry.get_project", AsyncMock(return_value={"project_id": "p", "config_json": {}})), patch.object(
        r, "get_embedding_async", AsyncMock(return_value=[0.1])
    ) as emb, patch.object(r, "_retrieve_from_path", AsyncMock(return_value=pool)):
        out = await r.retrieve("p", "Tem oficina?", top_k=2)
    assert emb.await_args.args[0] == "Tem oficina?"
    assert [c["id"] for c in out] == ["a", "b"]
