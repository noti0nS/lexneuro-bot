import asyncio
import logging
from datetime import datetime
from typing import TypeVar

T = TypeVar("T")


async def await_task_with_heartbeats(
    task: asyncio.Task[T], label: str, heartbeat_seconds: float = 10.0
) -> T:
    started_at = datetime.now().timestamp()

    while True:
        try:
            return await asyncio.wait_for(
                asyncio.shield(task), timeout=heartbeat_seconds
            )
        except asyncio.TimeoutError:
            logging.info(
                "%s (elapsed: %.2fs)",
                label,
                datetime.now().timestamp() - started_at,
            )
