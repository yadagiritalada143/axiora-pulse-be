"""Extended user-profile ("user_details") operations — one row per User, 1:1 on user_id."""
import logging
import secrets

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezone import now_ist, to_ist
from app.db.models import User, UserDetails
from app.models.user_details_models import CreateUserDetailsRequest, UpdateUserDetailsRequest, UserDetailsResponse

logger = logging.getLogger(__name__)

_PROFILE_ID_PREFIX = "AXR"
_PROFILE_ID_MAX_ATTEMPTS = 10


async def _generate_unique_profile_id(db: AsyncSession) -> str:
    """Generate a profile id like 'AXR-847291', retrying on the rare collision."""
    for _ in range(_PROFILE_ID_MAX_ATTEMPTS):
        candidate = f"{_PROFILE_ID_PREFIX}-{secrets.randbelow(900000) + 100000}"
        existing = await db.execute(select(UserDetails.id).where(UserDetails.profile_id == candidate))
        if existing.scalar_one_or_none() is None:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not generate a unique profile ID. Please try again.",
    )


async def _get_by_user_id(db: AsyncSession, user_id: int) -> UserDetails | None:
    result = await db.execute(select(UserDetails).where(UserDetails.user_id == user_id))
    return result.scalar_one_or_none()


class UserDetailsService:
    async def create(
        self, payload: CreateUserDetailsRequest, current_user: User, db: AsyncSession
    ) -> UserDetailsResponse:
        """Create the extended profile for the current user. Fails if one already exists."""
        existing = await _get_by_user_id(db, current_user.id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A profile already exists for this user.",
            )

        profile_id = await _generate_unique_profile_id(db)
        registered_at = to_ist(current_user.created_at)
        # users.username is the login email — fall back to it when no email is given.
        email = str(payload.email).lower().strip() if payload.email else current_user.username.lower().strip()
        record = UserDetails(
            profile_id=profile_id,
            user_id=current_user.id,
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            email=email,
            mobile_number=payload.mobile_number,
            date_of_birth=payload.date_of_birth,
            gender=payload.gender,
            nationality=payload.nationality,
            communication_preferences=payload.communication_preferences,
            created_at=registered_at,
            updated_at=registered_at,
        )
        db.add(record)
        await db.flush()
        await db.refresh(record)
        logger.info("Created user_details profile_id=%s for user_id=%s", profile_id, current_user.id)
        return UserDetailsResponse.model_validate(record)

    async def get_own(self, current_user: User, db: AsyncSession) -> UserDetailsResponse:
        record = await _get_by_user_id(db, current_user.id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
        return UserDetailsResponse.model_validate(record)

    async def update_own(
        self, payload: UpdateUserDetailsRequest, current_user: User, db: AsyncSession
    ) -> UserDetailsResponse:
        record = await _get_by_user_id(db, current_user.id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")

        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            if field == "email" and value is not None:
                value = str(value).lower().strip()
            elif field in ("first_name", "last_name") and value is not None:
                value = value.strip()
            setattr(record, field, value)

        record.updated_at = now_ist()
        await db.flush()
        await db.refresh(record)
        logger.info("Updated user_details profile_id=%s for user_id=%s", record.profile_id, current_user.id)
        return UserDetailsResponse.model_validate(record)

    async def set_status_by_user_id(
        self, user_id: int, profile_status: str, db: AsyncSession
    ) -> UserDetailsResponse:
        """Admin action: set a user's profile_status (Active/Inactive/Suspended) by user_id."""
        record = await _get_by_user_id(db, user_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found for this user.")

        record.profile_status = profile_status
        record.updated_at = now_ist()
        await db.flush()
        await db.refresh(record)
        logger.info(
            "Admin set profile_status=%s for profile_id=%s (user_id=%s)",
            profile_status, record.profile_id, user_id,
        )
        return UserDetailsResponse.model_validate(record)

    @staticmethod
    async def touch_last_login(user_id: int, db: AsyncSession) -> None:
        """Stamp last_login_date (IST) on successful login. No-op if no profile exists yet."""
        record = await _get_by_user_id(db, user_id)
        if record is not None:
            record.last_login_date = now_ist()


user_details_service = UserDetailsService()
