"""Build system and user prompt for LLM with RAG context, user profile, and conversation history."""
from datetime import date

# Profile-specific opening rules (context strictness + no-answer behavior)
_PROFILE_OPENINGS = {
    "factual": (
        'You are a helpful assistant for the project "{project_name}". '
        "You answer questions based ONLY on the provided context passages. "
        "Never invent information. When the context has relevant content, use it to answer directly."
    ),
    "sales": (
        'You are a helpful assistant for the project "{project_name}". '
        "You answer questions based on the provided context passages. "
        "When the context has relevant content, use it to answer directly and invite contact when appropriate. "
        "Never invent facts not supported by the context."
    ),
    "creative": (
        'You are a creative assistant for the project "{project_name}". '
        "Use the knowledge base passages as inspiration when they fit the question, "
        "but you may improvise in character when the passages are empty or only loosely related. "
        "Stay in the project's voice and never claim specific business facts without context support."
    ),
}

_DEFAULT_NO_ANSWER_FALLBACK = (
    "Responda em uma frase o que o serviço oferece sobre o tema e convide para contato."
)

_CALIBRATION_BLOCK = """\
Calibration (obrigatório):
- Responda sempre de forma direta. NUNCA use nenhuma destas frases (nem variações): "Com base no contexto fornecido", "Com base apenas na informação fornecida", "Segundo o conteúdo", "Segundo o contexto", "não encontrei informação específica", "não encontrei informação suficiente", "não há informações que justifiquem ou desaconselhem", "A pergunta é sobre", "recomendo consultar os links", "De acordo com as informações disponíveis". Se há trechos relevantes no contexto, use-os para responder diretamente.
- Quando não houver nada útil no contexto: {no_answer_fallback} Nunca explique que não encontrou informação, nem use frases longas negativas.
- Use linguagem natural e fluente em português. Nunca gere construções gramaticalmente incorretas como "Você pode abertura", "você pode fale", "para falecimento ou envio". Revise mentalmente a frase antes de responder.
"""

_CALIBRATION_CREATIVE = """\
Calibration (obrigatório):
- Responda sempre de forma direta, na persona do projeto. NUNCA use meta-frases ("Com base no contexto", "Segundo o conteúdo", "não encontrei informação", etc.).
- Quando não houver trechos úteis na base: {no_answer_fallback} Improvise curto, em personagem — sem explicar que faltou contexto.
- NUNCA mencione Mobi, mobicontabil, contabilidade, MEI ou convites comerciais de WhatsApp, salvo se esses termos aparecerem literalmente nos trechos da base acima.
- Use linguagem natural em português (pt-BR). Respostas curtas quando possível.
"""

_RULES_BLOCK = """\
Rules:
- Answer in Portuguese (pt-BR) by default. Only use another language if the user clearly writes in that language.
- {tone_instruction}
- {size_instruction}
- Do NOT cite internal file paths or document names; the user does not have access to them. If the context includes external URLs (sites, links) about the topic, you may mention those for further reading.
- If the user asks a follow-up that references previous conversation, use the conversation history and summaries to understand what they mean.
- Use the user profile information to personalize your responses when relevant (e.g. address them by name, consider their age or health conditions).
{sales_rule}\
"""

_SALES_RULE = (
    "- When the project is about services/sales: adopt a helpful, service-oriented tone. "
    'Instead of "I don\'t have that info", say what the service offers and invite to contact the team.\n'
)

USER_TEMPLATE = """\
{conversation_summaries}\
{conversation_history}\
Context from the knowledge base:

{context}

---

Question: {question}

Answer{answer_hint}:\
"""

USER_TEMPLATE_CREATIVE = """\
{conversation_summaries}\
{conversation_history}\
Optional inspiration from the knowledge base:

{context}

---

Question: {question}

Answer in character{answer_hint}:\
"""

CONVERSATION_HEADER = "Recent conversation with this user:\n\n"
CONVERSATION_ENTRY = "[{role}]: {content}\n"
CONVERSATION_SEPARATOR = "\n---\n\n"


def get_prompt_profile(project: dict) -> str:
    """Return prompt profile: factual | sales | creative."""
    cfg = project.get("config_json") or {}
    if isinstance(cfg, dict):
        profile = (cfg.get("prompt_profile") or "factual").strip().lower()
        if profile in ("factual", "sales", "creative"):
            return profile
    return "factual"


def get_no_answer_fallback(project: dict) -> str:
    """Project-specific fallback when RAG has no useful context."""
    cfg = project.get("config_json") or {}
    if isinstance(cfg, dict):
        fb = cfg.get("no_answer_fallback")
        if isinstance(fb, str) and fb.strip():
            return fb.strip()
    return _DEFAULT_NO_ANSWER_FALLBACK


