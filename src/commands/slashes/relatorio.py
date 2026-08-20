import asyncio
import logging

logger = logging.getLogger(__name__)
from datetime import UTC, datetime
from typing import Any

import discord
import httpx
from discord.ext import commands

from ...helpers.ai_tools import (
    ALL_RESEARCH_TOOLS,
    DocumentToolSetup,
    run_research_loop,
    setup_document_tools,
)
from ...helpers.async_utils import await_task_with_heartbeats
from ...helpers.attachments import (
    DocumentChunks,
    attachment_is_supported,
    read_attachment_text,
)
from ...helpers.content import build_filename, get_completion_text
from ...helpers.documents import DOCUMENT_FORMAT_CHOICES, generate_document
from ...helpers.llm import (
    LLMAborted,
    execute_chat_completion,
    llm_error_handling,
)
from ...helpers.send import send_document_result
from ...prompts.relatorio import build_relatorio_messages

SUPPORTED_INPUT_CONTENT_TYPES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "text/plain",
)

SUPPORTED_INPUT_EXTENSIONS = (".pdf", ".docx", ".odt", ".txt")

# Portuguese month names for date formatting
_MESES = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


def _format_date_pt(dt: datetime) -> str:
    return f"{dt.day} de {_MESES[dt.month - 1]} de {dt.year}"


