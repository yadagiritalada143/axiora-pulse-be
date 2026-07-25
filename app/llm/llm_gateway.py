from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel


# ── Request / Response envelopes ───────────────────────────────────────────────

class LLMRequest(BaseModel):
    system_prompt: str = ""
    user_prompt: str
    model: str = ""                 # if empty, provider uses its default
    temperature: float = 0.3
    max_tokens: int = 2048
    # NOTE: response_format="json" is only supported by some providers (OpenAI).
    # For HuggingFace / Llama we rely on prompt engineering instead.
    response_format: str = "text"   # text | json


class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    tokens_input: int = 0
    tokens_output: int = 0
    total_tokens: int = 0
    success: bool = True
    error: Optional[str] = None


# ── Abstract gateway ───────────────────────────────────────────────────────────

class LLMGateway(ABC):
    """
    Abstract base class for all LLM providers.
    All agents call LLMGateway.complete() — never the provider SDK directly.
    """

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a prompt and return a structured response."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return provider name string, e.g. 'huggingface'."""

    @abstractmethod
    def get_default_model(self) -> str:
        """Return the default model for this provider."""


# ── Factory ────────────────────────────────────────────────────────────────────

def get_llm_gateway(provider: Optional[str] = None) -> LLMGateway:
    """
    Return the appropriate LLM gateway instance.
    Defaults to settings.default_provider.
    """
    import logging
    import os
    from dotenv import load_dotenv

    load_dotenv()
    logger = logging.getLogger(__name__)
    provider = provider or os.getenv("DEFAULT_PROVIDER")

    # Dynamic fallback: if HuggingFace is selected but token is missing,
    # and we have an OpenAI API key, fallback to OpenAI.
    if provider == "huggingface" and not os.getenv("HF_TOKEN") and os.getenv("OPENAI_API_KEY"):
        logger.warning(
            "HF_TOKEN is not set, but OPENAI_API_KEY is available. "
            "Dynamically falling back to 'openai' provider."
        )
        provider = "openai"

    if provider == "huggingface":
        from app.llm.providers.huggingface_provider import HuggingFaceProvider
        return HuggingFaceProvider()
    elif provider == "openai":
        from app.llm.providers.openai_provider import OpenAIProvider
        return OpenAIProvider()
    elif provider == "anthropic":
        from app.llm.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    elif provider == "azure_openai":
        from app.llm.providers.azure_openai_provider import AzureOpenAIProvider
        return AzureOpenAIProvider()
    else:
        raise ValueError(
            f"Unsupported LLM provider: '{provider}'. "
            "Choose from: huggingface, openai, anthropic, azure_openai"
        )
