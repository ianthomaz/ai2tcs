"""POST /nabilvideomap/qualify-caption — nabilVideoMap cataloguing (sync Ollama + optional RAG)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import ollama
from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_token
from app.config import settings
from app import db as db_module
from app.models import (
    NabilLocationCandidate,
    NabilQualifyCaptionRequest,
    NabilQualifyCaptionResponse,
)
from app.registry import get_project, get_rag_policies
from app.rag.retrieve import retrieve

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nabilvideomap", tags=["nabilvideomap"])

NABIL_JOB_KIND = "nabil_qualify_caption"

LOCATION_ACCURACY = frozenset({"clear", "partial", "weak", "none", "conflicting"})
LOCATION_GRANULARITY = frozenset(
    {"neighborhood", "street", "poi", "zone", "citywide", "multiple", "unknown", "none"}
)

SUMMARY_MAX_CODEPOINTS = 140
_CAPTION_MAX_CHARS = 16000


class OllamaQualifyInfraError(Exception):
    """Ollama unreachable or hard failure (maps to HTTP 503)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _parse_json_object_from_content(content: str) -> dict[str, Any] | None:
    text = (content or "").strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        out = json.loads(m.group())
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None


def _normalize_enum_token(raw: object, allowed: frozenset[str]) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    return s if s in allowed else None


def _truncate_codepoints(s: str, max_cp: int) -> str:
    if max_cp <= 0:
        return ""
    out: list[str] = []
    n = 0
    for ch in s:
        if n >= max_cp:
            break
        out.append(ch)
        n += 1
    return "".join(out)


