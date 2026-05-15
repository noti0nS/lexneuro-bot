from dataclasses import dataclass
from typing import cast

import discord

from src.commands.peca import (
    AREA_CHOICES,
    PECA_FORMAT_CHOICES,
    TIPO_CHOICES,
    attachment_is_supported,
    build_peca_filename,
    filter_choices,
    area_autocomplete,
    tipo_autocomplete,
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
    assert "Não presuma dados" in system
    assert "Da Responsabilidade Civil da Requerida" in system
    assert "Da Improcedência do Pedido Autoral" in system
    assert "Da Inépcia da Inicial" in system
    assert "Da Inversão do Ônus da Prova" in system


def test_system_prompt_contains_structure_guidelines() -> None:
    messages = build_peca_messages(enunciado="test")
    system = messages[0]["content"]
    assert "endereçamento" in system.lower()
    assert "qualificação das partes" in system.lower()
    assert "síntese dos fatos" in system.lower()
    assert "fundamentos jurídicos" in system.lower()
    assert "pedidos" in system.lower()
    assert "valor da causa" in system.lower()
    assert "fechamento" in system.lower()


def test_system_prompt_no_generic_titles() -> None:
    messages = build_peca_messages(enunciado="test")
    system = messages[0]["content"]
    assert "Desenvolvimento" not in system.split("Desenvolvimento")[-1][:50]
    assert "Do Mérito" not in system.split("Do Mérito")[-1][:50]


def test_build_peca_filename_docx() -> None:
    filename = build_peca_filename(
        "Substabelecimento", user_id=123456, output_format="docx"
    )
    assert filename.startswith("peca_substabelecimento_123456_")
    assert filename.endswith(".docx")


def test_build_peca_filename_pdf() -> None:
    filename = build_peca_filename("Contestação", user_id=789, output_format="pdf")
    assert "peca_contesta" in filename
    assert "_789_" in filename
    assert filename.endswith(".pdf")


def test_build_peca_filename_odt() -> None:
    filename = build_peca_filename("Alvará", user_id=42, output_format="odt")
    assert "_42_" in filename
    assert filename.endswith(".odt")


def test_build_peca_filename_none_tipo_fallback() -> None:
    filename = build_peca_filename(None, user_id=1, output_format="docx")
    assert filename.startswith("peca_peca_1_")
    assert filename.endswith(".docx")


def test_build_peca_filename_sanitizes_special_chars() -> None:
    filename = build_peca_filename("ação @#$% 123", user_id=5, output_format="docx")
    assert "@" not in filename
    assert "#" not in filename
    assert "$" not in filename
    assert "%" not in filename


def test_format_choices_count() -> None:
    assert len(PECA_FORMAT_CHOICES) == 3
    values = {choice.value for choice in PECA_FORMAT_CHOICES}
    assert values == {"pdf", "docx", "odt"}


def test_attachment_is_supported_docx() -> None:
    result = attachment_is_supported(
        cast(
            discord.Attachment,
            cast(object, _Attachment(filename="caso.docx", content_type=None)),
        )
    )
    assert result is True


def test_attachment_is_supported_odt() -> None:
    result = attachment_is_supported(
        cast(
            discord.Attachment,
            cast(object, _Attachment(filename="enunciado.odt", content_type=None)),
        )
    )
    assert result is True


def test_attachment_is_supported_pdf() -> None:
    result = attachment_is_supported(
        cast(
            discord.Attachment,
            cast(object, _Attachment(filename="caso.pdf", content_type=None)),
        )
    )
    assert result is True


def test_attachment_is_supported_by_content_type() -> None:
    result = attachment_is_supported(
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
    result = attachment_is_supported(
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
    assert "Não presuma dados" in PECA_SYSTEM_PROMPT
    assert "Responda apenas com a peça processual completa" in PECA_SYSTEM_PROMPT


def test_tipo_choices_count() -> None:
    assert len(TIPO_CHOICES) == 7


def test_area_choices_count() -> None:
    assert len(AREA_CHOICES) == 11


def test_filter_choices_empty_current() -> None:
    result = filter_choices(["A", "B", "C"], "")
    assert len(result) == 3
    assert result[0].name == "A"
    assert result[0].value == "A"


def test_filter_choices_substring_match() -> None:
    result = filter_choices(["Civil", "Penal", "Trabalhista"], "il")
    assert len(result) == 1
    assert result[0].name == "Civil"


def test_filter_choices_case_insensitive() -> None:
    result = filter_choices(["Civil", "Penal"], "CI")
    assert len(result) == 1
    assert result[0].name == "Civil"


def test_filter_choices_no_match() -> None:
    result = filter_choices(["Civil", "Penal"], "XYZ")
    assert len(result) == 0


async def test_tipo_autocomplete_returns_all() -> None:
    result = await tipo_autocomplete(
        cast(discord.Interaction, cast(object, None)),
        "",
    )
    assert len(result) == len(TIPO_CHOICES)


async def test_tipo_autocomplete_filters() -> None:
    result = await tipo_autocomplete(
        cast(discord.Interaction, cast(object, None)),
        "Contest",
    )
    assert len(result) == 2
    names = {r.name for r in result}
    assert names == {"Contestação", "Contestação com reconvenção"}


async def test_area_autocomplete_returns_all() -> None:
    result = await area_autocomplete(
        cast(discord.Interaction, cast(object, None)),
        "",
    )
    assert len(result) == len(AREA_CHOICES)


async def test_area_autocomplete_filters() -> None:
    result = await area_autocomplete(
        cast(discord.Interaction, cast(object, None)),
        "trab",
    )
    assert len(result) == 1
    assert result[0].name == "Trabalhista"
