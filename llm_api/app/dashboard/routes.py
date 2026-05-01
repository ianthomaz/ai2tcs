"""Dashboard routes (HTML pages via Jinja2 + HTMX)."""
import asyncio
import secrets
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app import db as db_module
from app.config import settings
from app.dashboard import google_oauth
from app.dashboard import metrics_collect as metrics_collect
from app.ingest.indexer import get_index_stats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

# Simple in-memory session store
_sessions: set[str] = set()

# Paths that don't require auth
_PUBLIC_PATHS = frozenset(
    {
        "/dashboard/login",
        "/dashboard/auth/google",
        "/dashboard/auth/google/callback",
    }
)


class DashboardAuthMiddleware(BaseHTTPMiddleware):
    """Redirect to login if accessing /dashboard/* without valid session."""
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/dashboard") and request.url.path not in _PUBLIC_PATHS:
            session_id = request.cookies.get("dashboard_session")
            if not session_id or session_id not in _sessions:
                return RedirectResponse(url="/dashboard/login", status_code=302)
        return await call_next(request)


def _require_dashboard_auth(request: Request) -> None:
    """Dependency that verifies dashboard session (backup check)."""
    session_id = request.cookies.get("dashboard_session")
    if not session_id or session_id not in _sessions:
        raise HTTPException(status_code=401, detail="not authenticated")


async def _dashboard_health_checks() -> dict[str, Any]:
    """Ollama /api/tags reachability, Postgres ping, disk free under data_dir."""
    import shutil

    import httpx as hx

    checks: dict[str, Any] = {}
    ollama_url = f"{settings.ollama_host.rstrip('/')}/api/tags"
    try:
        async with hx.AsyncClient(timeout=5.0) as client:
            r = await client.get(ollama_url)
            checks["ollama"] = "ok" if r.status_code == 200 else "error"
    except Exception:
        checks["ollama"] = "error"
    try:
        pool = await db_module.get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "error"
    try:
        usage = shutil.disk_usage(str(settings.data_dir))
        free_gb = round(usage.free / (1024**3), 1)
        checks["disk"] = "ok" if free_gb > 1.0 else "low"
        checks["disk_free_gb"] = free_gb
    except Exception:
        checks["disk"] = "unknown"
    return checks


async def _usage_page_context() -> dict[str, Any]:
    """Metrics for /dashboard/usage (HTMX partial + full page)."""
    stats, checks, ps_raw, host = await asyncio.gather(
        db_module.job_stats(),
        _dashboard_health_checks(),
        metrics_collect.fetch_ollama_ps_payload(),
        asyncio.to_thread(metrics_collect.psutil_host_snapshot),
    )
    ref = float(settings.dashboard_ollama_memory_reference_gib)
    ollama = metrics_collect.build_ollama_memory_gauges(ps_raw, reference_gib=ref)
    ram_arc = metrics_collect.ram_gauge_arc(host)
    cpu_arc = metrics_collect.cpu_gauge_arc(host)
    arc_len = 251.327  # half circumference, r=80
    host_used_gib = host.get("ram_used_bytes", 0) / (1024**3) if host.get("ok") else 0.0
    host_total_gib = host.get("ram_total_bytes", 0) / (1024**3) if host.get("ok") else 0.0
    return {
        "stats": stats,
        "checks": checks,
        "host": host,
        "ollama": ollama,
        "ram_arc": ram_arc,
        "cpu_arc": cpu_arc,
        "arc_len": arc_len,
        "working_jobs": int(stats.get("by_status", {}).get("working", 0) or 0),
        "ref_gib": ref,
        "host_ram_used_gib": round(host_used_gib, 2),
        "host_ram_total_gib": round(host_total_gib, 2),
    }


# --- Auth ---


def _google_oauth_enabled() -> bool:
    return settings.dashboard_google_oauth_configured()


def _password_login_enabled() -> bool:
    return bool(settings.dashboard_user and settings.dashboard_password)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if not _google_oauth_enabled() and not _password_login_enabled():
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Dashboard não configurado: defina Google OAuth (DASHBOARD_GOOGLE_*) ou DASHBOARD_USER / DASHBOARD_PASSWORD no .env.",
                "google_oauth_enabled": False,
                "password_login_enabled": False,
            },
        )
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": None,
            "google_oauth_enabled": _google_oauth_enabled(),
            "password_login_enabled": _password_login_enabled(),
        },
    )