def _soft_clean_summary(s: str) -> str:
    """Trim; lightly reduce URLs/hashtags (best-effort)."""
    t = (s or "").strip()
    t = re.sub(r"https?://\S+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"#\w+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _coerce_location_confidence(raw: object) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    try:
        v = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if v < 0.0 or v > 1.0:
        return None
    return v


def _parse_candidates_raw(raw: object) -> tuple[list[dict[str, Any]], str]:
    """
    Normalize model output to a list of dicts.
    Returns (candidates, extra_note) where extra_note is non-empty if repair/drop happened.
    """
    notes: list[str] = []
    if raw is None:
        return [], ""

    data: Any = raw
    if isinstance(raw, str):
        raw_s = raw.strip()
        if not raw_s:
            return [], ""
        try:
            data = json.loads(raw_s)
        except json.JSONDecodeError:
            notes.append("llm_location_candidates was invalid JSON string; normalized to [].")
            return [], " ".join(notes)

    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        notes.append("llm_location_candidates was not a list; normalized to [].")
        return [], " ".join(notes)

    out: list[dict[str, Any]] = []
    dropped = 0
    for item in data:
        if not isinstance(item, dict):
            dropped += 1
            continue
        label = item.get("label")
        kind = item.get("kind")
        if not isinstance(label, str) or not label.strip():
            dropped += 1
            continue
        kn = _normalize_enum_token(kind, LOCATION_GRANULARITY)
        if kn is None:
            dropped += 1
            continue
        conf = item.get("confidence")
        conf_f: float | None = None
        if conf is not None and conf != "":
            try:
                cf = float(conf)
                if 0.0 <= cf <= 1.0:
                    conf_f = cf
            except (TypeError, ValueError):
                pass
        out.append({"label": label.strip(), "kind": kn, "confidence": conf_f})

    if dropped:
        notes.append(f"Dropped {dropped} invalid candidate entr(y/ies).")
    return out, " ".join(notes).strip()


def _try_build_response(parsed: dict[str, Any]) -> tuple[NabilQualifyCaptionResponse | None, list[str]]:
    errs: list[str] = []

    acc = _normalize_enum_token(parsed.get("location_accuracy"), LOCATION_ACCURACY)
    if acc is None:
        errs.append("location_accuracy invalid or missing")

    gran = _normalize_enum_token(parsed.get("location_granularity"), LOCATION_GRANULARITY)
    if gran is None:
        errs.append("location_granularity invalid or missing")

    if errs:
        return None, errs

    loc_label = parsed.get("location_primary_label")
    primary_label = str(loc_label).strip() if loc_label is not None else ""

    cand_raw, cand_note = _parse_candidates_raw(parsed.get("llm_location_candidates"))
    candidates: list[NabilLocationCandidate] = []
    for c in cand_raw:
        candidates.append(
            NabilLocationCandidate(
                label=str(c.get("label", "")),
                kind=str(c.get("kind", "")),
                confidence=c.get("confidence"),
            )
        )

    amb = parsed.get("location_ambiguity_notes")
    ambiguity = str(amb).strip() if amb is not None else ""
    if cand_note:
        ambiguity = (ambiguity + " " + cand_note).strip() if ambiguity else cand_note

    loc_conf = _coerce_location_confidence(parsed.get("location_confidence"))

    def _s(key: str) -> str:
        v = parsed.get(key)
        return str(v).strip() if v is not None else ""

    theme_p = _s("theme_primary")
    theme_s = _s("theme_secondary")
    tags = _s("theme_tags")
    theme_notes = _s("llm_theme_notes")

    summary_raw = parsed.get("summary_140")
    summary = _soft_clean_summary(str(summary_raw) if summary_raw is not None else "")
    summary = _truncate_codepoints(summary, SUMMARY_MAX_CODEPOINTS)

    assert acc is not None and gran is not None
    return (
        NabilQualifyCaptionResponse(
            location_accuracy=acc,
            location_granularity=gran,
            location_primary_label=primary_label,
            llm_location_candidates=candidates,
            location_ambiguity_notes=ambiguity,
            location_confidence=loc_conf,
            theme_primary=theme_p,
            theme_secondary=theme_s,
            theme_tags=tags,
            llm_theme_notes=theme_notes,
            summary_140=summary,
        ),
        [],
    )


def _system_prompt() -> str:
    return (
        "You are cataloguing Brazilian Portuguese Instagram captions about urban/political São Paulo. "
        "Reply with ONE JSON object only, no markdown fences. "
        "Use these exact English keys: "
        "location_accuracy, location_granularity, location_primary_label, llm_location_candidates, "
        "location_ambiguity_notes, location_confidence, theme_primary, theme_secondary, theme_tags, "
        "llm_theme_notes, summary_140. "
        "location_accuracy must be one of: clear, partial, weak, none, conflicting (lowercase). "
        "location_granularity must be one of: neighborhood, street, poi, zone, citywide, multiple, unknown, none. "
        "llm_location_candidates must be a JSON array of objects with keys label (string), kind (same enum as "
        "location_granularity), confidence (number 0-1 or omitted). "
        "location_confidence is a number from 0 to 1 or null if unknown. "
        "String fields may be empty strings when unknown. "
        "summary_140: at most 140 Unicode codepoints, plain language; avoid hashtags and bare URLs when possible. "
        "LANGUAGE (mandatory): Every free-text value MUST be in Brazilian Portuguese (pt-BR): "
        "location_primary_label, each llm_location_candidates[].label, location_ambiguity_notes, "
        "theme_primary, theme_secondary, theme_tags, llm_theme_notes, summary_140. "
        "Do not answer those fields in English. "
        "Exception: keep a proper noun or quoted phrase exactly as in the caption if it is not Portuguese. "
        "Only the JSON keys and the two enum fields above use the prescribed English tokens."
    )


def _user_prompt(caption: str, rag_block: str | None, repair_hint: str | None) -> str:
    parts = [f"Caption:\n{caption}"]
    if rag_block:
        parts.append(f"Indexed context (may be empty):\n{rag_block}")
    else:
        parts.append("Indexed context: (none — use caption only.)")
    if repair_hint:
        parts.append(f"Validation errors from your previous reply — fix and return ONLY valid JSON:\n{repair_hint}")
    parts.append(
        "Instrução final: todos os textos descritivos no JSON (temas, resumo, notas, rótulos de lugar) "
        "devem estar em português do Brasil (pt-BR), salvo nomes próprios citados na legenda."
    )
    return "\n\n".join(parts)


async def _build_rag_block(project_id: str, caption: str, project: dict) -> str:
    policies = get_rag_policies(project)
    top_k = int(policies.get("max_chunks_to_retrieve", 5))
    max_dist = float(policies.get("max_chunk_distance", 1.0))
    embed_model = "nomic-embed-text"
    if isinstance(project.get("config_json"), dict):
        embed_model = (project["config_json"] or {}).get("embedding_model") or embed_model

    chunks = await retrieve(project_id, caption, top_k=top_k, embedding_model=embed_model)
    kept = [c for c in chunks if c.get("distance") is None or float(c["distance"]) <= max_dist]
    if not kept:
        return (
            "(Nenhum trecho indexado acima do limiar de relevância para esta legenda. "
            "Responda apenas com base no texto da legenda; textos livres em português do Brasil.)"
        )

    parts: list[str] = []
    total = 0
    budget = max(500, int(settings.nabil_qualify_rag_context_max_chars))
    for c in kept:
        block = f"[{c.get('path', '')}]\n{c.get('snippet', '')}"
        if total + len(block) > budget:
            break
        parts.append(block)
        total += len(block)
    return "\n\n---\n\n".join(parts) if parts else (
        "(Nenhum trecho indexado acima do limiar de relevância para esta legenda. "
        "Responda apenas com base no texto da legenda; textos livres em português do Brasil.)"
    )


async def _ollama_chat(*, model: str, system: str, user: str, num_predict: int) -> str:
    def _call() -> dict:
        return ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            options={"temperature": 0.15, "num_predict": num_predict},
        )

    try:
        response = await asyncio.to_thread(_call)
    except Exception as e:
        logger.warning("Ollama qualify-caption failed: %s", e)
        raise OllamaQualifyInfraError(f"ollama_error: {e!s}") from e

    return (response.get("message") or {}).get("content") or ""


