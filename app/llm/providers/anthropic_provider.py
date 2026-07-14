"""
Anthropic Claude Provider – stub for Phase 2+.
Set DEFAULT_PROVIDER=anthropic and ANTHROPIC_API_KEY in .env to use this.
"""
from app.llm.llm_gateway import LLMGateway, LLMRequest, LLMResponse


class AnthropicProvider(LLMGateway):
    """Anthropic Claude provider — not yet implemented (Phase 2+)."""

    def get_provider_name(self) -> str:
        return "anthropic"

    def get_default_model(self) -> str:
        return "claude-3-5-sonnet-20241022"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError(
            "Anthropic provider is not implemented yet. "
            "Use DEFAULT_PROVIDER=huggingface or DEFAULT_PROVIDER=openai."
        )
