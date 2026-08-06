"""_sanitize_answer had zero test coverage despite being in prod since March 2026.

The system prompt (_CALIBRATION_BLOCK in app/rag/prompt.py) names ten forbidden
phrases. These tests pin that every one of them is actually stripped — anywhere in
the text, not just as a sentence-opening prefix, and every occurrence, not just the
first.
"""
from app.jobs.worker import _sanitize_answer

# The ten phrases _CALIBRATION_BLOCK bans, verbatim.
_FORBIDDEN_PHRASES = [
    "Com base no contexto fornecido",
    "Com base apenas na informação fornecida",
    "Segundo o conteúdo",
    "Segundo o contexto",
    "não encontrei informação específica",
    "não encontrei informação suficiente",
    "não há informações que justifiquem ou desaconselhem",
    "A pergunta é sobre",
    "recomendo consultar os links",
    "De acordo com as informações disponíveis",
]


def test_every_forbidden_phrase_is_stripped_as_a_prefix():
    for phrase in _FORBIDDEN_PHRASES:
        answer = f"{phrase}, a Mobi oferece consultoria contábil."
        cleaned = _sanitize_answer(answer)
        assert phrase.lower() not in cleaned.lower(), phrase


def test_every_forbidden_phrase_is_stripped_mid_text():
    """Before ago/2026 the regexes were anchored to ^, so only a prefix was caught."""
    for phrase in _FORBIDDEN_PHRASES:
        answer = f"A resposta é simples. {phrase}, isso ajuda bastante no seu caso."
        cleaned = _sanitize_answer(answer)
        assert phrase.lower() not in cleaned.lower(), phrase


def test_repeated_occurrence_is_stripped_not_just_the_first():
    """Before ago/2026 count=1 meant a second occurrence survived."""
    answer = "Com base no contexto fornecido, isso é X. Com base no contexto fornecido, isso é Y."
    cleaned = _sanitize_answer(answer)
    assert "com base no contexto fornecido" not in cleaned.lower()
    assert "isso é X." in cleaned or "X." in cleaned
    assert "isso é Y." in cleaned or "Y." in cleaned


def test_mid_text_removal_does_not_leave_double_spaces_or_orphan_comma():
    answer = "Frase inicial. Com base no contexto fornecido, o evento é sábado."
    cleaned = _sanitize_answer(answer)
    assert "  " not in cleaned
    assert not cleaned.startswith(",")
    assert "o evento é sábado" in cleaned


def test_clean_answer_is_untouched():
    answer = "O evento é sábado às 9h, na praça central."
    assert _sanitize_answer(answer) == answer


def test_negative_filler_still_removed():
    answer = "Não encontrei informação suficiente na base de conhecimento para responder essa pergunta."
    cleaned = _sanitize_answer(answer)
    assert cleaned == ""


def test_falecimento_fix_still_works_and_is_unaffected_by_the_new_rules():
    answer = "Temos contatos para falecimento no site."
    cleaned = _sanitize_answer(answer)
    assert "contatos para fale conosco" in cleaned


def test_falecimento_death_context_is_preserved():
    answer = "Em caso de falecimento de um associado, contate o suporte."
    assert _sanitize_answer(answer) == answer
