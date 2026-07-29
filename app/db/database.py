"""
app/db/database.py
────────────────────────────────────────────────────────────────────────────────
Async SQLAlchemy engine, session factory, FastAPI dependency, and migration runner.

Migration strategy:
  - `run_migrations()` is called once at startup (from main.py lifespan).
  - It runs `alembic upgrade head` programmatically so ANY pending migration
    (new table, new column, rename, etc.) is applied automatically.
  - This means deploying to a fresh database requires zero manual SQL —
    just start the server.

Session usage:
  - Inject `AsyncSession` via `Depends(get_db)` in route handlers.
"""
import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()

_DATABASE_URL = os.getenv("DATABASE_URL", "")

logger = logging.getLogger(__name__)


def _mask_database_url(url: str) -> str:
    """Redact credentials from database URLs before logging."""
    if not url:
        return "<empty>"
    if "://" not in url:
        return url

    scheme, remainder = url.split("://", 1)
    if "@" not in remainder:
        return f"{scheme}://<redacted>"

    auth, host = remainder.rsplit("@", 1)
    if ":" in auth:
        username, _ = auth.split(":", 1)
        return f"{scheme}://{username}:***@{host}"
    return f"{scheme}://***@{host}"

# ── Engine ─────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    _DATABASE_URL,
    echo=False,          # Set to True to log all SQL queries (debug only)
    pool_pre_ping=True,  # Detect stale connections before handing them out
    pool_size=10,
    max_overflow=20,
)

# ── Session factory ────────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Keep ORM objects accessible after commit
    autoflush=False,
    autocommit=False,
)


# ── FastAPI dependency ─────────────────────────────────────────────────────────

async def get_db():  # type: ignore[return]
    """Yield a managed async database session.

    Usage:
        async def my_endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            logger.exception("Database session error while handling request")
            await session.rollback()
            raise


# ── Migration runner ───────────────────────────────────────────────────────────

def _get_alembic_cfg() -> Config:
    """Build an Alembic Config pointing at our alembic.ini."""
    # Locate alembic.ini relative to this file:
    # app/db/database.py  →  ../../alembic.ini  (backend root)
    backend_root = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_root / "alembic.ini"

    cfg = Config(str(ini_path))
    # Escape % signs for ConfigParser interpolation (e.g. %40 → %%40).
    # Without this, URL-encoded characters in the DB password crash configparser.
    safe_url = _DATABASE_URL.replace("%", "%%")
    cfg.set_main_option("sqlalchemy.url", safe_url)
    return cfg


async def run_migrations() -> None:
    """Apply all pending Alembic migrations (upgrade to head).

    Called once during application startup in `main.py`.
    On a fresh database this creates all tables.
    On an existing database it applies only new migrations.
    The operation is idempotent — running it when already at head is a no-op.
    """
    import asyncio

    logger.info("Running DB migrations (alembic upgrade head)…")
    logger.info("Database URL: %s", _mask_database_url(_DATABASE_URL))

    cfg = _get_alembic_cfg()

    try:
        # Alembic's command.upgrade() is synchronous — run it in a thread pool
        # to keep the async event loop unblocked during startup.
        await asyncio.to_thread(command.upgrade, cfg, "head")
    except Exception:
        logger.exception(
            "Database migration failed. Check that PostgreSQL is running and DATABASE_URL is correct."
        )
        raise

    logger.info("DB migrations complete — schema is up to date.")
