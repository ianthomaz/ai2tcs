"""POST /task/{task_id} and GET /tasks — one door for every project's text tasks (docs/20).

Project: the key's project; with the operator (global) token, `project_id` in the body.
File tasks run for a project that enabled them in config_json.tasks; a code task runs only
for the key of one of its `allowed_projects`. The body is the task input.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from app.auth import key_project_id, require_token
from app.config import settings
from app.job_audit import log_sync_llm_job
from app.registry import get_project
from app.tasks import executor
from app.tasks.engine import PortError, error_body, read_json_object
from app.tasks.registry import CodeTask, code_task, file_task, list_code_tasks, list_file_tasks, project_task_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])


def _code_task_allowed(request: Request, task: CodeTask) -> bool:
    pid = key_project_id(request)
    return bool(pid and pid in task.allowed_projects())


@router.post("/task/{task_id}")
async def run_task(task_id: str, request: Request, _: None = Depends(require_token)) -> dict[str, Any]:
    code = code_task(task_id)
    spec = None if code else file_task(task_id)
    if code is None and spec is None:
        raise HTTPException(status_code=404, detail="task not found")
    if code is not None and not _code_task_allowed(request, code):
        raise HTTPException(status_code=403, detail=f"Task {task_id} is not enabled for this key")

    project_id: str | None = key_project_id(request)
    summary: dict[str, Any] = {}
    try:
        body = await read_json_object(request)
        project_id = project_id or (str(body.get("project_id") or "").strip() or None)
        if not project_id:
            raise PortError("invalid_request", "Com o token do operador, informe project_id.")
        project = await get_project(project_id)
        if code is not None:
            try:
                req = code.request_model.model_validate(body)
            except ValidationError as e:
                first = e.errors()[0] if e.errors() else {}
                where = ".".join(str(p) for p in first.get("loc", ())) or "body"
                raise PortError("invalid_request", f"Campo inválido: {where} — {first.get('msg', 'inválido')}")
            result = await code.run(req, project_id, project)
            summary = code.audit_summary(result)
        else:
            if project is None or project_task_config(project, task_id) is None:
                raise HTTPException(status_code=403, detail=f"Task {task_id} is not enabled for this project")
            task_input = {k: v for k, v in body.items() if k != "project_id"}
            result = await executor.run_file_task(spec, project, task_input)
            summary = executor.audit_summary(spec, result)
    except PortError as e:
        await log_sync_llm_job(
            request,
            project_id_explicit=project_id,
            job_kind=f"task_{task_id}",
            question=f"task:{task_id}",
            status="failed",
            model_alias=settings.task_model_alias,
            error_message=f"{e.code}: {e.message}",
            user_context={"endpoint": f"/task/{task_id}"},
        )
        return error_body(e.code, e.message)
    await log_sync_llm_job(
        request,
        project_id_explicit=project_id,
        job_kind=f"task_{task_id}",
        question=f"task:{task_id}",
        status="done",
        model_alias=result.get("model") or settings.task_model_alias,
        answer=summary,
        user_context={"endpoint": f"/task/{task_id}"},
    )
    return result


@router.get("/tasks")
async def list_tasks(request: Request, _: None = Depends(require_token)) -> dict[str, Any]:
    """Tasks this caller may run: the key's project view, or every task for the operator."""
    pid = key_project_id(request)
    project = await get_project(pid) if pid else None
    out = []
    for task_id in list_file_tasks():
        spec = file_task(task_id)
        if spec is None:
            continue
        enabled = project_task_config(project, task_id) is not None if pid else None
        if pid and not enabled:
            continue
        out.append({"task_id": task_id, "kind": "file", "description": spec.get("description"), "prompt_version": spec.get("prompt_version")})
    for task in list_code_tasks():
        if not pid or _code_task_allowed(request, task):
            out.append({"task_id": task.task_id, "kind": "code", "description": task.description})
    return {"tasks": out}
