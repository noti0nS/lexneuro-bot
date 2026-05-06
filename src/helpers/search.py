import asyncio
import logging
import re
from html.parser import HTMLParser
from typing import Any, override

import httpx

try:
    import ddgs
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("ddgs is required for /pesquisa") from exc


async def search_topics(
    topics: list[str],
    max_results: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    """Search each topic on DuckDuckGo and return results.

    Returns a dict mapping each topic to a list of search results.
    Each result contains: title, url, snippet.
    """
    results: dict[str, list[dict[str, Any]]] = {}

    for topic in topics:
        topic_results: list[dict[str, Any]] = []
        try:

            def _search():
                with ddgs.DDGS() as duck_search:
                    return list(duck_search.text(topic, max_results=max_results))

            search_output = await asyncio.to_thread(_search)
            for result in search_output:
                topic_results.append(
                    {
                        "title": result.get("title", ""),
                        "url": result.get("href", ""),
                        "snippet": result.get("body", ""),
                    }
                )
        except Exception as e:
            logging.warning("Web search failed for topic '%s': %s", topic, e)

        results[topic] = topic_results

    return results


_MAX_PAGE_CHARS = 8_000


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._text: list[str] = []
        self._skip_level = 0

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript", "nav", "footer", "header"):
            self._skip_level += 1

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "nav", "footer", "header"):
            self._skip_level = max(0, self._skip_level - 1)

    @override
    def handle_data(self, data: str) -> None:
        if self._skip_level == 0:
            stripped = data.strip()
            if stripped:
                self._text.append(stripped)

    def get_text(self) -> str:
        text = " ".join(self._text)
        text = re.sub(r"\s+", " ", text)
        return text


async def fetch_page_content(url: str, max_chars: int = _MAX_PAGE_CHARS) -> str:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; LexNeuroBot/1.0; "
                        "+https://github.com/noti0nS/lexneuro-bot)"
                    )
                },
            )
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return ""

        parser = _TextExtractor()
        parser.feed(response.text)
        return parser.get_text()[:max_chars]

    except Exception:
        logging.warning("Failed to fetch page content from %s", url, exc_info=True)
        return ""
