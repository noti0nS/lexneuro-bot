import json
from dataclasses import dataclass
from typing import Any, cast

from src.helpers.ai_tools import (
    ALL_RESEARCH_TOOLS,
    ContentFilterError,
    format_search_results,
    format_tool_call,
    handle_read_document_chunk,
    handle_search_document,
)
from src.helpers.attachments import build_document_chunks, extract_text_sync


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
        {
            "title": "Title 1",
            "url": "https://example.com/1",
            "snippet": "Snippet 1",
            "score": 0.95,
        },
        {"title": "Title 2", "url": "https://example.com/2", "snippet": "Snippet 2"},
    ]
    output = format_search_results(results)
    assert "Title 1" in output
    assert "https://example.com/1" in output
    assert "Snippet 1" in output
    assert "Title 2" in output
    assert '"score": 0.95' in output
    assert output.count('"score"') == 1  # missing score is omitted


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


def test_handle_search_document_multiword_fallback() -> None:
    doc = build_document_chunks(
        "contrato.pdf",
        (
            "Cláusula 1: O aluguel mensal será de R$ 2.500,00.\n\n"
            "Cláusula 2: Em caso de atraso, incidirá multa de 10% sobre o débito.\n\n"
            "Cláusula 3: Foro da Comarca de Curitiba."
        ),
    )
    raw = handle_search_document(doc, {"query": "cláusula multa débito"})
    hits = json.loads(raw)
    assert isinstance(hits, list)
    assert len(hits) >= 1
    assert hits[0]["match_index"] == 1


def test_handle_read_document_chunk_reads_up_to_25() -> None:
    text = "\n\n".join(f"Parágrafo {i}" for i in range(20))
    doc = build_document_chunks("doc.txt", text)
    raw = handle_read_document_chunk(doc, {"start_index": 0, "count": 15})
    chunks = json.loads(raw)
    assert len(chunks) == 15
    assert chunks[0]["chunk_index"] == 0
    assert chunks[-1]["chunk_index"] == 14


def test_extract_text_sync_case_insensitive_txt() -> None:
    result = extract_text_sync("Conteúdo em TXT".encode(), "CASO.TXT")
    assert result == "Conteúdo em TXT"
