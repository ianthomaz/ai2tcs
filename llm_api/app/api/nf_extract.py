"""POST /nfExtract — extract invoice data (XML/PDF/IMG)."""
from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile

from app.auth import require_token
from app.config import settings
from app.job_audit import log_sync_llm_job
from app.models import NFExtractResponse
from app.nfextract.parser import fetch_document_from_url, read_document_from_path, run_extraction_pipeline

router = APIRouter(tags=["nfExtract"])

UPLOAD_DIR = settings.data_dir / "nf_extract" / "incoming"
UPLOAD_RETENTION_SECONDS = 24 * 60 * 60

NF_EXTRACT_JOB_KIND = "nf_extract"


def _ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_filename(name: str | None) -> str:
    if not name:
        return "upload.bin"
    cleaned = Path(name).name.replace("/", "_").replace("\\", "_").strip()
    return cleaned or "upload.bin"


def _purge_expired_uploads() -> None:
    now = time.time()
    if not UPLOAD_DIR.exists():
        return
    for file_path in UPLOAD_DIR.iterdir():
        if not file_path.is_file():
            continue
        if now - file_path.stat().st_mtime > UPLOAD_RETENTION_SECONDS:
            try:
                file_path.unlink()
            except Exception:
                continue


def _nf_job_status(resp: NFExtractResponse) -> str:
    return "done" if (resp.status or "").lower() == "ok" else "failed"


def _nf_question(source: str, name: str | None) -> str:
    n = (name or "").strip() or "(sem nome)"
    return f"nfExtract:{source}:{n}"[:12000]


@router.post("/nfExtract", response_model=NFExtractResponse)
async def nf_extract(
    request: Request,
    file: UploadFile | None = File(default=None),
    server_file_path: str | None = Form(default=None),
    document_url: str | None = Form(default=None),
    model: str | None = Form(default=None),
    project_id: str | None = Header(
        default=None,
        alias="X-Project-Id",
        description="Optional; groups Job rows (use header so multipart body is not parsed twice for auth)",
    ),
    _: None = Depends(require_token),
) -> NFExtractResponse:
    sources = [bool(file), bool(server_file_path), bool(document_url)]
    model_name = settings.get_model_name(model, default_alias="smart")

    if sum(sources) != 1:
        r = NFExtractResponse(
            status="error",
            errors=["Send exactly one source: file OR server_file_path OR document_url."],
        )
        await log_sync_llm_job(
            request,
            project_id_explicit=project_id,
            job_kind=NF_EXTRACT_JOB_KIND,
            question="nfExtract:(invalid source count)",
            status="failed",
            model_alias=model_name,
            answer=r,
            error_message="; ".join(r.errors) if r.errors else None,
            user_context={"endpoint": "/nfExtract", "source": "none"},
        )
        return r

    if file:
        _ensure_upload_dir()
        _purge_expired_uploads()
        raw_bytes = await file.read()
        stored_name = f"{int(time.time())}_{uuid4().hex}_{_sanitize_filename(file.filename)}"
        (UPLOAD_DIR / stored_name).write_bytes(raw_bytes)
        result = await run_extraction_pipeline(
            source_type="upload",
            file_name=file.filename,
            raw_bytes=raw_bytes,
            ollama_host=settings.ollama_host,
            ollama_model=model_name,
            ollama_timeout_s=settings.nf_extract_ollama_timeout_s,
        )
        r = NFExtractResponse(**result)
        err = "; ".join(r.errors) if r.errors else None
        await log_sync_llm_job(
            request,
            project_id_explicit=project_id,
            job_kind=NF_EXTRACT_JOB_KIND,
            question=_nf_question("upload", file.filename),
            status=_nf_job_status(r),
            model_alias=model_name,
            answer=r,
            error_message=err,
            user_context={
                "endpoint": "/nfExtract",
                "source_type": "upload",
                "file_name": file.filename,
            },
        )
        return r

    if server_file_path:
        try:
            raw_bytes, file_name = read_document_from_path(server_file_path)
        except Exception as exc:  # noqa: BLE001
            r = NFExtractResponse(status="error", errors=[str(exc)], source_type="server_file_path")
            await log_sync_llm_job(
                request,
                project_id_explicit=project_id,
                job_kind=NF_EXTRACT_JOB_KIND,
                question=_nf_question("server_file_path", server_file_path),
                status="failed",
                model_alias=model_name,
                answer=r,
                error_message=str(exc),
                user_context={"endpoint": "/nfExtract", "source_type": "server_file_path"},
            )
            return r
        result = await run_extraction_pipeline(
            source_type="server_file_path",
            file_name=file_name,
            raw_bytes=raw_bytes,
            ollama_host=settings.ollama_host,
            ollama_model=model_name,
            ollama_timeout_s=settings.nf_extract_ollama_timeout_s,
        )
        r = NFExtractResponse(**result)
        err = "; ".join(r.errors) if r.errors else None
        await log_sync_llm_job(
            request,
            project_id_explicit=project_id,
            job_kind=NF_EXTRACT_JOB_KIND,
            question=_nf_question("server_file_path", file_name),
            status=_nf_job_status(r),
            model_alias=model_name,
            answer=r,
            error_message=err,
            user_context={"endpoint": "/nfExtract", "source_type": "server_file_path"},
        )
        return r

    try:
        raw_bytes, file_name = await fetch_document_from_url(document_url or "")
    except Exception as exc:  # noqa: BLE001
        r = NFExtractResponse(status="error", errors=[str(exc)], source_type="document_url")
        await log_sync_llm_job(
            request,
            project_id_explicit=project_id,
            job_kind=NF_EXTRACT_JOB_KIND,
            question=_nf_question("document_url", document_url),
            status="failed",
            model_alias=model_name,
            answer=r,
            error_message=str(exc),
            user_context={"endpoint": "/nfExtract", "source_type": "document_url"},
        )
        return r
    result = await run_extraction_pipeline(
        source_type="document_url",
        file_name=file_name,
        raw_bytes=raw_bytes,
        ollama_host=settings.ollama_host,
        ollama_model=model_name,
        ollama_timeout_s=settings.nf_extract_ollama_timeout_s,
    )
    r = NFExtractResponse(**result)
    err = "; ".join(r.errors) if r.errors else None
    await log_sync_llm_job(
        request,
        project_id_explicit=project_id,
        job_kind=NF_EXTRACT_JOB_KIND,
        question=_nf_question("document_url", file_name),
        status=_nf_job_status(r),
        model_alias=model_name,
        answer=r,
        error_message=err,
        user_context={"endpoint": "/nfExtract", "source_type": "document_url"},
    )
    return r
