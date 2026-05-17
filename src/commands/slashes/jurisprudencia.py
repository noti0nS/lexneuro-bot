import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any

import discord
from discord.ext import commands
from openai import APIError

from ...config import build_openai_chat_completion_kwargs, get_openai_config
from ...helpers.async_utils import await_task_with_heartbeats
from ...helpers.content import get_completion_text
from ...helpers.documents import generate_document
from ...helpers.llm import get_provider_error_detail
from ...helpers.search import fetch_page_content, search_topics
from ...helpers.send import send_document_result
from ...helpers.ui import FORMATO_JURISPRUDENCIA_CHOICES, TRIBUNAL_CHOICES
from ...prompts.jurisprudencia import build_jurisprudencia_messages

WEB_SEARCH_TOOL: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Busca na web por jurisprudência, acórdãos, ementas e decisões judiciais. "
                "Use quando precisar encontrar decisões de tribunais brasileiros."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termo de busca em português para encontrar jurisprudência relevante",
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
                "Use para obter o texto integral de decisões, acórdãos e ementas. "
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

JURISPRUDENCIA_TOOLS = WEB_SEARCH_TOOL + FETCH_PAGE_TOOL


def build_jurisprudencia_filename(
    consulta: str, user_id: int, output_format: str
) -> str:
    safe_consulta = re.sub(r"[^\w\s-]", "", consulta).strip().lower()
    safe_consulta = re.sub(r"[-\s]+", "_", safe_consulta) or "jurisprudencia"
    if len(safe_consulta) > 40:
        safe_consulta = safe_consulta[:40]
    epoch = int(datetime.now().timestamp())
    return f"jurisprudencia_{safe_consulta}_{user_id}_{epoch}{output_format}"


def _format_tool_call(tool_call: Any) -> dict[str, Any]:
    return {
        "id": tool_call.id,
        "type": "function",
        "function": {
            "name": tool_call.function.name,
            "arguments": tool_call.function.arguments,
        },
    }


def _format_search_results(results: list[dict[str, Any]]) -> str:
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


