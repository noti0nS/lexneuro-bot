import logging
from collections.abc import AsyncIterable
from typing import Any

import discord
import openai
from openai import APIError, AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from ..config import (
    OpenAIRequestConfig,
    build_openai_chat_completion_kwargs,
    get_model_chain,
    get_openai_config,
)


async def execute_chat_completion(
    config: dict[str, Any],
    model_name: str,
    messages: list[dict[str, Any]],
    **kwargs: Any,
) -> ChatCompletion:
    """
    Executes a chat completion request with automatic model chain resolution.
    """
    model_chain = get_model_chain(config, model_name)

    for model_index, model_attempt in enumerate(model_chain):
        try:
            openai_client, openai_config = get_openai_config(config, model_attempt)
            return await openai_client.chat.completions.create(
                **build_openai_chat_completion_kwargs(
                    openai_config, messages, stream=False, **kwargs
                )
            )
        except (
            openai.APIStatusError,
            openai.RateLimitError,
            openai.APIConnectionError,
        ) as e:
            if model_index == len(model_chain) - 1:
                raise
            logging.warning(
                "Model %s failed, falling back... Error: %s", model_attempt, e
            )
            continue
    raise RuntimeError("Model chain exhausted without result")


async def stream_chat_completion(
    config: dict[str, Any],
    model_name: str,
    messages: list[dict[str, Any]],
    **kwargs: Any,
) -> AsyncIterable[tuple[ChatCompletionChunk, str]]:
    """
    Streams a chat completion request with automatic model chain resolution.
    Yields tuples of (chunk, model_name_used).
    """
    model_chain = get_model_chain(config, model_name)

    for model_index, model_attempt in enumerate(model_chain):
        try:
            openai_client, openai_config = get_openai_config(config, model_attempt)
            stream = await openai_client.chat.completions.create(
                **build_openai_chat_completion_kwargs(
                    openai_config, messages, stream=True, **kwargs
                )
            )
            async for chunk in stream:
                yield chunk, model_attempt
            return
        except (
            openai.APIStatusError,
            openai.RateLimitError,
            openai.APIConnectionError,
        ) as e:
            if model_index == len(model_chain) - 1:
                raise
            logging.warning(
                "Model %s failed, falling back... Error: %s", model_attempt, e
            )
            continue


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
