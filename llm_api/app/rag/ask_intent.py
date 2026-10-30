"""Semantic cut for POST /ask: classify before RAG when project enables ask_intent."""
from __future__ import annotations

import logging
from typing import Any

from app.tasks.engine import PortError, chat_json, compact_json

logger = logging.getLogger(__name__)

KNOWLEDGE_KINDS = frozenset({"org_general", "user_system", "unknown"})

_CLASSIFY_SYSTEM = """You classify WhatsApp questions for a knowledge API. Reply with ONE JSON object only:
{
  "knowledge_kind": "org_general" | "user_system" | "unknown",
  "action": "<code from the closed list or null>",
  "action_payload": { } or null
}

Rules:
- org_general: facts about the organisation, how a programme works, public links the corpus can answer. action MUST be null.
- user_system: the person asks about THEIR status in the product (inscription, interest, "can you see if I'm registered?", completeness of THEIR record). Pick action from the closed list. Do NOT invent status in prose — the client will look it up.
- unknown: thanks, chitchat, no clear question, or nothing the API should answer. action MUST be null.
- Never invent an action code outside the closed list.
- action_payload may include event_name or event_id only if clearly inferable from the message or history; otherwise null.
"""


def action_codes(config: dict) -> list[str]:
    return [a["code"] for a in config.get("actions") or [] if isinstance(a, dict) and a.get("code")]


def build_classify_system(config: dict) -> str:
    lines = [_CLASSIFY_SYSTEM.strip(), "", "## Closed action list (use code exactly)"]
    for a in config.get("actions") or []:
        if not isinstance(a, dict) or not a.get("code"):
            continue
        lines.append(f"- {a['code']}: {a.get('meaning') or a['code']}")
    return "\n".join(lines)


def normalize_intent(raw: dict | None, config: dict) -> dict[str, Any]:
    """Validate model output against the closed list; coerce unsafe values to unknown."""
    allowed = set(action_codes(config))
    if not isinstance(raw, dict):
        return {"knowledge_kind": "unknown", "action": None, "action_payload": None}

    kind = raw.get("knowledge_kind")
    if kind not in KNOWLEDGE_KINDS:
        kind = "unknown"

    action = raw.get("action")
    if action == "" or action is False:
        action = None
    if isinstance(action, str):
        action = action.strip() or None

    payload = raw.get("action_payload")
    if payload is not None and not isinstance(payload, dict):
        payload = None
    if isinstance(payload, dict) and not payload:
        payload = None

    if kind == "org_general":
        return {"knowledge_kind": "org_general", "action": None, "action_payload": payload}
    if kind == "unknown":
        return {"knowledge_kind": "unknown", "action": None, "action_payload": None}
    # user_system
    if action not in allowed:
        return {"knowledge_kind": "unknown", "action": None, "action_payload": None}
    return {"knowledge_kind": "user_system", "action": action, "action_payload": payload}


def _validate_raw(obj: dict[str, Any], config: dict) -> list[str]:
    problems: list[str] = []
    kind = obj.get("knowledge_kind")
    if kind not in KNOWLEDGE_KINDS:
        problems.append("knowledge_kind inválido")
    action = obj.get("action")
    allowed = set(action_codes(config))
    if kind == "user_system":
        if not isinstance(action, str) or action not in allowed:
            problems.append("action fora da lista fechada")
    elif action not in (None, ""):
        problems.append("action deve ser null quando knowledge_kind não é user_system")
    return problems


async def classify_ask_intent(
    project: dict,
    config: dict,
    *,
    question: str,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """Call compact JSON model; always returns a normalized intent dict."""
    hist_lines: list[str] = []
    for row in (history or [])[-6:]:
        role = row.get("role") or "user"
        content = (row.get("content") or row.get("text") or "")[:400]
        if content:
            hist_lines.append(f"{role}: {content}")
    user_payload = {
        "question": question,
        "recent_history": hist_lines or None,
    }
    try:
        raw, _model = await chat_json(
            project,
            system=build_classify_system(config),
            user=compact_json(user_payload),
            validate=lambda o: _validate_raw(o, config),
            kind="ask_intent",
            model_alias="compact",
            attempts=2,
        )
        return normalize_intent(raw, config)
    except PortError as exc:
        logger.warning("ask_intent classify failed (%s); falling back to unknown", exc)
        return {"knowledge_kind": "unknown", "action": None, "action_payload": None}
    except Exception:
        logger.exception("ask_intent classify unexpected error; falling back to unknown")
        return {"knowledge_kind": "unknown", "action": None, "action_payload": None}
