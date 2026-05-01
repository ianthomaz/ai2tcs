"""GET /jobs, GET /jobs/stats, POST /jobs/{job_id}/cancel."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app import db as db_module
from app.auth import require_token
from app.models import JobListResponse, JobResponse, JobStatsResponse, UserSourceRef

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job_to_response(job: dict) -> JobResponse:
    raw_sources = job.get("sources") or []
    sources = [UserSourceRef(url=s["url"]) for s in raw_sources if s.get("url")]
    return JobResponse(
        job_id=job["id"],
        project_id=job["project_id"],
        question=job.get("question", ""),
        status=job["status"],
        progress=job.get("progress"),
        answer=job.get("answer"),
        sources=sources,
        confidence=job.get("confidence"),
        error_message=job.get("error_message"),
        created_at=job["created_at"].isoformat() if job.get("created_at") else None,
        updated_at=job["updated_at"].isoformat() if job.get("updated_at") else None,
        job_kind=job.get("job_kind"),
        transcript=job.get("transcript"),
    )


@router.get("/stats", response_model=JobStatsResponse)
async def job_stats(_: None = Depends(require_token)):
    stats = await db_module.job_stats()
    return JobStatsResponse(**stats)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    project_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _: None = Depends(require_token),
):
    jobs, total = await db_module.job_list(
        project_id=project_id,
        status=status,
        limit=min(limit, 200),
        offset=offset,
    )
    return JobListResponse(
        jobs=[_job_to_response(j) for j in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{job_id}/cancel", status_code=200)
async def cancel_job(job_id: str, _: None = Depends(require_token)):
    job = await db_module.job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] != "queued":
        raise HTTPException(status_code=409, detail=f"cannot cancel job with status '{job['status']}'")
    ap = job.get("audio_path")
    if ap:
        p = Path(ap)
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    await db_module.job_cancel(job_id)
    return {"job_id": job_id, "status": "cancelled"}
