import logging
import re
from io import BytesIO

import discord
import httpx

from ...helpers.render import detect_language_name, render_code_image

from . import trigger

_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:\w*\s*\n)?(?P<body>.*)```\s*$",
    re.DOTALL,
)

_LANG_PREFIX_RE = re.compile(r"^lang=([a-zA-Z0-9#+\-]+)\s*:?\s*", re.DOTALL)


@trigger("capture")
async def handle_capture(
    message: discord.Message,
    args: str,
    state: object,
    httpx_client: httpx.AsyncClient,
) -> None:
    lang_override = None
    text = args
    lang_match = _LANG_PREFIX_RE.match(text)
    if lang_match:
        lang_override = lang_match.group(1)
        text = text[lang_match.end():]

    code = _extract_code(text) if text else ""

    if not code and message.attachments:
        first = message.attachments[0]
        try:
            resp = await httpx_client.get(first.url)
            resp.raise_for_status()
        except Exception:
            logging.exception(
                "Trigger capture: failed to download attachment (user ID: %s)",
                message.author.id,
            )
            await message.reply("Não consegui baixar o anexo.")
            return
        code = resp.text.strip()

    if not code:
        await message.reply(
            "Envie um código após `lex!capture`. Ex: `lex!capture print('hello')` ou `lex!capture lang=python:print('hello')`"
        )
        return

    max_lines = state.config.get("capture", {}).get("max_lines", 200)  # pyright: ignore[reportAttributeAccessIssue]

    logging.info(
        "Trigger capture (user ID: %s, chars: %s, max_lines: %s)",
        message.author.id,
        len(code),
        max_lines,
    )

    try:
        lang = lang_override or detect_language_name(code)
        png_bytes = render_code_image(code, max_lines=max_lines, lang=lang_override)
    except Exception:
        logging.exception(
            "Trigger capture: render failed (user ID: %s)",
            message.author.id,
        )
        await message.reply("Falha ao renderizar o código. Tente novamente.")
        return

    discord_file = discord.File(
        fp=BytesIO(png_bytes),
        filename="code.png",
    )

    msg = f"Renderizado como **{lang}**" if lang else "Renderizado"
    await message.reply(msg, file=discord_file)


def _extract_code(text: str) -> str:
    text = text.strip()

    match = _CODE_FENCE_RE.match(text)
    if match:
        return match.group("body").strip()

    return text
