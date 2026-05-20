import asyncio
import json
import logging
from typing import Any, cast

from openai.types.chat import ChatCompletionMessageToolCall
from .llm import execute_chat_completion
from .async_utils import await_task_with_heartbeats
from .content import get_completion_text
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
) -> str:
    """Run the tool-calling research loop (web_search + fetch_page).

    Returns the final generated text.
    Raises APIError on provider errors.
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

                    page_content = await fetch_page_content(url)
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
