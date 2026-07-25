"""
HuggingFace Inference API Provider
────────────────────────────────────────────────────────────────────────────────
HuggingFace's serverless inference endpoint is OpenAI-compatible.
We use the OpenAI Python SDK pointed at HF's base URL with the HF token.

Supported models (Llama 3.2 family):
  - meta-llama/Llama-3.2-1B-Instruct   (fastest, free tier)
  - meta-llama/Llama-3.2-3B-Instruct   (default — good balance)
  - meta-llama/Llama-3.2-11B-Vision-Instruct
  - meta-llama/Llama-3.2-90B-Vision-Instruct

Prerequisites:
  1. Create HF account → https://huggingface.co
  2. Accept Llama 3.2 license → https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct
  3. Generate read token → https://huggingface.co/settings/tokens
  4. Set HF_TOKEN in your .env file

NOTE: HF inference API does NOT reliably support response_format=json_object.
      We rely on strong prompt engineering to get JSON output and parse it here.
"""

import json
import logging
import os
import re
from typing import Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI, APITimeoutError, APIError

from app.llm.llm_gateway import LLMGateway, LLMRequest, LLMResponse

load_dotenv()

logger = logging.getLogger(__name__)

# System-level JSON instruction injected into every request
_JSON_SYSTEM_SUFFIX = (
    "\n\nCRITICAL INSTRUCTION: You MUST respond with ONLY a valid JSON object. "
    "No markdown, no code fences, no explanation text before or after the JSON. "
    "Start your response with '{' and end with '}'. Nothing else."
)


class HuggingFaceProvider(LLMGateway):
    """
    Calls the HuggingFace Serverless Inference API using the
    OpenAI-compatible /v1/chat/completions endpoint.
    """

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

    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self._default_model
        messages = []

        # Build system message (inject JSON instruction when needed)
        system_content = request.system_prompt or ""
        if request.response_format == "json":
            system_content += _JSON_SYSTEM_SUFFIX

        if system_content:
            messages.append({"role": "system", "content": system_content})

        messages.append({"role": "user", "content": request.user_prompt})

        try:
            logger.debug(f"[HuggingFace] Calling model: {model}")
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                # NOTE: do NOT pass response_format — not universally supported by HF
            )

            raw_content = response.choices[0].message.content or ""
            usage = response.usage

            # If we asked for JSON, clean up the response
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
            logger.error(f"[HuggingFace] Request timed out for model {model}")
            return LLMResponse(
                content="",
                model=model,
                provider="huggingface",
                success=False,
                error="Request timed out. The model may be loading. Please try again.",
            )
        except APIError as e:
            logger.error(f"[HuggingFace] API error: {e}")
            return LLMResponse(
                content="",
                model=model,
                provider="huggingface",
                success=False,
                error=f"HuggingFace API error: {str(e)}",
            )
        except Exception as e:
            logger.error(f"[HuggingFace] Unexpected error: {e}", exc_info=True)
            return LLMResponse(
                content="",
                model=model,
                provider="huggingface",
                success=False,
                error="An unexpected error occurred. Please try again.",
            )

    @staticmethod
    def _extract_json(text: str) -> str:
        """
        Robustly extract a JSON object from LLM response text.
        Handles cases where the model wraps JSON in markdown code fences
        or adds extra text before/after.
        """
        if not text:
            return "{}"

        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = re.sub(r"```\s*$", "", text)
        text = text.strip()

        # Try direct parse first
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

        # Find the first {...} block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            candidate = match.group()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        logger.warning("[HuggingFace] Could not extract valid JSON from response")
        return text
