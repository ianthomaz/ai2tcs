"""API token validation.

Two kinds of Bearer token:
- project key `itcs_<project_id>_<hex>` (table ApiKey): bound to one project. A request that
  names another project (body/form `project_id`, `X-Project-Id`, path or query) is 403.
- global token (settings.llm_api_token): the operator's master key, still accepted while the
  projects migrate to their own keys. Projects listed in SCOPED_KEY_REQUIRED_PROJECTS refuse
  it (403); every use is logged with `auth=global` so the migration can be followed.
"""
import hashlib
import logging

from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app import db as db_module

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def requested_project_ids(request: Request) -> set[str]:
    """Every project the request names: JSON/form body, X-Project-Id header, path and query."""
    found: set[str] = set()
    content_type = request.headers.get("content-type", "").lower()
    try:
        if "application/json" in content_type:
            body = await request.json()
            if isinstance(body, dict):
                found.add(body.get("project_id"))
        elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            found.add(form.get("project_id"))
    except Exception:
        pass
    found.add(request.headers.get("x-project-id"))
    found.add(request.path_params.get("project_id"))
    found.add(request.query_params.get("project_id"))
    return {p.strip() for p in found if isinstance(p, str) and p.strip()}


async def require_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> None:
    """Dual authentication: Global token OR Project API Key."""
    token = credentials.credentials if credentials else None

    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    # 1. Global token
    if settings.llm_api_token and token == settings.llm_api_token:
        requested = await requested_project_ids(request)
        logger.info("auth=global path=%s projects=%s", request.url.path, ",".join(sorted(requested)) or "-")
        blocked = requested & settings.scoped_key_required_project_set()
        if blocked:
            raise HTTPException(
                status_code=403,
                detail=f"Project {sorted(blocked)[0]} requires its own API key",
            )
        return

    # 2. Project API Key
    key_hash = hash_key(token)
    project_id_from_key = await db_module.api_key_get_project_id(key_hash)

    if project_id_from_key:
        requested = await requested_project_ids(request)
        if requested - {project_id_from_key}:
            raise HTTPException(status_code=403, detail="API key not authorized for this project")

        # Inject project_id into request state
        request.state.project_id = project_id_from_key
        return

    raise HTTPException(status_code=401, detail="Invalid or revoked token")
