import logging
from dataclasses import dataclass
from io import BytesIO

import discord
import httpx

from .documents import get_processor
from .ui import (
    SUPPORTED_WORD_ATTACHMENT_EXTENSIONS,
    SUPPORTED_WORD_CONTENT_TYPES,
)

SUPPORTED_CONTENT_TYPES: tuple[str, ...] = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "text/plain",
)

SUPPORTED_EXTENSIONS: tuple[str, ...] = (".pdf", ".docx", ".odt", ".txt")


def attachment_is_supported(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    filename = attachment.filename.lower()
    return content_type in SUPPORTED_CONTENT_TYPES or filename.endswith(
        SUPPORTED_EXTENSIONS
    )


def _extract_text_sync(file_bytes: bytes, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "txt":
        return file_bytes.decode("utf-8", errors="replace")
    from markitdown import MarkItDown

    md = MarkItDown(enable_plugins=False)
    stream = BytesIO(file_bytes)
    result = md.convert_stream(stream, file_extension=ext)
    return result.text_content


async def read_attachment_text(
    attachment: discord.Attachment,
    http_client: httpx.AsyncClient,
) -> str:
    if not attachment_is_supported(attachment):
        raise ValueError("unsupported_attachment_type")

    import asyncio

    response = await http_client.get(attachment.url)
    response.raise_for_status()

    return await asyncio.to_thread(
        _extract_text_sync, response.content, attachment.filename
    )


@dataclass
class DocumentChunks:
    filename: str
    chunks: list[str]
    total_chunks: int = 0
    total_chars: int = 0

    def __post_init__(self) -> None:
        self.total_chunks = len(self.chunks)
        self.total_chars = sum(len(c) for c in self.chunks)


def build_document_chunks(filename: str, full_text: str) -> DocumentChunks:
    raw_chunks = [p.strip() for p in full_text.split("\n\n")]
    chunks = [c for c in raw_chunks if c]
    return DocumentChunks(filename=filename, chunks=chunks)


def attachment_is_supported_word_document(attachment: discord.Attachment) -> bool:
    content_type = attachment.content_type or ""
    filename = attachment.filename.lower()
    return content_type in SUPPORTED_WORD_CONTENT_TYPES or filename.endswith(
        SUPPORTED_WORD_ATTACHMENT_EXTENSIONS
    )


async def read_word_attachment(
    attachment: discord.Attachment, http_client: httpx.AsyncClient
) -> str:
    if not attachment_is_supported_word_document(attachment):
        raise ValueError("unsupported")

    response = await http_client.get(attachment.url)
    response.raise_for_status()

    ext = attachment.filename.lower().rsplit(".", 1)[-1]
    processor = get_processor(ext)
    return processor.extract_text(response.content)


async def download_attachment_text(
    httpx_client: httpx.AsyncClient,
    attachment: discord.Attachment,
    interaction: discord.Interaction,
) -> str | None:
    """Download attachment content as text.

    Returns the text on success, or None if an error occurred
    (error message already sent to the user).
    """
    try:
        response = await httpx_client.get(attachment.url)
        response.raise_for_status()
    except Exception:
        logging.exception(
            "File download failed (user ID: %s, file: %s)",
            interaction.user.id,
            attachment.filename,
        )
        await interaction.response.send_message(
            "Não consegui baixar o anexo. Tente novamente.", ephemeral=True
        )
        return None

    text = response.text.strip()
    if not text:
        await interaction.response.send_message(
            "O arquivo parece estar vazio.", ephemeral=True
        )
        return None

    return text
