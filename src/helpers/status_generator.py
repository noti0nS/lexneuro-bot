import asyncio
import logging

from openai import APIError, AsyncOpenAI

from ..config import OpenAIRequestConfig, build_openai_chat_completion_kwargs
from ..helpers.async_utils import await_task_with_heartbeats
from ..helpers.content import get_completion_text

STATUS_PROMPT = (
    "Generate 1 short Discord bot status for LexNeuro. "
    "Cute, smart, study/productivity theme in a discord teen way. "
    "Max 80 characters. "
    "Return only the status text in pt-br."
)

MAX_STATUS_CHARS = 128


async def generate_status_message(
    openai_client: AsyncOpenAI,
    openai_config: OpenAIRequestConfig,
) -> str | None:
    messages = [
        {"role": "user", "content": STATUS_PROMPT},
    ]

    try:
        completion_task = asyncio.create_task(
            openai_client.chat.completions.create(
                **build_openai_chat_completion_kwargs(
                    openai_config,
                    messages,
                    stream=False,
                    max_tokens=MAX_STATUS_CHARS,
                )
            )
        )
        completion = await await_task_with_heartbeats(
            completion_task,
            "Status generation LLM request still running",
        )

        raw = get_completion_text(completion)
        if not raw or not raw.strip():
            logging.warning("Status generation returned empty content")
            return None

        result = raw.strip()[:MAX_STATUS_CHARS]
        logging.info("Status generated: %s", result)
        return result

    except APIError:
        logging.exception("Status generation failed with API error")
        return None
    except Exception:
        logging.exception("Status generation failed")
        return None
