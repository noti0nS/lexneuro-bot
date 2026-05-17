import asyncio
import logging
import re
from datetime import datetime
from io import BytesIO
from typing import Any

import discord
import httpx
from discord.ext import commands
from openai import APIError

from ...config import build_openai_chat_completion_kwargs, get_openai_config
from ...helpers.ai_tools import ContentFilterError, run_research_loop
from ...helpers.async_utils import await_task_with_heartbeats
from ...helpers.content import get_completion_text
from ...helpers.documents import DOCUMENT_FORMAT_CHOICES, generate_document
from ...helpers.llm import get_provider_error_detail
from ...helpers.send import send_document_result
from ...prompts.relatorio import build_relatorio_messages

SUPPORTED_INPUT_CONTENT_TYPES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "text/plain",
)

SUPPORTED_INPUT_EXTENSIONS = (".pdf", ".docx", ".odt", ".txt")

FILE_MARKER = "### FONTE (extraída do arquivo)"

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


def attachment_is_supported(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    filename = attachment.filename.lower()
    return content_type in SUPPORTED_INPUT_CONTENT_TYPES or filename.endswith(
        SUPPORTED_INPUT_EXTENSIONS
    )


def _extract_file_text(file_bytes: bytes, filename: str) -> str:
    from markitdown import MarkItDown

    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    # txt files don't need markitdown
    if ext == "txt":
        return file_bytes.decode("utf-8", errors="replace")
    md = MarkItDown(enable_plugins=False)
    stream = BytesIO(file_bytes)
    result = md.convert_stream(stream, file_extension=ext)
    return result.text_content


def build_relatorio_filename(titulo: str, user_id: int, ext: str) -> str:
    safe_titulo = re.sub(r"[^\w\s-]", "", titulo).strip().lower()
    safe_titulo = re.sub(r"[-\s]+", "_", safe_titulo) or "relatorio"
    if len(safe_titulo) > 60:
        safe_titulo = safe_titulo[:60]
    epoch = int(datetime.now().timestamp())
    return f"relatorio_{safe_titulo}_{user_id}_{epoch}{ext}"


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
        arquivo="Arquivo com instruções ou material fonte (.pdf, .docx, .odt, .txt)",
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
        arquivo: discord.Attachment | None = None,
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
        if arquivo is not None and not attachment_is_supported(arquivo):
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

        logging.info(
            "Relatorio started (user ID: %s, titulo: %r, paginas: %s, pesquisar: %s, formato: %s)",
            interaction.user.id,
            titulo[:80],
            paginas,
            pesquisar == "true",
            formato_valor,
        )

        # Extract file text if attachment provided
        fonte_arquivo = ""
        if arquivo is not None:
            try:
                response = await httpx_client.get(arquivo.url)
                response.raise_for_status()
                extracted = _extract_file_text(response.content, arquivo.filename)
                if not extracted.strip():
                    await interaction.followup.send(
                        "O arquivo anexado parece estar vazio."
                    )
                    return
                fonte_arquivo = extracted
                logging.info(
                    "Relatorio file extracted (user ID: %s, length: %s)",
                    interaction.user.id,
                    len(fonte_arquivo),
                )
            except Exception:
                logging.exception(
                    "Relatorio file extraction failed (user ID: %s)",
                    interaction.user.id,
                )
                await interaction.followup.send(
                    "Não consegui ler o arquivo. Verifique se ele é válido."
                )
                return

        # Truncate file text if over max
        relatorio_config = state.config.get("relatorio", {})
        max_fonte_chars = relatorio_config.get("max_fonte_chars", 75000)
        if len(fonte_arquivo) > max_fonte_chars:
            logging.warning(
                "Relatorio file text truncated (user ID: %s, original: %s, max: %s)",
                interaction.user.id,
                len(fonte_arquivo),
                max_fonte_chars,
            )
            fonte_arquivo = fonte_arquivo[:max_fonte_chars]

        # Build messages
        autor = interaction.user.display_name
        data_atual = _format_date_pt(datetime.now())

        messages: list[dict[str, Any]] = build_relatorio_messages(
            titulo=titulo,
            descricao=descricao,
            autor=autor,
            data=data_atual,
            topicos=topicos,
            secoes=secoes,
            paginas=paginas,
            pesquisar=pesquisar == "true",
            instrucoes=instrucoes,
            fonte_arquivo=fonte_arquivo,
        )

        # Model resolution
        model = relatorio_config.get("model")
        curr_model = model if model else state.curr_model

        openai_client, openai_config = get_openai_config(state.config, curr_model)

        raw_output = ""
        request_started_at = datetime.now().timestamp()
        pesquisar_enabled = pesquisar == "true"

        try:
            if pesquisar_enabled:
                max_iterations = relatorio_config.get("max_tool_iterations", 15)
                search_results_count = relatorio_config.get(
                    "search_results_per_topic", 8
                )
                max_pages = relatorio_config.get("max_page_fetches", 5)

                raw_output = await run_research_loop(
                    openai_client=openai_client,
                    openai_config=openai_config,
                    messages=messages,
                    max_iterations=max_iterations,
                    search_results_per_topic=search_results_count,
                    max_page_fetches=max_pages,
                    user_id=interaction.user.id,
                )
            else:
                completion_task = asyncio.create_task(
                    openai_client.chat.completions.create(
                        **build_openai_chat_completion_kwargs(
                            openai_config,
                            messages,
                            stream=False,
                            tool_choice="none",
                        )
                    )
                )
                completion = await await_task_with_heartbeats(
                    completion_task,
                    (
                        "Relatorio LLM request still running "
                        f"(user ID: {interaction.user.id}, "
                        f"model: {openai_config['model']})"
                    ),
                )
                raw_output = get_completion_text(completion)

            elapsed = datetime.now().timestamp() - request_started_at
            logging.info(
                "Relatorio LLM request completed (user ID: %s, model: %s, elapsed: %.2fs)",
                interaction.user.id,
                openai_config["model"],
                elapsed,
            )

        except ContentFilterError as exc:
            logging.error(
                "Relatorio LLM content filter triggered (user ID: %s)",
                interaction.user.id,
            )
            await interaction.followup.send(str(exc))
            return
        except APIError as exc:
            logging.exception(
                "Provider error while generating relatorio: %s",
                get_provider_error_detail(exc),
            )
            await interaction.followup.send(
                "O provedor do modelo interrompeu a geração do relatório. "
                + f"Detalhe do provedor: `{str(exc)[:500]}`"
            )
            return
        except Exception:
            logging.exception("Error while generating relatorio")
            await interaction.followup.send(
                "Não consegui gerar o relatório agora. "
                + "Verifique os logs e tente novamente."
            )
            return

        if not raw_output.strip():
            await interaction.followup.send(
                "Não foi possível gerar o conteúdo do relatório."
            )
            return

        # Generate document file
        try:
            file_bytes, ext = generate_document(raw_output, titulo, formato_valor)
            filename = build_relatorio_filename(titulo, interaction.user.id, ext)
        except Exception:
            logging.exception("Error while generating relatorio document file")
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
