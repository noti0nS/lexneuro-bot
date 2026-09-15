import asyncio
import json
import logging

logger = logging.getLogger(__name__)
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

import discord
import httpx
from discord.ext import commands

from ...helpers.ai_tools import (
    DocumentToolSetup,
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
from ...prompts.peca import build_peca_messages

TIPO_CHOICES = [
    "Alvará",
    "Petição inicial",
    "Contestação",
    "Contestação com reconvenção",
    "Procuração",
    "Substabelecimento",
    "Contrato de honorários",
]

AREA_CHOICES = [
    "Civil",
    "Penal",
    "Trabalhista",
    "Tributário",
    "Constitucional",
    "Administrativo",
    "Empresarial",
    "Consumidor",
    "Família",
    "Previdenciário",
    "Ambiental",
]


def filter_choices(
    choices: list[str], current: str
) -> list[discord.app_commands.Choice[str]]:
    if not current:
        return [discord.app_commands.Choice(name=c, value=c) for c in choices]
    lowered = current.lower()
    return [
        discord.app_commands.Choice(name=c, value=c)
        for c in choices
        if lowered in c.lower()
    ]


def combine_enunciado(text: str, file_text: str | None) -> str:
    parts = [part.strip() for part in (text, file_text) if part and part.strip()]
    return "\n\n".join(parts)


async def tipo_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[discord.app_commands.Choice[str]]:
    del interaction
    return filter_choices(TIPO_CHOICES, current)


async def area_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[discord.app_commands.Choice[str]]:
    del interaction
    return filter_choices(AREA_CHOICES, current)


def register_peca_command(
    discord_bot: commands.Bot,
    state: Any,
    httpx_client: httpx.AsyncClient,
    user_has_permission: Any,
) -> None:
    @discord_bot.tree.command(
        name="peca",
        description="Gere uma peça processual completa a partir de um enunciado ou arquivo",
    )
    @discord.app_commands.describe(
        enunciado="Texto do enunciado (casos curtos)",
        enunciado_arquivo="Arquivo com o enunciado (.pdf, .docx, .odt, .txt)",
        fonte="Documento de apoio para consulta (opcional)",
        tipo="Tipo da peça processual (se omitido, o bot infere)",
        area="Área do Direito (ex: Civil, Penal, Trabalhista)",
        instrucoes="Instruções adicionais para a geração da peça",
        format="Formato do arquivo de saída",
    )
    @discord.app_commands.choices(format=DOCUMENT_FORMAT_CHOICES)
    @discord.app_commands.autocomplete(tipo=tipo_autocomplete, area=area_autocomplete)
    async def peca_command(
        interaction: discord.Interaction,
        enunciado: str = "",
        enunciado_arquivo: discord.Attachment | None = None,
        fonte: discord.Attachment | None = None,
        tipo: str | None = None,
        area: str | None = None,
        instrucoes: str | None = None,
        format: discord.app_commands.Choice[str] | None = None,
    ) -> None:
        formato_valor = format.value if format else "docx"

        if not enunciado.strip() and enunciado_arquivo is None:
            await interaction.response.send_message(
                "Informe o enunciado em texto ou anexe um arquivo com o enunciado "
                + "(.pdf, .docx, .odt, .txt). O documento de apoio (`fonte`) não "
                + "substitui o enunciado.",
                ephemeral=True,
            )
            return

        for attachment in (enunciado_arquivo, fonte):
            if attachment is not None and not attachment_is_supported(attachment):
                await interaction.response.send_message(
                    "Tipo de documento não suportado. Envie um arquivo "
                    + ".pdf, .docx, .odt ou .txt.",
                    ephemeral=True,
                )
                return

        peca_config = state.config.get("peca", {})
        max_file_mb = peca_config.get("max_file_mb", 25)
        max_enunciado_kb = peca_config.get("max_enunciado_kb", 1024)
        max_enunciado_chars = peca_config.get("max_enunciado_chars", 200000)
        peca_model = peca_config.get("model")
        curr_model = peca_model if peca_model else state.curr_model

        if enunciado_arquivo is not None:
            enunciado_file_kb = enunciado_arquivo.size / 1024
            if enunciado_file_kb > max_enunciado_kb:
                await interaction.response.send_message(
                    "O arquivo do enunciado excede o limite de "
                    + f"{max_enunciado_kb} KB ({enunciado_file_kb:.1f} KB). "
                    + "Envie um arquivo menor.",
                    ephemeral=True,
                )
                return

        if fonte is not None:
            file_size_mb = fonte.size / (1024 * 1024)
            if file_size_mb > max_file_mb:
                await interaction.response.send_message(
                    f"O arquivo de apoio excede o limite de {max_file_mb} MB "
                    + f"({file_size_mb:.1f} MB). "
                    + "Envie um arquivo menor.",
                    ephemeral=True,
                )
                return

        if not user_has_permission(interaction.user, interaction.channel, state.config):
            await interaction.response.send_message(
                "Você não tem permissão para usar este bot aqui.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)

        enunciado_text = enunciado.strip()
        enunciado_origem: str | None = None

        if enunciado_arquivo is not None:
            logger.info(
                "Peça enunciado file download started (user ID: %s, file: %s)",
                interaction.user.id,
                enunciado_arquivo.filename,
            )

            try:
                file_text = await read_attachment_text(enunciado_arquivo, httpx_client)
            except ValueError:
                await interaction.followup.send(
                    "Tipo de documento não suportado. Envie um arquivo "
                    + ".pdf, .docx, .odt ou .txt.",
                )
                return
            except Exception:
                logger.exception(
                    "Peça enunciado file extraction failed (user ID: %s, file: %s)",
                    interaction.user.id,
                    enunciado_arquivo.filename,
                )
                await interaction.followup.send(
                    "Não consegui extrair o texto do arquivo do enunciado. "
                    + "Verifique se ele é válido.",
                )
                return

            if not file_text.strip():
                await interaction.followup.send(
                    "O arquivo do enunciado parece estar vazio.",
                )
                return

            enunciado_text = combine_enunciado(enunciado_text, file_text)
            enunciado_origem = enunciado_arquivo.filename

            if len(enunciado_text) > max_enunciado_chars:
                await interaction.followup.send(
                    f"O enunciado tem {len(enunciado_text):,} caracteres, acima do "
                    + f"limite de {max_enunciado_chars:,}. Reduza o enunciado ou "
                    + "divida o arquivo em partes menores.",
                )
                return

            logger.info(
                "Peça enunciado file extraction completed (user ID: %s, file: %s, chars: %s)",
                interaction.user.id,
                enunciado_arquivo.filename,
                len(enunciado_text),
            )

        doc: DocumentChunks | None = None
        peca_tools: list[dict[str, Any]] = []
        peca_on_extra_tool: Callable[[str, dict[str, Any]], str] | None = None

        if fonte is not None:
            logger.info(
                "Peça file download started (user ID: %s, file: %s)",
                interaction.user.id,
                fonte.filename,
            )

            try:
                setup: DocumentToolSetup = await setup_document_tools(
                    fonte, httpx_client, []
                )
            except ValueError:
                await interaction.followup.send(
                    "O documento anexado parece estar vazio.",
                )
                return
            except Exception:
                logger.exception(
                    "Peça file extraction failed (user ID: %s, file: %s)",
                    interaction.user.id,
                    fonte.filename,
                )
                await interaction.followup.send(
                    "Não consegui extrair o texto do arquivo. Verifique se ele é válido.",
                )
                return

            doc = setup.doc
            peca_tools = setup.tools
            peca_on_extra_tool = setup.on_extra_tool

            logger.info(
                "Peça file extraction completed (user ID: %s, file: %s, chunks: %s, chars: %s)",
                interaction.user.id,
                fonte.filename,
                doc.total_chunks,
                doc.total_chars,
            )

        await interaction.followup.send(
            "Gerando a peça processual... Isso pode levar alguns segundos.",
        )

        logger.info(
            "Peça command started (user ID: %s, chars: %s, tipo: %r, area: %r, "
            + "format: %s, enunciado_arquivo: %r, has_fonte: %s)",
            interaction.user.id,
            len(enunciado_text),
            tipo,
            area,
            formato_valor,
            enunciado_origem,
            doc is not None,
        )

        messages = build_peca_messages(
            enunciado=enunciado_text,
            tipo=tipo,
            area=area,
            instrucoes=instrucoes,
            has_source_document=doc is not None,
            enunciado_arquivo_nome=enunciado_origem,
        )

        raw_output = ""
        request_started_at = datetime.now(tz=UTC).timestamp()

        try:
            async with llm_error_handling(interaction, "Peça"):
                if doc is not None:
                    for iteration in range(5):
                        logger.info(
                            "Peça LLM tool iteration %s/5 (user ID: %s, model: %s)",
                            iteration + 1,
                            interaction.user.id,
                            curr_model,
                        )

                        completion_task = asyncio.create_task(
                            execute_chat_completion(
                                config=state.config,
                                model_name=curr_model,
                                messages=messages,
                                stream=False,
                                tools=peca_tools,
                                tool_choice="auto",
                            )
                        )
                        completion = await await_task_with_heartbeats(
                            completion_task,
                            f"Peça LLM request still running (user ID: {interaction.user.id}, model: {curr_model})",
                        )
                        choice = completion.choices[0]

                        if choice.finish_reason != "tool_calls":
                            raw_output = get_completion_text(completion)
                            break

                        if choice.message and choice.message.tool_calls:
                            messages.append(choice.message.to_dict())
                            for tc_raw in choice.message.tool_calls:
                                tc = cast(Any, tc_raw)
                                try:
                                    args = json.loads(tc.function.arguments)
                                except json.JSONDecodeError:
                                    args = {}
                                assert peca_on_extra_tool is not None
                                result = peca_on_extra_tool(tc.function.name, args)
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tc.id,
                                        "content": result,
                                    }
                                )
                    else:
                        logger.warning(
                            "Peça tool loop exhausted, forcing final call (user ID: %s)",
                            interaction.user.id,
                        )
                        completion_task = asyncio.create_task(
                            execute_chat_completion(
                                config=state.config,
                                model_name=curr_model,
                                messages=messages,
                                stream=False,
                                tool_choice="none",
                            )
                        )
                        completion = await await_task_with_heartbeats(
                            completion_task,
                            f"Peça final generation still running (user ID: {interaction.user.id})",
                        )
                        raw_output = get_completion_text(completion)
                else:
                    logger.info(
                        "Peça LLM request starting (user ID: %s, model: %s)",
                        interaction.user.id,
                        curr_model,
                    )

                    completion_task = asyncio.create_task(
                        execute_chat_completion(
                            config=state.config,
                            model_name=curr_model,
                            messages=messages,
                            stream=False,
                        )
                    )
                    completion = await await_task_with_heartbeats(
                        completion_task,
                        f"Peça LLM request still running (user ID: {interaction.user.id}, model: {curr_model})",
                    )
                    raw_output = get_completion_text(completion)

                elapsed = datetime.now(tz=UTC).timestamp() - request_started_at
                logger.info(
                    "Peça LLM request completed (user ID: %s, model: %s, elapsed: %.2fs)",
                    interaction.user.id,
                    curr_model,
                    elapsed,
                )
        except LLMAborted:
            return

        if not raw_output.strip():
            await interaction.followup.send("Não foi possível gerar a peça processual.")
            return

        try:
            title = tipo if tipo else "Peça Processual"
            file_bytes, ext = generate_document(raw_output, title, formato_valor)
            filename = build_filename("peca", tipo or "peca", interaction.user.id, ext)
        except RuntimeError as exc:
            await interaction.followup.send(str(exc))
            return
        except Exception:
            logger.exception("Error while generating document file")
            await interaction.followup.send(
                "Não consegui gerar o arquivo do documento. "
                + "O conteúdo será enviado em mensagens."
            )
            await send_document_result(
                interaction, raw_output, "peca.txt", b"", label="Peça processual"
            )
            return

        await send_document_result(
            interaction, raw_output, filename, file_bytes, label="Peça processual"
        )
