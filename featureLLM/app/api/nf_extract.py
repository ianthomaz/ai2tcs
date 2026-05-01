"""POST /nfExtract — extract invoice data (XML/PDF/IMG)."""
from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.auth import require_token
from app.config import settings
from app.models import NFExtractResponse
from app.nfextract.parser import fetch_document_from_url, read_document_from_path, run_extraction_pipeline

router = APIRouter(tags=["nfExtract"])

UPLOAD_DIR = settings.data_dir / "nf_extract" / "incoming"
UPLOAD_RETENTION_SECONDS = 24 * 60 * 60


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


@router.post("/nfExtract", response_model=NFExtractResponse)
async def nf_extract(
    file: UploadFile | None = File(default=None),
    server_file_path: str | None = Form(default=None),
    document_url: str | None = Form(default=None),
    model: str | None = Form(default=None),
    _: None = Depends(require_token),
) -> NFExtractResponse:
    sources = [bool(file), bool(server_file_path), bool(document_url)]
    if sum(sources) != 1:
        return NFExtractResponse(
            status="error",
            errors=["Send exactly one source: file OR server_file_path OR document_url."],
        )

    model_name = settings.get_model_name(model, default_alias="smart")

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
        return NFExtractResponse(**result)

    if server_file_path:
        try:
            raw_bytes, file_name = read_document_from_path(server_file_path)
        except Exception as exc:  # noqa: BLE001
            return NFExtractResponse(status="error", errors=[str(exc)], source_type="server_file_path")
        result = await run_extraction_pipeline(
            source_type="server_file_path",
            file_name=file_name,
            raw_bytes=raw_bytes,
            ollama_host=settings.ollama_host,
            ollama_model=model_name,
            ollama_timeout_s=settings.nf_extract_ollama_timeout_s,
        )
        return NFExtractResponse(**result)

    try:
        raw_bytes, file_name = await fetch_document_from_url(document_url or "")
    except Exception as exc:  # noqa: BLE001
        return NFExtractResponse(status="error", errors=[str(exc)], source_type="document_url")
    result = await run_extraction_pipeline(
        source_type="document_url",
        file_name=file_name,
        raw_bytes=raw_bytes,
        ollama_host=settings.ollama_host,
        ollama_model=model_name,
        ollama_timeout_s=settings.nf_extract_ollama_timeout_s,
    )
    return NFExtractResponse(**result)
