import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import discord
import httpx
from openai.types.chat import ChatCompletionMessageToolCall
from .async_utils import await_task_with_heartbeats
from .attachments import (
    DocumentChunks,
    build_document_chunks,
    read_attachment_text,
)
from .content import get_completion_text
from .llm import execute_chat_completion
from .search import fetch_page_content, search_topics


class ContentFilterError(Exception):
    """Raised when the LLM content filter blocks generation."""

    pass


WEB_SEARCH_TOOL: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Busca na web por artigos, documentação técnica e fontes acadêmicas. "
                "Use quando precisar de informações atualizadas ou fontes específicas não disponíveis "
                "em seus dados de treinamento."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termo de busca para encontrar fontes relevantes",
                    }
                },
                "required": ["query"],
            },
        },
    }
]

FETCH_PAGE_TOOL: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": (
                "Acessa o conteúdo completo de uma página web. "
                "Use para obter o texto integral de artigos, documentação e fontes acadêmicas. "
                "Retorna o texto extraído da página (limitado a ~8000 caracteres). "
                "Só use para URLs retornadas pela ferramenta web_search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL completa da página a ser acessada",
                    }
                },
                "required": ["url"],
            },
        },
    }
]

ALL_RESEARCH_TOOLS = WEB_SEARCH_TOOL + FETCH_PAGE_TOOL


SEARCH_DOCUMENT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_document",
        "description": (
            "Search the user's uploaded document for keywords or phrases. "
            "Case-insensitive substring matching across all paragraphs. "
            "Optionally include surrounding paragraphs for context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword or phrase to search for (case-insensitive substring match).",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of matching chunks to return (default 5, max 10).",
                },
                "context_before": {
                    "type": "integer",
                    "description": "Number of paragraphs BEFORE each match to include (default 0).",
                },
                "context_after": {
                    "type": "integer",
                    "description": "Number of paragraphs AFTER each match to include (default 0).",
                },
            },
            "required": ["query"],
        },
    },
}

READ_DOCUMENT_CHUNK_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read_document_chunk",
        "description": (
            "Read a specific range of paragraphs from the user's uploaded document "
            "by chunk index. Use this to scan sections, read the beginning or end, "
            "or follow up on search_document results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "start_index": {
                    "type": "integer",
                    "description": "First chunk index to read (0-based).",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of chunks to read (default 5, max 10).",
                },
            },
            "required": ["start_index"],
        },
    },
}

DOCUMENT_TOOLS: list[dict[str, Any]] = [
    SEARCH_DOCUMENT_TOOL,
    READ_DOCUMENT_CHUNK_TOOL,
]


def handle_search_document(doc: DocumentChunks, args: dict[str, Any]) -> str:
    query = args["query"].lower()
    max_results = min(args.get("max_results", 5), 10)
    ctx_before = max(args.get("context_before", 0), 0)
    ctx_after = max(args.get("context_after", 0), 0)

    hits: list[dict[str, Any]] = []
    for i, chunk in enumerate(doc.chunks):
        if query in chunk.lower():
            start = max(0, i - ctx_before)
            end = min(doc.total_chunks, i + ctx_after + 1)
            context_chunks = [
                {"chunk_index": j, "chunk_text": doc.chunks[j][:2000]}
                for j in range(start, end)
            ]
            hits.append({"match_index": i, "context": context_chunks})
            if len(hits) >= max_results:
                break

    if not hits:
        return json.dumps(
            {
                "message": f'No paragraphs matched "{args["query"]}". Try a different keyword.'
            },
            ensure_ascii=False,
        )

    return json.dumps(hits, ensure_ascii=False, default=str)


def handle_read_document_chunk(doc: DocumentChunks, args: dict[str, Any]) -> str:
    start = max(args["start_index"], 0)
    count = min(args.get("count", 5), 10)
    end = min(doc.total_chunks, start + count)

    if start >= doc.total_chunks:
        return json.dumps(
            {
                "message": (
                    f"Start index {start} is out of range. "
                    f"Document has {doc.total_chunks} chunks."
                )
            },
            ensure_ascii=False,
        )

    chunks = [
        {"chunk_index": i, "chunk_text": doc.chunks[i][:2000]}
        for i in range(start, end)
    ]

    return json.dumps(chunks, ensure_ascii=False, default=str)


@dataclass
class DocumentToolSetup:
    doc: DocumentChunks
    tools: list[dict[str, Any]]
    on_extra_tool: Callable[[str, dict[str, Any]], str]


async def setup_document_tools(
    attachment: discord.Attachment,
    httpx_client: httpx.AsyncClient,
    base_tools: list[dict[str, Any]],
) -> DocumentToolSetup:
    """Extract, chunk and wire up document tools for a file attachment.

    Raises ValueError if the extracted content is empty.
    Other exceptions (download/extraction failures) propagate to caller.
    """
    extracted = await read_attachment_text(attachment, httpx_client)
    if not extracted.strip():
        raise ValueError("empty_document")

    doc = build_document_chunks(attachment.filename, extracted)
    tools = [*base_tools, *DOCUMENT_TOOLS]

    def _handle(tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "search_document":
            return handle_search_document(doc, args)
        if tool_name == "read_document_chunk":
            return handle_read_document_chunk(doc, args)
        return '{"error": "Unknown tool"}'

    return DocumentToolSetup(doc=doc, tools=tools, on_extra_tool=_handle)


def format_tool_call(tool_call: Any) -> dict[str, Any]:
    return {
        "id": tool_call.id,
        "type": "function",
        "function": {
            "name": tool_call.function.name,
            "arguments": tool_call.function.arguments,
        },
    }


def format_search_results(results: list[dict[str, Any]]) -> str:
    formatted = []
    for r in results:
        formatted.append(
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", ""),
            }
        )
    return json.dumps(formatted, ensure_ascii=False)


