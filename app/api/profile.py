"""Compatibility routes for the existing SPA user-profile contract."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, UploadFile, File
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
from app.services.s3_storage_service import s3_storage_service

auth_router = APIRouter(prefix="/auth", tags=["Profile"])
users_router = APIRouter(prefix="/users", tags=["Profile"])


def _to_current_user(user: User, details: UserDetails | None = None) -> CurrentUserResponse:
    avatar_url = None
    if details and details.avatar_url:
        avatar_url = s3_storage_service.get_proxy_avatar_url(user.id, details.avatar_url)

    return CurrentUserResponse(
        id=str(user.id),
        email=user.username,
        name=user.display_name or user.username.split("@", 1)[0],
        avatarUrl=avatar_url,
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

    if payload.avatarUrl is not None:
        if details is None:
            from app.services.user_details_service import _generate_unique_profile_id
            from app.core.timezone import to_ist
            profile_id = await _generate_unique_profile_id(db)
            registered_at = to_ist(current_user.created_at)
            name_parts = (current_user.display_name or current_user.username.split("@", 1)[0]).split(" ", 1)
            first_name = name_parts[0] or "User"
            last_name = name_parts[1] if len(name_parts) > 1 else "Profile"

            details = UserDetails(
                profile_id=profile_id,
                user_id=current_user.id,
                first_name=first_name,
                last_name=last_name,
                email=current_user.username,
                mobile_number="9999999999",
                avatar_url=payload.avatarUrl,
                created_at=registered_at,
                updated_at=registered_at,
            )
            db.add(details)
        else:
            details.avatar_url = payload.avatarUrl

        await db.flush()
        await db.refresh(details)

    return CurrentUserEnvelope(data=_to_current_user(current_user, details))


@users_router.post("/me/avatar", response_model=CurrentUserEnvelope, summary="Upload user profile avatar")
async def upload_user_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUserEnvelope:
    import os
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    content_type = (file.content_type or "").lower()

    allowed_types = {"image/jpeg", "image/png", "image/jpg"}
    allowed_exts = {".jpg", ".jpeg", ".png"}

    if content_type not in allowed_types and ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPG, JPEG, and PNG image files are allowed."
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded."
        )

    file_url, s3_key = s3_storage_service.upload_avatar(
        file_bytes=file_bytes,
        filename=filename or "avatar.png",
        user_id=current_user.id,
        content_type=content_type or "image/png"
    )

    details = (
        await db.execute(select(UserDetails).where(UserDetails.user_id == current_user.id))
    ).scalar_one_or_none()

    if details is None:
        from app.services.user_details_service import _generate_unique_profile_id
        from app.core.timezone import to_ist
        profile_id = await _generate_unique_profile_id(db)
        registered_at = to_ist(current_user.created_at)
        name_parts = (current_user.display_name or current_user.username.split("@", 1)[0]).split(" ", 1)
        first_name = name_parts[0] or "User"
        last_name = name_parts[1] if len(name_parts) > 1 else "Profile"

        details = UserDetails(
            profile_id=profile_id,
            user_id=current_user.id,
            first_name=first_name,
            last_name=last_name,
            email=current_user.username,
            mobile_number="9999999999",
            avatar_url=file_url,
            created_at=registered_at,
            updated_at=registered_at,
        )
        db.add(details)
    else:
        details.avatar_url = file_url

    await db.flush()
    await db.refresh(details)

    return CurrentUserEnvelope(data=_to_current_user(current_user, details))


@users_router.get("/{user_id}/avatar", summary="Stream user profile avatar image")
async def get_user_avatar_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Public proxy endpoint to stream the user's profile avatar image."""
    details = (
        await db.execute(select(UserDetails).where(UserDetails.user_id == user_id))
    ).scalar_one_or_none()

    if not details or not details.avatar_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found")

    file_bytes, content_type = s3_storage_service.get_avatar_bytes(details.avatar_url)
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar file not found")

    return Response(content=file_bytes, media_type=content_type)


# Extended profile ("user_details") 

@users_router.post(
    "/me/details",
    response_model=UserDetailsResponse,
    summary="Create or update the current user's extended profile",
)
@limiter.limit("20/minute")
async def upsert_user_details(
    request: Request,
    response: Response,
    payload: CreateUserDetailsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserDetailsResponse:
    """Upsert: creates the profile if none exists yet, otherwise overwrites it with
    the given fields. Returns 201 on create, 200 on update."""
    result, created = await user_details_service.upsert(payload, current_user, db)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return result


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