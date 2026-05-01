"""CRUD endpoints for project management."""
import json

from fastapi import APIRouter, Depends, HTTPException

from app import db as db_module
from app.auth import require_token
from app.ingest.indexer import get_index_stats
from app.models import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _normalize_config_json(raw: object) -> dict | None:
    """DB may return jsonb as dict or, in some rows, a JSON string — Pydantic expects dict | None."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _project_to_response(
    proj: dict,
    themes: list[str] | None = None,
    index_stats: dict | None = None,
) -> ProjectResponse:
    return ProjectResponse(
        project_id=proj["project_id"],
        name=proj.get("name"),
        sources=proj.get("sources", []),
        config_json=_normalize_config_json(proj.get("config_json")),
        themes=themes if themes is not None else [],
        created_at=proj["created_at"].isoformat() if proj.get("created_at") else None,
        updated_at=proj["updated_at"].isoformat() if proj.get("updated_at") else None,
        index_stats=index_stats,
    )


@router.get("", response_model=ProjectListResponse)
async def list_projects(_: None = Depends(require_token)):
    projects = await db_module.project_list_all()
    items = []
    for proj in projects:
        themes = await db_module.project_get_themes(proj["project_id"])
        items.append(_project_to_response(proj, themes))
    return ProjectListResponse(projects=items, total=len(items))


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, _: None = Depends(require_token)):
    proj = await db_module.project_get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="project not found")
    themes = await db_module.project_get_themes(project_id)
    index_stats = get_index_stats(project_id)
    return _project_to_response(proj, themes, index_stats)


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(request: ProjectCreateRequest, _: None = Depends(require_token)):
    existing = await db_module.project_get(request.project_id)
    if existing:
        raise HTTPException(status_code=409, detail="project_id already exists")
    proj = await db_module.project_create(
        project_id=request.project_id,
        name=request.name,
        sources=request.sources,
        config_json=request.config_json,
    )
    if request.themes:
        await db_module.project_themes_set(request.project_id, request.themes)
    themes = await db_module.project_get_themes(request.project_id)
    return _project_to_response(proj, themes)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, request: ProjectUpdateRequest, _: None = Depends(require_token)):
    existing = await db_module.project_get(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="project not found")
    proj = await db_module.project_update(
        project_id=project_id,
        name=request.name,
        sources=request.sources,
        config_json=request.config_json,
    )
    if request.themes is not None:
        await db_module.project_themes_set(project_id, request.themes)
    themes = await db_module.project_get_themes(project_id)
    return _project_to_response(proj, themes)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, _: None = Depends(require_token)):
    existing = await db_module.project_get(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="project not found")
    await db_module.project_delete(project_id)
