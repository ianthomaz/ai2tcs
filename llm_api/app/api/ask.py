"""POST /ask, GET /status/{job_id}, GET /result/{job_id}."""
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request

from app import db as db_module
from app.auth import ensure_job_visible, require_token
from app.models import AskIntent, AskRequest, AskResponse, ResultResponse, StatusResponse, UserSourceRef
from app.registry import get_project, get_rag_policies

router = APIRouter(tags=["ask"])

# Internal job statuses that map to Zapzap "processing"
_PROCESSING_INTERNAL = frozenset({"queued", "working"})


def _client_status(internal: str) -> str:
    return "processing" if internal in _PROCESSING_INTERNAL else internal


def _question_hash(project_id: str, question: str, user_id: str | None = None, job_ctx: dict | None = None) -> str:
    """Dedup key: the same question only collapses into one job when everything that shapes
    the answer is the same — who asks and the context sent (profile, history, prompt, model,
    callback). Two people asking the same thing get their own job."""
    normalized = " ".join(question.strip().lower().split())
    scope = json.dumps({"user_id": user_id or None, "ctx": job_ctx or None}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(f"{project_id}:{normalized}:{scope}".encode()).hexdigest()


@router.post("/ask", response_model=AskResponse, status_code=202)
async def ask(request: AskRequest, _: None = Depends(require_token)):
    project = await get_project(request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    user_context_dict: dict = {}
    if request.user_context:
        user_context_dict.update(request.user_context.model_dump(exclude_none=True, by_alias=False))
    if request.history:
        user_context_dict["__llm_history"] = [
            {"role": t.role, "content": t.text} for t in request.history
        ]
    if request.system_prompt:
        user_context_dict["__llm_system_prompt"] = request.system_prompt
    if request.model:
        user_context_dict["__llm_model"] = request.model
    if request.callback_url:
        user_context_dict["__llm_callback_url"] = request.callback_url
    job_ctx = user_context_dict if user_context_dict else None
    qhash = _question_hash(request.project_id, request.question, request.user_id, job_ctx)
    policies = get_rag_policies(project)
    dedup_ttl = policies.get("dedup_ttl_seconds", 600)
    existing = None
    if dedup_ttl > 0:
        existing = await db_module.job_find_recent_duplicate(
            request.project_id, qhash, within_seconds=dedup_ttl
        )
    if existing:
        return AskResponse(
            job_id=existing,
            message="Duplicate question; use existing job.",
            status_url=f"/status/{existing}",
            result_url=f"/result/{existing}",
        )
    job_id = await db_module.job_create(
        request.project_id,
        request.question,
        qhash,
        user_id=request.user_id,
        user_context=job_ctx,
        model_alias=request.model or "smart",
    )
    return AskResponse(
        job_id=job_id,
        message="Question received. Poll /status/{job_id} for progress, then /result/{job_id} for answer.",
        status_url=f"/status/{job_id}",
        result_url=f"/result/{job_id}",
    )


@router.get("/status/{job_id}", response_model=StatusResponse)
async def status(job_id: str, request: Request, _: None = Depends(require_token)):
    job = ensure_job_visible(request, await db_module.job_get(job_id))
    st = job["status"]
    return StatusResponse(
        job_id=job["id"],
        status=st,
        client_status=_client_status(st),
        progress=job.get("progress"),
        created_at=job["created_at"].isoformat() if job.get("created_at") else None,
    )


@router.get("/result/{job_id}", response_model=ResultResponse)
async def result(job_id: str, request: Request, _: None = Depends(require_token)):
    job = ensure_job_visible(request, await db_module.job_get(job_id))
    raw_sources = job.get("sources") or []
    sources = [UserSourceRef(url=s["url"]) for s in raw_sources if s.get("url")]
    raw_intent = job.get("intent")
    intent = None
    if isinstance(raw_intent, dict):
        try:
            intent = AskIntent.model_validate(raw_intent)
        except Exception:
            intent = None
    return ResultResponse(
        job_id=job["id"],
        status=job["status"],
        answer=job.get("answer"),
        sources=sources,
        confidence=job.get("confidence"),
        transcript=job.get("transcript"),
        stt_metadata=job.get("stt_metadata"),
        signals=job.get("signals"),
        intent=intent,
    )
