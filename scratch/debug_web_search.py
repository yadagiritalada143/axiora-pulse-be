"""
Debug script to directly test WebSearchService and DuckDuckGo response endpoints.
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.web_search_service import web_search_service

logging.basicConfig(level=logging.INFO)

async def test_search():
    print("Testing WebSearchService.search()...")
    res = await web_search_service.search("AI survey software competitors", max_results=5)
    print("Search Result Output:")
    print(res)

if __name__ == "__main__":
    asyncio.run(test_search())