async def run_research_loop(
    config: dict[str, Any],
    model_name: str,
    messages: list[dict[str, Any]],
    *,
    max_iterations: int,
    search_results_per_topic: int,
    max_page_fetches: int,
    tools: list[dict[str, Any]] | None = None,
    reasoning_effort: str | None = None,
    user_id: int,
    on_extra_tool: Callable[[str, dict[str, Any]], str] | None = None,
    httpx_client: httpx.AsyncClient | None = None,
) -> str:
    """Run the tool-calling research loop (web_search + fetch_page + optional extras).

    Returns the final generated text.
    Raises APIError on provider errors.

    on_extra_tool(tool_name, args) -> str:
        Called for tool calls not handled internally (web_search, fetch_page).
        Must return the tool result as a JSON string.
    """
    if tools is None:
        tools = ALL_RESEARCH_TOOLS

    pages_fetched = 0
    for iteration in range(max_iterations):
        logging.info(
            "Research LLM iteration %s/%s (user ID: %s, model: %s)",
            iteration + 1,
            max_iterations,
            user_id,
            model_name,
        )

        completion_task = asyncio.create_task(
            execute_chat_completion(
                config=config,
                model_name=model_name,
                messages=messages,
                tools=tools,
                reasoning_effort=reasoning_effort,
            )
        )
        completion = await await_task_with_heartbeats(
            completion_task,
            f"Research LLM request still running (user ID: {user_id}, model: {model_name})",
        )

        if not completion.choices:
            raise RuntimeError("LLM returned no choices")

        choice = completion.choices[0]

        # Handle tool calls
        if (
            choice.finish_reason == "tool_calls"
            and choice.message
            and choice.message.tool_calls
        ):
            tool_calls = cast(
                list[ChatCompletionMessageToolCall], choice.message.tool_calls
            )

            tool_summary = [
                f"{tc.function.name}({tc.function.arguments})" for tc in tool_calls
            ]
            logging.info(
                "Research tool calls requested (user ID: %s): %s",
                user_id,
                "; ".join(tool_summary),
            )

            messages.append(
                {
                    "role": "assistant",
                    "content": choice.message.content or "",
                    "tool_calls": [format_tool_call(tc) for tc in tool_calls],
                }
            )

            for tc in tool_calls:
                if tc.function.name == "web_search":
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": "Erro: argumentos inválidos.",
                            }
                        )
                        continue

                    query = args.get("query", "")
                    logging.info(
                        "Research web_search (user ID: %s, query: %s)",
                        user_id,
                        query,
                    )

                    try:
                        results = await search_topics(
                            [query],
                            max_results=search_results_per_topic,
                        )
                        search_data = results.get(query, [])
                    except Exception:
                        logging.exception(
                            "Research web search failed for query: %s", query
                        )
                        search_data = []

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": format_search_results(search_data),
                        }
                    )

                elif tc.function.name == "fetch_page":
                    if pages_fetched >= max_page_fetches:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": (
                                    "Limite de páginas atingido. "
                                    "Continue com as fontes já obtidas."
                                ),
                            }
                        )
                        continue

                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": "Erro: argumentos inválidos.",
                            }
                        )
                        continue

                    url = args.get("url", "")
                    logging.info(
                        "Research fetch_page (user ID: %s, url: %s)",
                        user_id,
                        url,
                    )
                    pages_fetched += 1

                    page_content = await fetch_page_content(
                        url, httpx_client=httpx_client
                    )
                    if page_content:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": page_content,
                            }
                        )
                    else:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": (
                                    "Não foi possível acessar o conteúdo "
                                    "desta página. Tente outra URL ou "
                                    "continue com as fontes disponíveis."
                                ),
                            }
                        )

                else:
                    if on_extra_tool is not None:
                        try:
                            args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            args = {}
                        result = on_extra_tool(tc.function.name, args)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": result,
                            }
                        )
                    else:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": f"Erro: ferramenta desconhecida '{tc.function.name}'.",
                            }
                        )

            continue

        # Handle stop (document complete)
        if choice.finish_reason == "stop":
            raw_output = get_completion_text(completion)
            if raw_output:
                return raw_output
            continue

        # Handle length (max_tokens reached)
        if choice.finish_reason == "length":
            logging.warning("Research LLM reached max_tokens (user ID: %s)", user_id)
            return get_completion_text(completion)

        # Handle content_filter
        if choice.finish_reason == "content_filter":
            logging.error(
                "Research LLM content filter triggered (user ID: %s)", user_id
            )
            raise ContentFilterError(
                "A geração do documento foi bloqueada pelo filtro de conteúdo do provedor."
            )

        # Unexpected finish reason — capture whatever content exists
        raw_output = get_completion_text(completion)
        if raw_output:
            return raw_output

    logging.warning(
        "Research tool loop exhausted, forcing final generation (user ID: %s)",
        user_id,
    )
    force_task = asyncio.create_task(
        execute_chat_completion(
            config=config,
            model_name=model_name,
            messages=messages,
            tool_choice="none",
            reasoning_effort=reasoning_effort,
        )
    )
    force_completion = await await_task_with_heartbeats(
        force_task,
        "Research final generation still running",
    )
    return get_completion_text(force_completion)
