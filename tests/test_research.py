from dataclasses import dataclass
from typing import Any, cast

from src.helpers.ai_tools import (
    ALL_RESEARCH_TOOLS,
    ContentFilterError,
    format_search_results,
    format_tool_call,
)


@dataclass
class _FunctionCall:
    name: str
    arguments: str


@dataclass
class _ToolCall:
    id: str
    function: _FunctionCall


def test_format_tool_call() -> None:
    tc = cast(
        Any,
        _ToolCall(
            id="call_1",
            function=_FunctionCall(name="web_search", arguments='{"query": "test"}'),
        ),
    )
    result = format_tool_call(tc)
    assert result["id"] == "call_1"
    assert result["type"] == "function"
    assert result["function"]["name"] == "web_search"
    assert result["function"]["arguments"] == '{"query": "test"}'


def test_format_search_results() -> None:
    results = [
        {"title": "Title 1", "url": "https://example.com/1", "snippet": "Snippet 1"},
        {"title": "Title 2", "url": "https://example.com/2", "snippet": "Snippet 2"},
    ]
    output = format_search_results(results)
    assert "Title 1" in output
    assert "https://example.com/1" in output
    assert "Snippet 1" in output
    assert "Title 2" in output


def test_format_search_results_empty() -> None:
    output = format_search_results([])
    assert output == "[]"


def test_format_search_results_missing_fields() -> None:
    results = [{"title": "Only Title"}]
    output = format_search_results(results)
    assert "Only Title" in output
    assert '""' in output  # empty url and snippet


def test_all_research_tools_has_web_search() -> None:
    tool_names = [t["function"]["name"] for t in ALL_RESEARCH_TOOLS]
    assert "web_search" in tool_names
    assert "fetch_page" in tool_names


def test_web_search_tool_has_query_param() -> None:
    ws_tool = next(
        t for t in ALL_RESEARCH_TOOLS if t["function"]["name"] == "web_search"
    )
    assert "query" in ws_tool["function"]["parameters"]["required"]


def test_fetch_page_tool_has_url_param() -> None:
    fp_tool = next(
        t for t in ALL_RESEARCH_TOOLS if t["function"]["name"] == "fetch_page"
    )
    assert "url" in fp_tool["function"]["parameters"]["required"]


def test_content_filter_error_is_exception() -> None:
    exc = ContentFilterError("test message")
    assert isinstance(exc, Exception)
    assert str(exc) == "test message"