@router.get("/auth/google")
async def google_oauth_start():
    if not _google_oauth_enabled():
        return RedirectResponse(url="/dashboard/login", status_code=302)
    state = google_oauth.new_oauth_state()
    redirect_uri = google_oauth.build_authorize_redirect_uri(settings.dashboard_oauth_redirect_base)
    url = google_oauth.authorization_url(
        client_id=settings.dashboard_google_client_id,
        redirect_uri=redirect_uri,
        state=state,
    )
    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(
        "dashboard_oauth_state",
        state,
        httponly=True,
        max_age=600,
        samesite="lax",
        path="/dashboard",
    )
    return response


@router.get("/auth/google/callback")
async def google_oauth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": f"Google OAuth: {error}",
                "google_oauth_enabled": _google_oauth_enabled(),
                "password_login_enabled": _password_login_enabled(),
            },
        )
    if not _google_oauth_enabled():
        return RedirectResponse(url="/dashboard/login", status_code=302)
    cookie_state = request.cookies.get("dashboard_oauth_state")
    if not cookie_state or not state or cookie_state != state:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Sessão OAuth inválida ou expirada. Tente novamente.",
                "google_oauth_enabled": _google_oauth_enabled(),
                "password_login_enabled": _password_login_enabled(),
            },
        )
    if not code:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Código OAuth em falta.",
                "google_oauth_enabled": _google_oauth_enabled(),
                "password_login_enabled": _password_login_enabled(),
            },
        )
    redirect_uri = google_oauth.build_authorize_redirect_uri(settings.dashboard_oauth_redirect_base)
    try:
        token_payload = await google_oauth.exchange_code(
            client_id=settings.dashboard_google_client_id,
            client_secret=settings.dashboard_google_client_secret,
            code=code,
            redirect_uri=redirect_uri,
        )
        access_token = token_payload.get("access_token")
        if not access_token:
            raise ValueError("no access_token in token response")
        email = await google_oauth.fetch_google_email(access_token)
    except Exception:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Falha ao validar login Google. Verifique Client ID/Secret e Redirect URI no GCP.",
                "google_oauth_enabled": _google_oauth_enabled(),
                "password_login_enabled": _password_login_enabled(),
            },
        )

    allowed = settings.dashboard_allowed_email_set()
    if not allowed:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": (
                    "Allowlist vazia: defina DASHBOARD_ALLOWED_EMAILS no .env da API "
                    "(pelo menos um e-mail, minúsculas, separados por vírgula)."
                ),
                "google_oauth_enabled": _google_oauth_enabled(),
                "password_login_enabled": _password_login_enabled(),
            },
        )
    if email not in allowed:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Você não tem acesso a esta área.",
                "google_oauth_enabled": _google_oauth_enabled(),
                "password_login_enabled": _password_login_enabled(),
            },
        )

    session_id = secrets.token_urlsafe(32)
    _sessions.add(session_id)
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie("dashboard_session", session_id, httponly=True, max_age=86400, samesite="lax", path="/")
    response.delete_cookie("dashboard_oauth_state", path="/dashboard")
    return response


@router.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if _google_oauth_enabled() and not _password_login_enabled():
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Este dashboard usa apenas login Google.",
                "google_oauth_enabled": True,
                "password_login_enabled": False,
            },
        )
    if not settings.dashboard_user or not settings.dashboard_password:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Dashboard não configurado",
                "google_oauth_enabled": _google_oauth_enabled(),
                "password_login_enabled": False,
            },
        )
    if username != settings.dashboard_user or password != settings.dashboard_password:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Usuário ou senha inválidos",
                "google_oauth_enabled": _google_oauth_enabled(),
                "password_login_enabled": _password_login_enabled(),
            },
        )
    session_id = secrets.token_urlsafe(32)
    _sessions.add(session_id)
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie("dashboard_session", session_id, httponly=True, max_age=86400, samesite="lax", path="/")
    return response


