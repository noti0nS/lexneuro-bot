import logging
from typing import Any

import discord
from openai import APIError, AsyncOpenAI

from ..config import OpenAIRequestConfig, build_openai_chat_completion_kwargs


async def stream_completion_to_channel(
    channel: discord.abc.Messageable,
    openai_client: AsyncOpenAI,
    openai_config: OpenAIRequestConfig,
    messages: list[dict[str, Any]],
) -> str:
    finish_reason = None
    response_chunks = []
    pending_content = ""
    max_message_length = 2000
    first_chunk_logged = False

    logging.info(
        "Streaming helper request started (model: %s, message_count: %s)",
        openai_config.get("model"),
        len(messages),
    )

    request_kwargs = build_openai_chat_completion_kwargs(
        openai_config, messages, stream=True
    )

    async for chunk in await openai_client.chat.completions.create(**request_kwargs):
        if finish_reason is not None:
            break

        if not (choice := chunk.choices[0] if chunk.choices else None):
            continue

        finish_reason = choice.finish_reason
        new_content = choice.delta.content or ""

        if pending_content == "" and new_content == "" and finish_reason is None:
            continue

        pending_content += new_content
        if not first_chunk_logged and (new_content != "" or finish_reason is not None):
            logging.info(
                "Streaming helper first chunk received (model: %s)",
                openai_config.get("model"),
            )
            first_chunk_logged = True

        while len(pending_content) >= max_message_length:
            split_at = pending_content.rfind("\n\n", 0, max_message_length)
            if split_at < max_message_length // 2:
                split_at = pending_content.rfind("\n", 0, max_message_length)
            if split_at < max_message_length // 2:
                split_at = max_message_length

            chunk_content = pending_content[:split_at].strip()
            if chunk_content:
                response_chunks.append(chunk_content)
                await channel.send(chunk_content)

            pending_content = pending_content[split_at:].lstrip()

    if pending_content.strip():
        response_chunks.append(pending_content.strip())
        await channel.send(pending_content.strip())

    logging.info(
        "Streaming helper request completed (model: %s, finish_reason: %s, chunks: %s)",
        openai_config.get("model"),
        finish_reason,
        len(response_chunks),
    )

    return "\n".join(response_chunks)


def get_provider_error_detail(exc: APIError) -> str:
    parts = [str(exc)]

    if code := getattr(exc, "code", None):
        parts.append(f"code={code}")
    if body := getattr(exc, "body", None):
        parts.append(f"body={body}")

    return "; ".join(parts)
