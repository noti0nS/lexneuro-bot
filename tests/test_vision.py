import json
from dataclasses import dataclass, field
from typing import Any, cast

import discord
import httpx

from src.bot import _extract_message_text, _process_attachments
from src.config import Limits
from src.helpers import vision
from src.helpers.vision import describe_images


@dataclass
class _Attachment:
    url: str
    content_type: str
    size: int = 1024
    filename: str = "img.png"


@dataclass
class _VMessage:
    content: str | None


@dataclass
class _VChoice:
    message: _VMessage


@dataclass
class _VCompletion:
    choices: list[_VChoice]


@dataclass
class _BotUser:
    mention: str = "<@999>"


@dataclass
class _FakeImageResponse:
    content: bytes

    def raise_for_status(self) -> None:
        return None


class _FakeHttp:
    async def get(self, url: str) -> _FakeImageResponse:
        return _FakeImageResponse(b"\x89PNG")


@dataclass
class _Msg:
    content: str = ""
    attachments: list[Any] = field(default_factory=list)
    mentions: list[object] = field(default_factory=list)
    embeds: list[object] = field(default_factory=list)
    components: list[object] = field(default_factory=list)


def _config() -> dict[str, Any]:
    return {
        "providers": {
            "openai": {"base_url": "https://api.openai.com/v1", "api_key": "k"}
        },
        "models": {},
        "vision_models": {"vision/brain": ["openai/gpt-4o"]},
    }


def _cast_attachments(items: list[_Attachment]) -> list[discord.Attachment]:
    return cast(
        list[discord.Attachment],
        [cast(discord.Attachment, cast(object, a)) for a in items],
    )


def _cast_http() -> httpx.AsyncClient:
    return cast(httpx.AsyncClient, cast(object, _FakeHttp()))


async def test_describe_images_returns_parsed_list(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    async def fake_execute(
        config: Any,
        model_name: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> _VCompletion:
        captured["messages"] = messages
        return _VCompletion(
            choices=[
                _VChoice(
                    message=_VMessage(content=json.dumps(["desc one", "desc two"]))
                )
            ]
        )

    monkeypatch.setattr(vision, "execute_chat_completion", fake_execute)

    attachments = _cast_attachments(
        [
            _Attachment(url="https://cdn/1.png", content_type="image/png"),
            _Attachment(url="https://cdn/2.jpg", content_type="image/jpeg"),
        ]
    )

    result = await describe_images(attachments, _config(), _cast_http())

    assert result == ["desc one", "desc two"]
    assert len(captured["messages"]) == 1
    content = captured["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert sum(1 for b in content if b["type"] == "image_url") == 2
    assert all(
        b["image_url"]["url"].startswith("data:")
        for b in content
        if b["type"] == "image_url"
    )


async def test_describe_images_strips_fenced_json(monkeypatch: Any) -> None:
    async def fake_execute(
        config: Any,
        model_name: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> _VCompletion:
        return _VCompletion(
            choices=[_VChoice(message=_VMessage(content='```json\n["a", "b"]\n```'))]
        )

    monkeypatch.setattr(vision, "execute_chat_completion", fake_execute)

    result = await describe_images(
        _cast_attachments([_Attachment(url="u", content_type="image/png")]),
        _config(),
        _cast_http(),
    )
    assert result == ["a", "b"]


async def test_describe_images_raises_on_bad_json(monkeypatch: Any) -> None:
    async def fake_execute(
        config: Any,
        model_name: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> _VCompletion:
        return _VCompletion(choices=[_VChoice(message=_VMessage(content="not json"))])

    monkeypatch.setattr(vision, "execute_chat_completion", fake_execute)

    try:
        await describe_images(
            _cast_attachments([_Attachment(url="u", content_type="image/png")]),
            _config(),
            _cast_http(),
        )
    except ValueError as exc:
        assert "invalid_vision_response" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid vision response")


def test_extract_message_text_builds_image_template() -> None:
    msg = _Msg(content="What is this?")
    text = _extract_message_text(
        cast(discord.Message, cast(object, msg)),
        cast(discord.ClientUser, cast(object, _BotUser())),
        doc_texts=[],
        image_descriptions=["a red circle", "a blue square"],
    )
    expected = (
        "USER_PROMPT:\nWhat is this?\n\nIMAGE#1\na red circle\n\nIMAGE#2\na blue square"
    )
    assert text == expected


def test_extract_message_text_no_images_unchanged() -> None:
    msg = _Msg(content="hello")
    text = _extract_message_text(
        cast(discord.Message, cast(object, msg)),
        cast(discord.ClientUser, cast(object, _BotUser())),
        doc_texts=["<file:x.txt>\nbody\n</file:x.txt>"],
        image_descriptions=None,
    )
    assert text == "hello\n<file:x.txt>\nbody\n</file:x.txt>"


async def test_process_attachments_marks_images_bad_without_vision() -> None:
    config = {"models": {}, "providers": {}}

    class _NoDownload:
        async def get(self, url: str):
            raise AssertionError("should not download images when vision disabled")

    msg = _Msg(
        attachments=[_Attachment(url="https://cdn/x.png", content_type="image/png")]
    )
    limits = Limits(
        max_text=1000, max_messages=10, max_attachment_kb=512, max_file_attachments=3
    )

    result = await _process_attachments(
        cast(discord.Message, cast(object, msg)),
        limits,
        cast(httpx.AsyncClient, cast(object, _NoDownload())),
        config,
    )
    assert result.image_descriptions == []
    assert result.has_bad_attachments is True
    assert result.warnings == set()


async def test_process_attachments_describes_images_with_vision(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_describe(
        attachments: list[discord.Attachment], config: Any, httpx_client: Any
    ) -> list[str]:
        captured["attachments"] = attachments
        return ["a cat sitting on a chair"]

    monkeypatch.setattr("src.bot.describe_images", fake_describe)

    msg = _Msg(
        attachments=[_Attachment(url="https://cdn/cat.png", content_type="image/png")]
    )
    limits = Limits(
        max_text=1000, max_messages=10, max_attachment_kb=512, max_file_attachments=3
    )

    result = await _process_attachments(
        cast(discord.Message, cast(object, msg)),
        limits,
        _cast_http(),
        _config(),
    )
    assert result.image_descriptions == ["a cat sitting on a chair"]
    assert result.has_bad_attachments is False
    assert len(captured["attachments"]) == 1
