"""Bike Anjo ops ports: /feedbackTriage, /healthNormalize, /replySuggest.

Only the Bike Anjo project key (settings.bikeanjo_ops_project_ids) gets in; the global token
and any other project key are 403. JSON sync: one call, one answer. Content errors
are HTTP 200 with the common envelope; 401/403 are transport.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.bikeanjo import feedback_triage, health_normalize, reply_suggest
from app.bikeanjo.common import PortError, error_body, read_request, require_bikeanjo_project
from app.config import settings
from app.job_audit import log_sync_llm_job
from app.registry import get_project

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bikeanjo"])


async def _serve(
    request: Request,
    project_id: str,
    *,
    endpoint: str,
    job_kind: str,
    model_cls: type[BaseModel],
    question: Callable[[Any], str],
    run: Callable[[Any, dict | None], Awaitable[dict[str, Any]]],
    summary: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    body: Any = None
    alias = settings.bikeanjo_ops_model_alias
    try:
        body = await read_request(request, model_cls)
        try:
            project = await get_project(project_id)
        except Exception:
            # Triage and health run on the default provider without it; replySuggest refuses.
            logger.warning("bikeanjo ops: project %s unreadable", project_id, exc_info=True)
            project = None
        result = await run(body, project)
    except PortError as e:
        await log_sync_llm_job(
            request,
            project_id_explicit=project_id,
            job_kind=job_kind,
            question=question(body) if body is not None else endpoint,
            status="failed",
            model_alias=alias,
            error_message=f"{e.code}: {e.message}",
            user_context={"endpoint": endpoint},
        )
        return error_body(e.code, e.message)
    await log_sync_llm_job(
        request,
        project_id_explicit=project_id,
        job_kind=job_kind,
        question=question(body),
        status="done",
        model_alias=result.get("model") or alias,
        answer=summary(result),
        user_context={"endpoint": endpoint},
    )
    return result


@router.post("/feedbackTriage")
async def feedback_triage_route(
    request: Request, project_id: str = Depends(require_bikeanjo_project)
) -> dict[str, Any]:
    return await _serve(
        request,
        project_id,
        endpoint="/feedbackTriage",
        job_kind="bikeanjo_feedback_triage",
        model_cls=feedback_triage.FeedbackTriageRequest,
        question=lambda b: f"feedbackTriage:{b.source}:{b.submission_id}",
        run=feedback_triage.run,
        summary=feedback_triage.audit_summary,
    )


@router.post("/healthNormalize")
async def health_normalize_route(
    request: Request, project_id: str = Depends(require_bikeanjo_project)
) -> dict[str, Any]:
    return await _serve(
        request,
        project_id,
        endpoint="/healthNormalize",
        job_kind="bikeanjo_health_normalize",
        model_cls=health_normalize.HealthNormalizeRequest,
        # No person id in the Job row: health data stays with Bike Anjo.
        question=lambda b: f"healthNormalize:{b.person.kind}",
        run=health_normalize.run,
        summary=health_normalize.audit_summary,
    )


@router.post("/replySuggest")
async def reply_suggest_route(
    request: Request, project_id: str = Depends(require_bikeanjo_project)
) -> dict[str, Any]:
    return await _serve(
        request,
        project_id,
        endpoint="/replySuggest",
        job_kind="bikeanjo_reply_suggest",
        model_cls=reply_suggest.ReplySuggestRequest,
        question=lambda b: f"replySuggest:{b.channel}:{b.ticket_id}",
        run=lambda b, project: reply_suggest.run(b, project_id, project),
        summary=reply_suggest.audit_summary,
    )
