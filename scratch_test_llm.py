import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure backend directory is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.llm.llm_gateway import get_llm_gateway, LLMRequest

async def test_llm():
    load_dotenv()
    print("DEFAULT_PROVIDER:", os.getenv("DEFAULT_PROVIDER"))
    print("OPENAI_MODEL:", os.getenv("OPENAI_MODEL"))
    print("OPENAI_TIMEOUT:", os.getenv("OPENAI_TIMEOUT"))
    print("OPENAI_MAX_RETRIES:", os.getenv("OPENAI_MAX_RETRIES"))
    print("API Key Length:", len(os.getenv("OPENAI_API_KEY") or ""))
    
    try:
        gateway = get_llm_gateway()
        print("Gateway initialized successfully!")
        
        req = LLMRequest(
            system_prompt="You are a helpful assistant.",
            user_prompt="Say 'hello world'",
            temperature=0.7
        )
        print("Sending completion request...")
        res = await gateway.complete(req)
        print("Response Success:", res.success)
        print("Response Content:", res.content)
        print("Response Error:", res.error)
    except Exception as e:
        print("Exception raised during execution:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_llm())
