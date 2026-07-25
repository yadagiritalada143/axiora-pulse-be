"""
Anthropic Claude Provider – stub for Phase 2+.
Set DEFAULT_PROVIDER=anthropic and ANTHROPIC_API_KEY in .env to use this.
Set ANTHROPIC_MODEL in .env to choose the Claude model (default: claude-3-5-sonnet-20241022).
"""
import os

from dotenv import load_dotenv
from app.llm.llm_gateway import LLMGateway, LLMRequest, LLMResponse

load_dotenv()


class AnthropicProvider(LLMGateway):
    """Anthropic Claude provider — not yet implemented (Phase 2+)."""

    def __init__(self):
        self._default_model = (
            os.getenv("ANTHROPIC_MODEL")
            or os.getenv("DEFAULT_MODEL")
            or "claude-3-5-sonnet-20241022"
        )

    def get_provider_name(self) -> str:
        return "anthropic"

    def get_default_model(self) -> str:
        return self._default_model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError(
            "Anthropic provider is not implemented yet. "
            "Use DEFAULT_PROVIDER=huggingface or DEFAULT_PROVIDER=openai."
        )
