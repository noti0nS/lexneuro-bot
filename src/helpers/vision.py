import base64
import json
import logging
from typing import Any

import discord
import httpx

from ..config import get_default_vision_model
from .llm import execute_chat_completion

VISION_PROMPT = (
    "You will be shown one or more images, in order. "
    "Return a JSON array of strings where the i-th element is a detailed "
    "description of the i-th image (objects, text, layout, and any context "
    "relevant to a legal study assistant). Respond with only the JSON array, "
    "no extra prose or markdown fences."
)


async def describe_images(
    attachments: list[discord.Attachment],
    config: dict[str, Any],
    httpx_client: httpx.AsyncClient,
) -> list[str]:
    """Describe attached images with the configured vision model.

    Downloads each image, embeds them as base64 data URLs in a single batched
    vision call, and parses the JSON array of per-image descriptions.

    Raises on API failure or when the response cannot be parsed into a list
    aligned with the input attachments.
    """
    if not attachments:
        return []

    content_blocks: list[dict[str, Any]] = [{"type": "text", "text": VISION_PROMPT}]
    for att in attachments:
        response = await httpx_client.get(att.url)
        response.raise_for_status()
        content_type = att.content_type or "image/png"
        encoded = base64.b64encode(response.content).decode("ascii")
        content_blocks.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{content_type};base64,{encoded}"},
            }
        )

    vision_model = get_default_vision_model(config)
    if vision_model is None:
        raise RuntimeError("vision_models is not configured")

    messages = [{"role": "user", "content": content_blocks}]
    completion = await execute_chat_completion(
        config, vision_model, messages, stream=False
    )
    raw = completion.choices[0].message.content or ""

    return _parse_vision_descriptions(raw, expected=len(attachments))


def _parse_vision_descriptions(raw: str, expected: int) -> list[str]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_vision_response: {exc}") from exc

    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError("invalid_vision_response: expected a list of strings")

    if len(data) != expected:
        logging.warning(
            "Vision model returned %s descriptions for %s images; using as-is.",
            len(data),
            expected,
        )

    return [item.strip() for item in data]
