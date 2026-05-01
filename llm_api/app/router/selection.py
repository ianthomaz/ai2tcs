"""Heuristics for specialist LLM selection when triage escalates."""

def select_specialist_alias(
    task_type: str | None = None,
    prompt: str | None = None,
    has_retrieve_context: bool = False,
    context_token_count: int = 0,
    prefer_smart: bool = False,
) -> str:
    """Heuristic selection of the best LLM alias for a given task.

    Rules based on 10-historical-router-plan.md § 4.2.
    """
    p = (prompt or "").lower()
    t = (task_type or "").lower()

    # 1. Reasoning: logic, calculations, explicit "why", step-by-step (avoid bare "porque" = "because")
    reasoning_markers = (
        "porquê",
        "por quê",
        "por que ",  # "why" two words; trailing space avoids matching "porque" (because)
        "por que?",
        "porque será",
        "calcula",
        "demonstra",
        "passo a passo",
        "prova por",
        "lógica formal",
    )
    if t == "reasoning" or any(m in p for m in reasoning_markers):
        return "reasoner"

    # 2. Extract / Classification (avoid lone brackets — too noisy in PT chat)
    extract_markers = ("json", "extrai", "classifica", "preencha os campos", "formato json")
    if t in ("extract", "classification") or any(m in p for m in extract_markers):
        return "compact"

    # 3. Smart: Deep RAG, large context, or explicit preference
    if prefer_smart or t == "rag_deep" or context_token_count > 2000:
        return "smart"

    # Default to smart for most RAG/general questions if not trivial
    return "smart"
