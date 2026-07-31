"""Reception of the rich context: it arrives (§1.1), but in a shape the model can use.

Covers the profile-display opt-in (labels, path expansion, code glossary) and the
router retrieval query. Every behaviour here is off by default, so projects that
send no platform context keep their current prompt byte-for-byte.
"""
from app.api.message_router import RouterRequest, _build_retrieval_query
from app.jobs.worker import _profile_from_request_context
from app.rag.prompt import build_system_prompt, get_profile_display_config

ZAP_CONTEXT = {
    "name": "Ana",
    "city": "Campinas",
    "clearance": "N",  # accepted on the wire, must never reach the prompt
    "journey_kind": "pofr",
    "journey_destination": "/eixo/event-123",
    "next_event_name": "EBA Vila Mariana",
    "current_time": "2026-07-31T09:00:00-03:00",
}


def _project(config: dict | None = None) -> dict:
    return {"project_id": "p1", "name": "P1", "config_json": config or {}}


def test_profile_display_defaults_to_raw_rendering() -> None:
    """No config → unchanged output, so other projects cannot be affected."""
    system = build_system_prompt(_project(), user_profile=_profile_from_request_context(ZAP_CONTEXT))
    assert "- journey_kind: pofr" in system
    assert "- journey_destination: /eixo/event-123" in system


def test_clearance_never_reaches_the_prompt() -> None:
    """NOIA is an authorization tier, validated upstream; the model has no use for it."""
    for config in ({}, {"profile_display": {"labels": True}}):
        system = build_system_prompt(
            _project(config), user_profile=_profile_from_request_context(ZAP_CONTEXT)
        )
        assert "clearance" not in system
        assert "Nível de cadastro" not in system


def test_labels_make_platform_fields_readable() -> None:
    system = build_system_prompt(
        _project({"profile_display": {"labels": True}}),
        user_profile=_profile_from_request_context(ZAP_CONTEXT),
    )
    assert "- Jornada aberta (tipo): pofr" in system
    assert "- Hora local do contato agora: 2026-07-31T09:00:00-03:00" in system
    # Keys outside the platform set keep their original rendering.
    assert "- city: Campinas" in system


def test_base_url_expands_path_so_model_never_emits_half_link() -> None:
    system = build_system_prompt(
        _project({"profile_display": {"labels": True, "base_url": "https://example.org/"}}),
        user_profile=_profile_from_request_context(ZAP_CONTEXT),
    )
    assert "https://example.org/eixo/event-123" in system


def test_glossary_decodes_opaque_journey_slug() -> None:
    system = build_system_prompt(
        _project(
            {
                "profile_display": {
                    "labels": True,
                    "glossary": {"journey_kind": {"pofr": "<significado real vem do seed>"}},
                }
            }
        ),
        user_profile=_profile_from_request_context(ZAP_CONTEXT),
    )
    assert "pofr (<significado real vem do seed>)" in system


def test_glossary_leaves_unknown_values_untouched() -> None:
    system = build_system_prompt(
        _project({"profile_display": {"labels": True, "glossary": {"journey_kind": {"outra": "x"}}}}),
        user_profile=_profile_from_request_context(ZAP_CONTEXT),
    )
    assert "- Jornada aberta (tipo): pofr\n" in system


def test_profile_display_config_ignores_malformed_values() -> None:
    cfg = get_profile_display_config(_project({"profile_display": {"glossary": "nope", "base_url": 7}}))
    assert cfg == {"labels": False, "base_url": "", "glossary": {}}


def test_retrieval_query_unchanged_without_context() -> None:
    """Clients that send no platform context must hit the index with the same query."""
    body = RouterRequest(message="como faço para participar?", project_id="p1")
    assert _build_retrieval_query(body) == "como faço para participar?"


def test_retrieval_query_includes_context_terms() -> None:
    body = RouterRequest(
        message="tem evento perto de mim?",
        project_id="bikeanjoall_2026",
        city="Campinas",
        interesse="aprender_a_pedalar",
        journey_kind="pofr",
        next_event_name="EBA Vila Mariana",
        clearance="N",
        journey_destination="/eixo/event-123",
        next_event_at="2026-08-10T14:00:00",
    )
    query = _build_retrieval_query(body)
    assert query.startswith("tem evento perto de mim?")
    assert "Campinas" in query
    assert "aprender_a_pedalar" in query
    assert "pofr" in query
    assert "EBA Vila Mariana" in query
    # Opaque codes, id paths and timestamps stay out: they are noise for the embedding.
    assert "/eixo/event-123" not in query
    assert "2026-08-10T14:00:00" not in query