def _audit_model_alias(body: NabilQualifyCaptionRequest) -> str:
    m = (body.model or "smart").strip().lower()
    return m if m else "smart"


async def _audit_qualify_call(
    body: NabilQualifyCaptionRequest,
    *,
    ollama_model: str,
    status: str,
    response: NabilQualifyCaptionResponse | None = None,
    error_message: str | None = None,
) -> None:
    """Persist a terminal Job row for dashboard / stats (never queued; worker ignores)."""
    ctx = {
        "endpoint": "nabilvideomap/qualify-caption",
        "use_rag": body.use_rag,
        "ollama_model": ollama_model,
        "num_predict": settings.nabil_qualify_effective_num_predict(),
    }
    answer = response.model_dump_json() if response is not None else None
    await db_module.job_insert_terminal_audit(
        body.project_id,
        job_kind=NABIL_JOB_KIND,
        question=body.text,
        status=status,
        model_alias=_audit_model_alias(body),
        answer=answer,
        error_message=error_message,
        user_context=ctx,
    )


@router.post("/qualify-caption", response_model=NabilQualifyCaptionResponse)
async def qualify_caption(
    body: NabilQualifyCaptionRequest,
    _: None = Depends(require_token),
) -> NabilQualifyCaptionResponse:
    """
    Synchronous caption → structured JSON for nabilVideoMap SQLite ingest.
    Up to 3 model calls on validation retries; 422 if schema still invalid; 503 on Ollama/infra errors.
    """
    if len(body.text) > _CAPTION_MAX_CHARS:
        await _audit_qualify_call(
            body,
            ollama_model=settings.get_model_name(body.model, default_alias="smart"),
            status="failed",
            error_message=f"qualify_caption_text_too_long: max {_CAPTION_MAX_CHARS} characters",
        )
        raise HTTPException(
            status_code=422,
            detail=f"qualify_caption_text_too_long: max {_CAPTION_MAX_CHARS} characters",
        )

    proj = await get_project(body.project_id)
    if not proj:
        await _audit_qualify_call(
            body,
            ollama_model=settings.get_model_name(body.model, default_alias="smart"),
            status="failed",
            error_message="project not found",
        )
        raise HTTPException(status_code=404, detail="project not found")

    rag_block: str | None = None
    if body.use_rag:
        rag_block = await _build_rag_block(body.project_id, body.text, proj)

    model_name = settings.get_model_name(body.model, default_alias="smart")
    num_predict = settings.nabil_qualify_effective_num_predict()
    system = _system_prompt()

    last_errors: list[str] = []

    for attempt in range(3):
        repair = "; ".join(last_errors) if last_errors else None
        user_msg = _user_prompt(body.text, rag_block, repair)
        try:
            content = await _ollama_chat(
                model=model_name,
                system=system,
                user=user_msg,
                num_predict=num_predict,
            )
        except OllamaQualifyInfraError as e:
            await _audit_qualify_call(
                body,
                ollama_model=model_name,
                status="failed",
                error_message=e.message,
            )
            raise HTTPException(status_code=503, detail=e.message) from e

        parsed = _parse_json_object_from_content(content)
        if parsed is None:
            last_errors = ["json_parse_failed"]
            continue

        built, verr = _try_build_response(parsed)
        if built is not None:
            await _audit_qualify_call(body, ollama_model=model_name, status="done", response=built)
            return built
        last_errors = verr or ["validation_failed"]

    detail = "qualify_schema_retry_exhausted: " + "; ".join(last_errors)
    await _audit_qualify_call(
        body,
        ollama_model=model_name,
        status="failed",
        error_message=detail,
    )
    raise HTTPException(status_code=422, detail=detail)
