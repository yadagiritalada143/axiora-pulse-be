"""
Web Tools — MCP Tools & OpenAI Function Schemas
──────────────────────────────────────────────────────────────────────────────
Exposes real-time web search and webpage scraping as registered MCP tools
and OpenAI-compatible function calling schemas.
"""
import logging
from typing import Any
from app.services.web_search_service import web_search_service
from app.services.web_scraper_service import web_scraper_service
from app.services.research_trace_service import research_trace_service

logger = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """
    Perform a real-time web search for market research, competitor benchmarking,
    industry trends, or customer data.
    """
    logger.info(f"[MCP Tool: web_search] Executing query: '{query}'")
    await research_trace_service.log_query(query=query)
    
    search_res = await web_search_service.search(query, max_results=max_results)
    
    results = search_res.get("results", [])
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict) and item.get("url"):
                await research_trace_service.log_source(
                    url=item["url"],
                    title=item.get("title"),
                    snippet=item.get("snippet"),
                )

    return search_res


async def scrape_webpage(url: str, max_length: int = 4000) -> dict[str, Any]:
    """
    Fetch and extract full body text content from a specific web page URL.
    """
    logger.info(f"[MCP Tool: scrape_webpage] Scraping URL: '{url}'")
    scrape_res = await web_scraper_service.scrape_webpage(url, max_length=max_length)

    text_content = scrape_res.get("content", "")
    snippet = text_content[:200] + "…" if len(text_content) > 200 else text_content
    await research_trace_service.log_source(
        url=url,
        title=scrape_res.get("title") or f"Webpage ({url})",
        snippet=snippet,
    )

    return scrape_res


# ── OpenAI Function Calling Definitions ─────────────────────────────────────
OPENAI_WEB_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "web_search": {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Performs a live real-time web search on DuckDuckGo/Web to find target customer trends, "
                "competitor products, pricing models, market statistics, or industry reports."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Specific search query (e.g. 'AI survey tools competitors pricing 2026')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of search result items to return (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    "scrape_webpage": {
        "type": "function",
        "function": {
            "name": "scrape_webpage",
            "description": (
                "Fetches and extracts clean body text content from a specific web URL. "
                "CRITICAL: You MUST ONLY pass exact real URLs returned from a previous 'web_search' call. "
                "Do NOT guess, invent, or hallucinate URL paths."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full HTTP/HTTPS URL returned from web_search to scrape",
                    },

                    "max_length": {
                        "type": "integer",
                        "description": "Maximum character length of content to extract (default 4000)",
                        "default": 4000,
                    },
                },
                "required": ["url"],
            },
        },
    },
}
