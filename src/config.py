from collections.abc import Mapping
from typing import Any, TypedDict

import yaml
from openai import AsyncOpenAI


class OpenAIRequestConfig(TypedDict):
    model: str
    provider: str
    base_url: str
    extra_headers: Mapping[str, str] | None
    extra_query: Mapping[str, str] | None
    extra_body: Mapping[str, Any] | None


def get_config(filename: str = "config.yaml") -> dict[str, Any]:
    with open(filename, encoding="utf-8") as file:
        return yaml.safe_load(file)


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


def get_openai_config(
    config: dict[str, Any], provider_slash_model: str
) -> tuple[AsyncOpenAI, OpenAIRequestConfig]:
    provider, model = provider_slash_model.removesuffix(":vision").split("/", 1)
    provider_config = config["providers"][provider]

    openai_client = AsyncOpenAI(
        base_url=provider_config["base_url"],
        api_key=provider_config.get("api_key", "sk-no-key-required"),
    )

    model_parameters = config["models"].get(provider_slash_model, None)
    extra_body = (provider_config.get("extra_body") or {}) | (
        model_parameters or {}
    ) or None

    return openai_client, {
        "model": model,
        "provider": provider,
        "base_url": provider_config["base_url"],
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
) -> dict[str, Any]:
    needs_deepseek_reasoning = _needs_deepseek_reasoning(openai_config)
    if needs_deepseek_reasoning:
        for msg in messages:
            if msg.get("role") == "assistant" and "reasoning_content" not in msg:
                msg["reasoning_content"] = ""

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
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
        if needs_deepseek_reasoning:
            merged_extra = dict(openai_config.get("extra_body") or {})
            merged_extra["thinking"] = {"type": "enabled"}
            kwargs["extra_body"] = merged_extra

    return kwargs
