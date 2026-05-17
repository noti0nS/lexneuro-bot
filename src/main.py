import argparse
import asyncio
import json
import logging

import discord

from .bot import create_discord_bot
from .config import get_bot_token, get_config, load_config, mask_sensitive_config
from .helpers.health_server import start_health_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)

parser = argparse.ArgumentParser()
parser.add_argument("--config", "-c", default="config.yaml")


async def main() -> None:
    load_config(parser.parse_args().config)
    config = get_config()
    logging.info(
        "Loaded config:\n%s",
        json.dumps(
            mask_sensitive_config(config), indent=2, sort_keys=True, ensure_ascii=False
        ),
    )
    discord_bot = create_discord_bot(config)

    try:
        await discord_bot.start(get_bot_token(config))
    except discord.LoginFailure as exc:
        logging.error(
            "Discord rejected the bot token. Check config.yaml bot_token (it must be the bot token, not the client secret) "
            + "and regenerate it if needed."
        )
        raise RuntimeError("Discord bot login failed.") from exc
    finally:
        await discord_bot.close()


def run() -> None:
    start_health_server()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
