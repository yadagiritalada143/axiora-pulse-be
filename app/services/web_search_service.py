"""
Web Search Service — Real-Time Search Provider
──────────────────────────────────────────────────────────────────────────────
Provides real-time web search capability for AI agents using:
  1. DuckDuckGo (Primary: zero-cost, keyless via duckduckgo_search or HTML fallback)
  2. Tavily API (Optional: if TAVILY_API_KEY is configured)
"""
import logging
import os
import re
from typing import Any
import httpx

logger = logging.getLogger(__name__)


class WebSearchService:
    """
    Service for executing real-time web search queries across providers.
    """

    def __init__(self) -> None:
        self.provider = os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo").lower()
        self.max_results = int(os.getenv("MAX_SEARCH_RESULTS", "5"))
        self.tavily_key = os.getenv("TAVILY_API_KEY", "").strip()

    async def search(self, query: str, max_results: int | None = None) -> dict[str, Any]:
        """
        Execute real-time web search for query.
        Returns dictionary containing query, provider used, and list of result items:
        [{"title": ..., "url": ..., "snippet": ...}]
        """
        limit = max_results or self.max_results
        cleaned_query = query.strip()

        if not cleaned_query:
            return {"query": query, "provider": self.provider, "results": [], "error": "Empty search query"}

        logger.info(f"[WebSearchService] Executing real-time search: '{cleaned_query}' (provider={self.provider})")

        # 1. Tavily API if explicitly configured and key available
        if self.provider == "tavily" and self.tavily_key:
            res = await self._search_tavily(cleaned_query, limit)
            if res.get("results"):
                return res

        # 2. DuckDuckGo Search (Primary & Fallback)
        return await self._search_duckduckgo(cleaned_query, limit)

    async def _search_duckduckgo(self, query: str, limit: int) -> dict[str, Any]:
        """Execute DuckDuckGo search via python library or direct HTML fallback."""
        results: list[dict[str, str]] = []

        # Attempt 1: Try ddgs or duckduckgo_search package if installed
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                ddg_gen = ddgs.text(query, max_results=limit)
                for item in ddg_gen:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("href", "") or item.get("link", ""),
                        "snippet": item.get("body", "") or item.get("snippet", ""),
                    })
            if results:
                logger.info(f"[WebSearchService] DuckDuckGo library returned {len(results)} results.")
                return {"query": query, "provider": "duckduckgo_library", "results": results}
        except Exception as e:
            logger.debug(f"[WebSearchService] DDG library search notice: {e}. Trying HTTP HTML fallback...")

        # Attempt 2: Direct HTTP POST to DuckDuckGo HTML endpoint
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://html.duckduckgo.com/",
            }
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query, "b": "", "kl": "us-en"},
                    headers=headers,
                )
                if resp.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "html.parser")
                    links = soup.find_all("a", class_="result__a")
                    snippets = soup.find_all("a", class_="result__snippet")

                    for i in range(min(limit, len(links))):
                        title = links[i].get_text(strip=True)
                        raw_href = links[i].get("href", "")
                        # Disentangle duckduckgo redirect URL if present
                        url_match = re.search(r"uddg=(https?%3A%2F%2F[^&]+)", raw_href)
                        if url_match:
                            import urllib.parse
                            url = urllib.parse.unquote(url_match.group(1))
                        else:
                            url = raw_href

                        snippet = snippets[i].get_text(strip=True) if i < len(snippets) else ""
                        if title and url and not url.startswith("//duckduckgo.com"):
                            results.append({"title": title, "url": url, "snippet": snippet})

                    if results:
                        logger.info(f"[WebSearchService] DuckDuckGo HTML POST returned {len(results)} results.")
                        return {"query": query, "provider": "duckduckgo_html", "results": results}
        except Exception as err:
            logger.warning(f"[WebSearchService] DDG HTML POST error: {err}")

        # Attempt 3: Fallback to DuckDuckGo Lite (https://lite.duckduckgo.com/lite/)
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.post(
                    "https://lite.duckduckgo.com/lite/",
                    data={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                )
                if resp.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "html.parser")
                    link_tags = soup.find_all("a", class_="result-link")
                    snippet_tags = soup.find_all("td", class_="result-snippet")

                    for i in range(min(limit, len(link_tags))):
                        title = link_tags[i].get_text(strip=True)
                        url = link_tags[i].get("href", "")
                        snippet = snippet_tags[i].get_text(strip=True) if i < len(snippet_tags) else ""
                        if title and url:
                            results.append({"title": title, "url": url, "snippet": snippet})

                    if results:
                        logger.info(f"[WebSearchService] DuckDuckGo Lite returned {len(results)} results.")
                        return {"query": query, "provider": "duckduckgo_lite", "results": results}
        except Exception as lite_err:
            logger.warning(f"[WebSearchService] DDG Lite fallback error: {lite_err}")


        return {"query": query, "provider": "duckduckgo", "results": results, "error": "No search results retrieved."}

    async def _search_tavily(self, query: str, limit: int) -> dict[str, Any]:
        """Execute Tavily search API call."""
        results: list[dict[str, str]] = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.tavily_key,
                        "query": query,
                        "max_results": limit,
                        "search_depth": "basic",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("results", []):
                        results.append({
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "snippet": item.get("content", ""),
                        })
                    return {"query": query, "provider": "tavily", "results": results}
        except Exception as e:
            logger.warning(f"[WebSearchService] Tavily search error: {e}")
        return {"query": query, "provider": "tavily", "results": [], "error": "Tavily search failed"}


web_search_service = WebSearchService()
