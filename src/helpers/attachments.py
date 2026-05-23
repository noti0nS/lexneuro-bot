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
    attachment: discord.Attachment, max_chars: int, http_client: httpx.AsyncClient
) -> tuple[str, bool]:
    if not attachment_is_supported_word_document(attachment):
        raise ValueError("unsupported")

    response = await http_client.get(attachment.url)
    response.raise_for_status()

    ext = attachment.filename.lower().rsplit(".", 1)[-1]
    processor = get_processor(ext)
    text = processor.extract_text(response.content)

    return text[:max_chars], len(text) > max_chars
