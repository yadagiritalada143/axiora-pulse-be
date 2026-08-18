"""
Web Scraper Service — Real-Time Webpage Extractor
──────────────────────────────────────────────────────────────────────────────
Fetches and extracts clean body content, headers, and metadata from target URLs
for AI agent context. Uses httpx and BeautifulSoup with safe token truncation.
"""
import logging
import re
from typing import Any
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class WebScraperService:
    """
    Service for fetching and extracting text content from specific webpage URLs.
    """

    def __init__(self, timeout: float = 10.0, max_length: int = 4000) -> None:
        self.timeout = timeout
        self.max_length = max_length

    async def scrape_webpage(self, url: str, max_length: int | None = None) -> dict[str, Any]:
        """
        Fetch and parse clean text content from target webpage URL.
        Returns:
            {
                "url": url,
                "title": title,
                "content": clean_text,
                "length": len(clean_text),
                "success": True/False
            }
        """
        limit = max_length or self.max_length
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        logger.info(f"[WebScraperService] Scraping webpage: '{clean_url}'")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(clean_url, headers=headers)
                if resp.status_code != 200:
                    return {
                        "url": clean_url,
                        "title": "",
                        "content": "",
                        "success": False,
                        "error": f"HTTP error status code {resp.status_code}",
                    }

                soup = BeautifulSoup(resp.text, "html.parser")

                # Extract title
                title = soup.title.string.strip() if (soup.title and soup.title.string) else clean_url

                # Check if page is a 404 or access denied page
                title_lower = title.lower()
                if any(err in title_lower for err in ("404", "not found", "access denied", "error", "page not found")):
                    return {
                        "url": clean_url,
                        "title": title,
                        "content": "",
                        "success": False,
                        "error": f"Page returned non-content error title: '{title}'",
                    }

                # Remove non-content tags
                for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "svg"]):
                    tag.decompose()

                # Extract main text
                lines = []
                for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
                    text = element.get_text(strip=True)
                    if text and len(text) > 5:
                        lines.append(text)

                if not lines:
                    # Fallback to full text decomposition
                    text = soup.get_text(separator="\n")
                    lines = [line.strip() for line in text.splitlines() if line.strip() and len(line.strip()) > 5]

                extracted_text = "\n".join(lines)

                if len(extracted_text) < 50:
                    return {
                        "url": clean_url,
                        "title": title,
                        "content": extracted_text,
                        "success": False,
                        "error": "Webpage contained insufficient main body text.",
                    }

                # Truncate content safely
                if len(extracted_text) > limit:
                    extracted_text = extracted_text[:limit] + "\n... [Content Truncated]"

                logger.info(f"[WebScraperService] Scraped {len(extracted_text)} chars from {clean_url}")
                return {
                    "url": clean_url,
                    "title": title,
                    "content": extracted_text,
                    "length": len(extracted_text),
                    "success": True,
                }


        except httpx.TimeoutException:
            logger.warning(f"[WebScraperService] Timeout fetching {clean_url}")
            return {"url": clean_url, "title": "", "content": "", "success": False, "error": "Request timed out"}
        except Exception as e:
            logger.error(f"[WebScraperService] Error scraping {clean_url}: {e}")
            return {"url": clean_url, "title": "", "content": "", "success": False, "error": str(e)}


web_scraper_service = WebScraperService()
