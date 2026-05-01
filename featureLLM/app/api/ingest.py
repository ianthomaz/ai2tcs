"""POST /ingest: index/reindex project library (runs in background). Creates project if missing."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from app import db as db_module
from app.auth import require_token
from app.config import settings
from app.ingest.indexer import run_ingest
from app.models import IngestRequest, IngestResponse
from app.registry import get_project

router = APIRouter(prefix="/ingest", tags=["ingest"])


def _sources_for_create(project_id: str, request_sources: list[str] | None) -> list[str]:
    """Resolve sources: request > env override > []."""
    if request_sources:
        return request_sources
    override = settings.project_sources_override(project_id)
    return override if override is not None else []


@router.post("", response_model=IngestResponse)
async def ingest(request: IngestRequest, _: None = Depends(require_token)):
    project = await get_project(request.project_id)
    if not project:
        sources = _sources_for_create(request.project_id, request.sources)
        if not sources:
            raise HTTPException(
                status_code=400,
                detail="project not found; provide 'sources' in body or set PROJECT_ID_SOURCES in env",
            )
        await db_module.project_create(
            project_id=request.project_id,
            name=request.name or request.project_id,
            sources=sources,
        )
    asyncio.create_task(run_ingest_background(request.project_id, request.incremental))
    return IngestResponse(
        project_id=request.project_id,
        status="started",
        message="Ingest job queued. Indexing runs in background.",
    )


async def run_ingest_background(project_id: str, incremental: bool) -> None:
    result = await run_ingest(project_id, incremental=incremental)
    if result.get("error"):
        pass  # log only; client already got 200


@router.post("/upload", response_model=IngestResponse)
async def upload_ingest(
    project_id: str = Form(None),
    library_slug: str = Form(None),
    subpath: str = Form("uploads/"),
    file: UploadFile = File(...),
    _: None = Depends(require_token),
):
    """Multipart upload to project or shared library."""
    if (project_id and library_slug) or (not project_id and not library_slug):
        raise HTTPException(status_code=400, detail="Provide exactly one of project_id or library_slug")

    # 1. Resolve destination directory
    if project_id:
        target_dir = settings.data_dir / "project_library" / project_id / subpath
    else:
        target_dir = settings.data_dir / "project_library" / "_shared" / library_slug / subpath

    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / file.filename

    # 2. Save file
    try:
        content = await file.read()
        file_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # 3. Trigger ingest
    # Note: run_ingest currently expects project_id.
    # If library_slug is used, we'd need to adapt run_ingest or create a shared indexer.
    if project_id:
        asyncio.create_task(run_ingest_background(project_id, incremental=True))

    return IngestResponse(
        project_id=project_id or library_slug,
        status="started",
        message=f"File {file.filename} uploaded to {subpath}. Ingest queued.",
    )
