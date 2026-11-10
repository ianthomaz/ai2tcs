"""signals: grounding, links the model never saw, and the 0–1 answer_confidence."""
from app.llm import signals

_CHUNKS = [{
    "snippet": "A oficina EBA acontece no Parque Ibirapuera aos sábados. Inscrição em https://bikeanjo.org/eba",
    "distance": 0.3,
    "url": None,
}]


def test_answer_backed_by_the_passage_scores_high():
    out = signals.build(chunks=_CHUNKS, answer="A oficina acontece aos sábados no Parque Ibirapuera: https://bikeanjo.org/eba")
    assert out["grounding"] == 1.0
    assert out["unsupported_links"] == []
    assert out["answer_confidence"] > 0.8
    assert out["confidence_basis"] == signals.CONFIDENCE_BASIS


def test_invented_link_and_content_pull_the_number_down():
    out = signals.build(chunks=_CHUNKS, answer="Tem oficina amanhã em Belém, veja https://bikeanjo.org/belem")
    assert out["unsupported_links"] == ["bikeanjo.org/belem"]
    assert out["answer_confidence"] < 0.3


def test_link_from_the_prompt_is_not_unsupported():
    out = signals.build(
        chunks=_CHUNKS,
        answer="Faça o cadastro em https://bikeanjo.org/cadastro",
        prompt_text="Link de cadastro: https://bikeanjo.org/cadastro",
    )
    assert out["unsupported_links"] == []


def test_no_answer_has_no_confidence_and_guard_halves_it():
    assert signals.build(chunks=[], answer=None)["answer_confidence"] is None
    plain = signals.build(chunks=_CHUNKS, answer="A oficina acontece aos sábados.")
    guarded = signals.build(chunks=_CHUNKS, answer="A oficina acontece aos sábados.", guard_hit=True)
    assert guarded["answer_confidence"] == round(plain["answer_confidence"] * 0.5, 3)


def test_distance_reference_follows_the_project_threshold():
    loose = signals.build(chunks=_CHUNKS, answer="A oficina acontece aos sábados.", distance_reference=1.2)
    tight = signals.build(chunks=_CHUNKS, answer="A oficina acontece aos sábados.", distance_reference=0.6)
    assert loose["answer_confidence"] > tight["answer_confidence"]
