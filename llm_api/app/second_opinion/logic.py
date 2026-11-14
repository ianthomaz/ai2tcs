"""Pure rules of the second opinion door: the case a project sends, the teacher's answer."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CHANNELS = ("whatsapp", "email", "ticket", "form", "chat", "other")
# Mesma escala do painel do projeto (⛔ 👎 👍 👍👍): a nota do professor e a humana se comparam.
RATINGS = ("stop", "bad", "good", "great")
PATHS = ("right", "wrong")
INTENTS = ("action", "question", "chitchat", "other")
REPLY_KINDS = ("acknowledge_done", "point_to_ui", "direct_answer", "silence", "escalate_human")

_SOURCE_REF = re.compile(r"^[A-Za-z0-9:._-]{1,120}$")
# Who wrote, as the project knows them (Bike Anjo: user_id). Never a phone or e-mail.
_SUBJECT_REF = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SLUG = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_TEXT_MAX = 4000
_FACTS_MAX_BYTES = 4000
_PROMPT = Path(__file__).with_name("teacher_prompt.md")
# The projects' folders (docs/27): house rules in _shared/, each project's diretrizes/.
LIBRARY_ROOT = Path(__file__).resolve().parents[2] / "project_library"
_GUIDANCE_MAX = 8000

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s().-]?){10,13}(?!\d)")


class CaseError(ValueError):
    pass


def redact(text: str) -> str:
    """The case goes to a market model: e-mail, CPF and phone-like numbers leave as tags."""
    text = _EMAIL.sub("[contato]", text)
    text = _CPF.sub("[documento]", text)
    return _PHONE.sub("[contato]", text)


def _text(v: Any, limit: int = _TEXT_MAX) -> str:
    return redact(v.strip())[:limit] if isinstance(v, str) else ""


def _small_object(v: Any, name: str) -> dict:
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise CaseError(f"{name}: objeto")
    if len(json.dumps(v, ensure_ascii=False).encode()) > _FACTS_MAX_BYTES:
        raise CaseError(f"{name}: até {_FACTS_MAX_BYTES} bytes")
    return json.loads(redact(json.dumps(v, ensure_ascii=False)))


def normalize_case(raw: Any) -> dict[str, Any]:
    """The case as the queue stores it and the teacher reads it. Generic: any project, any channel.

    `case_facts` and `context` belong to the project (the service does not know their keys);
    `allowed_actions` is the project's closed list — the teacher may only suggest from it.
    """
    if not isinstance(raw, dict):
        raise CaseError("o corpo é um objeto")
    ref = raw.get("source_ref")
    if not isinstance(ref, str) or not _SOURCE_REF.match(ref):
        raise CaseError("source_ref: até 120 caracteres de [A-Za-z0-9:._-]")
    channel = raw.get("channel")
    if channel not in CHANNELS:
        raise CaseError(f"channel: um de {', '.join(CHANNELS)}")
    kind = raw.get("case_kind")
    if kind is not None and (not isinstance(kind, str) or not _SLUG.match(kind)):
        raise CaseError("case_kind: slug em minúsculas (ex.: campaign_reply)")
    incoming = _text(raw.get("incoming_text"))
    if not incoming:
        raise CaseError("incoming_text é obrigatório")
    local = raw.get("local_answer") if isinstance(raw.get("local_answer"), dict) else {}
    conf = local.get("confidence")
    actions = raw.get("allowed_actions") or []
    if not isinstance(actions, list) or not all(isinstance(a, str) and _SLUG.match(a) for a in actions):
        raise CaseError("allowed_actions: lista de slugs")
    history = raw.get("history") or []
    if not isinstance(history, list):
        raise CaseError("history: lista")
    subject = raw.get("subject_ref")
    if subject is not None and (not isinstance(subject, str) or not _SUBJECT_REF.match(subject) or subject.isdigit()):
        raise CaseError("subject_ref: o id da pessoa no projeto, até 64 caracteres de [A-Za-z0-9_-]; nunca telefone")
    return {
        "source_ref": ref,
        "subject_ref": subject,
        "channel": channel,
        "case_kind": kind,
        "incoming_text": incoming,
        "history": [
            {"role": "assistant" if h.get("role") == "assistant" else "user", "content": _text(h.get("content"), 600)}
            for h in history[-6:]
            if isinstance(h, dict) and _text(h.get("content"), 600)
        ],
        "local_answer": {
            "text": _text(local.get("text")) or None,
            "route": _text(local.get("route"), 80) or None,
            "confidence": float(conf) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else None,
            "signals": _small_object(local.get("signals"), "local_answer.signals") or None,
        },
        "case_facts": _small_object(raw.get("case_facts"), "case_facts"),
        "context": _small_object(raw.get("context"), "context"),
        "allowed_actions": sorted(set(actions)),
    }


def library_guidance(project_id: str | None, root: Path | None = None) -> str:
    """House rules, the rules this project declines (its manifest) and its diretrizes/, as one
    text for the teacher. The agent reads them here; it gets no folder on disk."""
    base = root or LIBRARY_ROOT
    parts: list[str] = []
    house = base / "_shared" / "regras-da-casa.md"
    if house.is_file():
        parts.append(house.read_text(encoding="utf-8").strip())
    folder = base / project_id if project_id and _SLUG.match(project_id) else None
    if folder and folder.is_dir():
        manifest = folder / "README.md"
        if manifest.is_file():
            text = manifest.read_text(encoding="utf-8")
            mark = "## Regras da casa que este projeto não segue"
            if mark in text:
                parts.append(mark + text.split(mark, 1)[1].split("\n## ", 1)[0].rstrip())
        for f in sorted((folder / "diretrizes").glob("*.md")):
            parts.append(f"Diretriz do projeto ({f.name}):\n" + f.read_text(encoding="utf-8").strip())
    out = "\n\n".join(p for p in parts if p)
    return out[:_GUIDANCE_MAX]


def build_prompt(case: dict[str, Any], teacher_notes: str | None = None, project_id: str | None = None) -> str:
    """What the agent reads: the fixed rules, the house rules and the project's diretrizes
    (project_library), the project's notes (tone, limits) and the case."""
    parts = [_PROMPT.read_text(encoding="utf-8").strip()]
    guidance = library_guidance(project_id)
    if guidance:
        parts.append("REGRAS DA CASA E DIRETRIZES DO PROJETO (valem para julgar e para a resposta sugerida):\n" + guidance)
    if teacher_notes and teacher_notes.strip():
        parts.append("Notas do projeto (tom e limites):\n" + teacher_notes.strip()[:2000])
    # subject_ref is for the worker's read-only check, never for the teacher.
    shown = {k: v for k, v in case.items() if k != "subject_ref"}
    parts.append("CASO:\n" + json.dumps(shown, ensure_ascii=False, indent=1))
    return "\n\n".join(parts)