def register_jurisprudencia_command(
    discord_bot: commands.Bot,
    state: Any,
    user_has_permission: Any,
) -> None:
    @discord_bot.tree.command(
        name="jurisprudencia",
        description="Pesquise e resuma jurisprudência dos tribunais brasileiros",
    )
    @discord.app_commands.describe(
        consulta="Tema jurídico a ser pesquisado (ex: prescrição intercorrente na execução fiscal)",
        tribunal="Tribunal onde buscar (padrão: todos)",
        periodo="Período desejado (ex: 2023-2024, últimos 2 anos, após 2020)",
        formato="Formato de saída da pesquisa",
    )
    @discord.app_commands.choices(
        tribunal=TRIBUNAL_CHOICES,
        formato=FORMATO_JURISPRUDENCIA_CHOICES,
    )
    async def jurisprudencia_command(
        interaction: discord.Interaction,
        consulta: str,
        tribunal: discord.app_commands.Choice[str] | None = None,
        periodo: str | None = None,
        formato: discord.app_commands.Choice[str] | None = None,
    ) -> None:
        tribunal_valor = tribunal.value if tribunal else "todos"
        formato_valor = formato.value if formato else "docx"

        if not consulta.strip():
            await interaction.response.send_message(
                "Descreva o tema da pesquisa de jurisprudência.",
                ephemeral=True,
            )
            return

        if len(consulta.strip()) < 5:
            await interaction.response.send_message(
                "Descreva melhor o tema da pesquisa (mínimo 5 caracteres).",
                ephemeral=True,
            )
            return

        if not user_has_permission(interaction.user, interaction.channel, state.config):
            await interaction.response.send_message(
                "Você não tem permissão para usar este bot aqui.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Buscando jurisprudência... Isso pode levar alguns minutos.",
            ephemeral=True,
        )

        logging.info(
            "Jurisprudencia started (user ID: %s, consulta: %r, tribunal: %s, periodo: %s, formato: %s)",
            interaction.user.id,
            consulta[:80],
            tribunal_valor,
            periodo,
            formato_valor,
        )

        messages: list[dict[str, Any]] = build_jurisprudencia_messages(
            consulta=consulta,
            tribunal=tribunal_valor,
            periodo=periodo,
        )

        jur_config = state.config.get("jurisprudencia", {})
        max_iterations = jur_config.get("max_search_iterations", 12)
        search_results_count = jur_config.get("search_results_per_query", 8)
        max_pages = jur_config.get("max_page_fetches", 5)
        jur_model = jur_config.get("model")
        curr_model = jur_model if jur_model else state.curr_model

        openai_client, openai_config = get_openai_config(state.config, curr_model)

        raw_output = ""
        request_started_at = datetime.now().timestamp()
        pages_fetched = 0

        try:
            for iteration in range(max_iterations):
                logging.info(
                    "Jurisprudencia LLM iteration %s/%s (user ID: %s, model: %s)",
                    iteration + 1,
                    max_iterations,
                    interaction.user.id,
                    openai_config["model"],
                )

                completion_task = asyncio.create_task(
                    openai_client.chat.completions.create(
                        **build_openai_chat_completion_kwargs(
                            openai_config,
                            messages,
                            stream=False,
                            tools=JURISPRUDENCIA_TOOLS,
                        )
                    )
                )
                completion = await await_task_with_heartbeats(
                    completion_task,
                    (
                        "Jurisprudencia LLM request still running "
                        f"(user ID: {interaction.user.id}, "
                        f"model: {openai_config['model']})"
                    ),
                )

                if not completion.choices:
                    raise RuntimeError("LLM returned no choices")

                choice = completion.choices[0]

                if (
                    choice.finish_reason == "tool_calls"
                    and choice.message
                    and choice.message.tool_calls
                ):
                    tool_calls = choice.message.tool_calls

                    tool_summary = [
                        f"{tc.function.name}({tc.function.arguments})"
                        for tc in tool_calls
                    ]
                    logging.info(
                        "Jurisprudencia tool calls requested (user ID: %s): %s",
                        interaction.user.id,
                        "; ".join(tool_summary),
                    )

                    messages.append(
                        {
                            "role": "assistant",
                            "content": choice.message.content or "",
                            "tool_calls": [_format_tool_call(tc) for tc in tool_calls],
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
                                "Jurisprudencia web_search (user ID: %s, query: %s)",
                                interaction.user.id,
                                query,
                            )

                            try:
                                results = await search_topics(
                                    [query],
                                    max_results=search_results_count,
                                )
                                search_data = results.get(query, [])
                            except Exception:
                                logging.exception(
                                    "Jurisprudencia web search failed for query: %s",
                                    query,
                                )
                                search_data = []

                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc.id,
                                    "content": _format_search_results(search_data),
                                }
                            )

                        elif tc.function.name == "fetch_page":
                            if pages_fetched >= max_pages:
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
                                "Jurisprudencia fetch_page (user ID: %s, url: %s)",
                                interaction.user.id,
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

                if choice.finish_reason == "stop":
                    raw_output = get_completion_text(completion)
                    if raw_output:
                        break
                    continue

                if choice.finish_reason == "length":
                    logging.warning(
                        "Jurisprudencia LLM reached max_tokens (user ID: %s)",
                        interaction.user.id,
                    )
                    raw_output = get_completion_text(completion)
                    break

                if choice.finish_reason == "content_filter":
                    logging.error(
                        "Jurisprudencia LLM content filter triggered (user ID: %s)",
                        interaction.user.id,
                    )
                    await interaction.followup.send(
                        "A geração da pesquisa foi bloqueada pelo filtro de conteúdo do provedor."
                    )
                    return

                raw_output = get_completion_text(completion)
                if raw_output:
                    break

            if not raw_output.strip():
                logging.warning(
                    "Jurisprudencia tool loop exhausted, forcing final generation (user ID: %s)",
                    interaction.user.id,
                )
                force_task = asyncio.create_task(
                    openai_client.chat.completions.create(
                        **build_openai_chat_completion_kwargs(
                            openai_config,
                            messages,
                            stream=False,
                            tool_choice="none",
                        )
                    )
                )
                force_completion = await await_task_with_heartbeats(
                    force_task,
                    "Jurisprudencia final generation still running",
                )
                raw_output = get_completion_text(force_completion)

            elapsed = datetime.now().timestamp() - request_started_at
            logging.info(
                "Jurisprudencia LLM request completed (user ID: %s, model: %s, elapsed: %.2fs)",
                interaction.user.id,
                openai_config["model"],
                elapsed,
            )

        except APIError as exc:
            logging.exception(
                "Provider error while generating jurisprudencia: %s",
                get_provider_error_detail(exc),
            )
            await interaction.followup.send(
                "O provedor do modelo interrompeu a geração da pesquisa. "
                + f"Detalhe do provedor: `{str(exc)[:500]}`"
            )
            return
        except Exception:
            logging.exception("Error while generating jurisprudencia research")
            await interaction.followup.send(
                "Não consegui gerar a pesquisa de jurisprudência agora. "
                + "Verifique os logs e tente novamente."
            )
            return

        if not raw_output.strip():
            await interaction.followup.send(
                "Não foi possível encontrar jurisprudência relevante sobre o tema. "
                + "Tente refinar a consulta ou ampliar o período."
            )
            return

        try:
            file_bytes, ext = generate_document(raw_output, consulta, formato_valor)
            filename = build_jurisprudencia_filename(consulta, interaction.user.id, ext)
        except Exception:
            logging.exception("Error while generating jurisprudencia document file")
            await interaction.followup.send(
                "Não consegui gerar o arquivo do documento. "
                + "O conteúdo será enviado em mensagens."
            )
            await send_document_result(
                interaction,
                raw_output,
                "jurisprudencia.txt",
                b"",
                label="Jurisprudência",
            )
            return

        await send_document_result(
            interaction, raw_output, filename, file_bytes, label="Jurisprudência"
        )
