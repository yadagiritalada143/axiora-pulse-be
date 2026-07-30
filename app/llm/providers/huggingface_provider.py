"""
HuggingFace Inference API Provider
────────────────────────────────────────────────────────────────────────────────
Supports stream=True for token/chunk streaming.
"""
import json
import logging
import os
import re
from typing import AsyncGenerator

from dotenv import load_dotenv
from openai import AsyncOpenAI, APITimeoutError, APIError

from app.llm.llm_gateway import LLMGateway, LLMRequest, LLMResponse

load_dotenv()

logger = logging.getLogger(__name__)

_JSON_SYSTEM_SUFFIX = (
    "\n\nCRITICAL INSTRUCTION: You MUST respond with ONLY a valid JSON object. "
    "No markdown, no code fences, no explanation text before or after the JSON. "
    "Start your response with '{' and end with '}'. Nothing else."
)


class HuggingFaceProvider(LLMGateway):
    def __init__(self):
        hf_token = os.getenv("HF_TOKEN")
        if not hf_token:
            raise ValueError(
                "HF_TOKEN is not set. "
                "Get your token at https://huggingface.co/settings/tokens "
                "and add it to your .env file."
            )
        self.client = AsyncOpenAI(
            api_key=hf_token,
            base_url=os.getenv("HF_BASE_URL"),
            timeout=int(os.getenv("HF_TIMEOUT")),
            max_retries=int(os.getenv("HF_MAX_RETRIES")),
        )
        self._default_model = (
            os.getenv("HF_MODEL")
            or os.getenv("DEFAULT_MODEL")
            or "meta-llama/Llama-3.1-8B-Instruct"
        )

    def get_provider_name(self) -> str:
        return "huggingface"

    def get_default_model(self) -> str:
        return self._default_model

    async def complete_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Stream response tokens/chunks word-by-word/line-by-line."""
        model = request.model or self._default_model
        messages = []

        system_content = request.system_prompt or ""
        if request.response_format == "json":
            system_content += _JSON_SYSTEM_SUFFIX

        if system_content:
            messages.append({"role": "system", "content": system_content})

        messages.append({"role": "user", "content": request.user_prompt})

        try:
            stream_resp = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
            )
            async for chunk in stream_resp:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"[HuggingFace Stream Error]: {e}")
            yield f"[Stream Error: {e}]"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self._default_model

        if request.stream:
            chunks = []
            async for chunk in self.complete_stream(request):
                chunks.append(chunk)
            raw_content = "".join(chunks)
            if request.response_format == "json":
                raw_content = self._extract_json(raw_content)
            return LLMResponse(
                content=raw_content,
                model=model,
                provider="huggingface",
                total_tokens=len(raw_content) // 4,
                success=True,
            )

        messages = []
        system_content = request.system_prompt or ""
        if request.response_format == "json":
            system_content += _JSON_SYSTEM_SUFFIX

        if system_content:
            messages.append({"role": "system", "content": system_content})

        messages.append({"role": "user", "content": request.user_prompt})

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )

            raw_content = response.choices[0].message.content or ""
            usage = response.usage

            if request.response_format == "json":
                raw_content = self._extract_json(raw_content)

            return LLMResponse(
                content=raw_content,
                model=model,
                provider="huggingface",
                tokens_input=usage.prompt_tokens if usage else 0,
                tokens_output=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                success=True,
            )

        except APITimeoutError:
            return LLMResponse(content="", model=model, provider="huggingface",
                               success=False, error="Request timed out.")
        except APIError as e:
            return LLMResponse(content="", model=model, provider="huggingface",
                               success=False, error=str(e))
        except Exception as e:
            logger.error(f"[HuggingFace] Unexpected error: {e}", exc_info=True)
            return LLMResponse(content="", model=model, provider="huggingface",
                               success=False, error="Unexpected error.")

    @staticmethod
    def _extract_json(text: str) -> str:
        if not text:
            return "{}"

        text = re.sub(r"```(?:json)?\s*", "", text)
        text = re.sub(r"```\s*$", "", text)
        text = text.strip()

        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            candidate = match.group()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        return text
