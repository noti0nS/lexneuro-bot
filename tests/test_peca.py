from dataclasses import dataclass
from typing import cast

import discord

from src.commands.peca import (
    PECA_FORMAT_CHOICES,
    _attachment_is_supported,
    _build_peca_filename,
)
from src.prompts.peca import PECA_SYSTEM_PROMPT, build_peca_messages


@dataclass
class _Attachment:
    filename: str
    content_type: str | None


def test_build_messages_defaults() -> None:
    messages = build_peca_messages(enunciado="João alugou apartamento de Maria")
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "João alugou apartamento de Maria" in messages[1]["content"]
    assert "(inferir automaticamente)" in messages[0]["content"]
    assert "(nenhuma)" in messages[0]["content"]


def test_build_messages_all_params() -> None:
    messages = build_peca_messages(
        enunciado="caso de despejo",
        tipo="Contestação",
        area="Civil",
        instrucoes="incluir tutela de urgência",
    )
    system = messages[0]["content"]
    assert "Contestação" in system
    assert "Civil" in system
    assert "incluir tutela de urgência" in system
    assert "(inferir automaticamente)" not in system
    assert "(nenhuma)" not in system


def test_build_messages_returns_list_of_dicts() -> None:
    messages = build_peca_messages(enunciado="test")
    assert isinstance(messages, list)
    for msg in messages:
        assert isinstance(msg, dict)
        assert "role" in msg
        assert "content" in msg
    assert len(messages) == 2


def test_build_messages_enunciado_as_user_message() -> None:
    messages = build_peca_messages(enunciado="Caso prático de direito penal")
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Caso prático de direito penal"


def test_system_prompt_contains_placeholders() -> None:
    messages = build_peca_messages(enunciado="test")
    system = messages[0]["content"]
    assert "Processo nº __________" in system
    assert "Comarca de __________" in system
    assert "CPF nº __________" in system
    assert "OAB/UF nº ________" in system
    assert "R$ XXXX" in system


def test_system_prompt_contains_quality_rules() -> None:
    messages = build_peca_messages(enunciado="test")
    system = messages[0]["content"]
    assert "NUNCA INVENTE DADOS" in system
    assert "Da Responsabilidade Civil da Requerida" in system
    assert "Da Improcedência do Pedido Autoral" in system
    assert "Da Inépcia da Inicial" in system
    assert "Da Inversão do Ônus da Prova" in system


def test_system_prompt_contains_structure_guidelines() -> None:
    messages = build_peca_messages(enunciado="test")
    system = messages[0]["content"]
    assert "Endereçamento" in system
    assert "Qualificação das partes" in system
    assert "Síntese objetiva dos fatos" in system
    assert "Fundamentos jurídicos" in system
    assert "Pedidos" in system
    assert "Valor da causa" in system
    assert "Fechamento" in system


def test_system_prompt_no_generic_titles() -> None:
    messages = build_peca_messages(enunciado="test")
    system = messages[0]["content"]
    assert "Desenvolvimento" not in system.split("Desenvolvimento")[-1][:50]
    assert "Do Mérito" not in system.split("Do Mérito")[-1][:50]


def test_build_peca_filename_docx() -> None:
    filename = _build_peca_filename("ação de despejo", "docx")
    assert filename.startswith("peca_")
    assert filename.endswith(".docx")


def test_build_peca_filename_pdf() -> None:
    filename = _build_peca_filename("contestação", "pdf")
    assert filename.endswith(".pdf")


def test_build_peca_filename_odt() -> None:
    filename = _build_peca_filename("agravo de instrumento", "odt")
    assert filename.endswith(".odt")


def test_build_peca_filename_sanitizes_special_chars() -> None:
    filename = _build_peca_filename("ação @#$% 123", "docx")
    assert "@" not in filename
    assert "#" not in filename
    assert "$" not in filename
    assert "%" not in filename


def test_build_peca_filename_empty_fallback() -> None:
    filename = _build_peca_filename("@#$", "docx")
    assert filename.startswith("peca_peca_") or filename.startswith("peca__")
    assert filename.endswith(".docx")


def test_format_choices_count() -> None:
    assert len(PECA_FORMAT_CHOICES) == 3
    values = {choice.value for choice in PECA_FORMAT_CHOICES}
    assert values == {"pdf", "docx", "odt"}


def test_attachment_is_supported_docx() -> None:
    result = _attachment_is_supported(
        cast(
            discord.Attachment,
            cast(object, _Attachment(filename="caso.docx", content_type=None)),
        )
    )
    assert result is True


def test_attachment_is_supported_odt() -> None:
    result = _attachment_is_supported(
        cast(
            discord.Attachment,
            cast(object, _Attachment(filename="enunciado.odt", content_type=None)),
        )
    )
    assert result is True


def test_attachment_is_supported_pdf() -> None:
    result = _attachment_is_supported(
        cast(
            discord.Attachment,
            cast(object, _Attachment(filename="caso.pdf", content_type=None)),
        )
    )
    assert result is True


def test_attachment_is_supported_by_content_type() -> None:
    result = _attachment_is_supported(
        cast(
            discord.Attachment,
            cast(
                object,
                _Attachment(
                    filename="file.bin",
                    content_type="application/pdf",
                ),
            ),
        )
    )
    assert result is True


def test_attachment_rejects_unsupported() -> None:
    result = _attachment_is_supported(
        cast(
            discord.Attachment,
            cast(
                object,
                _Attachment(filename="image.png", content_type="image/png"),
            ),
        )
    )
    assert result is False


def test_system_prompt_constant_unchanged() -> None:
    assert "NUNCA INVENTE DADOS" in PECA_SYSTEM_PROMPT
    assert "Responda APENAS com a peça processual completa" in PECA_SYSTEM_PROMPT
