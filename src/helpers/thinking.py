from __future__ import annotations

from collections.abc import Callable
from typing import Any

THINKING_NONE = "none"
THINKING_LOW = "low"
THINKING_MEDIUM = "medium"
THINKING_HIGH = "high"


def _resolve_google(level: str, model: str = "") -> dict[str, Any]:
    """Google AI OpenAI-compatible proxy (generativelanguage/v1beta/openai).

    This endpoint speaks the OpenAI Chat Completions schema, so reasoning is
    controlled with the standard top-level ``reasoning_effort`` parameter. The
    Google-native ``generationConfig``/``enable_thinking`` fields are rejected
    here. The caller emits ``reasoning_effort`` as a top-level field, so no
    extra body fields are contributed by this resolver.
    """
    return {}


def _resolve_deepseek(level: str, model: str = "") -> dict[str, Any]:
    """DeepSeek exposes reasoning via the ``thinking`` body field."""
    if level == THINKING_NONE:
        return {"thinking": {"type": "disabled"}}
    return {"thinking": {"type": "enabled"}}


def _resolve_openai_compat(level: str, model: str = "") -> dict[str, Any]:
    """OpenAI, xAI, OpenRouter, Groq, etc.

    These providers accept ``reasoning_effort`` as a top-level parameter (handled
    by the caller), so the resolver contributes no extra body fields here. The
    mapping exists so the factory is exhaustive and future providers can hook in.
    """
    return {}


_RESOLVERS: dict[str, Callable[..., dict[str, Any]]] = {
    "google": _resolve_google,
    "deepseek": _resolve_deepseek,
    "openai_compat": _resolve_openai_compat,
}


def thinking_family(provider: str, base_url: str) -> str:
    """Classify a provider into a thinking-control family."""
    provider_lower = provider.lower()
    base_lower = base_url.lower()
    if (
        "google" in provider_lower
        or "generativelanguage" in base_lower
        or "gemini" in base_lower
    ):
        return "google"
    if "deepseek" in provider_lower or "api.deepseek.com" in base_lower:
        return "deepseek"
    return "openai_compat"


def resolve_thinking_body(
    provider: str, base_url: str, level: str, model: str = ""
) -> dict[str, Any]:
    """Resolve a thinking ``level`` into provider-specific request body fields.

    Returns a dict intended to be merged into the request ``extra_body``. The
    ``openai_compat`` family intentionally returns ``{}`` because those providers
    expect ``reasoning_effort`` as a top-level parameter rather than inside the
    body.
    """
    family = thinking_family(provider, base_url)
    return dict(_RESOLVERS[family](level, model=model))


def uses_top_level_reasoning_effort(provider: str, base_url: str) -> bool:
    """Whether ``reasoning_effort`` should be sent as a top-level parameter.

    All supported providers (Google OpenAI-compatible proxy, OpenAI, xAI,
    OpenRouter, DeepSeek, Groq, ...) accept the OpenAI-standard top-level
    ``reasoning_effort`` field on their OpenAI-compatible endpoints.
    """
    return True
