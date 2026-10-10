"""POST /feedbackTriage — scores, tags and urgency for Bike Anjo ops text. No RAG.

Contract: contracts/bikeanjo/feedback-triage.schema.json · prompt triage-v1.
Sources: EBA feedback, cyclist history, support ticket (contact form, bug reports).
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.bikeanjo.common import (
    PortError,
    chat_json,
    clamp_confidence,
    compact_json,
    fold,
    grave_hits,
    load_prompt,
)

PROMPT_VERSION = "triage-v2"

TAGS = ("grave", "construtiva", "elogio_pessoa", "elogio_geral", "bug_sistema", "logistica", "aprendizado", "outro")
URGENCIES = ("none", "watch", "urgent")
SCORE_KEYS = ("text_quality", "information_value", "answer_solidity")
ANCHOR_MAX = 160
THEME_MAX = 40
NAMED_PEOPLE_MAX = 5

_MARKER_RE = re.compile(r"\[(contato|documento)\]", re.IGNORECASE)
# Rule 9 of triage-v2: adult subject, text says the child is the one who took the workshop.
# Matched on fold(text). Recall over precision — the outcome is only "a person reviews it".
_CHILD_MENTION = re.compile(r"\b(meu|minha|nosso|nossa) (filh[oa]s?|net[oa]s?|crianca|menin[oa])\b")
_CHILD_DID = re.compile(r"\b(fez|fizeram|aprendeu|aprenderam|participou|pedalou|conseguiu|adorou|amou)\b")
MINOR_MISMATCH_CONFIDENCE = 0.5
MINOR_MISMATCH_THEME = "texto sobre o menor, sujeito adulto"


class Subject(BaseModel):
    model_config = ConfigDict(extra="ignore")
    subject_id: str | None = None  # LCCCN account or D_… dependent; null for a ticket without account
    user_id: str | None = None
    dependent_id: int | None = None

    def kind(self) -> Literal["adult", "dependent", "none"]:
        """What the model may know about the subject — never the id itself."""
        sid = (self.subject_id or "").strip()
        if sid.startswith("D_") or self.dependent_id is not None:
            return "dependent"
        if sid or (self.user_id or "").strip():
            return "adult"
        return "none"


class FeedbackTriageRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source: Literal["eba-feedback", "historico-ciclista", "support_ticket"]
    submission_id: str
    subject: Subject = Subject()
    event_id: str | None = None
    locale: str = "pt-BR"
    fields: dict[str, str]
    scales: dict[str, Any] = {}

    @field_validator("submission_id", mode="before")
    @classmethod
    def _id_as_str(cls, v: object) -> object:
        return str(v) if isinstance(v, int) else v

    @field_validator("fields")
    @classmethod
    def _non_empty_fields(cls, v: dict[str, str]) -> dict[str, str]:
        kept = {k: s.strip() for k, s in v.items() if isinstance(s, str) and s.strip()}
        if not kept:
            raise ValueError("precisa de ao menos um texto não vazio")
        return kept


def _scales(raw: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for k, v in raw.items():
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 5:
            out[k] = n
    return out


def system_prompt() -> str:
    return (
        load_prompt("feedback-triage-v2.md")
        + "\n\n"
        + load_prompt("feedback-triage-fewshots.md")
        + "\n\nResponda com UM objeto JSON com as chaves scores, tags, urgency, anchor_quote, "
        "named_people, theme_free, confidence — nada fora dele."
    )


def user_prompt(req: FeedbackTriageRequest) -> str:
    # Only what the classification needs: no submission, person or event ids. The subject
    # goes as its kind (adult / dependent / none) — rule 9 of triage-v2 needs it.
    return compact_json(
        {
            "source": req.source,
            "subject": {"kind": req.subject.kind()},
            "fields": req.fields,
            "scales": _scales(req.scales),
        }
    )


def minor_text_on_adult_subject(req: FeedbackTriageRequest) -> bool:
    if req.subject.kind() != "adult":
        return False
    text = fold(" ".join(req.fields.values()))
    return bool(_CHILD_MENTION.search(text) and _CHILD_DID.search(text))


def validate_model_output(obj: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    scores = obj.get("scores")
    if not isinstance(scores, dict):
        return ["scores ausente"]
    for k in SCORE_KEYS:
        if _score(scores.get(k)) is None:
            problems.append(f"scores.{k} precisa ser inteiro 1-5")
    return problems


def _score(v: object) -> int | None:
    try:
        n = int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 5 else None


def _strip_markers(s: str) -> str:
    return re.sub(r"\s+", " ", _MARKER_RE.sub("", s)).strip(" .,;:-")


def _truncate_words(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    cut = s[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit // 2 else cut).rstrip(" .,;:-")


def _anchor(raw: object, fields: dict[str, str], warnings: list[str]) -> str:
    """Near-literal quote from some field, never carrying [contato]/[documento]."""
    haystack = [fold(_strip_markers(v)) for v in fields.values()]
    cand = _truncate_words(_strip_markers(str(raw or "")), ANCHOR_MAX)
    if cand and any(fold(cand) in h for h in haystack):
        return cand
    longest = max(fields.values(), key=len)
    first_sentence = re.split(r"(?<=[.!?])\s", _strip_markers(longest), maxsplit=1)[0]
    if cand:
        warnings.append("anchor_quote_replaced")
    return _truncate_words(first_sentence, ANCHOR_MAX)


def postprocess(obj: dict[str, Any], req: FeedbackTriageRequest, model: str) -> dict[str, Any]:
    warnings: list[str] = []
    text_all = fold(" ".join(req.fields.values()))

    tags: list[str] = []
    for t in obj.get("tags") or []:
        tv = str(t).strip().lower()
        if tv in TAGS and tv not in tags:
            tags.append(tv)
        elif tv not in TAGS:
            warnings.append(f"tag_dropped:{tv[:30]}")

    urgency = str(obj.get("urgency") or "").strip().lower()
    if urgency not in URGENCIES:
        warnings.append("urgency_defaulted")
        urgency = "none"

    if "grave" not in tags and grave_hits(*req.fields.values()):
        tags.insert(0, "grave")
        warnings.append("grave_by_keyword")
    if "grave" in tags:
        urgency = "urgent"

    named: list[str] = []
    for p in obj.get("named_people") or []:
        name = str(p or "").strip()
        if name and fold(name) in text_all and name not in named:
            named.append(name)
        elif name:
            warnings.append("named_people_dropped")
    named = named[:NAMED_PEOPLE_MAX]

    if "elogio_pessoa" in tags and not named:
        tags.remove("elogio_pessoa")
        if "elogio_geral" not in tags:
            tags.append("elogio_geral")
        warnings.append("elogio_pessoa_without_name")

    scores_raw = obj.get("scores") or {}
    scores = {k: _score(scores_raw.get(k)) or 3 for k in SCORE_KEYS}

    theme = obj.get("theme_free")
    theme_free = _truncate_words(str(theme).strip(), THEME_MAX) if isinstance(theme, str) and theme.strip() else None
    confidence = clamp_confidence(obj.get("confidence"))

    if minor_text_on_adult_subject(req):
        if urgency == "none":
            urgency = "watch"
        confidence = min(confidence, MINOR_MISMATCH_CONFIDENCE)
        theme_free = theme_free or MINOR_MISMATCH_THEME
        warnings.append("subject_minor_mismatch")

    return {
        "status": "ok",
        "scores": scores,
        "tags": tags,
        "urgency": urgency,
        "anchor_quote": _anchor(obj.get("anchor_quote"), req.fields, warnings),
        "named_people": named,
        "theme_free": theme_free,
        "confidence": confidence,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "warnings": sorted(set(warnings)),
    }


async def run(req: FeedbackTriageRequest, project: dict | None) -> dict[str, Any]:
    if req.locale != "pt-BR":
        raise PortError("invalid_request", "locale suportado: pt-BR")
    obj, model = await chat_json(
        project,
        system=system_prompt(),
        user=user_prompt(req),
        validate=validate_model_output,
    )
    return postprocess(obj, req, model)


def audit_summary(result: dict[str, Any]) -> dict[str, Any]:
    """What the Job row keeps: labels only — no quote, no names, no text of the person."""
    return {k: result.get(k) for k in ("scores", "tags", "urgency", "confidence", "prompt_version")}
