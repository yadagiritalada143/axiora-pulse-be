"""Compatibility routes for the existing SPA user-profile contract."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.models.auth_models import (
    CurrentUserEnvelope,
    CurrentUserResponse,
    UpdateCurrentUserRequest,
)

auth_router = APIRouter(prefix="/auth", tags=["Profile"])
users_router = APIRouter(prefix="/users", tags=["Profile"])


def _to_current_user(user: User) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=str(user.id),
        email=user.username,
        name=user.display_name or user.username.split("@", 1)[0],
        avatarUrl=None,
        role=user.role,
        createdAt=user.created_at,
        updatedAt=user.updated_at,
    )


@auth_router.get("/me", response_model=CurrentUserResponse, summary="Get the current user")
async def get_current_user_profile(current_user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return _to_current_user(current_user)


@users_router.patch("/me", response_model=CurrentUserEnvelope, summary="Update the current user profile")
async def update_current_user_profile(
    payload: UpdateCurrentUserRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUserEnvelope:
    email = str(payload.email).lower().strip()
    if email != current_user.username:
        existing = await db.execute(select(User.id).where(User.username == email, User.id != current_user.id))
        if existing.scalar_one_or_none() is not None:
            import logging
            logging.getLogger(__name__).warning(
                "Profile update conflict: user_id=%s tried to change email to %r but it already exists",
                current_user.id, email
            )
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")
        current_user.username = email

    current_user.display_name = payload.name.strip()
    await db.flush()
    await db.refresh(current_user)
    return CurrentUserEnvelope(data=_to_current_user(current_user))
