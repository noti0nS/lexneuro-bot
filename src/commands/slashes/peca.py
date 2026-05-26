import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime
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
        enunciado="Enunciado do caso prático ou instruções da peça",
        fonte="Documento fonte (.pdf, .docx, .odt, .txt)",
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
        fonte: discord.Attachment | None = None,
        tipo: str | None = None,
        area: str | None = None,
        instrucoes: str | None = None,
        format: discord.app_commands.Choice[str] | None = None,
    ) -> None:
        formato_valor = format.value if format else "docx"

        if not enunciado.strip() and fonte is None:
            await interaction.response.send_message(
                "Informe um enunciado ou anexe um arquivo (.pdf, .docx, .odt) com o caso.",
                ephemeral=True,
            )
            return

        if not user_has_permission(interaction.user, interaction.channel, state.config):
            await interaction.response.send_message(
                "Você não tem permissão para usar este bot aqui.", ephemeral=True
            )
            return

        peca_config = state.config.get("peca", {})
        max_file_mb = peca_config.get("max_file_mb", 25)
        peca_model = peca_config.get("model")
        curr_model = peca_model if peca_model else state.curr_model

        combined_text = enunciado.strip()

        doc: DocumentChunks | None = None
        peca_tools: list[dict[str, Any]] = []
        peca_on_extra_tool: Callable[[str, dict[str, Any]], str] | None = None

        if fonte is not None:
            if not attachment_is_supported(fonte):
                await interaction.response.send_message(
                    "Tipo de documento não suportado. Envie um arquivo .pdf, .docx, .odt ou .txt.",
                    ephemeral=True,
                )
                return

            file_size_mb = fonte.size / (1024 * 1024)
            if file_size_mb > max_file_mb:
                await interaction.response.send_message(
                    f"O arquivo excede o limite de {max_file_mb} MB "
                    + f"({file_size_mb:.1f} MB). "
                    + "Envie um arquivo menor.",
                    ephemeral=True,
                )
                return

            logging.info(
                "Peça file download started (user ID: %s, file: %s)",
                interaction.user.id,
                fonte.filename,
            )

            try:
                setup: DocumentToolSetup = await setup_document_tools(
                    fonte, httpx_client, []
                )
            except ValueError:
                await interaction.response.send_message(
                    "O documento anexado parece estar vazio.",
                    ephemeral=True,
                )
                return
            except Exception:
                logging.exception(
                    "Peça file extraction failed (user ID: %s, file: %s)",
                    interaction.user.id,
                    fonte.filename,
                )
                await interaction.response.send_message(
                    "Não consegui extrair o texto do arquivo. Verifique se ele é válido.",
                    ephemeral=True,
                )
                return

            doc = setup.doc
            peca_tools = setup.tools
            peca_on_extra_tool = setup.on_extra_tool

            logging.info(
                "Peça file extraction completed (user ID: %s, file: %s, chunks: %s, chars: %s)",
                interaction.user.id,
                fonte.filename,
                doc.total_chunks,
                doc.total_chars,
            )

        await interaction.response.send_message(
            "Gerando a peça processual... Isso pode levar alguns segundos.",
            ephemeral=True,
        )

        logging.info(
            "Peça command started (user ID: %s, chars: %s, tipo: %r, area: %r, format: %s, has_file: %s)",
            interaction.user.id,
            len(combined_text),
            tipo,
            area,
            formato_valor,
            doc is not None,
        )

        messages = build_peca_messages(
            enunciado=combined_text,
            tipo=tipo,
            area=area,
            instrucoes=instrucoes,
            has_attachment=doc is not None,
        )

        raw_output = ""
        request_started_at = datetime.now().timestamp()

        try:
            async with llm_error_handling(interaction, "Peça"):
                if doc is not None:
                    for iteration in range(5):
                        logging.info(
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
                        logging.warning(
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
                    logging.info(
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

                elapsed = datetime.now().timestamp() - request_started_at
                logging.info(
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
            logging.exception("Error while generating document file")
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