def get_profile_display_config(project: dict) -> dict:
    """Rendering options for the user-profile block (config_json.profile_display).

    Opt-in per project: with no config the profile block renders exactly as before
    (raw `- key: value` lines), so projects that do not send platform context are
    byte-identical.

    - labels: translate known platform keys to readable labels.
    - base_url: expand path-only values (e.g. "/eixo/event-1") into full URLs, so
      the model never emits a half-link to the user.
    - glossary: {field: {raw_value: meaning}} for opaque slugs the model cannot
      decode on its own (e.g. journey kinds).
    """
    cfg = project.get("config_json") or {}
    disp = cfg.get("profile_display") if isinstance(cfg, dict) else None
    if not isinstance(disp, dict):
        return {"labels": False, "base_url": "", "glossary": {}}
    glossary = disp.get("glossary")
    base_url = disp.get("base_url")
    return {
        "labels": bool(disp.get("labels")),
        "base_url": base_url.strip().rstrip("/") if isinstance(base_url, str) else "",
        "glossary": glossary if isinstance(glossary, dict) else {},
    }


# Readable labels for the platform context the client sends (§1.1 of the Bike Anjo
# contract). Only keys listed here are relabelled; every other metadata key keeps
# its raw rendering, so existing projects are unaffected.
_PLATFORM_FIELD_LABELS = {
    "journey_kind": "Jornada aberta (tipo)",
    "journey_destination": "Jornada aberta (destino)",
    "next_event_name": "Próximo evento inscrito",
    "next_event_at": "Data do próximo evento inscrito",
    "current_time": "Hora local do contato agora",
}

# Values that are paths, not text: expanded with base_url when configured.
_PATH_VALUED_FIELDS = ("journey_destination",)


def _render_metadata_value(key: str, value: object, display: dict) -> str:
    """Render one metadata value, expanding paths and decoding known codes."""
    text = str(value)
    base_url = display.get("base_url") or ""
    if base_url and key in _PATH_VALUED_FIELDS and text.startswith("/"):
        text = f"{base_url}{text}"
    meaning = (display.get("glossary") or {}).get(key, {})
    if isinstance(meaning, dict):
        decoded = meaning.get(str(value))
        if decoded:
            text = f"{text} ({decoded})"
    return text


def _format_user_profile(profile: dict | None, display: dict | None = None) -> str:
    """Format user profile for inclusion in the system prompt."""
    if not profile:
        return ""
    display = display or {"labels": False, "base_url": "", "glossary": {}}
    parts = ["About the current user:"]
    if profile.get("display_name"):
        parts.append(f"- Name: {profile['display_name']}")
    if profile.get("birth_date"):
        try:
            bd = profile["birth_date"]
            if isinstance(bd, str):
                bd_date = date.fromisoformat(bd)
            else:
                bd_date = bd
            age = (date.today() - bd_date).days // 365
            parts.append(f"- Birth date: {bd_date.isoformat()} (age: {age})")
        except (ValueError, TypeError):
            parts.append(f"- Birth date: {profile['birth_date']}")
    if profile.get("notes"):
        parts.append(f"- Notes: {profile['notes']}")
    metadata = profile.get("metadata") or {}
    if isinstance(metadata, dict):
        use_labels = display.get("labels")
        for key, value in metadata.items():
            label = _PLATFORM_FIELD_LABELS.get(key, key) if use_labels else key
            parts.append(f"- {label}: {_render_metadata_value(key, value, display)}")
    if len(parts) <= 1:
        return ""
    return "\n".join(parts) + "\n"


def _format_conversation_summaries(summaries: list[dict]) -> str:
    """Format monthly conversation summaries for context."""
    if not summaries:
        return ""
    parts = ["Summary of past conversations with this user:\n"]
    for s in summaries:
        parts.append(f"[{s['period']}] ({s['message_count']} messages):\n{s['summary'][:600]}\n")
    parts.append("---\n\n")
    return "\n".join(parts)


def _format_conversation_history(history: list[dict], max_turns: int = 6) -> str:
    """Format recent conversation history for inclusion in the prompt."""
    if not history:
        return ""
    recent = history[-(max_turns * 2):]
    lines = [CONVERSATION_HEADER]
    for msg in recent:
        role_label = "Usuário" if msg["role"] == "user" else "Assistente"
        content = msg["content"][:500]
        lines.append(CONVERSATION_ENTRY.format(role=role_label, content=content))
    lines.append(CONVERSATION_SEPARATOR)
    return "".join(lines)


