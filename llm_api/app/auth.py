"""API token validation."""
import hashlib
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app import db as db_module

security = HTTPBearer(auto_error=False)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def require_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> None:
    """Dual authentication: Global token OR Project API Key."""
    token = credentials.credentials if credentials else None

    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    # 1. Try global token
    if settings.llm_api_token and token == settings.llm_api_token:
        return

    # 2. Try Project API Key
    key_hash = hash_key(token)
    project_id_from_key = await db_module.api_key_get_project_id(key_hash)

    if project_id_from_key:
        # Verify if the request's project_id matches the key's project_id
        requested_project_id = None
        content_type = request.headers.get("content-type", "").lower()

        try:
            if "application/json" in content_type:
                body = await request.json()
                requested_project_id = body.get("project_id")
            elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
                form = await request.form()
                requested_project_id = form.get("project_id")
        except Exception:
            pass

        if requested_project_id and requested_project_id != project_id_from_key:
            raise HTTPException(status_code=403, detail="API key not authorized for this project")

        # Inject project_id into request state
        request.state.project_id = project_id_from_key
        return

    raise HTTPException(status_code=401, detail="Invalid or revoked token")