def extract_json(text: str) -> dict[str, Any] | None:
    """First JSON object in the agent's output (agents sometimes wrap it in prose or fences)."""
    if not isinstance(text, str):
        return None
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                esc = (ch == "\\") and not esc
                if ch == '"' and not esc:
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                        return obj if isinstance(obj, dict) else None
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def normalize_opinion(raw: Any, case: dict[str, Any]) -> dict[str, Any]:
    """The teacher's answer, checked against the closed lists. Raises CaseError when it does not fit."""
    if not isinstance(raw, dict):
        raise CaseError("resposta do professor não é um objeto")
    for key, allowed in (
        ("local_answer_rating", RATINGS), ("local_answer_path", PATHS), ("intent", INTENTS), ("reply_kind", REPLY_KINDS),
    ):
        if raw.get(key) not in allowed:
            raise CaseError(f"{key}: um de {', '.join(allowed)}")
    reply = raw.get("suggested_reply")
    if not isinstance(reply, str):
        raise CaseError("suggested_reply: texto")
    if raw["reply_kind"] == "silence":
        reply = ""
    action = raw.get("suggested_action")
    out_action = None
    if isinstance(action, dict) and action.get("type") not in (None, "", "none"):
        if action["type"] not in case.get("allowed_actions", []):
            raise CaseError(f"suggested_action.type fora da lista do caso: {action['type']!r}")
        out_action = {
            "type": action["type"],
            "already_applied": bool(action.get("already_applied")),
            "why": _text(action.get("why"), 300) or None,
        }
    conf = raw.get("confidence")
    strs = lambda v: [s.strip()[:200] for s in v if isinstance(s, str) and s.strip()][:20] if isinstance(v, list) else []  # noqa: E731
    return {
        "local_answer_rating": raw["local_answer_rating"],
        "local_answer_path": raw["local_answer_path"],
        "path_note": _text(raw.get("path_note"), 500),
        "intent": raw["intent"],
        "reply_kind": raw["reply_kind"],
        "suggested_reply": reply.strip()[:1500],
        "suggested_action": out_action,
        "checked": strs(raw.get("checked")),
        "missing": strs(raw.get("missing")),
        "confidence": min(1.0, max(0.0, float(conf))) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else None,
        "knowledge_gap": _text(raw.get("knowledge_gap"), 500) or None,
    }


def project_settings(project: dict | None) -> dict[str, Any]:
    """config_json.second_opinion of a project: {enabled, teacher_notes}. Off unless enabled is true."""
    cfg = (project or {}).get("config_json")
    raw = cfg.get("second_opinion") if isinstance(cfg, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    notes = raw.get("teacher_notes")
    return {"enabled": raw.get("enabled") is True, "teacher_notes": notes if isinstance(notes, str) else None}
