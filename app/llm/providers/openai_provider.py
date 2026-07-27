"""
OpenAI Provider – alternative to HuggingFace.
Set DEFAULT_PROVIDER=openai and OPENAI_API_KEY in .env to use this.
"""
import logging
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI, APITimeoutError, APIError

from app.llm.llm_gateway import LLMGateway, LLMRequest, LLMResponse

load_dotenv()

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMGateway):
    def __init__(self):
        openai_api_key = os.getenv("OPENAI_API_KEY", "ollama")
        base_url = os.getenv("OPENAI_BASE_URL")
        if not openai_api_key and not base_url:
            raise ValueError(
                "OPENAI_API_KEY is not set. Add it to your .env file."
            )
        
        timeout_str = os.getenv("OPENAI_TIMEOUT", "60").strip()
        retries_str = os.getenv("OPENAI_MAX_RETRIES", "2").strip()
        timeout = int(timeout_str) if timeout_str.isdigit() else 60
        max_retries = int(retries_str) if retries_str.isdigit() else 2

        client_kwargs = {
            "api_key": openai_api_key or "ollama",
            "timeout": timeout,
            "max_retries": max_retries,
        }
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = AsyncOpenAI(**client_kwargs)
        self._default_model = (
            os.getenv("OPENAI_MODEL")
            or os.getenv("DEFAULT_MODEL")
            or "gpt-4o-mini"
        )
        # Strip any HuggingFace-style model names that may have slipped through DEFAULT_MODEL (only if base_url is not set)
        if not base_url and "/" in self._default_model and not self._default_model.startswith("ft:"):
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
        }

        if "gpt-5.4" in model or model.startswith("o1"):
            kwargs["max_completion_tokens"] = request.max_tokens
        else:
            kwargs["max_tokens"] = request.max_tokens

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
