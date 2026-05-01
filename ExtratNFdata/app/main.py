"""FastAPI app for NF extraction (XML/PDF/IMG) with local LLM enrichment."""
from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, UploadFile

from app.models import NFExtractResponse
from app.parser import fetch_document_from_url, read_document_from_path, run_extraction_pipeline

app = FastAPI(title="NF Extract API")

OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_MODEL = "llama3:8b"
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "storage" / "incoming"
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
        age = now - file_path.stat().st_mtime
        if age > UPLOAD_RETENTION_SECONDS:
            try:
                file_path.unlink()
            except Exception:
                # Purge should never break request processing.
                continue


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/nfExtract", response_model=NFExtractResponse)
async def nf_extract(
    file: UploadFile | None = File(default=None),
    server_file_path: str | None = Form(default=None),
    document_url: str | None = Form(default=None),
) -> NFExtractResponse:
    sources = [bool(file), bool(server_file_path), bool(document_url)]
    if sum(sources) != 1:
        return NFExtractResponse(
            status="error",
            errors=["Send exactly one source: file OR server_file_path OR document_url."],
        )

    if file:
        _ensure_upload_dir()
        _purge_expired_uploads()
        raw_bytes = await file.read()
        stored_name = f"{int(time.time())}_{uuid4().hex}_{_sanitize_filename(file.filename)}"
        stored_path = UPLOAD_DIR / stored_name
        stored_path.write_bytes(raw_bytes)
        result = await run_extraction_pipeline(
            source_type="upload",
            file_name=file.filename,
            raw_bytes=raw_bytes,
            ollama_host=OLLAMA_HOST,
            ollama_model=OLLAMA_MODEL,
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
            ollama_host=OLLAMA_HOST,
            ollama_model=OLLAMA_MODEL,
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
        ollama_host=OLLAMA_HOST,
        ollama_model=OLLAMA_MODEL,
    )
    return NFExtractResponse(**result)
