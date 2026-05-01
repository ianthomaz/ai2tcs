"""User profile and conversation management endpoints."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException

from app import db as db_module
from app.auth import require_token
from app.models import (
    ConversationResetRequest,
    ConversationResetResponse,
    MaintenanceResponse,
    UserProfileRequest,
    UserProfileResponse,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.put("/profile", response_model=UserProfileResponse)
async def upsert_profile(request: UserProfileRequest, _: None = Depends(require_token)):
    """Create or update a user profile for a project.

    Metadata fields are merged (not replaced) on update — you can send only new fields.
    """
    birth_dt = None
    if request.birth_date:
        try:
            birth_dt = datetime.strptime(request.birth_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="birth_date must be YYYY-MM-DD")

    await db_module.user_profile_upsert(
        user_id=request.user_id,
        project_id=request.project_id,
        display_name=request.display_name,
        birth_date=birth_dt,
        notes=request.notes,
        metadata=request.metadata,
    )
    profile = await db_module.user_profile_get(request.user_id, request.project_id)
    if not profile:
        raise HTTPException(status_code=500, detail="failed to save profile")
    return UserProfileResponse(
        user_id=profile["user_id"],
        project_id=profile["project_id"],
        display_name=profile["display_name"],
        birth_date=profile["birth_date"],
        notes=profile["notes"],
        metadata=profile["metadata"],
        created_at=profile["created_at"].isoformat() if profile.get("created_at") else None,
        updated_at=profile["updated_at"].isoformat() if profile.get("updated_at") else None,
    )


@router.get("/profile/{project_id}/{user_id}", response_model=UserProfileResponse)
async def get_profile(project_id: str, user_id: str, _: None = Depends(require_token)):
    """Get a user's profile for a project."""
    profile = await db_module.user_profile_get(user_id, project_id)
    if not profile:
        raise HTTPException(status_code=404, detail="profile not found")
    return UserProfileResponse(
        user_id=profile["user_id"],
        project_id=profile["project_id"],
        display_name=profile["display_name"],
        birth_date=profile["birth_date"],
        notes=profile["notes"],
        metadata=profile["metadata"],
        created_at=profile["created_at"].isoformat() if profile.get("created_at") else None,
        updated_at=profile["updated_at"].isoformat() if profile.get("updated_at") else None,
    )


@router.delete("/profile/{project_id}/{user_id}")
async def delete_profile(project_id: str, user_id: str, _: None = Depends(require_token)):
    """Delete a user's profile for a project."""
    deleted = await db_module.user_profile_delete(user_id, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="profile not found")
    return {"deleted": True}


@router.post("/conversation/reset", response_model=ConversationResetResponse)
async def reset_conversation(request: ConversationResetRequest, _: None = Depends(require_token)):
    """Delete all conversation history for a user+project. Profile is kept."""
    count = await db_module.conversation_delete(request.user_id, request.project_id)
    return ConversationResetResponse(
        user_id=request.user_id,
        project_id=request.project_id,
        messages_deleted=count,
        message=f"Conversation reset. {count} messages deleted. Profile preserved.",
    )


@router.post("/conversation/maintenance", response_model=MaintenanceResponse)
async def run_maintenance(_: None = Depends(require_token)):
    """Manually trigger conversation maintenance (summarize + purge old messages)."""
    from app.jobs.conversation_maintenance import summarize_and_purge_old_conversations
    stats = await summarize_and_purge_old_conversations(max_age_days=30)
    return MaintenanceResponse(**stats)
