import asyncio
import logging
from typing import Any

import discord
from discord.ext import commands
from openai import APIError

from ..config import build_openai_chat_completion_kwargs, get_openai_config
from ..helpers.async_utils import await_task_with_heartbeats
from ..helpers.content import get_completion_text
from ..helpers.llm import get_provider_error_detail
from ..prompts.regex import build_regex_messages


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

        logging.info(
            "Regex command (user ID: %s, linguagem: %s, descricao: %r)",
            interaction.user.id,
            linguagem,
            descricao[:80],
        )

        openai_client, openai_config = get_openai_config(state.config, state.curr_model)

        raw_output = ""
        try:
            messages = build_regex_messages(
                descricao=descricao.strip(),
                exemplos=exemplos.strip() if exemplos else None,
                linguagem=linguagem,
            )
            logging.info(
                "Regex LLM request started (user ID: %s, model: %s)",
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
                f"Regex LLM request still running (user ID: {interaction.user.id})",
            )
            raw_output = get_completion_text(completion)
            logging.info(
                "Regex LLM request completed (user ID: %s)",
                interaction.user.id,
            )
        except APIError as exc:
            logging.exception(
                "Provider error while generating regex: %s",
                get_provider_error_detail(exc),
            )
            await interaction.followup.send(
                f"O provedor do modelo interrompeu a geração. Detalhe: `{str(exc)[:500]}`"
            )
            return
        except Exception:
            logging.exception("Error while generating regex")
            await interaction.followup.send(
                "Não consegui gerar a regex agora. Tente novamente."
            )
            return

        if not raw_output:
            await interaction.followup.send("Não foi possível gerar a regex.")
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
