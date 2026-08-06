"""POST /audio/transcribe and POST /audio/ask — async local STT (Whisper) + optional RAG."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app import db as db_module
from app.auth import require_token
from app.config import settings
from app.models import AudioJobResponse
from app.registry import get_project
from app.stt.audio_validate import validate_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audio", tags=["audio"])


def _parse_json_object(raw: str | None, field_name: str) -> dict | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        val = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"invalid JSON in {field_name}: {e}") from e
    if not isinstance(val, dict):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a JSON object")
    return val


def _parse_history(raw: str | None) -> list[dict] | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        val = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"invalid JSON in history_json: {e}") from e
    if not isinstance(val, list):
        raise HTTPException(status_code=400, detail="history_json must be a JSON array")
    out: list[dict] = []
    for row in val:
        if not isinstance(row, dict):
            continue
        role = row.get("role") or "user"
        content = row.get("content") or row.get("text") or ""
        out.append({"role": role, "content": str(content)[:2000]})
    return out or None


def _build_user_context_for_ask(
    *,
    user_context_json: str | None,
    history_json: str | None,
    system_prompt: str | None,
    model: str | None,
    stt_language: str | None,
) -> dict | None:
    merged: dict = {}
    uc = _parse_json_object(user_context_json, "user_context_json")
    if uc:
        merged.update(uc)
    hist = _parse_history(history_json)
    if hist:
        merged["__llm_history"] = hist
    if system_prompt and system_prompt.strip():
        merged["__llm_system_prompt"] = system_prompt.strip()
    if model and model.strip():
        merged["__llm_model"] = model.strip()
    if stt_language and stt_language.strip():
        merged["__stt_language"] = stt_language.strip()
    return merged if merged else None


def _stt_only_context(stt_language: str | None) -> dict | None:
    if not stt_language or not stt_language.strip():
        return None
    return {"__stt_language": stt_language.strip()}


async def _enqueue_audio_job(
    *,
    project_id: str,
    file: UploadFile,
    user_id: str | None,
    job_kind: str,
    user_context: dict | None,
) -> AudioJobResponse:
    if not settings.whisper_enabled:
        raise HTTPException(status_code=503, detail="Whisper STT is disabled (WHISPER_ENABLED=false)")

    project = await get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")

    try:
        raw, ext = await validate_upload(file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    job_id = str(uuid4())
    tmp_dir = settings.data_dir / settings.audio_temp_subdir
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dest = tmp_dir / f"{job_id}{ext}"
    try:
        dest.write_bytes(raw)
    except OSError as e:
        logger.exception("failed to write audio temp file")
        raise HTTPException(status_code=500, detail=f"could not store upload: {e}") from e

    try:
        await db_module.job_create(
            project_id,
            "[audio]",
            None,
            user_id=user_id,
            user_context=user_context,
            job_kind=job_kind,
            audio_path=str(dest.resolve()),
            job_id=job_id,
        )
    except Exception:
        # dest was already written to disk; without this it becomes a permanent
        # orphan under audio_temp_subdir, since no Job row exists to reference it
        # and nothing in the repo reaps unreferenced files there.
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            logger.warning("failed to clean up orphaned audio temp file %s", dest)
        raise

    return AudioJobResponse(
        job_id=job_id,
        message="Audio received. Poll /status/{job_id}, then /result/{job_id}.",
        status_url=f"/status/{job_id}",
        result_url=f"/result/{job_id}",
    )


@router.post("/transcribe", response_model=AudioJobResponse, status_code=202)
async def audio_transcribe(
    _: None = Depends(require_token),
    project_id: str = Form(...),
    file: UploadFile = File(...),
    user_id: str | None = Form(None),
    language: str | None = Form(
        None,
        description="Optional BCP-47 language code for STT (e.g. pt). Empty = auto-detect.",
    ),
):
    """Queue local transcription only; result.answer and result.transcript contain the text."""
    ctx = _stt_only_context(language)
    return await _enqueue_audio_job(
        project_id=project_id,
        file=file,
        user_id=user_id,
        job_kind="audio_transcribe",
        user_context=ctx,
    )


@router.post("/ask", response_model=AudioJobResponse, status_code=202)
async def audio_ask(
    _: None = Depends(require_token),
    project_id: str = Form(...),
    file: UploadFile = File(...),
    user_id: str | None = Form(None),
    model: str | None = Form(None),
    system_prompt: str | None = Form(None),
    user_context_json: str | None = Form(None),
    history_json: str | None = Form(None),
    language: str | None = Form(None),
):
    """Transcribe audio, then run the same RAG pipeline as POST /ask with the transcript as question."""
    ctx = _build_user_context_for_ask(
        user_context_json=user_context_json,
        history_json=history_json,
        system_prompt=system_prompt,
        model=model,
        stt_language=language,
    )
    return await _enqueue_audio_job(
        project_id=project_id,
        file=file,
        user_id=user_id,
        job_kind="audio_ask",
        user_context=ctx,
    )
