import asyncio
import logging
from typing import Any

import discord
import httpx
from discord.ext import commands

from ...helpers.async_utils import await_task_with_heartbeats
from ...helpers.attachments import download_attachment_text
from ...helpers.content import get_completion_text
from ...helpers.llm import (
    LLMAborted,
    execute_chat_completion,
    llm_error_handling,
)
from ...helpers.send import send_followup_chunked
from ...prompts.sql_cmd import build_sql_messages

DIALETO_SQL_CHOICES = [
    discord.app_commands.Choice(name="Genérico (padrão SQL)", value="generico"),
    discord.app_commands.Choice(name="PostgreSQL", value="postgresql"),
    discord.app_commands.Choice(name="MySQL / MariaDB", value="mysql"),
    discord.app_commands.Choice(name="SQLite", value="sqlite"),
    discord.app_commands.Choice(name="SQL Server", value="sqlserver"),
    discord.app_commands.Choice(name="Oracle", value="oracle"),
]

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

            file_text = await download_attachment_text(
                httpx_client, arquivo, interaction
            )
            if file_text is None:
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

        raw_output = ""
        try:
            async with llm_error_handling(interaction, "SQL"):
                messages = build_sql_messages(
                    consulta=sql_text,
                    dialeto=dialeto_valor,
                )
                logging.info(
                    "SQL LLM request started (user ID: %s, model: %s)",
                    interaction.user.id,
                    state.curr_model,
                )
                completion_task = asyncio.create_task(
                    execute_chat_completion(
                        config=state.config,
                        model_name=state.curr_model,
                        messages=messages,
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
        except LLMAborted:
            return

        if not raw_output:
            await interaction.followup.send("Não foi possível analisar a SQL.")
            return

        await send_followup_chunked(interaction, raw_output)
