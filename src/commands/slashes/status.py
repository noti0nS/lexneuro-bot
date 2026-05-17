import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from ...db import get_connection
from ...helpers.status_db import get_latest_message


def _is_admin(user: discord.User | discord.Member, state: object) -> bool:
    config = getattr(state, "config", {}) or {}
    admin_ids = config.get("permissions", {}).get("users", {}).get("admin_ids", [])
    return user.id in admin_ids


def register_status_commands(
    discord_bot: commands.Bot,
    state: object,
) -> None:
    async def get_latest_timestamp() -> datetime | None:
        latest = get_latest_message()
        if latest is None:
            return None
        _, created_at_str = latest
        try:
            return datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except (ValueError, TypeError):
            return None

    @discord_bot.tree.command(
        name="status-reset",
        description="Force immediate status regeneration (admin only)",
    )
    async def status_reset(interaction: discord.Interaction) -> None:
        if not _is_admin(interaction.user, state):
            await interaction.response.send_message(
                "Você não tem permissão para usar este comando.", ephemeral=True
            )
            return

        from ...helpers.status_scheduler import update_status

        conn = get_connection()
        try:
            conn.execute("DELETE FROM status_history ORDER BY id DESC LIMIT 1")
            conn.commit()
        finally:
            conn.close()

        await interaction.response.send_message(
            "Regenerando status agora...", ephemeral=True
        )
        logging.info(
            "Status reset triggered by admin (user ID: %s)", interaction.user.id
        )
        await update_status(discord_bot)

    @discord_bot.tree.command(
        name="status-time",
        description="Show time remaining until the next automatic status change",
    )
    async def status_time(interaction: discord.Interaction) -> None:
        config = getattr(state, "config", {}) or {}
        status_config = config.get("status") or {}
        interval_hours = status_config.get("interval_hours", 24)

        latest_ts = await get_latest_timestamp()
        if latest_ts is None:
            remaining = interval_hours
        else:
            age_hours = (datetime.now(timezone.utc) - latest_ts).total_seconds() / 3600
            remaining = max(0.0, interval_hours - age_hours)

        hours = int(remaining)
        minutes = int((remaining - hours) * 60)
        time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

        await interaction.response.send_message(
            f"Próxima troca automática de status em: **{time_str}** (intervalo: {interval_hours}h)",
            ephemeral=True,
        )
