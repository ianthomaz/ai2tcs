"""Post-generation guards against cross-project bleed in LLM answers."""
from __future__ import annotations

import logging
import re

from app.rag.prompt import get_no_answer_fallback, get_prompt_profile

logger = logging.getLogger(__name__)

# Known sales bleed patterns (estudosMobi-style fallbacks on non-Mobi projects).
_CROSS_PROJECT_BLEED_PATTERNS = (
    re.compile(r"\bmobi\s+cuida\b", re.IGNORECASE),
    re.compile(r"\bmobicontabil\b", re.IGNORECASE),
    re.compile(r"a\s+mobi\s+cuida", re.IGNORECASE),
    re.compile(r"fale\s+com\s+a\s+equipe\s+pelo\s+whatsapp", re.IGNORECASE),
)

_FORBIDDEN_TERMS_CREATIVE = ("mobi", "mobicontabil", "mobicontabil.com.br")


def _has_cross_project_bleed(answer: str, project_id: str, prompt_profile: str) -> bool:
    if prompt_profile != "creative" or project_id == "estudosmobi":
        return False
    low = answer.lower()
    if any(term in low for term in _FORBIDDEN_TERMS_CREATIVE):
        return True
    return any(p.search(answer) for p in _CROSS_PROJECT_BLEED_PATTERNS)


def guard_answer_for_profile(answer: str, project: dict) -> str:
    """Replace answers that bleed another project's sales voice with project fallback."""
    if not answer or not answer.strip():
        return answer
    project_id = (project.get("project_id") or "").strip()
    prompt_profile = get_prompt_profile(project)
    if not _has_cross_project_bleed(answer, project_id, prompt_profile):
        return answer
    fallback = get_no_answer_fallback(project)
    logger.info(
        "cross_project_bleed_corrected project=%s profile=%s len=%d",
        project_id,
        prompt_profile,
        len(answer),
    )
    return fallback
