import asyncio
import logging
from typing import Any

import discord
from discord.app_commands import Choice
from discord.ext import commands

from ..config import get_config


def register_model_command(
    discord_bot: commands.Bot,
    state: Any,
) -> None:
    @discord_bot.tree.command(
        name="model", description="View or switch the current model"
    )
    async def model_command(interaction: discord.Interaction, model: str) -> None:
        interaction_channel_type = (
            interaction.channel.type if interaction.channel else None
        )

        if model == state.curr_model:
            output = f"Current model: `{state.curr_model}`"
        else:
            user_is_admin = (
                interaction.user.id in state.config["permissions"]["users"]["admin_ids"]
            )
            if user_is_admin:
                state.curr_model = model
                output = f"Model switched to: `{model}`"
                logging.info(output)
            else:
                output = "You don't have permission to change the model."

        await interaction.response.send_message(
            output, ephemeral=(interaction_channel_type == discord.ChannelType.private)
        )

    @model_command.autocomplete("model")
    async def model_autocomplete(
        interaction: discord.Interaction, curr_str: str
    ) -> list[Choice[str]]:
        del interaction

        if curr_str == "":
            state.config = await asyncio.to_thread(get_config)

        choices = (
            [Choice(name=f"◉ {state.curr_model} (current)", value=state.curr_model)]
            if curr_str.lower() in state.curr_model.lower()
            else []
        )
        choices += [
            Choice(name=f"○ {model_name}", value=model_name)
            for model_name in state.config["models"]
            if model_name != state.curr_model and curr_str.lower() in model_name.lower()
        ]

        return choices[:25]
