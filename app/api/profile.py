"""Compatibility routes for the existing SPA user-profile contract."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.limiter import limiter
from app.db.database import get_db
from app.db.models import User, UserDetails
from app.models.auth_models import (
    CurrentUserEnvelope,
    CurrentUserResponse,
    UpdateCurrentUserRequest,
)
from app.models.user_details_models import (
    CreateUserDetailsRequest,
    UpdateUserDetailsRequest,
    UserDetailsResponse,
)
from app.services.user_details_service import user_details_service

auth_router = APIRouter(prefix="/auth", tags=["Profile"])
users_router = APIRouter(prefix="/users", tags=["Profile"])


def _to_current_user(user: User, details: UserDetails | None = None) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=str(user.id),
        email=user.username,
        name=user.display_name or user.username.split("@", 1)[0],
        avatarUrl=None,
        role=user.role,
        createdAt=user.created_at,
        updatedAt=user.updated_at,
        profileId=details.profile_id if details else None,
        firstName=details.first_name if details else None,
        lastName=details.last_name if details else None,
        mobileNumber=details.mobile_number if details else None,
        dateOfBirth=details.date_of_birth if details else None,
        gender=details.gender if details else None,
        profileStatus=details.profile_status if details else None,
        nationality=details.nationality if details else None,
        communicationPreferences=details.communication_preferences if details else None,
        lastLoginDate=details.last_login_date if details else None,
    )


@auth_router.get("/me", response_model=CurrentUserResponse, summary="Get the current user")
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUserResponse:
    details = (
        await db.execute(select(UserDetails).where(UserDetails.user_id == current_user.id))
    ).scalar_one_or_none()
    return _to_current_user(current_user, details)


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
    details = (
        await db.execute(select(UserDetails).where(UserDetails.user_id == current_user.id))
    ).scalar_one_or_none()
    return CurrentUserEnvelope(data=_to_current_user(current_user, details))


# Extended profile ("user_details") 

@users_router.post(
    "/me/details",
    response_model=UserDetailsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create the current user's extended profile",
)
@limiter.limit("20/minute")
async def create_user_details(
    request: Request,
    payload: CreateUserDetailsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserDetailsResponse:
    return await user_details_service.create(payload, current_user, db)


@users_router.get(
    "/me/details",
    response_model=UserDetailsResponse,
    summary="Get the current user's extended profile",
)
@limiter.limit("60/minute")
async def get_user_details(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserDetailsResponse:
    return await user_details_service.get_own(current_user, db)


@users_router.put(
    "/me/details",
    response_model=UserDetailsResponse,
    summary="Update the current user's extended profile",
)
@limiter.limit("20/minute")
async def update_user_details(
    request: Request,
    payload: UpdateUserDetailsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserDetailsResponse:
    return await user_details_service.update_own(payload, current_user, db)