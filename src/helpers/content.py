import re
from typing import Any

_CODEHOLDER = "\x00"


def get_completion_text(completion: Any) -> str:
    if not (choice := completion.choices[0] if completion.choices else None):
        return ""

    message = getattr(choice, "message", None)
    content = getattr(message, "content", "")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        chunks = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text" and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
                continue

            part_type = getattr(part, "type", None)
            part_text = getattr(part, "text", None)
            if part_type == "text" and isinstance(part_text, str):
                chunks.append(part_text)

        return "".join(chunks).strip()

    return str(content).strip()


def sanitize_discord_markdown(text: str) -> str:
    saved: list[str] = []

    def _save(m: re.Match[str]) -> str:
        saved.append(m.group(0))
        return f"{_CODEHOLDER}{len(saved) - 1}{_CODEHOLDER}"

    text = re.sub(r"```[\s\S]*?```", _save, text)
    text = re.sub(r"`[^`\n]+`", _save, text)

    text = re.sub(r"^#{4,}\s*", "", text, flags=re.MULTILINE)

    text = re.sub(r"\$\$[\s\S]*?\$\$", _clean_latex_block, text)
    text = re.sub(r"(?<!\$)\$(?!\$)([^$\n]+?)\$(?!\$)", _clean_latex_inline, text)
    text = re.sub(r"\\\([\s\S]*?\\\)", _clean_latex_block, text)
    text = re.sub(r"\\\[[\s\S]*?\\\]", _clean_latex_block, text)
    text = re.sub(r"\\[a-zA-Z]+(?:\{[^}]*\})*", _remove_latex_cmd, text)

    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)

    text = re.sub(r"^[|\s\-:]*\-{3,}[|\s\-:]*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\|(.+)\|$", _table_to_text, text, flags=re.MULTILINE)

    text = re.sub(r"^\s*-{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\*{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*_{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*(?:[-*_]\s+){2,}[-*_]\s*$", "", text, flags=re.MULTILINE)

    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"**\1**", text)
    text = re.sub(r"__\*\*(.+?)\*\*__", r"**\1**", text)
    text = re.sub(r"\*\*__(.+?)__\*\*", r"**\1**", text)
    text = re.sub(r"~~\*\*(.+?)\*\*~~", r"**\1**", text)
    text = re.sub(r"\*\*~~(.+?)~~\*\*", r"**\1**", text)
    text = re.sub(r"~~\*(.+?)\*~~", r"*\1*", text)
    text = re.sub(r"\*~~(.+?)~~\*", r"*\1*", text)
    text = re.sub(r"__~~(.+?)~~__", r"__\1__", text)
    text = re.sub(r"~~__(.+?)__~~", r"~~\1~~", text)

    text = re.sub(r"^\[\^[^\]]*\]:.+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[\^[^\]]*\]", "", text)

    text = re.sub(r"^(\s*[-*+])\s*\[[ xX]\]\s*", r"\1 ", text, flags=re.MULTILINE)

    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"^> +> ", "> ", text, flags=re.MULTILINE)

    for i, original in enumerate(saved):
        text = text.replace(f"{_CODEHOLDER}{i}{_CODEHOLDER}", original)

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _clean_latex_block(m: re.Match[str]) -> str:
    content = m.group(0)
    if content.startswith("$$"):
        content = content[2:-2]
    elif content.startswith("\\(") or content.startswith("\\["):
        content = content[2:-2]
    content = re.sub(r"\\[a-zA-Z]+(?:\{[^}]*\})*", "", content)
    content = re.sub(r"[{}]", "", content)
    return content.strip()


def _clean_latex_inline(m: re.Match[str]) -> str:
    content = m.group(1)
    content = re.sub(r"\\[a-zA-Z]+(?:\{[^}]*\})*", "", content)
    content = re.sub(r"[{}]", "", content)
    return content.strip()


def _remove_latex_cmd(m: re.Match[str]) -> str:
    text = m.group(0)
    text = re.sub(r"^\\[a-zA-Z]+", "", text)
    text = re.sub(r"[{}]", "", text)
    return text.strip()


def _table_to_text(m: re.Match[str]) -> str:
    cells = [cell.strip() for cell in m.group(1).split("|")]
    return " | ".join(cells)
