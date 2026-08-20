import base64
import json
import logging
import re
from typing import Any

import discord
import httpx

from ..config import get_vision_model_chain
from .llm import execute_chat_completion


VISION_PROMPT = (
    "You will be shown one or more images, in order. "
    "Return a JSON array of strings where the i-th element is a detailed "
    "description of the i-th image (objects, text, layout, and any context "
    "relevant to a legal study assistant). Respond with only the JSON array, "
    "no extra prose, no markdown fences, and no <think> reasoning blocks."
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_THINK_TRAILING_RE = re.compile(r"<think>.*$", re.DOTALL)


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

    vision_chain = get_vision_model_chain(config)
    if not vision_chain:
        raise RuntimeError("vision_models is not configured")

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

    messages = [{"role": "user", "content": content_blocks}]

    last_exc: Exception | None = None
    completion = None
    for model_attempt in vision_chain:
        try:
            completion = await execute_chat_completion(
                config, model_attempt, messages, stream=False
            )
            break
        except Exception as exc:  # noqa: BLE001
            logging.warning(
                "Vision model %s failed, trying next in chain... Error: %s",
                model_attempt,
                exc,
            )
            last_exc = exc
    if completion is None:
        assert last_exc is not None
        raise last_exc

    raw = completion.choices[0].message.content or ""
    raw = _strip_think_blocks(raw)

    if not raw.strip():
        logging.warning(
            "Vision model '%s' returned an empty response for %s image(s). "
            + "This often means the model or provider could not process the image "
            + "(e.g. the model is not multimodal, or the image was rejected).",
            vision_chain[0],
            len(attachments),
        )

    return _parse_vision_descriptions(raw, expected=len(attachments))


def _strip_think_blocks(text: str) -> str:
    return _THINK_TRAILING_RE.sub("", _THINK_RE.sub("", text)).strip()


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    return cleaned


def _try_json_array(text: str) -> list[str] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        else:
            return None

    if isinstance(data, list) and all(isinstance(item, str) for item in data):
        return [item.strip() for item in data]
    return None


def _parse_vision_descriptions(raw: str, expected: int) -> list[str]:
    cleaned = _strip_fences(raw)

    parsed = _try_json_array(cleaned)
    if parsed is not None:
        if len(parsed) != expected:
            logging.warning(
                "Vision model returned %s descriptions for %s images; using as-is.",
                len(parsed),
                expected,
            )
        return parsed

    # Model answered in prose instead of JSON.
    if cleaned:
        logging.warning(
            "Vision model did not return JSON (raw=%r); attempting prose fallback.",
            cleaned[:200],
        )
        if expected == 1:
            return [cleaned]
        raise ValueError(
            "invalid_vision_response: prose fallback only supports a single image"
        )

    raise ValueError("invalid_vision_response: empty response")
