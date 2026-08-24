import asyncio
import logging
import re
from typing import Any

import ddgs
import httpx
import requests
from bs4 import BeautifulSoup
from ddgs.exceptions import DDGSException
from markdownify import markdownify
from tavily import TavilyClient
from tavily import errors as tavily_errors

from ..config import SearchSettings

logger = logging.getLogger(__name__)

_TAVILY_ERRORS: tuple[type[Exception], ...] = (
    tavily_errors.BadRequestError,
    tavily_errors.ForbiddenError,
    tavily_errors.InvalidAPIKeyError,
    tavily_errors.MissingAPIKeyError,
    tavily_errors.TimeoutError,
    tavily_errors.UsageLimitExceededError,
    requests.exceptions.RequestException,
)

_DDG_ERRORS: tuple[type[Exception], ...] = (
    DDGSException,
    httpx.HTTPError,
)


def normalize_tavily_result(result: dict[str, Any]) -> dict[str, Any]:
    """Map a Tavily search result to the normalized result shape.

    Tavily results carry `content` and a relevance `score` (0-1);
    downstream consumers expect `snippet` plus an optional `score`.
    """
    return {
        "title": result.get("title", ""),
        "url": result.get("url", ""),
        "snippet": result.get("content", ""),
        "score": result.get("score"),
    }


def normalize_ddg_result(result: dict[str, Any]) -> dict[str, Any]:
    """Map a DuckDuckGo (ddgs) search result to the normalized result shape."""
    return {
        "title": result.get("title", ""),
        "url": result.get("href", ""),
        "snippet": result.get("body", ""),
        "score": None,
    }


async def _search_tavily(
    topic: str, max_results: int, api_key: str | None
) -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        client = TavilyClient(api_key=api_key or None)
        response = client.search(topic, max_results=max_results, timeout=30.0)
        return response.get("results", [])

    output = await asyncio.to_thread(_run)
    return [normalize_tavily_result(r) for r in output]


async def _search_ddg(topic: str, max_results: int) -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        with ddgs.DDGS() as duck_search:
            return list(duck_search.text(topic, max_results=max_results))

    output = await asyncio.to_thread(_run)
    return [normalize_ddg_result(r) for r in output]


async def search_topics(
    topics: list[str],
    max_results: int = 5,
    search_settings: SearchSettings | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Search each topic on the web and return results.

    Tavily is used when enabled in the config (an empty api_key falls back
    to Tavily's rate-limited keyless mode); DuckDuckGo is used otherwise,
    and also as the fallback when a Tavily search fails.

    Returns a dict mapping each topic to a list of search results.
    Each result contains: title, url, snippet, score (score may be None).
    Never raises: a failed search logs a warning and maps to an empty list.
    """
    if search_settings is None:
        search_settings = SearchSettings(tavily_enabled=False, tavily_api_key="")

    results: dict[str, list[dict[str, Any]]] = {}

    for topic in topics:
        if search_settings.tavily_enabled:
            try:
                results[topic] = await _search_tavily(
                    topic, max_results, search_settings.tavily_api_key
                )
                continue
            except _TAVILY_ERRORS as e:
                logger.warning(
                    "Tavily search failed for topic '%s' (%s); falling back to DuckDuckGo",
                    topic,
                    e,
                )

        try:
            results[topic] = await _search_ddg(topic, max_results)
        except _DDG_ERRORS as e:
            logger.warning("DuckDuckGo search failed for topic '%s': %s", topic, e)
            results[topic] = []

    return results


_MAX_PAGE_CHARS = 8_000

_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

# Tags removed entirely before HTML-to-markdown conversion (boilerplate
# that would otherwise render as noise for the LLM).
_FETCH_STRIP_TAGS: list[str] = [
    "script",
    "style",
    "noscript",
    "nav",
    "footer",
    "header",
    "aside",
    "form",
    "iframe",
]


def html_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_FETCH_STRIP_TAGS):
        tag.decompose()
    # markdownify 1.x accepts `strip`/`convert` but ignores them, so the
    # boilerplate tags are removed with BeautifulSoup above instead.
    text = markdownify(str(soup), heading_style="ATX")
    # markdownify pads blocks with blank lines; collapse long runs so the
    # character budget goes to real content.
    return re.sub(r"\n{3,}", "\n\n", text).strip()


async def fetch_page_content(
    url: str,
    max_chars: int = _MAX_PAGE_CHARS,
    httpx_client: httpx.AsyncClient | None = None,
) -> str:
    try:
        client = httpx_client or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        try:
            response = await client.get(
                url, headers={"User-Agent": _BROWSER_USER_AGENT}
            )
            response.raise_for_status()
        finally:
            if httpx_client is None:
                await client.aclose()

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return ""

        if "text/html" in content_type:
            text = html_to_markdown(response.text)
        else:
            text = response.text.strip()

        return text[:max_chars]

    except Exception:
        logger.warning("Failed to fetch page content from %s", url, exc_info=True)
        return ""
