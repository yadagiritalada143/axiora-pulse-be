"""
Unit Tests for Real-Time Web Search, Web Scraping, and OpenAI Tool Calling
"""
import pytest
from app.services.web_search_service import WebSearchService, web_search_service
from app.services.web_scraper_service import WebScraperService, web_scraper_service
from app.mcp.tool_registry import mcp_tool_registry, ALLOWED_AGENT_TOOLS
from app.llm.llm_gateway import LLMRequest


@pytest.mark.asyncio
async def test_web_search_service():
    """Test web search service with DuckDuckGo."""
    service = WebSearchService()
    res = await service.search("AI survey software market", max_results=3)

    assert "query" in res
    assert "provider" in res
    assert "results" in res
    assert isinstance(res["results"], list)


@pytest.mark.asyncio
async def test_web_scraper_service():
    """Test web scraper service HTML parsing."""
    service = WebScraperService()
    # Test invalid domain error handling
    res = await service.scrape_webpage("https://invalid-domain-axiora-pulse-test-12345.org")

    assert res["success"] is False
    assert "error" in res


@pytest.mark.asyncio
async def test_mcp_tool_registry_web_tools():
    """Test MCP registry tool registration and permission matrix."""
    assert "web_search" in mcp_tool_registry.list_tools()
    assert "scrape_webpage" in mcp_tool_registry.list_tools()

    # Test permission check
    assert mcp_tool_registry.is_agent_authorized("market_research_agent", "web_search")
    assert mcp_tool_registry.is_agent_authorized("market_research_agent", "scrape_webpage")
    assert not mcp_tool_registry.is_agent_authorized("financial_readiness_agent", "scrape_webpage")

    # Test schema generation
    schemas = mcp_tool_registry.get_openai_tool_definitions("market_research_agent")
    assert len(schemas) >= 2
    tool_names = [s["function"]["name"] for s in schemas]
    assert "web_search" in tool_names
    assert "scrape_webpage" in tool_names


@pytest.mark.asyncio
async def test_mcp_call_tool_web_search():
    """Test executing web_search via MCP tool registry dispatch."""
    res = await mcp_tool_registry.call_tool(
        "web_search", caller_agent="market_research_agent", query="Axiora Pulse AI", max_results=2
    )

    assert res["success"] is True
    assert "result" in res
    assert "results" in res["result"]
