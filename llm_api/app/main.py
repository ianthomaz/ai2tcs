"""FastAPI app: API on port 28471, background worker, dashboard."""
import asyncio
import logging
import time
import uuid
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import close_pool, get_pool
from app.api import ask, audio, boleto_extract, extract, edu, health, ingest, jobs, message_router, nabil_qualify, nf_extract, projects, users
from app.dashboard.routes import router as dashboard_router, DashboardAuthMiddleware
from app.jobs import worker as job_worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()

    # Load worker configuration from settings (default to 1 of each if not set)
    # format: {"fast": 2, "compact": 1, "smart": 1, "reasoner": 1}
    import json
    import os
    workers_conf = {}
    try:
        workers_json = os.environ.get("LLM_WORKERS_JSON")
        if workers_json:
            workers_conf = json.loads(workers_json)
    except Exception:
        logger.warning("Failed to parse LLM_WORKERS_JSON, using defaults")

    if not workers_conf:
        workers_conf = {"fast": 1, "compact": 1, "smart": 1, "reasoner": 1}

    tasks = []
    for alias, count in workers_conf.items():
        for i in range(count):
            t = asyncio.create_task(job_worker._worker_coro(alias_filter=alias))
            tasks.append(t)
            logger.info("Worker task started for %s (instance %d)", alias, i+1)

    # Fallback/generic worker
    tasks.append(asyncio.create_task(job_worker._worker_coro()))
    logger.info("Generic worker task started")

    yield
    for t in tasks:
        t.cancel()

    # Wait for all tasks to be cancelled
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await close_pool()
    logger.info("pool closed")


app = FastAPI(title="LLM API", lifespan=lifespan)


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    """Log request timing with a request id for quick troubleshooting."""
    if not settings.request_logging_enabled:
        return await call_next(request)
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            "request_id=%s method=%s path=%s status_code=500 duration_ms=%s",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
        )
        raise
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["x-request-id"] = request_id
    logger.info(
        "request_id=%s method=%s path=%s status_code=%s duration_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

# Dashboard auth middleware
app.add_middleware(DashboardAuthMiddleware)

# Static files for dashboard
_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# API routers
app.include_router(ingest.router)
app.include_router(ask.router)
app.include_router(audio.router)
app.include_router(extract.router)
app.include_router(nabil_qualify.router)
app.include_router(message_router.router)
app.include_router(health.router)
app.include_router(projects.router)
app.include_router(jobs.router)
app.include_router(nf_extract.router)
app.include_router(boleto_extract.router)
app.include_router(edu.router)
app.include_router(users.router)

# Dashboard (HTMX + Jinja2)
app.include_router(dashboard_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
