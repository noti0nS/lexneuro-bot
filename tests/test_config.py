from src.config import (
    build_openai_chat_completion_kwargs,
    get_bot_token,
    get_openai_config,
    mask_sensitive_config,
)


def test_get_bot_token_raises_when_missing() -> None:
    try:
        get_bot_token({})
    except RuntimeError as exc:
        assert "bot_token" in str(exc)
    else:
        raise AssertionError("Expected get_bot_token to raise when token is missing")


def test_get_openai_config_merges_provider_and_model_extra_body() -> None:
    config = {
        "providers": {
            "openai": {
                "base_url": "https://api.example.com/v1",
                "api_key": "abc",
                "extra_body": {"temperature": 0.2},
                "extra_headers": {"x-test": "1"},
                "extra_query": {"q": "v"},
            }
        },
        "models": {"openai/gpt-test": {"max_tokens": 100}},
    }

    _, openai_config = get_openai_config(config, "openai/gpt-test")

    assert openai_config["model"] == "gpt-test"
    assert openai_config["extra_headers"] == {"x-test": "1"}
    assert openai_config["extra_query"] == {"q": "v"}
    assert openai_config["extra_body"] == {"temperature": 0.2, "max_tokens": 100}


def test_mask_sensitive_config_redacts_private_values() -> None:
    config = {
        "bot_token": "discord-token",
        "providers": {
            "openai": {
                "base_url": "https://api.example.com/v1",
                "api_key": "secret-key",
                "extra_headers": {"Authorization": "Bearer secret"},
            }
        },
        "nested": [{"refresh_token": "refresh"}],
    }

    masked = mask_sensitive_config(config)

    assert masked["bot_token"] == "***REDACTED***"
    assert masked["providers"]["openai"]["api_key"] == "***REDACTED***"
    assert (
        masked["providers"]["openai"]["extra_headers"]["Authorization"]
        == "***REDACTED***"
    )
    assert masked["nested"][0]["refresh_token"] == "***REDACTED***"


def test_build_kwargs_includes_reasoning_effort() -> None:
    config = {
        "providers": {
            "deepseek": {
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "test-key",
            }
        },
        "models": {},
    }
    _, openai_config = get_openai_config(config, "deepseek/deepseek-chat")
    messages = [{"role": "user", "content": "hello"}]
    kwargs = build_openai_chat_completion_kwargs(
        openai_config, messages, stream=False, reasoning_effort="high"
    )
    assert kwargs["reasoning_effort"] == "high"


def test_build_kwargs_deepseek_thinking_body() -> None:
    config = {
        "providers": {
            "deepseek": {
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "test-key",
            }
        },
        "models": {},
    }
    _, openai_config = get_openai_config(config, "deepseek/deepseek-r1")
    messages = [{"role": "user", "content": "hello"}]
    kwargs = build_openai_chat_completion_kwargs(
        openai_config, messages, stream=False, reasoning_effort="high"
    )
    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["extra_body"]["thinking"] == {"type": "enabled"}


def test_build_kwargs_deepseek_thinking_merges_existing_extra_body() -> None:
    config = {
        "providers": {
            "deepseek": {
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "test-key",
                "extra_body": {"temperature": 0.3},
            }
        },
        "models": {},
    }
    _, openai_config = get_openai_config(config, "deepseek/deepseek-r1")
    messages = [{"role": "user", "content": "hello"}]
    kwargs = build_openai_chat_completion_kwargs(
        openai_config, messages, stream=False, reasoning_effort="high"
    )
    assert kwargs["extra_body"]["temperature"] == 0.3
    assert kwargs["extra_body"]["thinking"] == {"type": "enabled"}


def test_build_kwargs_no_thinking_without_reasoning_effort() -> None:
    config = {
        "providers": {
            "deepseek": {
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "test-key",
            }
        },
        "models": {},
    }
    _, openai_config = get_openai_config(config, "deepseek/deepseek-r1")
    messages = [{"role": "user", "content": "hello"}]
    kwargs = build_openai_chat_completion_kwargs(openai_config, messages, stream=False)
    assert "reasoning_effort" not in kwargs
    assert kwargs.get("extra_body") is None


def test_build_kwargs_non_deepseek_no_thinking_body() -> None:
    config = {
        "providers": {
            "openai": {
                "base_url": "https://api.openai.com/v1",
                "api_key": "test-key",
            }
        },
        "models": {},
    }
    _, openai_config = get_openai_config(config, "openai/gpt-4o")
    messages = [{"role": "user", "content": "hello"}]
    kwargs = build_openai_chat_completion_kwargs(
        openai_config, messages, stream=False, reasoning_effort="high"
    )
    assert kwargs["reasoning_effort"] == "high"
    assert "thinking" not in kwargs.get("extra_body", {})
