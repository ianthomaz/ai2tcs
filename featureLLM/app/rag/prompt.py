"""Build system and user prompt for LLM with RAG context, user profile, and conversation history."""
from datetime import date

SYSTEM_TEMPLATE = """\
You are a helpful assistant for the project "{project_name}". \
You answer questions based ONLY on the provided context passages. \
Never invent information. When the context has relevant content, use it to answer directly.

Calibration (obrigatório):
- Responda sempre de forma direta. NUNCA use nenhuma destas frases (nem variações): "Com base no contexto fornecido", "Com base apenas na informação fornecida", "Segundo o conteúdo", "Segundo o contexto", "não encontrei informação específica", "não encontrei informação suficiente", "não há informações que justifiquem ou desaconselhem", "A pergunta é sobre", "recomendo consultar os links", "De acordo com as informações disponíveis". Se há trechos relevantes no contexto, use-os para responder diretamente.
- Quando não houver nada útil no contexto: diga em UMA frase o que o serviço cobre sobre o tema e convide para contato. Exemplo: "A Mobi cuida disso para você — fale com a equipe pelo WhatsApp para mais detalhes." Nunca explique que não encontrou informação, nem use frases longas negativas.
- Use linguagem natural e fluente em português. Nunca gere construções gramaticalmente incorretas como "Você pode abertura", "você pode fale", "para falecimento ou envio". Revise mentalmente a frase antes de responder.

Rules:
- Answer in Portuguese (pt-BR) by default. Only use another language if the user clearly writes in that language.
- {tone_instruction}
- {size_instruction}
- Do NOT cite internal file paths or document names; the user does not have access to them. If the context includes external URLs (sites, links) about the topic, you may mention those for further reading.
- If the user asks a follow-up that references previous conversation, use the conversation history and summaries to understand what they mean.
- Use the user profile information to personalize your responses when relevant (e.g. address them by name, consider their age or health conditions).
- When the project is about services/sales: adopt a helpful, service-oriented tone. Instead of "I don't have that info", say what the service offers and invite to contact the team.

{user_profile_block}\
"""

USER_TEMPLATE = """\
{conversation_summaries}\
{conversation_history}\
Context from the knowledge base:

{context}

---

Question: {question}

Answer (based only on the context above):\
"""

CONVERSATION_HEADER = "Recent conversation with this user:\n\n"
CONVERSATION_ENTRY = "[{role}]: {content}\n"
CONVERSATION_SEPARATOR = "\n---\n\n"


def _format_user_profile(profile: dict | None) -> str:
    """Format user profile for inclusion in the system prompt."""
    if not profile:
        return ""
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
        for key, value in metadata.items():
            parts.append(f"- {key}: {value}")
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
    """Format recent conversation history for inclusion in the prompt.

    Keeps at most max_turns exchanges (user+assistant pairs) to avoid
    blowing up context size on a 7B model.
    """
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
    """Return (system_message, user_message).
    extra_system_instruction: optional project-specific behavior (e.g. role/context like vendedor).
    conversation_override: when set, use these {role, content} rows for the history block instead of conversation_history.
    client_system_prompt_prefix: prepended before the default RAG system template (e.g. WhatsApp persona).
    """
    project_name = project.get("name") or project.get("project_id", "unknown")
    profile_block = _format_user_profile(user_profile)

    # Resolve tone and size instructions
    config = llm_config or {}
    tone = config.get("tone_of_voice", "direct")
    size = config.get("message_size", "medium")
    tone_inst = TONE_MAP.get(tone, TONE_MAP["direct"])
    size_inst = SIZE_MAP.get(size, SIZE_MAP["medium"])

    system = SYSTEM_TEMPLATE.format(
        project_name=project_name,
        user_profile_block=profile_block,
        tone_instruction=tone_inst,
        size_instruction=size_inst,
    )
    if extra_system_instruction and extra_system_instruction.strip():
        system = system.rstrip() + "\n\n" + extra_system_instruction.strip() + "\n"
    if client_system_prompt_prefix and client_system_prompt_prefix.strip():
        system = client_system_prompt_prefix.strip() + "\n\n" + system

    summaries_text = _format_conversation_summaries(conversation_summaries or [])
    conv_source = conversation_override if conversation_override is not None else (conversation_history or [])
    conv_text = _format_conversation_history(conv_source)

    if not chunks:
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

    user = USER_TEMPLATE.format(
        conversation_summaries=summaries_text,
        conversation_history=conv_text,
        context=context,
        question=question,
    )
    return system, user
