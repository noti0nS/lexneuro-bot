from io import BytesIO
from typing import Any, cast

import discord

from src.helpers.send import send_document_result

LARGE_BYTES = b"x" * (int(7.5 * 1024 * 1024))


class _FakeFollowup:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def send(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


class _FakeThread:
    def __init__(self, name: str) -> None:
        self.mention = f"#{name}"
        self.sent: list[str] = []

    async def send(self, content: str, **__: Any) -> None:
        self.sent.append(content)


class _FakeTextChannel:
    def __init__(self) -> None:
        self.type = discord.ChannelType.text
        self.threads: list[_FakeThread] = []

    async def create_thread(self, **__: Any) -> _FakeThread:
        thread = _FakeThread("fake-thread")
        self.threads.append(thread)
        return thread


class _FakeInteraction:
    def __init__(self, channel: object | None = None) -> None:
        self.followup = _FakeFollowup()
        self.channel = channel


def _cast_interaction(obj: _FakeInteraction) -> discord.Interaction:
    return cast(discord.Interaction, cast(object, obj))


async def test_send_small_file_attaches() -> None:
    channel = _FakeTextChannel()
    interaction = _FakeInteraction(channel=channel)
    content = "Conteúdo do documento"
    file_bytes = b"document bytes"

    await send_document_result(
        _cast_interaction(interaction),
        content,
        "teste.docx",
        file_bytes,
        label="Teste",
    )

    assert len(interaction.followup.calls) == 1
    args, kwargs = interaction.followup.calls[0]
    assert "Teste concluída!" in args[0]
    assert kwargs.get("file") is not None
    discord_file = kwargs["file"]
    assert isinstance(discord_file, discord.File)
    assert BytesIO(file_bytes).read() == discord_file.fp.read()  # type: ignore[arg-type]


async def test_send_large_file_creates_thread_and_chunks() -> None:
    channel = _FakeTextChannel()
    interaction = _FakeInteraction(channel=channel)
    content = "Linha 1\nLinha 2\nLinha 3"

    await send_document_result(
        _cast_interaction(interaction),
        content,
        "pesquisa_grande.docx",
        LARGE_BYTES,
        label="Pesquisa",
    )

    assert len(channel.threads) == 1
    thread = channel.threads[0]
    assert len(thread.sent) >= 2
    assert "Pesquisa concluída!" in thread.sent[0]


async def test_send_large_file_no_channel_sends_error() -> None:
    interaction = _FakeInteraction(channel=None)

    await send_document_result(
        _cast_interaction(interaction),
        "",
        "teste.docx",
        LARGE_BYTES,
    )

    assert len(interaction.followup.calls) == 1
    args, _ = interaction.followup.calls[0]
    assert "Não foi possível criar uma thread" in args[0]


async def test_send_large_file_non_text_channel_sends_error() -> None:
    interaction = _FakeInteraction(channel="not_a_text_channel")

    await send_document_result(
        _cast_interaction(interaction),
        "",
        "teste.docx",
        LARGE_BYTES,
    )

    assert len(interaction.followup.calls) == 1
    args, _ = interaction.followup.calls[0]
    assert "Não foi possível criar uma thread neste canal" in args[0]


async def test_send_default_label() -> None:
    channel = _FakeTextChannel()
    interaction = _FakeInteraction(channel=channel)
    file_bytes = b"doc"

    await send_document_result(
        _cast_interaction(interaction),
        "content",
        "doc.docx",
        file_bytes,
    )

    args, _ = interaction.followup.calls[0]
    assert "Documento concluída!" in args[0]
