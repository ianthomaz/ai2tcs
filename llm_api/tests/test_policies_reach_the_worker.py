"""Policies the worker reads must come through get_rag_policies (it returns a fixed set)."""
from app.jobs.worker import followup_search_query
from app.registry import get_rag_policies


def test_rated_examples_and_followup_reach_the_worker():
    p = get_rag_policies({"config_json": {"policies": {"rated_examples": 2, "retrieval_query_with_history": True}}})
    assert p["rated_examples"] == 2 and p["retrieval_query_with_history"] is True
    assert get_rag_policies({"config_json": {"policies": {"rated_examples": 99}}})["rated_examples"] == 5
    assert get_rag_policies({"config_json": {"policies": {"rated_examples": "x"}}})["rated_examples"] == 0
    off = get_rag_policies({"config_json": {}})
    assert off["rated_examples"] == 0 and off["retrieval_query_with_history"] is False
    assert get_rag_policies({})["rated_examples"] == 0


def test_short_followup_searches_with_the_previous_user_turn():
    hist = [
        {"role": "user", "content": "Tem oficina EBA em São Paulo?"},
        {"role": "assistant", "content": "Tem, aos sábados."},
        {"role": "user", "content": "E em Curitiba?"},
    ]
    assert followup_search_query("E em Curitiba?", hist) == "Tem oficina EBA em São Paulo?\nE em Curitiba?"
    long_q = "Quero saber como funciona o curso de formação de voluntários"
    assert followup_search_query(long_q, hist) == long_q
    assert followup_search_query("E em Curitiba?", None) == "E em Curitiba?"
    assert followup_search_query("E em Curitiba?", [{"role": "user", "content": "E em Curitiba?"}]) == "E em Curitiba?"
