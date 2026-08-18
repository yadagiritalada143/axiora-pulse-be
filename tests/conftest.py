import os
import shutil
import pytest
import pytest_asyncio
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import patch
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from httpx import AsyncClient, ASGITransport

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/axiora_test",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("OTP_EXPIRE_MINUTES", "10")

from app.db.models import Base, User
from app.core.security import hash_password_async
from main import app
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.core.limiter import limiter

# Disable rate limiting during tests
limiter.enabled = False

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

_UPLOADS_WORKSPACES_DIR = Path("uploads/workspaces")


@pytest.fixture(autouse=True)
def _cleanup_local_upload_files():
    """Remove any files s3_storage_service falls back to writing under
    uploads/workspaces/ during a test (no AWS credentials configured in
    the test environment). Prevents test runs from leaving disk artifacts
    behind on every pytest invocation. Tracks individual files (not just
    top-level workspace directories) so new files written inside an
    already-existing workspace folder are still caught."""
    before = set(_UPLOADS_WORKSPACES_DIR.rglob("*")) if _UPLOADS_WORKSPACES_DIR.exists() else set()
    yield
    if not _UPLOADS_WORKSPACES_DIR.exists():
        return
    after = set(_UPLOADS_WORKSPACES_DIR.rglob("*"))
    for entry in sorted(after - before, key=lambda p: len(p.parts), reverse=True):
        if not entry.exists():
            continue
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink(missing_ok=True)

@pytest.fixture(autouse=True)
def _reset_dependency_overrides():
    """Guarantee app.dependency_overrides is empty before and after every test.

    Several tests mutate app.dependency_overrides[get_current_user] directly
    via a local `authenticate_as()`/`_mock_current_user` helper instead of
    going through the `client` fixture's teardown. Relying solely on that
    fixture's clear() makes cleanup dependent on test/fixture ordering; this
    autouse fixture removes that dependency so an override set in one test
    can never leak into another regardless of execution order.
    """
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def stub_enqueue_email_job():
    """Replace the fire-and-forget transactional email dispatcher with a
    plain Mock so registration/password-reset flows don't spawn real
    background asyncio tasks that attempt live SMTP connections during
    tests. Autoused below; request this fixture by name in a test to
    assert on how it was called."""
    with patch("app.services.auth_service.enqueue_email_job") as mock_enqueue:
        yield mock_enqueue


@pytest.fixture(autouse=True)
def _autouse_stub_enqueue_email_job(stub_enqueue_email_job):
    yield stub_enqueue_email_job


@pytest_asyncio.fixture
async def test_engine():
    # Prefer a PostgreSQL test database when TEST_DATABASE_URL is provided.
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    if TEST_DATABASE_URL.startswith("sqlite"):
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def db_transaction_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        async_session = async_sessionmaker(
            bind=connection, class_=AsyncSession, expire_on_commit=False
        )
        async with async_session() as session:
            try:
                yield session
            finally:
                if session.in_transaction():
                    await session.rollback()
                await session.close()
                if transaction.is_active:
                    await transaction.rollback()

@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
        await session.rollback()
        # Clear out tables after each test to ensure test isolation
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()

@pytest_asyncio.fixture
async def normal_user(db_session: AsyncSession) -> User:
    user = User(
        username="user@axiorapulse.com",
        password=await hash_password_async("Test@12345"),
        role="user",
        register_mfa=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        username="admin@axiorapulse.com",
        password=await hash_password_async("Test@12345"),
        role="admin",
        register_mfa=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    # Set default database override
    async def _override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = _override_get_db
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
        
    # Clean up overrides
    app.dependency_overrides.clear()
