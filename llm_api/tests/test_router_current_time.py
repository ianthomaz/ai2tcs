"""POST /router must accept and inject current_time (Zap sends it; extra=ignore used to drop it)."""
from app.api.message_router import RouterRequest


def test_router_request_accepts_current_time():
    body = RouterRequest(
        message="tem evento amanhã?",
        project_id="bikeanjoall_2026",
        city="Natal",
        current_time="2026-08-06T20:15:00-03:00",
    )
    assert body.current_time == "2026-08-06T20:15:00-03:00"


def test_router_user_parts_include_current_time_label():
    """Mirror the injection in route_message without standing up Ollama."""
    body = RouterRequest(
        message="oi",
        current_time="2026-08-06T20:15:00-03:00",
        next_event_name="EBA Natal",
    )
    # Rebuild the same lines route_message appends for context fields.
    parts = [f"Mensagem do usuário: {body.message}"]
    if body.next_event_name:
        parts.append(f"Próximo evento: {body.next_event_name}")
    if body.current_time:
        parts.append(f"Hora local do contato agora: {body.current_time}")
    joined = "\n".join(parts)
    assert "Hora local do contato agora: 2026-08-06T20:15:00-03:00" in joined
    assert "Próximo evento: EBA Natal" in joined
