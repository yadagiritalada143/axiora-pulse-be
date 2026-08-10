"""
LLM Connectivity Test Script for OpenAI Provider
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.providers.openai_provider import OpenAIProvider
from app.llm.llm_gateway import LLMRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

async def test_openai_connectivity():
    print("=" * 60)
    print("Testing OpenAI Provider Connectivity...")
    print("=" * 60)

    try:
        provider = OpenAIProvider()
        print(f"[+] Provider initialized successfully.")
        print(f"    - Provider Name: {provider.get_provider_name()}")
        print(f"    - Default Model: {provider.get_default_model()}")
    except Exception as e:
        print(f"[!] Failed to initialize OpenAIProvider: {e}")
        return

    # 1. Test Standard Completion
    print("\n--- Test 1: Standard Completion ---")
    request = LLMRequest(
        system_prompt="You are a helpful assistant.",
        user_prompt="Say 'OpenAI connectivity operational!'",
        max_tokens=50
    )

    try:
        response = await provider.complete(request)
        if response.success:
            print(f"[✓] Complete succeeded!")
            print(f"    Model Used: {response.model}")
            print(f"    Response Content: {response.content.strip()}")
            print(f"    Tokens - Input: {response.tokens_input}, Output: {response.tokens_output}, Total: {response.total_tokens}")
        else:
            print(f"[X] Complete returned failure:")
            print(f"    Error: {response.error}")
    except Exception as e:
        print(f"[X] Complete raised exception: {e}")

    # 2. Test Stream Completion
    print("\n--- Test 2: Stream Completion ---")
    stream_request = LLMRequest(
        system_prompt="You are a helpful assistant.",
        user_prompt="Count from 1 to 5.",
        max_tokens=50,
        stream=True
    )

    try:
        print("    Streamed output: ", end="", flush=True)
        chunks = []
        async for chunk in provider.complete_stream(stream_request):
            print(chunk, end="", flush=True)
            chunks.append(chunk)
        print("\n[✓] Stream completed successfully!")
        print(f"    Total chunks received: {len(chunks)}")
    except Exception as e:
        print(f"\n[X] Complete stream raised exception: {e}")

    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_openai_connectivity())
