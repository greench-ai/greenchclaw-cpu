"""
GreenClaw CPU — Web Tools.

Web search and page fetching for real-time information.
Combines Brave Search API, web fetching, and URL content extraction.
"""

import logging
from typing import Optional

from .base import Tool, ToolCategory, ToolResult

logger = logging.getLogger(__name__)


class WebSearchTool(Tool):
    """Search the web using Brave Search API for real-time information."""

    name = "web_search"
    description = (
        "Search the web for real-time information on any topic. "
        "Returns titles, URLs, and snippets. Use this when you need current info, "
        "news, prices, weather, sports scores, or anything that changes over time."
    )
    category = ToolCategory.WEB
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query (be specific for better results)",
            },
            "count": {
                "type": "integer",
                "description": "Number of results to return (default: 5, max: 10)",
            },
            "freshness": {
                "type": "string",
                "description": "Filter by recency: 'day', 'week', 'month', 'year', or empty for any time",
            },
        },
        "required": ["query"],
    }

    async def execute(
        self,
        query: str,
        count: int = 5,
        freshness: Optional[str] = None,
    ) -> ToolResult:
        import os

        api_key = os.environ.get("BRAVE_API_KEY")
        if not api_key:
            return ToolResult(
                success=False,
                error="Brave Search API key not configured. Set BRAVE_API_KEY environment variable, or use web_fetch for direct URL access.",
            )

        count = min(count, 10)
        params = {
            "q": query,
            "count": count,
        }
        if freshness:
            params["freshness"] = freshness

        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": api_key,
                    },
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            web_results = data.get("web", {}).get("results", [])
            for item in web_results[:count]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                    "page_age": item.get("page_age", ""),
                })

            return ToolResult(
                success=True,
                content=results,
                metadata={"query": query, "count": len(results)},
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(success=False, error=f"Brave Search HTTP error: {e.response.status_code}")
        except Exception as e:
            return ToolResult(success=False, error=f"Web search failed: {e}")


class WebFetchTool(Tool):
    """Fetch and extract readable content from a URL."""

    name = "web_fetch"
    description = (
        "Fetch the content of a web page and extract readable text. "
        "Use this to get detailed information from a specific URL. "
        "Returns the page title, main content, links, and images found."
    )
    category = ToolCategory.WEB
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch (must start with http:// or https://)",
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum characters to extract (default: 5000)",
            },
        },
        "required": ["url"],
    }

    async def execute(self, url: str, max_chars: int = 5000) -> ToolResult:
        import os

        # Use the web_fetch tool from the agent's own capabilities
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return ToolResult(success=False, error="URL must start with http:// or https://")
        except Exception:
            return ToolResult(success=False, error=f"Invalid URL: {url}")

        try:
            import httpx
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; GreenClaw/1.0; +https://github.com/greench-ai/greenchclaw-cpu)",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            }

            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type and "text/plain" not in content_type:
                    return ToolResult(
                        success=False,
                        error=f"Content type not supported: {content_type}",
                    )

                html = resp.text
                text = _extract_text(html, max_chars)

                return ToolResult(
                    success=True,
                    content={
                        "url": url,
                        "status": resp.status_code,
                        "content_type": content_type,
                        "text": text,
                        "size": len(html),
                    },
                    metadata={"url": url, "chars": len(text)},
                )
        except httpx.HTTPStatusError as e:
            return ToolResult(success=False, error=f"HTTP error: {e.response.status_code}")
        except Exception as e:
            return ToolResult(success=False, error=f"Fetch failed: {e}")


def _extract_text(html: str, max_chars: int) -> str:
    """Extract readable text from HTML."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Get text
        text = soup.get_text(separator="\n", strip=True)

        # Clean up whitespace
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n".join(lines)

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n… [truncated at {max_chars} chars]"

        return text
    except ImportError:
        # Fallback: strip tags manually
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars] + ("… [truncated]" if len(text) > max_chars else "")


def register_web_tools(registry) -> None:
    """Register web tools."""
    registry.register(WebSearchTool())
    registry.register(WebFetchTool())
