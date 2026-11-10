"""Pure rules of the ratings door: what an item is, what it proposes, which examples fit.

Nothing here touches the database or the model, so every rule is testable as is.
"""
from __future__ import annotations

import re
from typing import Any

from app.llm.signals import STOPWORDS, URL_RE, WORD_RE, fold, norm_url

RATINGS = ("stop", "bad", "good", "great")
REJECTED = ("stop", "bad")
MAX_ITEMS = 200
_TEXT_MAX = 4000
_REASON_MAX = 500
_SOURCE_REF = re.compile(r"^[A-Za-z0-9:._-]{1,120}$")
_TERM_MIN = 3
_TERM_MAX = 200
EXAMPLE_MIN_OVERLAP = 0.25


class ItemError(ValueError):
    pass


def _text(v: Any, limit: int) -> str:
    return v.strip()[:limit] if isinstance(v, str) else ""


def normalize_item(raw: Any) -> dict[str, Any]:
    """One rating as the door stores it. `rating: null` means «the person took the rating back»."""
    if not isinstance(raw, dict):
        raise ItemError("cada item é um objeto")
    ref = raw.get("source_ref")
    if not isinstance(ref, str) or not _SOURCE_REF.match(ref):
        raise ItemError("source_ref: até 120 caracteres de [A-Za-z0-9:._-]")
    rating = raw.get("rating")
    if rating is None:
        return {"source_ref": ref, "rating": None}
    if rating not in RATINGS:
        raise ItemError(f"rating: um de {', '.join(RATINGS)} ou null")
    question, answer = _text(raw.get("question"), _TEXT_MAX), _text(raw.get("answer"), _TEXT_MAX)
    if not question or not answer:
        raise ItemError("question e answer são obrigatórios com rating")
    signals = raw.get("signals") if isinstance(raw.get("signals"), dict) else None
    terms = raw.get("suggested_terms") if isinstance(raw.get("suggested_terms"), list) else []
    return {
        "source_ref": ref,
        "rating": rating,
        "question": question,
        "answer": answer,
        "reason": _text(raw.get("reason"), _REASON_MAX) or None,
        "signals": signals,
        "rated_at": raw.get("rated_at") if isinstance(raw.get("rated_at"), str) else None,
        "suggested_terms": [t.strip()[:_TERM_MAX] for t in terms if isinstance(t, str) and len(t.strip()) >= _TERM_MIN],
    }


def proposals_for(item: dict[str, Any]) -> list[tuple[str, str]]:
    """Forbidden terms a rejected answer suggests (kind, value). Good answers suggest nothing.

    - links the model never saw (`signals.unsupported_links`), or every link of the answer when
      the reason talks about a link and the client sent no signals;
    - terms the person typed (`suggested_terms`).
    """
    if item.get("rating") not in REJECTED:
        return []
    out: list[str] = []
    sig = item.get("signals") or {}
    unsupported = sig.get("unsupported_links") if isinstance(sig, dict) else None
    if isinstance(unsupported, list):
        out += [norm_url(u) for u in unsupported if isinstance(u, str) and u.strip()]
    elif "link" in fold(item.get("reason") or ""):
        out += [norm_url(u) for u in URL_RE.findall(item.get("answer") or "")]
    out += item.get("suggested_terms") or []
    seen: list[tuple[str, str]] = []
    for v in out:
        v = v.strip()
        if len(v) >= _TERM_MIN and ("forbidden_term", v) not in seen:
            seen.append(("forbidden_term", v))
    return seen


def _content_words(text: str) -> set[str]:
    return {w for w in WORD_RE.findall(fold(URL_RE.sub(" ", text or ""))) if w not in STOPWORDS}


def pick_examples(question: str, rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Approved answers whose question shares the most content words with this one.

    Overlap = shared words / words of the new question; below EXAMPLE_MIN_OVERLAP nothing fits.
    """
    if limit <= 0:
        return []
    asked = _content_words(question)
    if not asked:
        return []
    scored = []
    for r in rows:
        overlap = len(asked & _content_words(r.get("question") or "")) / len(asked)
        if overlap >= EXAMPLE_MIN_OVERLAP:
            scored.append((overlap, r))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [r for _, r in scored[:limit]]


def examples_block(examples: list[dict[str, Any]]) -> str:
    if not examples:
        return ""
    lines = [
        "Respostas que pessoas do projeto aprovaram para perguntas parecidas. Siga o tom e o "
        "tamanho; fatos, datas e links só valem se os trechos desta pergunta confirmarem."
    ]
    for e in examples:
        lines.append(f"Pergunta: {e['question']}\nResposta aprovada: {e['answer']}")
    return "\n\n".join(lines)


def add_forbidden_term(config_json: dict | None, term: str) -> dict:
    """Project config with `term` in policies.forbidden_terms (same list the answer guard reads)."""
    cfg = dict(config_json or {})
    policies = dict(cfg.get("policies") or {})
    terms = [t for t in (policies.get("forbidden_terms") or []) if isinstance(t, str)]
    if term.lower() not in {t.lower() for t in terms}:
        terms.append(term)
    policies["forbidden_terms"] = terms
    cfg["policies"] = policies
    return cfg
