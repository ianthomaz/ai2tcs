"""Tests for cross-project answer bleed guard."""
from app.rag.answer_guard import guard_answer_for_profile


def _project(project_id: str, profile: str = "creative", fallback: str = "Resposta surreal curta.", when_no_answer: str | None = "allow_model") -> dict:
    """aiclaudia-style: allow_model keeps a user-facing fallback when the guard fires.

    Bike Anjo uses when_no_answer=no_answer and must get silence ("") instead.
    """
    config: dict = {
        "prompt_profile": profile,
        "no_answer_fallback": fallback,
    }
    if when_no_answer is not None:
        config["policies"] = {"when_no_answer": when_no_answer}
    return {
        "project_id": project_id,
        "name": project_id,
        "config_json": config,
    }


def test_guard_replaces_mobi_bleed_on_creative() -> None:
    proj = _project("aiclaudia")
    contaminated = "A Mobi cuida disso para você — fale com a equipe pelo WhatsApp."
    out = guard_answer_for_profile(contaminated, proj)
    assert "Mobi" not in out
    assert out == "Resposta surreal curta."


def test_guard_silence_when_no_answer_policy() -> None:
    proj = _project("bikeanjoall_2026", when_no_answer="no_answer", fallback="instrução interna do prompt")
    contaminated = "A Mobi cuida disso para você — fale com a equipe pelo WhatsApp."
    assert guard_answer_for_profile(contaminated, proj) == ""


def test_guard_allows_mobi_on_estudosmobi() -> None:
    proj = _project("estudosmobi", profile="sales", fallback="Contato Mobi.")
    text = "A Mobi cuida disso para você."
    assert guard_answer_for_profile(text, proj) == text


def test_guard_allows_clean_creative_answer() -> None:
    proj = _project("aiclaudia")
    text = "Paris é a capital, mas minha chave está num universo paralelo."
    assert guard_answer_for_profile(text, proj) == text


def test_creative_system_prompt_forbids_mobi_mention() -> None:
    from app.rag.prompt import build_system_prompt

    system = build_system_prompt(_project("aiclaudia"))
    assert "NUNCA mencione Mobi" in system
