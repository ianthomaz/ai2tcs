"""Terminal Job rows for synchronous LLM endpoints (dashboard / ops visibility)."""
from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from pydantic import BaseModel

from app import db as db_module

# FK on Job.project_id → Project. Seeded by migration; used when no project in request.
SYNC_AUDIT_FALLBACK_PROJECT_ID = "itcs_sync_tools"


def resolve_audit_project_id(request: Request, explicit: str | None) -> str:
    st = getattr(request.state, "project_id", None)
    if isinstance(st, str) and st.strip():
        return st.strip()
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    return SYNC_AUDIT_FALLBACK_PROJECT_ID


def _json_answer(payload: Any) -> str | None:
    if payload is None:
        return None
    if isinstance(payload, BaseModel):
        return payload.model_dump_json()
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, ensure_ascii=False)
    return str(payload)


async def log_sync_llm_job(
    request: Request,
    *,
    project_id_explicit: str | None,
    job_kind: str,
    question: str,
    status: str,
    model_alias: str,
    answer: Any = None,
    error_message: str | None = None,
    user_context: dict[str, Any] | None = None,
) -> None:
    """
    Insert a terminal Job row (same pattern as nabil qualify-caption audit).
    status: done | failed (dashboard lists both).
    """
    pid = resolve_audit_project_id(request, project_id_explicit)
    ans = _json_answer(answer)
    await db_module.job_insert_terminal_audit(
        pid,
        job_kind=job_kind,
        question=(question or "")[:12000],
        status=status,
        model_alias=(model_alias or "smart")[:128],
        answer=ans,
        error_message=error_message[:12000] if error_message else None,
        user_context=user_context,
    )