TONE_MAP = {
    "informal": "Adote um tom informal, descontraído e amigável.",
    "friendly": "Adote um tom amigável, acolhedor e prestativo.",
    "technical": "Adote um tom técnico, preciso e profissional.",
    "sales": "Adote um tom vendedor, persuasivo e focado em converter o interesse do usuário em serviço/contato.",
    "direct": "Adote um tom direto, objetivo e sem rodeios.",
}

SIZE_MAP = {
    "short": "Responda de forma muito breve (máximo 2 parágrafos).",
    "medium": "Responda de forma equilibrada (2 a 4 parágrafos).",
    "detailed": "Responda de forma detalhada, explicando bem os pontos relevantes do contexto.",
}


def build_system_prompt(
    project: dict,
    user_profile: dict | None = None,
    llm_config: dict | None = None,
    extra_system_instruction: str | None = None,
    client_system_prompt_prefix: str | None = None,
) -> str:
    """Build the system message without RAG user context."""
    project_name = project.get("name") or project.get("project_id", "unknown")
    profile_block = _format_user_profile(user_profile, get_profile_display_config(project))
    prompt_profile = get_prompt_profile(project)
    no_answer_fallback = get_no_answer_fallback(project)

    config = llm_config or {}
    tone = config.get("tone_of_voice", "direct")
    size = config.get("message_size", "medium")
    tone_inst = TONE_MAP.get(tone, TONE_MAP["direct"])
    size_inst = SIZE_MAP.get(size, SIZE_MAP["medium"])

    opening = _PROFILE_OPENINGS.get(prompt_profile, _PROFILE_OPENINGS["factual"]).format(
        project_name=project_name
    )
    if prompt_profile == "creative":
        calibration = _CALIBRATION_CREATIVE.format(no_answer_fallback=no_answer_fallback)
    else:
        calibration = _CALIBRATION_BLOCK.format(no_answer_fallback=no_answer_fallback)
    sales_rule = _SALES_RULE if prompt_profile == "sales" else ""
    rules = _RULES_BLOCK.format(
        tone_instruction=tone_inst,
        size_instruction=size_inst,
        sales_rule=sales_rule,
    )

    system = f"{opening}\n\n{calibration}\n{rules}\n{profile_block}"
    if extra_system_instruction and extra_system_instruction.strip():
        system = system.rstrip() + "\n\n" + extra_system_instruction.strip() + "\n"
    if client_system_prompt_prefix and client_system_prompt_prefix.strip():
        system = client_system_prompt_prefix.strip() + "\n\n" + system
    return system


def build_messages(
    project: dict,
    question: str,
    chunks: list[dict],
    conversation_history: list[dict] | None = None,
    user_profile: dict | None = None,
    conversation_summaries: list[dict] | None = None,
    extra_system_instruction: str | None = None,
    conversation_override: list[dict] | None = None,
    client_system_prompt_prefix: str | None = None,
    llm_config: dict | None = None,
) -> tuple[str, str]:
    """Return (system_message, user_message)."""
    prompt_profile = get_prompt_profile(project)
    system = build_system_prompt(
        project,
        user_profile=user_profile,
        llm_config=llm_config,
        extra_system_instruction=extra_system_instruction,
        client_system_prompt_prefix=client_system_prompt_prefix,
    )

    summaries_text = _format_conversation_summaries(conversation_summaries or [])
    conv_source = conversation_override if conversation_override is not None else (conversation_history or [])
    conv_text = _format_conversation_history(conv_source)

    if not chunks:
        if prompt_profile == "creative":
            context = "(No passages retrieved — respond in character.)"
        else:
            context = "(No relevant passages found in the knowledge base.)"
    else:
        context_blocks = []
        for c in chunks:
            path = c.get("path", "")
            snippet = c.get("snippet", "")
            dist = c.get("distance")
            header = f"[Source: {path}]"
            if dist is not None:
                header += f" (relevance: {1 - dist:.2f})"
            context_blocks.append(f"{header}\n{snippet}")
        context = "\n\n---\n\n".join(context_blocks)

    answer_hint = "" if prompt_profile == "creative" else " (based only on the context above)"
    user_template = USER_TEMPLATE_CREATIVE if prompt_profile == "creative" else USER_TEMPLATE

    user = user_template.format(
        conversation_summaries=summaries_text,
        conversation_history=conv_text,
        context=context,
        question=question,
        answer_hint=answer_hint,
    )
    return system, user
