"""
Axiora Pulse – Core AI Orchestration Engine
FastAPI Application Entry Point
──────────────────────────────────────────────────────────────────────────────
Start the server:
  uvicorn main:app --reload --host 0.0.0.0 --port 8000

Swagger UI:   http://localhost:8000/docs
ReDoc:        http://localhost:8000/redoc
Health:       http://localhost:8000/health
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.limiter import limiter
from app.db.database import run_migrations
from app.skills.skill_registry import skill_registry

# ── Logging must be configured before any other imports ───────────────────────
setup_logging()
logger = logging.getLogger(__name__)


# ── Startup / Shutdown lifecycle ───────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ────────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info(f"  {settings.app_name}  v{settings.app_version}")
    logger.info("=" * 60)

    # Validate security config (JWT Secret validation)
    _validate_security_config()

    # Apply any pending DB migrations (Alembic upgrade head)
    await run_migrations()

    # Load all skill YAML files into the registry
    skill_registry.load_all()
    loaded = skill_registry.list_skills()
    logger.info(f"Skill registry ready: {loaded}")

    # Validate that the configured LLM provider credentials exist
    _validate_provider_config()

    logger.info("Server is ready.")
    if settings.debug:
        logger.info(f"  Docs  →  http://localhost:8000/docs")
    logger.info(f"  Health →  http://localhost:8000/health")
    logger.info("=" * 60)

    yield  # ← Application runs here

    # ── SHUTDOWN ───────────────────────────────────────────────────────────────
    logger.info(f"Shutting down {settings.app_name}…")


def _validate_provider_config() -> None:
    """Warn at startup if the configured provider has no API key."""
    provider = settings.default_provider
    if provider == "huggingface" and not settings.hf_token:
        logger.warning(
            "⚠  HF_TOKEN is not set. "
            "Add it to your .env file. "
            "Get a token at https://huggingface.co/settings/tokens"
        )
    elif provider == "openai" and not settings.openai_api_key:
        logger.warning("⚠  OPENAI_API_KEY is not set. Add it to your .env file.")
    else:
        logger.info(f"LLM provider: {provider} | model: {settings.default_model}")


def _validate_security_config() -> None:
    """Validate JWT secret is customized if not in debug mode."""
    if settings.jwt_secret_key == "axiora-pulse-change-this-secret-in-production" and not settings.debug:
        logger.critical("CRITICAL SECURITY ERROR: JWT_SECRET_KEY is using the insecure default value in production mode!")
        raise ValueError(
            "CRITICAL SECURITY ERROR: JWT_SECRET_KEY is using the insecure default value in production mode! "
            "Please configure JWT_SECRET_KEY in your .env file."
        )


# ── FastAPI app ────────────────────────────────────────────────────────────────

# Tags listed in alphabetical order — FastAPI preserves this order in Swagger UI.
_OPENAPI_TAGS = [
    {
        "name": "AI Mentor",
        "description": "Founder-facing AI Mentor: chat.",
    },
    {
        "name": "Auth",
        "description": "User registration and login. Issues JWT Bearer tokens for authenticated access.",
    },
    {
        "name": "Health",
        "description": "Global server health check — confirms startup, LLM provider, and loaded skills.",
    },
    {
        "name": "Orchestration",
        "description": "Idea-validation orchestration workflows powered by MCP, Skills, and Agentic Workflows.",
    },
    {
        "name": "Root",
        "description": "Root discovery endpoint — lists available API routes.",
    },
]

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Core AI Orchestration Engine for Axiora Pulse. "
        "Converts founder ideas into structured validation journeys using "
        "MCP, Skills, and Agentic Workflows."
    ),
    openapi_tags=_OPENAPI_TAGS,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# ── Rate Limiter ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ───────────────────────────────────────────────────────────────────────
# Parse allowed origins from settings
origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
if settings.debug and (not origins or "*" in origins):
    origins = ["*"]
    allow_credentials = False
else:
    allow_credentials = "*" not in origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ────────────────────────────────────────────────────────────────────
from app.api.v1 import orchestration as orchestration_router
from app.api.v1 import mentor as mentor_router
from app.api.v1 import auth as auth_router

app.include_router(orchestration_router.router, prefix="/api/v1")
app.include_router(mentor_router.router, prefix="/api/v1")
app.include_router(auth_router.router, prefix="/api/v1")


# ── Root endpoints ─────────────────────────────────────────────────────────────

@app.get("/", tags=["Root"], summary="Root endpoint")
async def root() -> dict:
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "validate_idea": "POST /api/v1/orchestration/run",
            "mentor_chat":   "POST /api/v1/mentor/chat",
        },
    }


@app.get("/health", tags=["Health"], summary="Global health check")
async def health() -> dict:
    """
    Returns overall server health, loaded skills, and provider configuration.
    Use this to confirm the server started correctly.
    """
    skills = skill_registry.list_skills()

    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "llm_provider": settings.default_provider,
        "llm_model": settings.default_model,
        "skills_loaded": skills,
        "skills_count": len(skills),
        "provider_configured": _is_provider_configured(),
    }


def _is_provider_configured() -> bool:
    provider = settings.default_provider
    if provider == "huggingface":
        return bool(settings.hf_token)
    elif provider == "openai":
        return bool(settings.openai_api_key)
    elif provider == "anthropic":
        return bool(settings.anthropic_api_key)
    return False
