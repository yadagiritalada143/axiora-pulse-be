"""
OpenAI Provider – alternative to HuggingFace.
Set DEFAULT_PROVIDER=openai and OPENAI_API_KEY in .env to use this.
"""
import logging

from openai import AsyncOpenAI, APITimeoutError, APIError

from app.core.config import settings
from app.llm.llm_gateway import LLMGateway, LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMGateway):
    def __init__(self):
        if not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Add it to your .env file."
            )
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout,
            max_retries=settings.openai_max_retries,
        )
        self._default_model = settings.default_model or "gpt-4o-mini"
        if "/" in self._default_model or "llama" in self._default_model.lower():
            self._default_model = "gpt-4o-mini"

    def get_provider_name(self) -> str:
        return "openai"

    def get_default_model(self) -> str:
        return self._default_model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self._default_model
        messages = []

        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.user_prompt})

        kwargs: dict = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        if request.response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            usage = response.usage

            return LLMResponse(
                content=content,
                model=model,
                provider="openai",
                tokens_input=usage.prompt_tokens if usage else 0,
                tokens_output=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                success=True,
            )

        except APITimeoutError:
            return LLMResponse(content="", model=model, provider="openai",
                               success=False, error="Request timed out.")
        except APIError as e:
            return LLMResponse(content="", model=model, provider="openai",
                               success=False, error=str(e))
        except Exception as e:
            logger.error(f"[OpenAI] Unexpected error: {e}", exc_info=True)
            return LLMResponse(content="", model=model, provider="openai",
                               success=False, error="Unexpected error.")