@router.get("/logout")
async def logout(request: Request):
    session_id = request.cookies.get("dashboard_session")
    if session_id and session_id in _sessions:
        _sessions.discard(session_id)
    response = RedirectResponse(url="/dashboard/login", status_code=302)
    response.delete_cookie("dashboard_session", path="/")
    response.delete_cookie("dashboard_oauth_state", path="/dashboard")
    return response


# --- Dashboard Home ---


@router.get("", response_class=HTMLResponse)
async def dashboard_home(request: Request, _: None = Depends(_require_dashboard_auth)):
    stats = await db_module.job_stats()
    projects = await db_module.project_list_all()
    recent_jobs, _ = await db_module.job_list(limit=10)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"stats": stats, "projects": projects, "recent_jobs": recent_jobs},
    )


@router.get("/usage", response_class=HTMLResponse)
async def dashboard_usage(request: Request, _: None = Depends(_require_dashboard_auth)):
    ctx = await _usage_page_context()
    return templates.TemplateResponse(request, "usage.html", ctx)


# --- Projects ---


@router.get("/projects", response_class=HTMLResponse)
async def projects_list(request: Request, _: None = Depends(_require_dashboard_auth)):
    projects = await db_module.project_list_all()
    for p in projects:
        p["themes"] = await db_module.project_get_themes(p["project_id"])
    return templates.TemplateResponse(request, "projects/list.html", {"projects": projects})


@router.get("/projects/new", response_class=HTMLResponse)
async def project_create_form(request: Request, _: None = Depends(_require_dashboard_auth)):
    return templates.TemplateResponse(request, "projects/create.html", {"error": None})


@router.post("/projects/new")
async def project_create_submit(
    request: Request,
    project_id: str = Form(...),
    name: str = Form(""),
    sources: str = Form(""),
    themes: str = Form(""),
    _: None = Depends(_require_dashboard_auth),
):
    existing = await db_module.project_get(project_id)
    if existing:
        return templates.TemplateResponse(
            request,
            "projects/create.html",
            {"error": f"project_id '{project_id}' já existe"},
        )
    sources_list = [s.strip() for s in sources.strip().split("\n") if s.strip()]
    themes_list = [t.strip() for t in themes.strip().split(",") if t.strip()]
    await db_module.project_create(project_id=project_id, name=name or None, sources=sources_list)
    if themes_list:
        await db_module.project_themes_set(project_id, themes_list)
    return RedirectResponse(url=f"/dashboard/projects/{project_id}", status_code=302)


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(project_id: str, request: Request, _: None = Depends(_require_dashboard_auth)):
    proj = await db_module.project_get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="project not found")
    proj["themes"] = await db_module.project_get_themes(project_id)
    jobs, total = await db_module.job_list(project_id=project_id, limit=20)
    try:
        index_stats = get_index_stats(project_id)
    except Exception:
        index_stats = {"chunks": 0, "last_ingest": None}
    if not isinstance(index_stats, dict):
        index_stats = {"chunks": 0, "last_ingest": None}
    return templates.TemplateResponse(
        request,
        "projects/detail.html",
        {"project": proj, "jobs": jobs, "total_jobs": total, "index_stats": index_stats},
    )


@router.post("/projects/{project_id}/edit")
async def project_edit_submit(
    project_id: str,
    request: Request,
    name: str = Form(""),
    sources: str = Form(""),
    themes: str = Form(""),
    rag_alias: str = Form("smart"),
    edu_alias: str = Form("fast"),
    _: None = Depends(_require_dashboard_auth),
):
    existing = await db_module.project_get(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="project not found")

    sources_list = [s.strip() for s in sources.strip().split("\n") if s.strip()]
    themes_list = [t.strip() for t in themes.strip().split(",") if t.strip()]

    cfg = existing.get("config_json") or {}
    if not isinstance(cfg, dict):
        cfg = {}

    llm_opts = cfg.get("llm_options", {})
    if not isinstance(llm_opts, dict):
        llm_opts = {}

    llm_opts["rag_alias"] = rag_alias
    llm_opts["edu_alias"] = edu_alias
    cfg["llm_options"] = llm_opts

    await db_module.project_update(project_id=project_id, name=name or None, sources=sources_list, config_json=cfg)
    await db_module.project_themes_set(project_id, themes_list)
    return RedirectResponse(url=f"/dashboard/projects/{project_id}", status_code=302)


