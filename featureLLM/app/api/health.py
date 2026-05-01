"""GET /health, GET /metrics - improved with real checks."""
import shutil
import time

import httpx
from fastapi import APIRouter

from app import db as db_module
from app.config import settings

router = APIRouter(tags=["health"])

_start_time = time.time()


@router.get("/health")
async def health():
    """Liveness: check Ollama, PostgreSQL, and disk space."""
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
    except Exception as e:
        checks["postgres"] = {"status": "error", "detail": str(e)}

    # Disk space
    try:
        usage = shutil.disk_usage(str(settings.data_dir))
        free_gb = round(usage.free / (1024**3), 1)
        checks["disk"] = {"status": "ok" if free_gb > 1.0 else "low", "free_gb": free_gb}
    except Exception:
        checks["disk"] = {"status": "unknown"}

    all_ok = all(c.get("status") == "ok" for c in checks.values())
    uptime_seconds = round(time.time() - _start_time)

    return {
        "status": "ok" if all_ok else "degraded",
        "uptime_seconds": uptime_seconds,
        "checks": checks,
    }


@router.get("/metrics")
async def metrics():
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
            from app.stt.metrics import stt_metric_lines

            lines.extend(stt_metric_lines())
        except Exception:
            pass
        return "\n".join(lines) + "\n"
    except Exception:
        return "llm_api_ready 0\n"
