"""Answer signals: what the service knows about an answer, not what the model says about it.

The model's own confidence is an opinion (seen high on answers people rated bad). These come
from the pipeline: how close the best passage was, how many passed the threshold, whether the
sanitizer or a guard changed the text, whether the prompt neared the context window, how
much of the answer the passages back up (`grounding`, links outside the passages) and one
0–1 number built only from these (`answer_confidence`, recipe `confidence_basis`).
Additive in the API (`signals`): clients that do not read it are unaffected.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

CONFIDENCE_BASIS = "signals-v1"

_URL = re.compile(r"https?://[^\s)>\]\"']+", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]{4,}")
# Frequent pt-BR words of 4+ letters that say nothing about the content.
_STOP = frozenset(
    "para pelo pela pelos pelas como mais mas muito muita isso esse essa este esta estas estes "
    "aqui voce voces vamos pode podem fazer temos quando onde qual quais sobre entre depois "
    "antes ainda tambem cada todo toda todos todas outro outra seja sera ser sao estao esta "
    "nosso nossa nossos nossas seu sua seus suas dele dela algum alguma nada tudo bem sim nao "
    "obrigado obrigada favor ola tudo".split()
)


def best_distance(chunks: list[dict]) -> float | None:
    values = [float(c["distance"]) for c in chunks if c.get("distance") is not None]
    return round(min(values), 3) if values else None


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in t if not unicodedata.combining(ch))


def _norm_url(url: str) -> str:
    u = url.lower().rstrip(".,;:!?")
    u = re.sub(r"^https?://(www\.)?", "", u)
    return u.rstrip("/")


def grounding(chunks: list[dict], answer: str | None, prompt_text: str = "") -> dict[str, Any]:
    """How much of the answer the passages back up.

    `grounding`: share of the answer's content words (4+ letters, not stopwords, outside
    links) found in the passages; None without passages or content words.
    `unsupported_links`: links in the answer the model never saw — in no passage (text or
    `url`) and nowhere in the prompt (project instruction, profile, history).
    """
    text = answer or ""
    links = [_norm_url(u) for u in _URL.findall(text)]
    passages = " ".join(f"{c.get('snippet') or ''} {c.get('url') or ''}" for c in chunks)
    passages_folded = _fold(passages)
    seen = f"{passages} {prompt_text}"
    seen_links = {_norm_url(u) for u in _URL.findall(seen)}
    seen_folded = _fold(seen)
    unsupported = sorted({u for u in links if u not in seen_links and u not in seen_folded})
    words = [w for w in _WORD.findall(_fold(_URL.sub(" ", text))) if w not in _STOP]
    if not chunks or not words:
        share = None
    else:
        vocab = set(_WORD.findall(passages_folded))
        share = round(sum(1 for w in words if w in vocab) / len(words), 3)
    return {"grounding": share, "unsupported_links": unsupported[:5]}


def answer_confidence(out: dict[str, Any], distance_reference: float = 1.0) -> float | None:
    """0–1 from the signals only (never the model's own score). None without an answer.

    Mean of retrieval closeness (1 − best_distance / reference) and grounding, each 0 when
    missing; halved by a guard hit or a link no passage carries; ×0.8 near the context limit.
    """
    if not out.get("answer_chars"):
        return None
    d = out.get("best_distance")
    retrieval = max(0.0, min(1.0, 1 - d / distance_reference)) if d is not None and distance_reference > 0 else 0.0
    score = (retrieval + (out.get("grounding") or 0.0)) / 2
    if out.get("guard_hit") or out.get("unsupported_links"):
        score *= 0.5
    if out.get("near_ctx_limit"):
        score *= 0.8
    return round(score, 3)


def build(
    *,
    chunks: list[dict],
    answer: str | None,
    sanitize_hit: bool = False,
    guard_hit: bool = False,
    metrics: dict[str, Any] | None = None,
    distance_reference: float = 1.0,
    prompt_text: str = "",
    **extra: Any,
) -> dict[str, Any]:
    m = metrics or {}
    out: dict[str, Any] = {
        "best_distance": best_distance(chunks),
        "chunks_kept": len(chunks),
        "sanitize_hit": sanitize_hit,
        "guard_hit": guard_hit,
        "answer_chars": len((answer or "").strip()),
        "prompt_tokens": m.get("prompt_tokens"),
        "near_ctx_limit": m.get("near_ctx_limit"),
    }
    out.update(grounding(chunks, answer, prompt_text))
    out.update(extra)
    out["answer_confidence"] = answer_confidence(out, distance_reference)
    out["confidence_basis"] = CONFIDENCE_BASIS
    return out