@router.post("/projects/{project_id}/delete")
async def project_delete(project_id: str, _: None = Depends(_require_dashboard_auth)):
    await db_module.project_delete(project_id)
    return RedirectResponse(url="/dashboard/projects", status_code=302)


# --- Jobs ---


@router.get("/jobs", response_class=HTMLResponse)
async def jobs_list(
    request: Request,
    project_id: str = "",
    status: str = "",
    page: int = 1,
    _: None = Depends(_require_dashboard_auth),
):
    limit = 25
    offset = (page - 1) * limit
    jobs, total = await db_module.job_list(
        project_id=project_id or None,
        status=status or None,
        limit=limit,
        offset=offset,
    )
    projects = await db_module.project_list_ids()
    total_pages = max(1, (total + limit - 1) // limit)
    return templates.TemplateResponse(
        request,
        "jobs/list.html",
        {
            "jobs": jobs,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "projects": projects,
            "filter_project": project_id,
            "filter_status": status,
        },
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(job_id: str, request: Request, _: None = Depends(_require_dashboard_auth)):
    job = await db_module.job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return templates.TemplateResponse(request, "jobs/detail.html", {"job": job})


@router.post("/jobs/{job_id}/cancel")
async def job_cancel(job_id: str, _: None = Depends(_require_dashboard_auth)):
    job = await db_module.job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] == "queued":
        ap = job.get("audio_path")
        if ap:
            p = Path(ap)
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass
        await db_module.job_cancel(job_id)
    return RedirectResponse(url=f"/dashboard/jobs/{job_id}", status_code=302)


# --- HTMX Partials ---


@router.get("/partials/stats", response_class=HTMLResponse)
async def partial_stats(request: Request, _: None = Depends(_require_dashboard_auth)):
    stats = await db_module.job_stats()
    return templates.TemplateResponse(request, "partials/stats_cards.html", {"stats": stats})


@router.get("/partials/usage-body", response_class=HTMLResponse)
async def partial_usage_body(request: Request, _: None = Depends(_require_dashboard_auth)):
    ctx = await _usage_page_context()
    return templates.TemplateResponse(request, "partials/usage_body.html", ctx)


@router.get("/partials/recent-jobs", response_class=HTMLResponse)
async def partial_recent_jobs(request: Request, _: None = Depends(_require_dashboard_auth)):
    recent_jobs, _ = await db_module.job_list(limit=10)
    return templates.TemplateResponse(request, "partials/recent_jobs.html", {"recent_jobs": recent_jobs})


@router.get("/partials/health", response_class=HTMLResponse)
async def partial_health(request: Request, _: None = Depends(_require_dashboard_auth)):
    checks = await _dashboard_health_checks()
    return templates.TemplateResponse(request, "partials/health_badge.html", {"checks": checks})

# --- API Keys ---


@router.get("/projects/{project_id}/keys", response_class=HTMLResponse)
async def project_keys_list(project_id: str, request: Request, _: None = Depends(_require_dashboard_auth)):
    keys = await db_module.api_key_list(project_id)
    return templates.TemplateResponse(
        request,
        "projects/keys.html",
        {"project_id": project_id, "keys": keys, "new_key": None}
    )


@router.post("/projects/{project_id}/keys", response_class=HTMLResponse)
async def project_key_generate(
    project_id: str,
    request: Request,
    label: str = Form(""),
    _: None = Depends(_require_dashboard_auth)
):
    from app.auth import hash_key
    raw_key = f"itcs_{project_id}_{secrets.token_hex(12)}"
    key_hash = hash_key(raw_key)
    await db_module.api_key_create(project_id, key_hash, label or None)

    keys = await db_module.api_key_list(project_id)
    return templates.TemplateResponse(
        request,
        "projects/keys.html",
        {"project_id": project_id, "keys": keys, "new_key": raw_key}
    )


@router.post("/projects/{project_id}/keys/{key_id}/revoke")
async def project_key_revoke(
    project_id: str,
    key_id: str,
    _: None = Depends(_require_dashboard_auth)
):
    await db_module.api_key_revoke(key_id)
    return RedirectResponse(url=f"/dashboard/projects/{project_id}/keys", status_code=302)
