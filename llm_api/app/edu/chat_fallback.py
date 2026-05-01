"""Structured fallback when the model fails JSON/schema after retry (keeps UI toggles working)."""

from __future__ import annotations

from app.edu.structured_reply import ParsedEduChat

# Single segment: polite Chinese + PT explanation for the learner.
_FALLBACK_SEGMENTS: list[dict] = [
    {
        "hanzi": "请稍后再试。",
        "pinyin": "Qǐng shāohòu zài shì.",
        "translation": {
            "pt": "Não consegui preparar a resposta agora. Pergunta de novo em instantes.",
            "en": "",
            "es": "",
        },
    }
]

_FALLBACK_FULL = "".join(s["hanzi"] for s in _FALLBACK_SEGMENTS)


def fallback_structured_parse() -> ParsedEduChat:
    """Always-valid ParsedEduChat for API responses when the model output fails validation."""
    return ParsedEduChat(
        reply=_FALLBACK_FULL,
        reply_structured=[dict(s) for s in _FALLBACK_SEGMENTS],
        full_reply_text=_FALLBACK_FULL,
    )
