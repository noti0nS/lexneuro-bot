import asyncio
import logging

logger = logging.getLogger(__name__)
from typing import Any

import discord
from discord.ext import commands

from ...helpers.async_utils import await_task_with_heartbeats
from ...helpers.content import get_completion_text
from ...helpers.llm import (
    LLMAborted,
    execute_chat_completion,
    llm_error_handling,
)
from ...helpers.send import send_followup_chunked
from ...prompts.regex import build_regex_messages


def register_regex_command(
    discord_bot: commands.Bot,
    state: Any,
) -> None:
    @discord_bot.tree.command(
        name="regex",
        description="Construa e teste uma expressão regular a partir de uma descrição em português",
    )
    @discord.app_commands.describe(
        descricao="O que você quer capturar? Ex: emails entre tags HTML, datas no formato dd/mm/aaaa",
        exemplos="Texto de exemplo para testar a regex",
        linguagem="Linguagem/flavor da regex (ex: python, javascript, java, csharp, go, rust)",
    )
    async def regex_command(
        interaction: discord.Interaction,
        descricao: str,
        exemplos: str | None = None,
        linguagem: str = "python",
    ) -> None:

        if not descricao.strip():
            await interaction.response.send_message(
                "Descreva o que você quer capturar com a regex.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message("Montando a regex...", ephemeral=True)

        logger.info(
            "Regex command (user ID: %s, linguagem: %s, descricao: %r)",
            interaction.user.id,
            linguagem,
            descricao[:80],
        )

        raw_output = ""
        try:
            async with llm_error_handling(interaction, "Regex"):
                messages = build_regex_messages(
                    descricao=descricao.strip(),
                    exemplos=exemplos.strip() if exemplos else None,
                    linguagem=linguagem,
                )
                logger.info(
                    "Regex LLM request started (user ID: %s, model: %s)",
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
                    f"Regex LLM request still running (user ID: {interaction.user.id})",
                )
                raw_output = get_completion_text(completion)
                logger.info(
                    "Regex LLM request completed (user ID: %s)",
                    interaction.user.id,
                )
        except LLMAborted:
            return

        if not raw_output:
            await interaction.followup.send("Não foi possível gerar a regex.")
            return

        await send_followup_chunked(interaction, raw_output)
