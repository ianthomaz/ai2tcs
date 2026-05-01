"""Parse /edu/chat LLM output: structured JSON for Chinese Learning UI or plain-text fallback."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*([\s\S]*?)\s*```\s*$", re.IGNORECASE)


@dataclass
class ParsedEduChat:
    """Result of parsing model output."""

    reply: str
    reply_structured: list[dict] | None
    full_reply_text: str | None


MAX_SEGMENTS = 24

_JSON_RETRY_USER = """Your previous reply was rejected: it must be ONE JSON object only (no markdown), valid schema, every segment with non-empty hanzi, pinyin with tone marks (not numbers), and non-empty translation.pt (Portuguese). Keys translation.en and translation.es may be "".
Schema:
{"reply_structured":[{"hanzi":"...","pinyin":"...","translation":{"pt":"...","en":"","es":""}}],"full_reply_text":"..."}
Reply again to the student's last question following that schema."""


def json_retry_user_message() -> str:
    """User-role message for a single repair attempt after invalid model output."""
    return _JSON_RETRY_USER


def structured_reply_valid(parsed: ParsedEduChat) -> bool:
    """True if parsed output is acceptable for /edu/chat (structured + schema)."""
    if not parsed.reply_structured or not parsed.full_reply_text:
        return False
    if len(parsed.reply_structured) > MAX_SEGMENTS:
        return False
    for seg in parsed.reply_structured:
        if not isinstance(seg, dict):
            return False
        hanzi = str(seg.get("hanzi", "") or "").strip()
        pinyin = str(seg.get("pinyin", "") or "").strip()
        trans = seg.get("translation")
        if not hanzi or not pinyin:
            return False
        if isinstance(trans, dict):
            pt = str(trans.get("pt", "") or "").strip()
        else:
            pt = ""
        if not pt:
            return False
    return True


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    m = _JSON_FENCE.match(text)
    if m:
        return m.group(1).strip()
    return text


def _normalize_translation(raw: object) -> dict[str, str]:
    if isinstance(raw, dict):
        return {
            "pt": str(raw.get("pt", "") or "").strip(),
            "en": str(raw.get("en", "") or "").strip(),
            "es": str(raw.get("es", "") or "").strip(),
        }
    if isinstance(raw, str) and raw.strip():
        s = raw.strip()
        return {"pt": s, "en": s, "es": s}
    return {"pt": "", "en": "", "es": ""}


def parse_edu_chat_response(raw: str) -> ParsedEduChat:
    """Try to parse JSON with reply_structured + full_reply_text; else plain-text fallback."""
    text = (raw or "").strip()
    if not text:
        return ParsedEduChat(reply="", reply_structured=None, full_reply_text=None)

    candidate = _strip_markdown_fence(text)
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return ParsedEduChat(reply=text, reply_structured=None, full_reply_text=None)

    if not isinstance(data, dict):
        return ParsedEduChat(reply=text, reply_structured=None, full_reply_text=None)

    segments_raw = data.get("reply_structured")
    if not isinstance(segments_raw, list) or not segments_raw:
        return ParsedEduChat(reply=text, reply_structured=None, full_reply_text=None)

    structured: list[dict] = []
    for item in segments_raw:
        if not isinstance(item, dict):
            continue
        hanzi = str(item.get("hanzi", "") or "").strip()
        if not hanzi:
            continue
        pinyin = str(item.get("pinyin", "") or "").strip()
        translation = _normalize_translation(item.get("translation"))
        structured.append(
            {
                "hanzi": hanzi,
                "pinyin": pinyin,
                "translation": translation,
            }
        )

    if not structured:
        return ParsedEduChat(reply=text, reply_structured=None, full_reply_text=None)

    full_reply_text = data.get("full_reply_text")
    if isinstance(full_reply_text, str) and full_reply_text.strip():
        full_reply_text = full_reply_text.strip()
    else:
        full_reply_text = "".join(s["hanzi"] for s in structured)

    # Plain reply for legacy clients: prefer concatenated hanzi
    reply_plain = full_reply_text
    return ParsedEduChat(
        reply=reply_plain,
        reply_structured=structured,
        full_reply_text=full_reply_text,
    )
