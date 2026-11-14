"""Second opinion queue (docs/26-second-opinion.md).

Project side (project key, or operator token + project_id):
  POST /second-opinion             enqueue a case
  GET  /second-opinion/stats       how the teacher rated the local answers, per case_kind and week
  GET  /second-opinion/{source_ref} status and the teacher's answer
Worker side (SECOND_OPINION_WORKER_TOKEN; 404 when unset or wrong):
  POST /second-opinion/worker/claim
  POST /second-opinion/worker/{id}/result
"""
from __future__ import annotations

import asyncio
import hmac
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.auth import key_project_id, require_token
from app.config import settings
from app.registry import get_project
from app.second_opinion import logic, store
from app.tasks.engine import PortError, read_json_object

router = APIRouter(prefix="/second-opinion", tags=["second-opinion"])
logger = logging.getLogger(__name__)


async def _project(request: Request, explicit: Any) -> tuple[str, dict]:
    pid = key_project_id(request) or (explicit.strip() if isinstance(explicit, str) else "")
    if not pid:
        raise HTTPException(status_code=400, detail="project_id is required with the operator token")
    project = await get_project(pid)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return pid, project


async def _body(request: Request) -> dict[str, Any]:
    try:
        return await read_json_object(request)
    except PortError as e:
        raise HTTPException(status_code=400, detail=e.message)


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in ("source_ref", "channel", "case_kind", "status", "response", "agent", "error", "created_at", "finished_at")}


@router.post("")
async def enqueue(request: Request, _: None = Depends(require_token)) -> dict[str, Any]:
    body = await _body(request)
    pid, project = await _project(request, body.get("project_id"))
    # Two switches, both must be on: the service's (kill switch) and the project's.
    if not settings.second_opinion_enabled:
        return {"status": "skipped", "reason": "disabled"}
    if not logic.project_settings(project)["enabled"]:
        return {"status": "skipped", "reason": "project_disabled"}
    try:
        case = logic.normalize_case(body)
    except logic.CaseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    outcome, row = await store.enqueue(pid, case, max(0, settings.second_opinion_daily_limit))
    if outcome == "queued":
        ring_the_bell()
    if outcome == "limit":
        return {"status": "skipped", "reason": "daily_limit"}
    return {"status": outcome, **_public(row)} if outcome == "exists" else {"status": "queued", "source_ref": case["source_ref"]}


@router.get("/stats")
async def stats(request: Request, days: int = 30, project_id: str | None = None, _: None = Depends(require_token)) -> dict[str, Any]:
    pid, _project_row = await _project(request, project_id)
    days = min(max(days, 1), 180)
    return {"days": days, "weeks": await store.stats(pid, days)}


@router.get("/{source_ref}")
async def get_one(source_ref: str, request: Request, project_id: str | None = None, _: None = Depends(require_token)) -> dict[str, Any]:
    pid, _project_row = await _project(request, project_id)
    row = await store.get(pid, source_ref)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return _public(row)


def ring_the_bell() -> None:
    """Wake the host worker (SECOND_OPINION_NOTIFY_URL, e.g. http://host.docker.internal:9191/notify).

    Fire and forget: a worker that is off finds the case when it starts (it drains the queue first).
    """
    url = (settings.second_opinion_notify_url or "").strip()
    if not url:
        return

    async def _ring() -> None:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(url)
        except httpx.HTTPError as e:
            logger.warning(
                "second_opinion: worker bell did not answer (%s): %s — case stays queued until the host worker drains",
                url,
                e,
            )

    asyncio.get_running_loop().create_task(_ring())


def _require_worker(request: Request) -> None:
    expected = settings.second_opinion_worker_token
    got = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    if not expected or not got or not hmac.compare_digest(got.encode(), expected.encode()):
        raise HTTPException(status_code=404)


@router.post("/worker/claim")
async def worker_claim(request: Request) -> Any:
    _require_worker(request)
    if not settings.second_opinion_enabled:
        return Response(status_code=204)
    row = await store.claim()
    if row is None:
        return Response(status_code=204)
    project = await get_project(row["project_id"])
    notes = logic.project_settings(project)["teacher_notes"]
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "source_ref": row["source_ref"],
        "subject_ref": (row["request"] or {}).get("subject_ref"),
        "prompt": logic.build_prompt(row["request"], notes, row["project_id"]),
    }


@router.post("/worker/{case_id}/result")
async def worker_result(case_id: int, request: Request) -> dict[str, Any]:
    _require_worker(request)
    body = await _body(request)
    agent = body.get("agent") if isinstance(body.get("agent"), str) and body["agent"].strip() else "unknown"
    row = await store.get_working(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no working case with this id")
    error = body.get("error") if isinstance(body.get("error"), str) else None
    opinion = None
    if not error:
        raw = body.get("response")
        if isinstance(body.get("output"), str):
            raw = logic.extract_json(body["output"])
        try:
            opinion = logic.normalize_opinion(raw, row["request"])
            # The worker consulted the project's system (read only) before asking the agent.
            opinion["case_check"] = "ok" if body.get("case_check") == "ok" else None
        except logic.CaseError as e:
            error = f"invalid_opinion: {e}"
    await store.finish(case_id, agent, opinion, (error or "")[:500] or None)
    return {"status": "done" if opinion is not None else "failed", "error": error}
