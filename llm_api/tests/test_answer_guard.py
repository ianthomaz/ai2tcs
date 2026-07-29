"""Tests for cross-project answer bleed guard."""
from app.rag.answer_guard import guard_answer_for_profile


def _project(project_id: str, profile: str = "creative", fallback: str = "Resposta surreal curta.") -> dict:
    return {
        "project_id": project_id,
        "name": project_id,
        "config_json": {
            "prompt_profile": profile,
            "no_answer_fallback": fallback,
        },
    }


def test_guard_replaces_mobi_bleed_on_creative() -> None:
    proj = _project("aiclaudia")
    contaminated = "A Mobi cuida disso para você — fale com a equipe pelo WhatsApp."
    out = guard_answer_for_profile(contaminated, proj)
    assert "Mobi" not in out
    assert out == "Resposta surreal curta."


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
