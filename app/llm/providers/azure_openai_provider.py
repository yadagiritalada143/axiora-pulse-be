"""
Azure OpenAI Provider – stub for Phase 2+.
Set DEFAULT_PROVIDER=azure_openai and related env vars in .env to use this.
"""
from app.llm.llm_gateway import LLMGateway, LLMRequest, LLMResponse


class AzureOpenAIProvider(LLMGateway):
    """Azure OpenAI provider — not yet implemented (Phase 2+)."""

    def get_provider_name(self) -> str:
        return "azure_openai"

    def get_default_model(self) -> str:
        return "gpt-4o"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError(
            "Azure OpenAI provider is not implemented yet. "
            "Use DEFAULT_PROVIDER=huggingface or DEFAULT_PROVIDER=openai."
        )
