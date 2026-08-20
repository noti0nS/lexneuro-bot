import asyncio
import logging

logger = logging.getLogger(__name__)
from datetime import UTC, datetime
from typing import TypeVar

T = TypeVar("T")


async def await_task_with_heartbeats[T](
    task: asyncio.Task[T], label: str, heartbeat_seconds: float = 10.0
) -> T:
    started_at = datetime.now(tz=UTC).timestamp()

    while True:
        try:
            return await asyncio.wait_for(
                asyncio.shield(task), timeout=heartbeat_seconds
            )
        except TimeoutError:
            logger.info(
                "%s (elapsed: %.2fs)",
                label,
                datetime.now(tz=UTC).timestamp() - started_at,
            )
