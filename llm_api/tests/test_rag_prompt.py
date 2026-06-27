"""Tests for RAG prompt profiles and project policy helpers."""
from app.rag.prompt import build_messages, build_system_prompt, get_no_answer_fallback, get_prompt_profile
from app.registry import get_rag_policies, get_router_config


def _project(config_json: dict | None = None) -> dict:
    return {
        "project_id": "test_proj",
        "name": "Test Project",
        "config_json": config_json or {},
    }


def test_prompt_profile_defaults_to_factual() -> None:
    assert get_prompt_profile(_project()) == "factual"


def test_prompt_profile_creative() -> None:
    proj = _project({"prompt_profile": "creative"})
    assert get_prompt_profile(proj) == "creative"


def test_system_prompt_factual_has_no_mobi_example() -> None:
    system = build_system_prompt(_project())
    assert "Mobi" not in system
    assert "ONLY on the provided context" in system


def test_system_prompt_creative_allows_improv() -> None:
    proj = _project({"prompt_profile": "creative"})
    system = build_system_prompt(proj)
    assert "improvise" in system.lower() or "improv" in system.lower()
    assert "ONLY on the provided context" not in system


def test_no_answer_fallback_custom() -> None:
    proj = _project({"no_answer_fallback": "Fale com nosso time pelo site."})
    assert get_no_answer_fallback(proj) == "Fale com nosso time pelo site."
    system = build_system_prompt(proj)
    assert "Fale com nosso time pelo site." in system


def test_build_messages_creative_user_template() -> None:
    proj = _project({"prompt_profile": "creative"})
    _, user = build_messages(proj, "Oi?", [])
    assert "Optional inspiration" in user
    assert "in character" in user


def test_dedup_ttl_in_policies() -> None:
    proj = _project({"policies": {"dedup_ttl_seconds": 0}})
    assert get_rag_policies(proj)["dedup_ttl_seconds"] == 0


def test_router_config_extra_block() -> None:
    proj = _project({"router": {"extra_system_block": "Custom router rules."}})
    cfg = get_router_config(proj)
    assert cfg["extra_system_block"] == "Custom router rules."
