"""
Azure OpenAI Provider – stub for Phase 2+.
Set DEFAULT_PROVIDER=azure_openai and related env vars in .env to use this.
Set AZURE_OPENAI_MODEL in .env to choose the deployment model (default: gpt-4o).
"""
import os

from dotenv import load_dotenv
from app.llm.llm_gateway import LLMGateway, LLMRequest, LLMResponse

load_dotenv()


class AzureOpenAIProvider(LLMGateway):
    """Azure OpenAI provider — not yet implemented (Phase 2+)."""

    def __init__(self):
        self._default_model = (
            os.getenv("AZURE_OPENAI_MODEL")
            or os.getenv("DEFAULT_MODEL")
            or "gpt-4o"
        )

    def get_provider_name(self) -> str:
        return "azure_openai"

    def get_default_model(self) -> str:
        return self._default_model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError(
            "Azure OpenAI provider is not implemented yet. "
            "Use DEFAULT_PROVIDER=huggingface or DEFAULT_PROVIDER=openai."
        )
