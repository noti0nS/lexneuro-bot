from typing import override

import discord

VISION_MODEL_TAGS = (
    "claude",
    "gemini",
    "gemma",
    "gpt-4",
    "gpt-5",
    "grok-4",
    "llama",
    "llava",
    "mistral",
    "o3",
    "o4",
    "vision",
    "vl",
)

TRIGGER_PREFIX = "lex!"

EMBED_COLOR_COMPLETE = discord.Color.dark_green()
EMBED_COLOR_INCOMPLETE = discord.Color.orange()

STREAMING_INDICATOR = " \U000026aa"
EDIT_DELAY_SECONDS = 1

MAX_MESSAGE_NODES = 500

SUPPORTED_WORD_ATTACHMENT_EXTENSIONS = (".docx", ".odt")
SUPPORTED_WORD_CONTENT_TYPES = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
)

FORMAT_LABELS: dict[str, str] = {
    "pdf": "PDF",
    "md": "Markdown",
    "docx": "DOCX",
    "odt": "ODT",
}

FORMAT_EMOJIS: dict[str, str] = {
    "pdf": "\U0001f4c4",
    "md": "\U0001f4dd",
    "docx": "\U0001f4d8",
    "odt": "\U0001f4d7",
}

CAPTURE_FILE_EXTENSIONS = (
    "py",
    "cs",
    "java",
    "js",
    "ts",
    "jsx",
    "tsx",
    "go",
    "rs",
    "cpp",
    "c",
    "h",
    "cs",
    "rb",
    "php",
    "swift",
    "kt",
    "lua",
    "sh",
    "bash",
    "ps1",
    "sql",
    "html",
    "css",
    "scss",
    "yaml",
    "yml",
    "json",
    "toml",
    "xml",
    "md",
    "r",
    "dart",
    "ex",
    "exs",
    "elm",
    "hs",
    "clj",
    "erl",
    "fs",
    "fsx",
    "scala",
    "groovy",
    "pl",
    "vim",
    "make",
    "cmake",
    "docker",
    "nginx",
    "tf",
    "hcl",
    "nim",
    "zig",
    "jl",
)


class FormatButton(discord.ui.Button["FormatSelectView"]):
    def __init__(self, fmt: str, label: str, emoji: str) -> None:
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.primary
            if fmt == "pdf"
            else discord.ButtonStyle.secondary,
        )
        self._fmt = fmt

    @override
    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if view is None:
            return
        await view.handle_format(interaction, self._fmt)


class FormatSelectView(discord.ui.View):
    def __init__(self, *, timeout: float | None = None) -> None:
        super().__init__(timeout=timeout)
        for fmt in ("pdf", "md", "docx", "odt"):
            self.add_item(FormatButton(fmt, FORMAT_LABELS[fmt], FORMAT_EMOJIS[fmt]))

    async def on_format_selected(
        self, interaction: discord.Interaction, fmt: str
    ) -> None:
        raise NotImplementedError

    async def handle_format(self, interaction: discord.Interaction, fmt: str) -> None:
        for child in self.children:
            child.disabled = True  # pyright: ignore[reportAttributeAccessIssue]
        await interaction.response.edit_message(view=self)
        await self.on_format_selected(interaction, fmt)
