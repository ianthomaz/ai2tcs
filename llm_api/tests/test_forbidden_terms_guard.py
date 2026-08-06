"""Per-project forbidden terms, and the per-project reflection override.

Both are opt-in: with no config the behaviour must be byte-for-byte what it was,
because every project in the repo today configures neither.
"""
from unittest.mock import patch

import pytest

from app.registry import get_rag_feature_flags
from app.rag.answer_guard import (
    find_forbidden_terms,
    get_forbidden_terms,
    guard_answer_for_profile,
)

FALLBACK = "Fallback do projeto."


def _project(project_id="p1", profile=None, terms=None, extra_policies=None):
    policies = dict(extra_policies or {})
    if terms is not None:
        policies["forbidden_terms"] = terms
    config = {"no_answer_fallback": FALLBACK}
    if profile:
        config["prompt_profile"] = profile
    if policies:
        config["policies"] = policies
    return {"project_id": project_id, "config_json": config}


# --- reading the config ---------------------------------------------------


@pytest.mark.parametrize(
    "config,expected",
    [
        ({}, []),
        ({"policies": {}}, []),
        ({"policies": {"forbidden_terms": []}}, []),
        ({"policies": {"forbidden_terms": ["Mobi", " cnpj ", "", "  "]}}, ["Mobi", "cnpj"]),
        # Malformed config must degrade to "no terms", never raise on the answer path.
        ({"policies": {"forbidden_terms": "mobi"}}, []),
        ({"policies": {"forbidden_terms": ["ok", 7, None]}}, ["ok"]),
        ({"policies": "nope"}, []),
        ({}, []),
    ],
)
def test_get_forbidden_terms_is_tolerant(config, expected):
    assert get_forbidden_terms({"config_json": config}) == expected


def test_get_forbidden_terms_handles_missing_config():
    assert get_forbidden_terms({}) == []
    assert get_forbidden_terms({"config_json": None}) == []


def test_find_forbidden_terms_is_case_insensitive_substring():
    assert find_forbidden_terms("A MOBI cuida disso", ["mobi"]) == ["mobi"]
    assert find_forbidden_terms("nada aqui", ["mobi"]) == []
    # Same semantics as scripts/eval_rag.py score_answer: substring, not word.
    assert find_forbidden_terms("mobilidade urbana", ["mobi"]) == ["mobi"]
    assert find_forbidden_terms("x", []) == []


# --- unchanged behaviour when nothing is configured -----------------------


def test_factual_project_without_terms_is_untouched():
    answer = "A Mobi cuida disso para você — fale com a equipe pelo WhatsApp."
    # This is exactly the bleed string, on a factual project: today it passes
    # through, and without configured terms it must keep passing through.
    assert guard_answer_for_profile(answer, _project()) == answer


def test_creative_bleed_still_caught_without_any_config():
    answer = "A Mobi cuida disso para você."
    # Default when_no_answer is no_answer → silence, not the prompt-instruction fallback.
    assert guard_answer_for_profile(answer, _project(profile="creative")) == ""


def test_estudosmobi_creative_still_exempt():
    answer = "A Mobi cuida disso para você."
    project = _project(project_id="estudosmobi", profile="creative")
    assert guard_answer_for_profile(answer, project) == answer


def test_empty_answer_short_circuits():
    project = _project(terms=["mobi"])
    assert guard_answer_for_profile("", project) == ""
    assert guard_answer_for_profile("   ", project) == "   "


# --- the case that was impossible before ----------------------------------


def test_factual_project_can_now_declare_its_own_terms():
    answer = "Recomendo procurar a mobicontabil para isso."
    project = _project(terms=["mobicontabil"])
    # factual profile: the hardcoded guard never fires here, only the config does.
    # Default when_no_answer=no_answer → empty string (WhatsApp silence).
    assert guard_answer_for_profile(answer, project) == ""


def test_sales_project_can_declare_terms_too():
    answer = "Fale com o concorrente XPTO."
    project = _project(profile="sales", terms=["XPTO"])
    assert guard_answer_for_profile(answer, project) == ""


def test_configured_terms_win_for_a_project_the_hardcoded_guard_exempts():
    """estudosmobi is exempt from the mobi patterns, but not from its own list."""
    project = _project(project_id="estudosmobi", profile="creative", terms=["reembolso garantido"])
    assert guard_answer_for_profile("Oferecemos reembolso garantido.", project) == ""
    # Its own brand still passes, as before.
    assert guard_answer_for_profile("A Mobi cuida disso.", project) == "A Mobi cuida disso."


def test_user_facing_fallback_kept_when_when_no_answer_is_not_no_answer():
    project = _project(terms=["telemóvel"], extra_policies={"when_no_answer": "allow_model"})
    assert guard_answer_for_profile("Abra no telemóvel.", project) == FALLBACK


def test_bikeanjo_forbidden_terms_become_silence():
    project = _project(
        project_id="bikeanjoall_2026",
        terms=["telemóvel", "De nada", "posso ajudar em mais"],
        extra_policies={"when_no_answer": "no_answer"},
    )
    assert guard_answer_for_profile("De nada! Qualquer coisa estou à disposição.", project) == ""
    assert guard_answer_for_profile("Abra o link no telemóvel.", project) == ""


def test_clean_answer_passes_with_terms_configured():
    project = _project(terms=["mobi", "xpto"])
    answer = "O evento acontece no sábado."
    assert guard_answer_for_profile(answer, project) == answer


# --- reflection override --------------------------------------------------


def test_reflection_falls_back_to_global_when_project_is_silent():
    for global_value in (True, False):
        with patch("app.config.settings.rag_reflection_enabled", global_value):
            flags = get_rag_feature_flags({"config_json": {}})
            assert flags["rag_reflection_enabled"] is global_value


def test_reflection_project_override_wins_over_global():
    project = {"config_json": {"policies": {"rag_reflection_enabled": True}}}
    with patch("app.config.settings.rag_reflection_enabled", False):
        assert get_rag_feature_flags(project)["rag_reflection_enabled"] is True

    project_off = {"config_json": {"policies": {"rag_reflection_enabled": False}}}
    with patch("app.config.settings.rag_reflection_enabled", True):
        assert get_rag_feature_flags(project_off)["rag_reflection_enabled"] is False


def test_reflection_joins_the_other_rag_flags():
    flags = get_rag_feature_flags({"config_json": {}})
    assert set(flags) == {"rag_hybrid_enabled", "rag_rerank_enabled", "rag_reflection_enabled"}
