from dataclasses import dataclass, field
from typing import Any, cast

from src.helpers.search import (
    fetch_page_content,
    html_to_markdown,
    normalize_ddg_result,
    normalize_tavily_result,
    search_topics,
)


def test_normalize_tavily_result() -> None:
    result = normalize_tavily_result(
        {
            "title": "STF decides case",
            "url": "https://portal.stf.jus.br/example",
            "content": "Full excerpt of the decision.",
            "score": 0.97,
        }
    )
    assert result == {
        "title": "STF decides case",
        "url": "https://portal.stf.jus.br/example",
        "snippet": "Full excerpt of the decision.",
        "score": 0.97,
    }


def test_normalize_tavily_result_missing_fields() -> None:
    result = normalize_tavily_result({"title": "Only Title"})
    assert result["title"] == "Only Title"
    assert result["url"] == ""
    assert result["snippet"] == ""
    assert result["score"] is None


def test_normalize_ddg_result() -> None:
    result = normalize_ddg_result(
        {"title": "TJSP ruling", "href": "https://tjsp.jus.br/x", "body": "Excerpt."}
    )
    assert result == {
        "title": "TJSP ruling",
        "url": "https://tjsp.jus.br/x",
        "snippet": "Excerpt.",
        "score": None,
    }


def test_normalize_ddg_result_missing_fields() -> None:
    result = normalize_ddg_result({})
    assert result == {"title": "", "url": "", "snippet": "", "score": None}


async def test_search_topics_empty_list() -> None:
    assert await search_topics([]) == {}


def test_html_to_markdown_converts_headings_and_links() -> None:
    html = (
        "<html><body>"
        "<h1>Repercussão geral</h1>"
        '<p>Leia a <a href="https://example.com/decisao">decisão</a>.</p>'
        "</body></html>"
    )
    markdown = html_to_markdown(html)
    assert "# Repercussão geral" in markdown
    assert "[decisão](https://example.com/decisao)" in markdown


def test_html_to_markdown_strips_boilerplate_tags() -> None:
    html = (
        "<html><body>"
        "<script>var x = 'track';</script>"
        "<nav>Menu Home Contact</nav>"
        "<h1>Real Content</h1>"
        "</body></html>"
    )
    markdown = html_to_markdown(html)
    assert "Real Content" in markdown
    assert "track" not in markdown
    assert "Menu Home Contact" not in markdown


def test_html_to_markdown_collapses_blank_lines() -> None:
    html = "<p>a</p><p>b</p><p>c</p>"
    assert "\n\n\n" not in html_to_markdown(html)


@dataclass
class _FakeResponse:
    headers: dict[str, str] = field(default_factory=dict)
    text: str = ""

    def raise_for_status(self) -> None:
        return None


@dataclass
class _FakeClient:
    response: _FakeResponse
    requested_headers: dict[str, str] = field(default_factory=dict)

    async def get(
        self, url: str, headers: dict[str, str] | None = None
    ) -> _FakeResponse:
        if headers is not None:
            self.requested_headers.update(headers)
        return self.response


async def test_fetch_page_contenthtml_to_markdown() -> None:
    html = (
        "<html><body>"
        "<script>evil()</script>"
        "<h1>Título da Decisão</h1>"
        "<p>Conteúdo relevante.</p>"
        "</body></html>"
    )
    client = _FakeResponse(
        headers={"content-type": "text/html; charset=utf-8"}, text=html
    )
    httpx_client = _FakeClient(response=client)

    content = await fetch_page_content(
        "https://example.com/decisao", httpx_client=cast(Any, httpx_client)
    )

    assert "# Título da Decisão" in content
    assert "Conteúdo relevante." in content
    assert "evil()" not in content
    # browser-like User-Agent was sent
    assert "Mozilla/5.0" in httpx_client.requested_headers.get("User-Agent", "")


async def test_fetch_page_content_plain_text_passthrough() -> None:
    client = _FakeResponse(headers={"content-type": "text/plain"}, text="raw text")
    content = await fetch_page_content(
        "https://example.com/a.txt",
        httpx_client=cast(Any, _FakeClient(response=client)),
    )
    assert content == "raw text"


async def test_fetch_page_content_rejects_binary_content_type() -> None:
    client = _FakeResponse(headers={"content-type": "application/pdf"}, text="%PDF-1.4")
    content = await fetch_page_content(
        "https://example.com/a.pdf",
        httpx_client=cast(Any, _FakeClient(response=client)),
    )
    assert content == ""


async def test_fetch_page_content_truncates_to_max_chars() -> None:
    html = "<p>" + "x" * 20_000 + "</p>"
    client = _FakeResponse(headers={"content-type": "text/html"}, text=html)
    content = await fetch_page_content(
        "https://example.com/big",
        max_chars=100,
        httpx_client=cast(Any, _FakeClient(response=client)),
    )
    assert len(content) <= 100
