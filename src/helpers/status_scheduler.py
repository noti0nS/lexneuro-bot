import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from ..config import get_config, get_openai_config
from ..db import init_db
from .status_db import add_message, get_latest_message, get_random_message
from .status_generator import generate_status_message


async def _apply_status(bot: commands.Bot, text: str) -> None:
    activity = discord.CustomActivity(name=text[:128])
    await bot.change_presence(activity=activity)
    logging.info("Status updated to: %s", text[:128])


async def update_status(bot: commands.Bot) -> None:
    config = get_config()

    status_config = config.get("status") or {}

    if not status_config.get("enabled", True):
        fallback = config.get("status_message") or ""
        if fallback:
            await _apply_status(bot, fallback)
        return

    interval_hours = status_config.get("interval_hours", 24)
    max_history = status_config.get("max_history", 100)

    latest = get_latest_message()
    if latest is not None:
        content, created_at_str = latest
        try:
            created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            age_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600
            if age_hours < interval_hours:
                logging.info(
                    "Latest DB message is fresh (age=%.1fh). Applying: %s",
                    age_hours,
                    content,
                )
                await _apply_status(bot, content)
                return
        except (ValueError, TypeError):
            logging.warning("Could not parse created_at timestamp: %s", created_at_str)

    status_model = status_config.get("model")
    if status_model:
        try:
            openai_client, openai_config = get_openai_config(config, status_model)
            generated = await generate_status_message(openai_client, openai_config)
            if generated:
                add_message(generated, max_history=max_history)
                await _apply_status(bot, generated)
                return
        except Exception:
            logging.exception(
                "Status generation failed, falling back to DB random or config"
            )

    random_msg = get_random_message()
    if random_msg:
        logging.info("Falling back to random DB message: %s", random_msg)
        await _apply_status(bot, random_msg)
        return

    fallback = config.get("status_message") or ""
    if fallback:
        logging.info("Falling back to config status_message: %s", fallback)
        await _apply_status(bot, fallback)


_status_loop_started = False


def start_status_scheduler(bot: commands.Bot) -> None:
    global _status_loop_started
    if _status_loop_started:
        return
    _status_loop_started = True

    init_db()

    @tasks.loop(hours=1)
    async def status_loop() -> None:
        await update_status(bot)

    @status_loop.before_loop
    async def before_status_loop() -> None:
        await bot.wait_until_ready()

    bot.loop.create_task(_run_initial_and_start(bot, status_loop))


async def _run_initial_and_start(
    bot: commands.Bot,
    loop: tasks.Loop,  # pyright: ignore[reportMissingTypeArgument]
) -> None:
    await bot.wait_until_ready()
    await update_status(bot)
    loop.start()
    logging.info("Status scheduler started (interval=1h)")
