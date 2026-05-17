from collections.abc import Awaitable, Callable
from typing import Any

import discord
import httpx

TriggerHandler = Callable[
    [discord.Message, str, Any, httpx.AsyncClient],
    Awaitable[None],
]

_registry: dict[str, TriggerHandler] = {}


def trigger(name: str):
    def decorator(func: TriggerHandler) -> TriggerHandler:
        _registry[name] = func
        return func

    return decorator


def get_handler(name: str) -> TriggerHandler | None:
    return _registry.get(name)


from . import capture  # noqa: E402, F401 — triggers @trigger registration  # pyright: ignore[reportUnusedImport]
