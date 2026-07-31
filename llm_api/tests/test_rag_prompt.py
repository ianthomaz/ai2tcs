"""Tests for RAG prompt profiles and project policy helpers."""
from app.jobs.worker import _profile_from_request_context
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
    assert "NUNCA mencione Mobi" in system


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


def test_profile_from_request_context_promotes_rich_fields() -> None:
    """§1.1: journey/next_event/current_time land in metadata; clearance stays out."""
    profile = _profile_from_request_context(
        {
            "name": "Ana",
            "city": "Campinas",
            "clearance": "N",
            "intended_clearance": "O",
            "journey_kind": "onboarding",
            "journey_destination": "/eixo/cadastro",
            "next_event_name": "Pedal Noturno",
            "next_event_at": "2026-09-10T19:00:00-03:00",
            "current_time": "2026-07-29T23:00:00-03:00",
            "interesse": "passeio",
        }
    )
    assert profile["display_name"] == "Ana"
    meta = profile["metadata"]
    assert meta["city"] == "Campinas"
    # Authorization tier (NOIA) never reaches the prompt — see _profile_from_request_context.
    assert "clearance" not in meta
    assert "intended_clearance" not in meta
    assert meta["journey_kind"] == "onboarding"
    # An internal reference, not a link the model could hand over.
    assert "journey_destination" not in meta
    assert meta["next_event_name"] == "Pedal Noturno"
    assert meta["next_event_at"] == "2026-09-10T19:00:00-03:00"
    assert meta["current_time"] == "2026-07-29T23:00:00-03:00"
    assert meta["interesse"] == "passeio"


def test_system_prompt_includes_rich_user_metadata() -> None:
    profile = _profile_from_request_context(
        {
            "name": "Ana",
            "clearance": "O",
            "journey_kind": "event_signup",
            "next_event_name": "EBA Centro",
            "current_time": "2026-07-29T23:00:00-03:00",
        }
    )
    system = build_system_prompt(_project(), user_profile=profile)
    assert "clearance" not in system
    assert "- journey_kind: event_signup" in system
    assert "- next_event_name: EBA Centro" in system
    assert "- current_time: 2026-07-29T23:00:00-03:00" in system
    assert "Name: Ana" in system
