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

WEEKDAY_OPTIONS: list[discord.app_commands.Choice[str]] = [
    discord.app_commands.Choice(name="Segunda-feira", value="segunda"),
    discord.app_commands.Choice(name="Terça-feira", value="terca"),
    discord.app_commands.Choice(name="Quarta-feira", value="quarta"),
    discord.app_commands.Choice(name="Quinta-feira", value="quinta"),
    discord.app_commands.Choice(name="Sexta-feira", value="sexta"),
    discord.app_commands.Choice(name="Sábado", value="sabado"),
    discord.app_commands.Choice(name="Domingo", value="domingo"),
]

PYTHON_WEEKDAY: dict[str, int] = {
    "segunda": 0,
    "terca": 1,
    "quarta": 2,
    "quinta": 3,
    "sexta": 4,
    "sabado": 5,
    "domingo": 6,
}

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

EXTENSAO_CHOICES = [
    discord.app_commands.Choice(name="Direto ao Ponto (~1 pág. / 500w)", value="curto"),
    discord.app_commands.Choice(name="Padrão (~3 págs. / 1.500w)", value="padrao"),
    discord.app_commands.Choice(
        name="Dossiê Completo (5+ págs. / 2.500+w)", value="completo"
    ),
]

FORMATO_CHOICES = [
    discord.app_commands.Choice(name="DOCX (Microsoft Word)", value="docx"),
    discord.app_commands.Choice(name="ODT (LibreOffice)", value="odt"),
]