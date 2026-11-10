"""POST /ask dedup: one job only for the same question with the same asker and context."""
from app.api.ask import _question_hash


def test_same_question_same_asker_and_context_collapses():
    ctx = {"city": "Curitiba", "__llm_history": [{"role": "user", "content": "oi"}]}
    assert _question_hash("p", "Tem oficina?", "u1", ctx) == _question_hash("p", "  tem   OFICINA? ", "u1", dict(ctx))


def test_different_people_or_context_get_their_own_job():
    base = _question_hash("p", "Tem oficina?", "u1", {"city": "Curitiba"})
    assert base != _question_hash("p", "Tem oficina?", "u2", {"city": "Curitiba"})
    assert base != _question_hash("p", "Tem oficina?", "u1", {"city": "Belém"})
    assert base != _question_hash("p", "Tem oficina?", None, None)
    assert base != _question_hash("q", "Tem oficina?", "u1", {"city": "Curitiba"})
