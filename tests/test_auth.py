import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password_async, verify_password_async
from app.db.models import User
from app.services.email_service import OTPResult


def successful_otp_result() -> OTPResult:
    return OTPResult(success=True, channel="email")


async def create_user(
    db_session: AsyncSession,
    *,
    username: str = "verified@axiorapulse.com",
    password: str = "Test@12345",
    register_mfa: bool = True,
    role: str = "user",
) -> User:
    user = User(
        username=username,
        password=await hash_password_async(password),
        role=role,
        register_mfa=register_mfa,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def get_user_by_username(db_session: AsyncSession, username: str) -> User | None:
    result = await db_session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


@pytest.mark.asyncio
async def test_register_success_persists_user_and_dispatches_otp(
    client: AsyncClient,
    db_session: AsyncSession,
):
    with patch(
        "app.services.auth_service.dispatch_otp",
        new=AsyncMock(return_value=successful_otp_result()),
    ) as dispatch_otp:
        response = await client.post(
            "/api/v1/auth/register",
            json={"username": "NewUser@AxioraPulse.com", "password": "Test@12345"},
        )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["username"] == "newuser@axiorapulse.com"
    assert data["registerMFA"] is False

    user = await get_user_by_username(db_session, "newuser@axiorapulse.com")
    assert user is not None
    assert user.register_otp is not None
    assert await verify_password_async("Test@12345", user.password)
    dispatch_otp.assert_awaited_once_with("newuser@axiorapulse.com", user.register_otp)


@pytest.mark.asyncio
async def test_register_existing_user_returns_conflict(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await create_user(db_session, username="dupe@axiorapulse.com")

    with patch("app.services.auth_service.dispatch_otp", new=AsyncMock()) as dispatch_otp:
        response = await client.post(
            "/api/v1/auth/register",
            json={"username": "dupe@axiorapulse.com", "password": "Test@12345"},
        )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"] == "An account with this email already exists."
    dispatch_otp.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_invalid_email_is_rejected(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "not-an-email", "password": "Test@12345"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_verify_registration_otp_success_returns_tokens(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(
        db_session,
        username="otp-success@axiorapulse.com",
        register_mfa=False,
    )
    user.register_otp = 123456
    user.register_otp_expiry = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/verifyOTP",
        json={
            "id": user.id,
            "otp": 123456,
            "flow": "register",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "success"
    assert data["access_token"]
    assert data["refresh_token"]

    await db_session.refresh(user)
    assert user.register_mfa is True
    assert user.register_otp is None


@pytest.mark.asyncio
async def test_verify_registration_otp_invalid_then_invalidates_after_three_attempts(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(
        db_session,
        username="otp-invalid@axiorapulse.com",
        register_mfa=False,
    )
    user.register_otp = 111111
    user.register_otp_expiry = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
    await db_session.commit()

    for _ in range(2):
        response = await client.post(
            "/api/v1/auth/verifyOTP",
            json={"id": user.id, "otp": 999999, "flow": "register"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"] == "OTP is wrong"

    response = await client.post(
        "/api/v1/auth/verifyOTP",
        json={"id": user.id, "otp": 999999, "flow": "register"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "failed"
    assert "Too many failed attempts" in response.json()["message"]
    await db_session.refresh(user)
    assert user.register_otp is None
    assert user.register_otp_attempts == 0


@pytest.mark.asyncio
async def test_verify_registration_otp_expired_clears_code(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(
        db_session,
        username="otp-expired@axiorapulse.com",
        register_mfa=False,
    )
    user.register_otp = 222222
    user.register_otp_expiry = datetime.now(tz=timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/verifyOTP",
        json={"id": user.id, "otp": 222222, "flow": "register"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "OTP is expired !"
    await db_session.refresh(user)
    assert user.register_otp is None


@pytest.mark.asyncio
async def test_user_login_dispatches_mfa_code_and_updates_database(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(db_session, username="login@axiorapulse.com")

    with patch(
        "app.services.auth_service.dispatch_login_otp",
        new=AsyncMock(return_value=successful_otp_result()),
    ) as dispatch_login_otp:
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": user.username, "password": "Test@12345"},
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "success"
    await db_session.refresh(user)
    assert user.login_otp is not None
    dispatch_login_otp.assert_awaited_once_with(user.username, user.login_otp)


@pytest.mark.asyncio
async def test_admin_login_returns_jwt_for_standard_login(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await create_user(
        db_session,
        username="admin-login@axiorapulse.com",
        role="admin",
    )

    response = await client.post(
        "/api/v1/auth/admin/login",
        json={"username": "admin-login@axiorapulse.com", "password": "Test@12345"},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "success"
    assert data["role"] == "admin"
    assert data["access_token"]
    assert data["refresh_token"]


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(client: AsyncClient, db_session: AsyncSession):
    user = await create_user(db_session, username="wrong-password@axiorapulse.com")

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "Wrong@12345"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_login_rejects_unverified_account(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(
        db_session,
        username="unverified-login@axiorapulse.com",
        register_mfa=False,
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "Test@12345"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_verify_login_success_returns_tokens_and_clears_otp(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(db_session, username="verify-login@axiorapulse.com")
    user.login_otp = 333333
    user.login_otp_expiry = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/verify-login",
        json={"emailOrMobile": user.username, "otp": 333333},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["access_token"]
    assert data["refresh_token"]
    await db_session.refresh(user)
    assert user.login_otp is None


@pytest.mark.asyncio
async def test_verify_login_rejects_incorrect_expired_and_empty_values(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(db_session, username="login-otp-cases@axiorapulse.com")
    user.login_otp = 444444
    user.login_otp_expiry = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
    await db_session.commit()

    wrong_response = await client.post(
        "/api/v1/auth/verify-login",
        json={"emailOrMobile": user.username, "otp": 111111},
    )
    assert wrong_response.status_code == status.HTTP_400_BAD_REQUEST

    user.login_otp = 444444
    user.login_otp_expiry = datetime.now(tz=timezone.utc) - timedelta(minutes=1)
    await db_session.commit()
    expired_response = await client.post(
        "/api/v1/auth/verify-login",
        json={"emailOrMobile": user.username, "otp": 444444},
    )
    assert expired_response.status_code == status.HTTP_400_BAD_REQUEST

    empty_response = await client.post(
        "/api/v1/auth/verify-login",
        json={"emailOrMobile": "", "otp": ""},
    )
    assert empty_response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_forgot_password_request_is_successful_and_dispatches_without_network(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(db_session, username="forgot-request@axiorapulse.com")

    with patch(
        "app.services.auth_service.dispatch_password_reset_otp",
        new=AsyncMock(return_value=successful_otp_result()),
    ) as dispatch_reset_otp:
        response = await client.post(
            "/api/v1/auth/forgot-password/request",
            json={"emailOrMobile": user.username},
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "success"
    await db_session.refresh(user)
    assert user.forgot_password_otp is not None
    dispatch_reset_otp.assert_awaited_once_with(user.username, user.forgot_password_otp)


@pytest.mark.asyncio
async def test_forgot_password_verify_returns_signed_reset_token(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(db_session, username="forgot-verify@axiorapulse.com")
    user.forgot_password_otp = 555555
    user.forgot_password_otp_expiry = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/forgot-password/verify",
        json={"emailOrMobile": user.username, "code": 555555},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    payload = jwt.decode(
        data["reset_token"],
        os.getenv("JWT_SECRET_KEY"),
        algorithms=[os.getenv("JWT_ALGORITHM")],
    )
    assert payload["sub"] == str(user.id)
    assert payload["scope"] == "password_reset"
    await db_session.refresh(user)
    assert user.forgot_password_otp is None


@pytest.mark.asyncio
async def test_forgot_password_verify_rejects_incorrect_and_expired_codes(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(db_session, username="forgot-cases@axiorapulse.com")
    user.forgot_password_otp = 666666
    user.forgot_password_otp_expiry = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
    await db_session.commit()

    wrong_response = await client.post(
        "/api/v1/auth/forgot-password/verify",
        json={"emailOrMobile": user.username, "code": 123456},
    )
    assert wrong_response.status_code == status.HTTP_400_BAD_REQUEST

    user.forgot_password_otp = 666666
    user.forgot_password_otp_expiry = datetime.now(tz=timezone.utc) - timedelta(minutes=1)
    await db_session.commit()
    expired_response = await client.post(
        "/api/v1/auth/forgot-password/verify",
        json={"emailOrMobile": user.username, "code": 666666},
    )
    assert expired_response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_forgot_password_reset_updates_hash_and_revokes_old_access_token(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(db_session, username="forgot-reset@axiorapulse.com")
    old_hash = user.password
    old_access_token = jwt.encode(
        {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "iat": datetime.now(tz=timezone.utc) - timedelta(minutes=5),
            "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=30),
        },
        os.getenv("JWT_SECRET_KEY"),
        algorithm=os.getenv("JWT_ALGORITHM"),
    )
    reset_token = jwt.encode(
        {
            "sub": str(user.id),
            "username": user.username,
            "scope": "password_reset",
            "iat": datetime.now(tz=timezone.utc),
            "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=10),
        },
        os.getenv("JWT_SECRET_KEY"),
        algorithm=os.getenv("JWT_ALGORITHM"),
    )

    response = await client.post(
        "/api/v1/auth/forgot-password/reset",
        json={"reset_token": reset_token, "new_password": "NewPass@12345"},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Password has been reset successfully. Please log in with your new password."
    await db_session.refresh(user)
    assert user.password != old_hash
    assert await verify_password_async("NewPass@12345", user.password)
    assert user.password_changed_at is not None

    protected_response = await client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {old_access_token}"},
        json={"current_password": "NewPass@12345", "new_password": "Another@12345"},
    )
    assert protected_response.status_code == status.HTTP_401_UNAUTHORIZED

    reused_response = await client.post(
        "/api/v1/auth/forgot-password/reset",
        json={"reset_token": reset_token, "new_password": "Another@12345"},
    )
    assert reused_response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_forgot_password_reset_rejects_invalid_and_expired_tokens(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await create_user(db_session, username="forgot-reset-fail@axiorapulse.com")
    expired_reset_token = jwt.encode(
        {
            "sub": str(user.id),
            "username": user.username,
            "scope": "password_reset",
            "iat": datetime.now(tz=timezone.utc) - timedelta(minutes=20),
            "exp": datetime.now(tz=timezone.utc) - timedelta(minutes=1),
        },
        os.getenv("JWT_SECRET_KEY"),
        algorithm=os.getenv("JWT_ALGORITHM"),
    )

    invalid_response = await client.post(
        "/api/v1/auth/forgot-password/reset",
        json={"reset_token": "not-a-real-token", "new_password": "NewPass@12345"},
    )
    assert invalid_response.status_code == status.HTTP_401_UNAUTHORIZED

    expired_response = await client.post(
        "/api/v1/auth/forgot-password/reset",
        json={"reset_token": expired_reset_token, "new_password": "NewPass@12345"},
    )
    assert expired_response.status_code == status.HTTP_401_UNAUTHORIZED