def register_relatorio_command(
    discord_bot: commands.Bot,
    state: Any,
    httpx_client: httpx.AsyncClient,
    user_has_permission: Any,
) -> None:
    @discord_bot.tree.command(
        name="relatorio",
        description="Gere um relatório acadêmico estruturado a partir de um título e descrição",
    )
    @discord.app_commands.describe(
        titulo="Título do relatório (ex: Árvores B, B+, Heap e Trie)",
        descricao="Descrição / objetivo do trabalho",
        topicos="Tópicos a abordar, separados por vírgula (opcional — o LLM infere da descrição)",
        secoes="Seções para cada tópico, separadas por vírgula (opcional)",
        paginas="Número alvo de páginas (1–50)",
        pesquisar="Fazer pesquisa web para enriquecer o relatório?",
        fonte="Documento fonte (.pdf, .docx, .odt, .txt)",
        instrucoes="Instruções adicionais para a geração do relatório",
        formato="Formato do arquivo de saída",
    )
    @discord.app_commands.choices(
        pesquisar=[
            discord.app_commands.Choice(name="Sim", value="true"),
            discord.app_commands.Choice(name="Não (recomendado)", value="false"),
        ],
        formato=DOCUMENT_FORMAT_CHOICES,
    )
    async def relatorio_command(
        interaction: discord.Interaction,
        titulo: str,
        descricao: str,
        topicos: str = "",
        secoes: str = "",
        paginas: int = 6,
        pesquisar: str = "false",
        fonte: discord.Attachment | None = None,
        instrucoes: str = "",
        formato: discord.app_commands.Choice[str] | None = None,
    ) -> None:
        formato_valor = formato.value if formato else "docx"

        if not titulo.strip():
            await interaction.response.send_message(
                "Informe um título para o relatório.",
                ephemeral=True,
            )
            return

        if not descricao.strip():
            await interaction.response.send_message(
                "Descreva o objetivo do relatório.",
                ephemeral=True,
            )
            return

        if paginas < 1:
            await interaction.response.send_message(
                "O número de páginas deve ser no mínimo 1.",
                ephemeral=True,
            )
            return

        if paginas > 50:
            await interaction.response.send_message(
                "O número de páginas não pode exceder 50.",
                ephemeral=True,
            )
            return

        if not user_has_permission(interaction.user, interaction.channel, state.config):
            await interaction.response.send_message(
                "Você não tem permissão para usar este bot aqui.", ephemeral=True
            )
            return

        # Validate attachment if provided
        if fonte is not None and not attachment_is_supported(fonte):
            await interaction.response.send_message(
                (
                    "Tipo de arquivo não suportado. "
                    "Envie um arquivo .pdf, .docx, .odt ou .txt."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Gerando o relatório... Isso pode levar alguns minutos.",
            ephemeral=True,
        )

        logger.info(
            "Relatorio started (user ID: %s, titulo: %r, paginas: %s, pesquisar: %s, formato: %s, has_file: %s)",
            interaction.user.id,
            titulo[:80],
            paginas,
            pesquisar == "true",
            formato_valor,
            fonte is not None,
        )

        pesquisar_enabled = pesquisar == "true"
        doc: DocumentChunks | None = None
        fonte_arquivo = ""
        on_extra_tool = None
        extended_tools = list(ALL_RESEARCH_TOOLS)

        if fonte is not None:
            relatorio_config = state.config.get("relatorio", {})
            max_fonte_kb = relatorio_config.get("max_fonte_kb", 512)
            file_size_kb = fonte.size / 1024
            if file_size_kb > max_fonte_kb:
                await interaction.followup.send(
                    f"O arquivo excede o limite de {max_fonte_kb} KB ({file_size_kb:.1f} KB). Envie um arquivo menor."
                )
                return

            if pesquisar_enabled:
                try:
                    setup: DocumentToolSetup = await setup_document_tools(
                        fonte, httpx_client, extended_tools
                    )
                except ValueError:
                    await interaction.followup.send(
                        "O arquivo anexado parece estar vazio."
                    )
                    return
                except Exception:
                    logger.exception(
                        "Relatorio file extraction failed (user ID: %s)",
                        interaction.user.id,
                    )
                    await interaction.followup.send(
                        "Não consegui extrair o texto do arquivo. Verifique se ele é válido."
                    )
                    return

                doc = setup.doc
                extended_tools = setup.tools
                on_extra_tool = setup.on_extra_tool

                logger.info(
                    "Relatorio file stored as chunks (user ID: %s, filename: %s, chunks: %s)",
                    interaction.user.id,
                    fonte.filename,
                    doc.total_chunks,
                )
            else:
                try:
                    extracted = await read_attachment_text(fonte, httpx_client)
                except Exception:
                    logger.exception(
                        "Relatorio file extraction failed (user ID: %s)",
                        interaction.user.id,
                    )
                    await interaction.followup.send(
                        "Não consegui extrair o texto do arquivo. Verifique se ele é válido."
                    )
                    return

                if not extracted.strip():
                    await interaction.followup.send(
                        "O arquivo anexado parece estar vazio."
                    )
                    return

                logger.info(
                    "Relatorio file extracted (user ID: %s, chars: %s)",
                    interaction.user.id,
                    len(extracted),
                )

                fonte_arquivo = extracted

        relatorio_config = state.config.get("relatorio", {})
        autor = interaction.user.display_name
        data_atual = _format_date_pt(datetime.now(tz=UTC))

        messages: list[dict[str, Any]] = build_relatorio_messages(
            titulo=titulo,
            descricao=descricao,
            autor=autor,
            data=data_atual,
            topicos=topicos,
            secoes=secoes,
            paginas=paginas,
            pesquisar=pesquisar_enabled,
            instrucoes=instrucoes,
            fonte_arquivo=fonte_arquivo,
            has_attachment=doc is not None,
        )

        # Model resolution
        model = relatorio_config.get("model")
        curr_model = model if model else state.curr_model

        raw_output = ""
        request_started_at = datetime.now(tz=UTC).timestamp()

        try:
            async with llm_error_handling(interaction, "Relatório"):
                if pesquisar_enabled:
                    max_iterations = relatorio_config.get("max_tool_iterations", 15)
                    search_results_count = relatorio_config.get(
                        "search_results_per_topic", 8
                    )
                    max_pages = relatorio_config.get("max_page_fetches", 5)

                    raw_output = await run_research_loop(
                        config=state.config,
                        model_name=curr_model,
                        messages=messages,
                        max_iterations=max_iterations,
                        search_results_per_topic=search_results_count,
                        max_page_fetches=max_pages,
                        user_id=interaction.user.id,
                        tools=extended_tools,
                        on_extra_tool=on_extra_tool,
                        httpx_client=httpx_client,
                    )
                else:
                    logger.info(
                        "Relatorio request started (user ID: %s, model: %s)",
                        interaction.user.id,
                        curr_model,
                    )
                    completion_task = asyncio.create_task(
                        execute_chat_completion(
                            config=state.config,
                            model_name=curr_model,
                            messages=messages,
                            tool_choice="none",
                        )
                    )
                    completion = await await_task_with_heartbeats(
                        completion_task,
                        f"Relatorio LLM request still running (user ID: {interaction.user.id}, model: {curr_model})",
                    )
                    raw_output = get_completion_text(completion)

                elapsed = datetime.now(tz=UTC).timestamp() - request_started_at
                logger.info(
                    "Relatorio LLM request completed (user ID: %s, model: %s, elapsed: %.2fs)",
                    interaction.user.id,
                    curr_model,
                    elapsed,
                )
        except LLMAborted:
            return

        if not raw_output.strip():
            await interaction.followup.send(
                "Não foi possível gerar o conteúdo do relatório."
            )
            return

        # Generate document file
        try:
            file_bytes, ext = generate_document(raw_output, titulo, formato_valor)
            filename = build_filename("relatorio", titulo, interaction.user.id, ext)
        except Exception:
            logger.exception("Error while generating relatorio document file")
            await interaction.followup.send(
                "Não consegui gerar o arquivo do relatório. "
                + "O conteúdo será enviado em mensagens."
            )
            await send_document_result(
                interaction, raw_output, "relatorio.txt", b"", label="Relatório"
            )
            return

        await send_document_result(
            interaction, raw_output, filename, file_bytes, label="Relatório"
        )
