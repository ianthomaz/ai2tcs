"""GET /health, GET /metrics - improved with real checks."""
import logging
import shutil
import time

import httpx
from fastapi import APIRouter, Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, PlainTextResponse

from app import db as db_module
from app.auth import require_operator, security, token_is_valid
from app.config import settings

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)

_start_time = time.time()


@router.get("/health")
async def health(
    request: Request,
    strict: bool = False,
    credentials: HTTPAuthorizationCredentials | None = Security(security),
):
    """Liveness: check Ollama, PostgreSQL, and disk space.

    Without a token the body is only `status` and `uptime_seconds` (the service is reachable
    on the internet; model names and disk are not for everyone). With a valid key or the
    operator token, `checks` too. The body never carries error text. `?strict=1` answers 503
    when degraded, so an HTTP monitor (itcsManifest.yaml) sees Ollama or Postgres down."""
    checks = {}

    # Ollama
    ollama_url = f"{settings.ollama_host.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(ollama_url)
            ollama_ok = r.status_code == 200
            models = [m["name"] for m in r.json().get("models", [])] if ollama_ok else []
        checks["ollama"] = {"status": "ok", "models": models}
    except Exception:
        checks["ollama"] = {"status": "unreachable"}

    # PostgreSQL
    try:
        pool = await db_module.get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["postgres"] = {"status": "ok"}
    except Exception:
        logger.exception("health: postgres check failed")
        checks["postgres"] = {"status": "error"}

    # Disk space
    try:
        usage = shutil.disk_usage(str(settings.data_dir))
        free_gb = round(usage.free / (1024**3), 1)
        checks["disk"] = {"status": "ok" if free_gb > 1.0 else "low", "free_gb": free_gb}
    except Exception:
        checks["disk"] = {"status": "unknown"}

    # Second-opinion queue depth (informational; never flips overall health by itself)
    try:
        from app.second_opinion import store as so_store

        depth = await so_store.queue_depth()
        checks["second_opinion"] = {
            "status": "ok",
            "enabled": bool(settings.second_opinion_enabled),
            "notify_url_configured": bool((settings.second_opinion_notify_url or "").strip()),
            **depth,
        }
    except Exception:
        logger.exception("health: second_opinion queue check failed")
        checks["second_opinion"] = {"status": "error"}

    # Core liveness only: Ollama, Postgres, disk. Queue depth is informational.
    core = {k: checks[k] for k in ("ollama", "postgres", "disk") if k in checks}
    all_ok = all(c.get("status") == "ok" for c in core.values())
    uptime_seconds = round(time.time() - _start_time)

    body: dict = {
        "status": "ok" if all_ok else "degraded",
        "uptime_seconds": uptime_seconds,
    }
    if await token_is_valid(request, credentials):
        body["checks"] = checks
    if strict and not all_ok:
        return JSONResponse(body, status_code=503)
    return body


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics(_: None = Depends(require_operator)):
    """Real metrics from job stats."""
    try:
        stats = await db_module.job_stats()
        lines = [
            f'llm_api_ready 1',
            f'llm_jobs_total {stats["total"]}',
            f'llm_jobs_last_24h {stats["last_24h"]}',
        ]
        for status_name, count in stats.get("by_status", {}).items():
            lines.append(f'llm_jobs_by_status{{status="{status_name}"}} {count}')
        for proj, count in stats.get("by_project", {}).items():
            lines.append(f'llm_jobs_by_project{{project="{proj}"}} {count}')
        if stats.get("avg_duration_seconds") is not None:
            lines.append(f'llm_jobs_avg_duration_seconds {stats["avg_duration_seconds"]}')
        try:
            for proj, c in (await db_module.llm_heavy_counts_24h()).items():
                lines.append(f'llm_calls_heavy_24h{{project="{proj}"}} {c["heavy"]}')
                lines.append(f'llm_calls_near_ctx_limit_24h{{project="{proj}"}} {c["near_limit"]}')
        except Exception:
            pass
        try:
            from app.stt.metrics import stt_metric_lines

            lines.extend(stt_metric_lines())
        except Exception:
            pass
        try:
            from app.second_opinion import store as so_store

            depth = await so_store.queue_depth()
            lines.append(f'second_opinion_queued {depth["queued"]}')
            lines.append(f'second_opinion_working {depth["working"]}')
            lines.append(f'second_opinion_working_stale {depth["working_stale"]}')
            age = depth["oldest_queued_age_seconds"]
            if age is not None:
                lines.append(f"second_opinion_oldest_queued_age_seconds {age}")
        except Exception:
            pass
        return PlainTextResponse("\n".join(lines) + "\n")
    except Exception:
        return PlainTextResponse("llm_api_ready 0\n")
