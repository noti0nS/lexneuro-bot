import asyncio
import logging
from typing import Any

import discord
import httpx
from discord.ext import commands
from openai import APIError

from ..config import build_openai_chat_completion_kwargs, get_openai_config
from ..helpers.async_utils import await_task_with_heartbeats
from ..helpers.content import get_completion_text
from ..helpers.llm import get_provider_error_detail
from ..helpers.ui import DIALETO_SQL_CHOICES
from ..prompts.sql_cmd import build_sql_messages

SQL_EXTENSIONS = (".sql",)
SQL_CONTENT_TYPES = (
    "application/sql",
    "text/plain",
    "application/octet-stream",
    "text/x-sql",
)


def _attachment_is_sql(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    filename = attachment.filename.lower()
    return content_type in SQL_CONTENT_TYPES or filename.endswith(SQL_EXTENSIONS)


def register_sql_command(
    discord_bot: commands.Bot,
    state: Any,
    httpx_client: httpx.AsyncClient,
) -> None:
    @discord_bot.tree.command(
        name="sql",
        description="Formate e explique uma consulta SQL",
    )
    @discord.app_commands.describe(
        consulta="Consulta SQL para formatar e explicar",
        arquivo="Arquivo .sql com a consulta",
        dialeto="Dialeto SQL usado na consulta",
    )
    @discord.app_commands.choices(dialeto=DIALETO_SQL_CHOICES)
    async def sql_command(
        interaction: discord.Interaction,
        consulta: str | None = None,
        arquivo: discord.Attachment | None = None,
        dialeto: discord.app_commands.Choice[str] | None = None,
    ) -> None:
        dialeto_valor = dialeto.value if dialeto else "generico"

        if (not consulta or not consulta.strip()) and arquivo is None:
            await interaction.response.send_message(
                "Informe uma consulta SQL ou anexe um arquivo .sql.",
                ephemeral=True,
            )
            return

        sql_text = (consulta or "").strip()

        if arquivo is not None:
            if not _attachment_is_sql(arquivo):
                await interaction.response.send_message(
                    "Tipo de arquivo não suportado. Envie um arquivo .sql.",
                    ephemeral=True,
                )
                return

            logging.info(
                "SQL file download started (user ID: %s, file: %s)",
                interaction.user.id,
                arquivo.filename,
            )
            try:
                response = await httpx_client.get(arquivo.url)
                response.raise_for_status()
            except Exception:
                logging.exception(
                    "SQL file download failed (user ID: %s, file: %s)",
                    interaction.user.id,
                    arquivo.filename,
                )
                await interaction.response.send_message(
                    "Não consegui baixar o anexo. Tente novamente.",
                    ephemeral=True,
                )
                return

            file_text = response.text.strip()
            if not file_text:
                await interaction.response.send_message(
                    "O arquivo parece estar vazio.", ephemeral=True
                )
                return

            if sql_text:
                sql_text = (
                    f"{sql_text}\n\n--- ARQUIVO: {arquivo.filename} ---\n\n{file_text}"
                )
            else:
                sql_text = file_text

        if not sql_text:
            await interaction.response.send_message(
                "A consulta SQL está vazia.", ephemeral=True
            )
            return

        max_sql_chars = 50000
        if len(sql_text) > max_sql_chars:
            original_length = len(sql_text)
            sql_text = sql_text[:max_sql_chars]
            logging.warning(
                "SQL text truncated (user ID: %s, original length: %s)",
                interaction.user.id,
                original_length,
            )

        await interaction.response.send_message("Analisando a SQL...", ephemeral=True)

        logging.info(
            "SQL command (user ID: %s, dialeto: %s, chars: %s)",
            interaction.user.id,
            dialeto_valor,
            len(sql_text),
        )

        openai_client, openai_config = get_openai_config(state.config, state.curr_model)

        raw_output = ""
        try:
            messages = build_sql_messages(
                consulta=sql_text,
                dialeto=dialeto_valor,
            )
            logging.info(
                "SQL LLM request started (user ID: %s, model: %s)",
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
                f"SQL LLM request still running (user ID: {interaction.user.id})",
            )
            raw_output = get_completion_text(completion)
            logging.info(
                "SQL LLM request completed (user ID: %s)",
                interaction.user.id,
            )
        except APIError as exc:
            logging.exception(
                "Provider error while analyzing SQL: %s",
                get_provider_error_detail(exc),
            )
            await interaction.followup.send(
                f"O provedor do modelo interrompeu a análise. Detalhe: `{str(exc)[:500]}`"
            )
            return
        except Exception:
            logging.exception("Error while analyzing SQL")
            await interaction.followup.send(
                "Não consegui analisar a SQL agora. Tente novamente."
            )
            return

        if not raw_output:
            await interaction.followup.send("Não foi possível analisar a SQL.")
            return

        if len(raw_output) <= 2000:
            await interaction.followup.send(raw_output)
        else:
            chunks: list[str] = []
            remaining = raw_output
            while len(remaining) > 2000:
                split_at = remaining.rfind("\n", 0, 2000)
                if split_at == -1:
                    split_at = 2000
                chunks.append(remaining[:split_at])
                remaining = remaining[split_at:].lstrip()
            if remaining:
                chunks.append(remaining)
            for chunk in chunks:
                await interaction.followup.send(chunk)
