"""POST /ratings · GET /ratings/proposals · POST /ratings/proposals/{id}/decision (docs/22).

Project: the key's project; with the operator token, `project_id` in the body or query.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import key_project_id, require_token
from app.ratings import logic, store
from app.registry import get_project
from app.tasks.engine import read_json_object, PortError

router = APIRouter(prefix="/ratings", tags=["ratings"])


async def _project_id(request: Request, explicit: Any) -> str:
    pid = key_project_id(request) or (explicit.strip() if isinstance(explicit, str) else "")
    if not pid:
        raise HTTPException(status_code=400, detail="project_id is required with the operator token")
    if await get_project(pid) is None:
        raise HTTPException(status_code=404, detail="project not found")
    return pid


@router.post("")
async def post_ratings(request: Request, _: None = Depends(require_token)) -> dict[str, Any]:
    try:
        body = await read_json_object(request)
    except PortError as e:
        raise HTTPException(status_code=400, detail=e.message)
    pid = await _project_id(request, body.get("project_id"))
    raw = body.get("items")
    if not isinstance(raw, list) or not raw or len(raw) > logic.MAX_ITEMS:
        raise HTTPException(status_code=400, detail=f"items: lista de 1 a {logic.MAX_ITEMS}")
    try:
        items = [logic.normalize_item(r) for r in raw]
    except logic.ItemError as e:
        raise HTTPException(status_code=400, detail=str(e))
    stored = removed = new_proposals = 0
    for item in items:
        await store.save(pid, item)
        if item["rating"] is None:
            removed += 1
            continue
        stored += 1
        for kind, value in logic.proposals_for(item):
            new_proposals += int(await store.propose(pid, kind, value, item["source_ref"]))
    return {"status": "ok", "stored": stored, "removed": removed, "new_proposals": new_proposals}


@router.get("/proposals")
async def get_proposals(request: Request, status: str | None = "pending", project_id: str | None = None, _: None = Depends(require_token)) -> dict[str, Any]:
    pid = await _project_id(request, project_id)
    if status not in (None, "pending", "approved", "rejected", "all"):
        raise HTTPException(status_code=400, detail="status: pending, approved, rejected ou all")
    return {"proposals": await store.list_proposals(pid, None if status == "all" else status)}


@router.post("/proposals/{proposal_id}/decision")
async def post_decision(proposal_id: int, request: Request, _: None = Depends(require_token)) -> dict[str, Any]:
    try:
        body = await read_json_object(request)
    except PortError as e:
        raise HTTPException(status_code=400, detail=e.message)
    pid = await _project_id(request, body.get("project_id"))
    decision = body.get("decision")
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision: approve ou reject")
    by = body.get("decided_by")
    out = await store.decide(pid, proposal_id, decision == "approve", by.strip()[:200] if isinstance(by, str) and by.strip() else None)
    if out is None:
        raise HTTPException(status_code=404, detail="no pending proposal with this id")
    return {"status": "ok", "proposal": out}
