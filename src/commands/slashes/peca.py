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
from ...helpers.async_utils import await_task_with_heartbeats
from ...helpers.content import get_completion_text
from ...helpers.documents import DOCUMENT_FORMAT_CHOICES, generate_document
from ...helpers.llm import get_provider_error_detail
from ...helpers.send import send_document_result
from ...prompts.peca import build_peca_messages

SUPPORTED_INPUT_CONTENT_TYPES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
)

SUPPORTED_INPUT_EXTENSIONS = (".pdf", ".docx", ".odt")

FILE_MARKER = "### CASO PRÁTICO (extraído do arquivo)"


def attachment_is_supported(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    filename = attachment.filename.lower()
    return content_type in SUPPORTED_INPUT_CONTENT_TYPES or filename.endswith(
        SUPPORTED_INPUT_EXTENSIONS
    )


def _extract_file_text(file_bytes: bytes, filename: str) -> str:
    from markitdown import MarkItDown

    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    md = MarkItDown(enable_plugins=False)
    stream = BytesIO(file_bytes)
    result = md.convert_stream(stream, file_extension=ext)
    return result.text_content


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


def build_peca_filename(tipo: str | None, user_id: int, ext: str) -> str:
    safe_tipo = re.sub(r"[^\w\s-]", "", tipo or "").strip().lower()
    safe_tipo = re.sub(r"[-\s]+", "_", safe_tipo) or "peca"
    if len(safe_tipo) > 60:
        safe_tipo = safe_tipo[:60]
    epoch = int(datetime.now().timestamp())
    return f"peca_{safe_tipo}_{user_id}_{epoch}{ext}"


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
        arquivo="Arquivo (.pdf, .docx, .odt) com o enunciado do caso",
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
        arquivo: discord.Attachment | None = None,
        tipo: str | None = None,
        area: str | None = None,
        instrucoes: str | None = None,
        format: discord.app_commands.Choice[str] | None = None,
    ) -> None:
        formato_valor = format.value if format else "docx"

        if not enunciado.strip() and arquivo is None:
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
        max_enunciado_chars = peca_config.get("max_enunciado_chars", 50000)
        max_file_mb = peca_config.get("max_file_mb", 25)
        peca_model = peca_config.get("model")
        curr_model = peca_model if peca_model else state.curr_model

        combined_text = enunciado.strip()

        if arquivo is not None:
            if not attachment_is_supported(arquivo):
                await interaction.response.send_message(
                    "Tipo de documento não suportado. Envie um arquivo .pdf, .docx ou .odt.",
                    ephemeral=True,
                )
                return

            file_size_mb = arquivo.size / (1024 * 1024)
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
                arquivo.filename,
            )

            try:
                response = await httpx_client.get(arquivo.url)
                response.raise_for_status()
            except Exception:
                logging.exception(
                    "Peça file download failed (user ID: %s, file: %s)",
                    interaction.user.id,
                    arquivo.filename,
                )
                await interaction.response.send_message(
                    "Não consegui baixar o anexo. Tente novamente.",
                    ephemeral=True,
                )
                return

            logging.info(
                "Peça file extraction started (user ID: %s, file: %s, bytes: %s)",
                interaction.user.id,
                arquivo.filename,
                len(response.content),
            )

            try:
                extracted = await asyncio.to_thread(
                    _extract_file_text, response.content, arquivo.filename
                )
            except Exception:
                logging.exception(
                    "Peça file extraction failed (user ID: %s, file: %s)",
                    interaction.user.id,
                    arquivo.filename,
                )
                await interaction.response.send_message(
                    "Não consegui extrair o texto do anexo. Verifique se o arquivo é válido.",
                    ephemeral=True,
                )
                return

            if not extracted.strip():
                await interaction.response.send_message(
                    "O documento anexado parece estar vazio.",
                    ephemeral=True,
                )
                return

            logging.info(
                "Peça file extraction completed (user ID: %s, file: %s, chars: %s)",
                interaction.user.id,
                arquivo.filename,
                len(extracted),
            )

            if combined_text:
                combined_text = f"{combined_text}\n\n{FILE_MARKER}\n\n{extracted}"
            else:
                combined_text = f"{FILE_MARKER}\n\n{extracted}"

        total_chars = len(combined_text)
        if total_chars > max_enunciado_chars:
            combined_text = combined_text[:max_enunciado_chars]
            logging.warning(
                "Peça enunciado truncated (user ID: %s, original: %s, max: %s)",
                interaction.user.id,
                total_chars,
                max_enunciado_chars,
            )

        await interaction.response.send_message(
            "Gerando a peça processual... Isso pode levar alguns segundos.",
            ephemeral=True,
        )

        logging.info(
            "Peça command started (user ID: %s, chars: %s, tipo: %r, area: %r, format: %s)",
            interaction.user.id,
            len(combined_text),
            tipo,
            area,
            formato_valor,
        )

        openai_client, openai_config = get_openai_config(state.config, curr_model)

        messages = build_peca_messages(
            enunciado=combined_text,
            tipo=tipo,
            area=area,
            instrucoes=instrucoes,
        )

        raw_output = ""
        request_started_at = datetime.now().timestamp()

        try:
            logging.info(
                "Peça LLM request starting (user ID: %s, model: %s)",
                interaction.user.id,
                openai_config["model"],
            )

            completion_task = asyncio.create_task(
                openai_client.chat.completions.create(
                    **build_openai_chat_completion_kwargs(
                        openai_config, messages, stream=False
                    )
                )
            )
            completion = await await_task_with_heartbeats(
                completion_task,
                (
                    "Peça LLM request still running "
                    f"(user ID: {interaction.user.id}, model: {openai_config['model']})"
                ),
            )

            elapsed = datetime.now().timestamp() - request_started_at
            logging.info(
                "Peça LLM request completed (user ID: %s, model: %s, elapsed: %.2fs)",
                interaction.user.id,
                openai_config["model"],
                elapsed,
            )

            raw_output = get_completion_text(completion)

        except APIError as exc:
            logging.exception(
                "Provider error while generating peça: %s",
                get_provider_error_detail(exc),
            )
            await interaction.followup.send(
                "O provedor do modelo interrompeu a geração da peça. "
                + f"Detalhe do provedor: `{str(exc)[:500]}`"
            )
            return
        except Exception:
            logging.exception("Error while generating peça")
            await interaction.followup.send(
                "Não consegui gerar a peça processual agora. "
                + "Verifique os logs e tente novamente."
            )
            return

        if not raw_output.strip():
            await interaction.followup.send("Não foi possível gerar a peça processual.")
            return

        try:
            title = tipo if tipo else "Peça Processual"
            file_bytes, ext = generate_document(raw_output, title, formato_valor)
            filename = build_peca_filename(tipo, interaction.user.id, ext)
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
