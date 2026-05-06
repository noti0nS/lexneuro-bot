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
