from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "Axiora Pulse AI Engine"
    app_version: str = "1.0.0"
    debug: bool = False
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    # ── LLM Provider ─────────────────────────────────────────────────────────
    default_provider: Literal["huggingface", "openai", "anthropic", "azure_openai"] = "huggingface"
    default_model: str = "meta-llama/Llama-3.2-3B-Instruct"

    # ── Hugging Face ─────────────────────────────────────────────────────────
    hf_token: str = ""
    hf_timeout: int = 120
    hf_max_retries: int = 2
    # HF Inference Router is OpenAI-compatible and supports multiple providers
    hf_base_url: str = "https://router.huggingface.co/v1"

    # ── OpenAI ───────────────────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_timeout: int = 60
    openai_max_retries: int = 2

    # ── Anthropic ────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""

    # ── Azure OpenAI ─────────────────────────────────────────────────────────
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-02-01"
    azure_openai_deployment: str = ""

    # ── Validation Scoring Weights ────────────────────────────────────────────
    # Phase 1: only idea_validation_agent is active (weight = 1.0)
    # These will be normalized to 1.0 total when all agents are added.
    idea_clarity_weight: float = 0.20
    market_opportunity_weight: float = 0.25
    survey_signal_weight: float = 0.25
    gtm_readiness_weight: float = 0.15
    financial_readiness_weight: float = 0.15

    # ── Auth / JWT ────────────────────────────────────────────────────────────
    jwt_secret_key: str = "axiora-pulse-change-this-secret-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # ── OTP ───────────────────────────────────────────────────────────────────
    otp_expire_minutes: int = 10

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/axiora_local_db"

    # ── SMTP / Email ──────────────────────────────────────────────────────────
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "Axiora Pulse"


settings = Settings()
