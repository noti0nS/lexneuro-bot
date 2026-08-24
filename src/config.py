import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypedDict

import yaml
from openai import AsyncOpenAI

from .helpers.thinking import (
    THINKING_NONE,
    resolve_thinking_body,
    uses_top_level_reasoning_effort,
)

DEFAULT_MAX_TEXT = 100000
DEFAULT_MAX_MESSAGES = 25
DEFAULT_MAX_ATTACHMENT_KB = 512
DEFAULT_MAX_FILE_ATTACHMENTS = 3


class OpenAIRequestConfig(TypedDict):
    model: str
    provider: str
    base_url: str
    extra_headers: Mapping[str, str] | None
    extra_query: Mapping[str, str] | None
    extra_body: Mapping[str, Any] | None


_config: dict[str, Any] | None = None


def load_config(path: str) -> dict[str, Any]:
    global _config
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    _config = cfg
    return cfg


def get_config() -> dict[str, Any]:
    cfg = _config
    if cfg is None:
        raise RuntimeError("call load_config() before get_config()")
    return cfg


_SENSITIVE_CONFIG_KEYWORDS = (
    "api_key",
    "access_token",
    "auth",
    "authorization",
    "client_secret",
    "password",
    "secret",
    "token",
)


def mask_sensitive_config(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***REDACTED***"
            if any(
                keyword in str(key).lower() for keyword in _SENSITIVE_CONFIG_KEYWORDS
            )
            else mask_sensitive_config(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask_sensitive_config(item) for item in value]
    if isinstance(value, tuple):
        return tuple(mask_sensitive_config(item) for item in value)
    return value


def get_bot_token(config: dict[str, Any]) -> str:
    bot_token = (config.get("bot_token") or "").strip()
    if not bot_token:
        raise RuntimeError("config.yaml is missing Discord bot_token.")
    return bot_token


@dataclass
class SearchSettings:
    """Web search provider settings (`search` config section).

    DuckDuckGo is always available; Tavily (enabled + optional key)
    is preferred when configured, with DuckDuckGo as its fallback.
    """

    tavily_enabled: bool
    tavily_api_key: str

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SearchSettings":
        search_config = config.get("search") or {}
        tavily_config = search_config.get("tavily") or {}
        return cls(
            tavily_enabled=bool(tavily_config.get("enabled", False)),
            tavily_api_key=os.getenv(
                "TAVILY_API_KEY", tavily_config.get("api_key") or ""
            ).strip(),
        )


def get_model_chain(config: dict[str, Any], model_name: str) -> list[str]:
    models_dict = config.get("models", {})
    vision_dict = config.get("vision_models", {})
    entry = models_dict.get(model_name) or vision_dict.get(model_name)
    if isinstance(entry, list):
        return entry
    return [model_name]


def get_default_vision_model(config: dict[str, Any]) -> str | None:
    vision_dict = config.get("vision_models")
    if not vision_dict:
        return None
    return next(iter(vision_dict))


def get_vision_model_chain(config: dict[str, Any]) -> list[str]:
    """Resolve the default vision alias's model chain from `vision_models`.

    Uses `vision_models` directly (not `get_model_chain`) so a vision alias
    that shares a name with a `models` alias is not shadowed by the main
    model chain.
    """
    vision_dict = config.get("vision_models")
    if not vision_dict:
        return []
    entry = vision_dict[next(iter(vision_dict))]
    if isinstance(entry, list):
        return entry
    return [entry]


_openai_clients: dict[tuple[str, str], AsyncOpenAI] = {}


def get_openai_config(
    config: dict[str, Any],
    provider_slash_model: str,
    *,
    is_vision: bool = False,
) -> tuple[AsyncOpenAI, OpenAIRequestConfig]:
    provider, model = provider_slash_model.removesuffix(":vision").split("/", 1)
    provider_config = config["providers"][provider]

    base_url = os.getenv(
        f"PROVIDER_{provider.upper()}_BASE_URL", provider_config["base_url"]
    )
    api_key = os.getenv(
        f"PROVIDER_{provider.upper()}_API_KEY",
        provider_config.get("api_key", "sk-no-key-required"),
    )

    cache_key = (base_url, api_key)
    openai_client = _openai_clients.get(cache_key)
    if openai_client is None:
        openai_client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        _openai_clients[cache_key] = openai_client

    model_parameters = (
        config.get("models", {}).get(provider_slash_model)
        or config.get("vision_models", {}).get(provider_slash_model)
        or None
    )

    extra_body = (provider_config.get("extra_body") or {}) | (model_parameters or {})
    if is_vision:
        extra_body = (extra_body or {}) | resolve_thinking_body(
            provider, base_url, THINKING_NONE, model=model
        )
    extra_body = extra_body or None

    return openai_client, {
        "model": model,
        "provider": provider,
        "base_url": base_url,
        "extra_headers": provider_config.get("extra_headers"),
        "extra_query": provider_config.get("extra_query"),
        "extra_body": extra_body,
    }


def _needs_deepseek_reasoning(openai_config: OpenAIRequestConfig) -> bool:
    provider = openai_config.get("provider", "").lower()
    model = openai_config.get("model", "").lower()
    base_url = openai_config.get("base_url", "").lower()
    return (
        provider == "deepseek" or "deepseek" in model or "api.deepseek.com" in base_url
    )


def build_openai_chat_completion_kwargs(
    openai_config: OpenAIRequestConfig,
    messages: list[dict[str, Any]],
    *,
    stream: bool,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    reasoning_effort: str | None = None,
    thinking_level: str | None = None,
) -> dict[str, Any]:
    needs_deepseek_reasoning = _needs_deepseek_reasoning(openai_config)
    if needs_deepseek_reasoning:
        messages = [
            {**msg, "reasoning_content": msg.get("reasoning_content", "")}
            if msg.get("role") == "assistant"
            else msg
            for msg in messages
        ]

    provider = openai_config["provider"]
    base_url = openai_config["base_url"]

    kwargs: dict[str, Any] = {
        "model": openai_config["model"],
        "messages": messages,
        "stream": stream,
    }

    if openai_config["extra_headers"] is not None:
        kwargs["extra_headers"] = openai_config["extra_headers"]
    if openai_config["extra_query"] is not None:
        kwargs["extra_query"] = openai_config["extra_query"]
    if openai_config["extra_body"] is not None:
        kwargs["extra_body"] = openai_config["extra_body"]
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if tools is not None:
        kwargs["tools"] = tools
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice
    if reasoning_effort is not None or thinking_level is not None:
        level = reasoning_effort or thinking_level
        assert level is not None
        if uses_top_level_reasoning_effort(provider, base_url):
            kwargs["reasoning_effort"] = level
        thinking_body = resolve_thinking_body(
            provider, base_url, level, model=openai_config["model"]
        )
        if thinking_body:
            merged_extra = dict(openai_config.get("extra_body") or {})
            merged_extra.update(thinking_body)
            kwargs["extra_body"] = merged_extra

    return kwargs


@dataclass
class Limits:
    max_text: int
    max_messages: int
    max_attachment_kb: int
    max_file_attachments: int

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "Limits":
        return cls(
            max_text=config.get("max_text", DEFAULT_MAX_TEXT),
            max_messages=config.get("max_messages", DEFAULT_MAX_MESSAGES),
            max_attachment_kb=config.get(
                "max_attachment_kb", DEFAULT_MAX_ATTACHMENT_KB
            ),
            max_file_attachments=config.get(
                "max_file_attachments", DEFAULT_MAX_FILE_ATTACHMENTS
            ),
        )
