from src.prompts.pesquisa import (
    EXTENSAO_LABELS,
    REFINEMENT_PROMPT,
    build_pesquisa_messages,
    build_refinement_message,
)
from src.commands.pesquisa import build_pesquisa_filename
from src.helpers.ui import EXTENSAO_CHOICES, FORMATO_CHOICES


def test_build_messages_defaults() -> None:
    messages = build_pesquisa_messages(tema="FGTS e sucessão")
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "FGTS e sucessão" in messages[1]["content"]


def test_build_messages_all_params() -> None:
    messages = build_pesquisa_messages(
        tema="alvará judicial",
        extensao="completo",
        paginas=10,
    )
    system = messages[0]["content"]
    assert "alvará judicial" in system
    assert "Dossiê Completo" in system
    assert "10" in system


def test_build_messages_paginas_in_prompt() -> None:
    messages = build_pesquisa_messages(tema="test", paginas=7)
    assert "7" in messages[0]["content"]


def test_build_messages_extensao_curto() -> None:
    messages = build_pesquisa_messages(tema="test", extensao="curto")
    assert "Direto ao Ponto" in messages[0]["content"]


def test_build_messages_extensao_completo() -> None:
    messages = build_pesquisa_messages(tema="test", extensao="completo")
    assert "Dossiê Completo" in messages[0]["content"]


def test_build_messages_no_contexto_param() -> None:
    import inspect

    sig = inspect.signature(build_pesquisa_messages)
    assert "contexto" not in sig.parameters


def test_build_messages_no_instrucoes_extras_param() -> None:
    import inspect

    sig = inspect.signature(build_pesquisa_messages)
    assert "instrucoes_extras" not in sig.parameters


def test_build_messages_no_modo_pensamento_param() -> None:
    import inspect

    sig = inspect.signature(build_pesquisa_messages)
    assert "modo_pensamento" not in sig.parameters


def test_build_messages_includes_abnt_reference() -> None:
    from src.prompts.abnt import load_abnt_reference

    messages = build_pesquisa_messages(tema="test")
    abnt_ref = load_abnt_reference()
    assert abnt_ref.splitlines()[0] in messages[0]["content"]


def test_build_messages_returns_list_of_dicts() -> None:
    messages = build_pesquisa_messages(tema="test")
    assert isinstance(messages, list)
    for msg in messages:
        assert isinstance(msg, dict)
        assert "role" in msg
        assert "content" in msg


def test_refinement_prompt_built() -> None:
    msg = build_refinement_message()
    assert "ANÁLISE PRELIMINAR" in msg
    assert "Pergunta" in msg
    assert "Resposta" in msg
    assert "3 a 5" in msg


def test_refinement_prompt_is_constant() -> None:
    assert build_refinement_message() == REFINEMENT_PROMPT


def test_extensao_labels_keys() -> None:
    assert set(EXTENSAO_LABELS.keys()) == {"curto", "padrao", "completo"}


def test_extensao_choices_count() -> None:
    assert len(EXTENSAO_CHOICES) == 3


def test_format_choices_count() -> None:
    assert len(FORMATO_CHOICES) == 2


def test_build_pesquisa_filename_docx() -> None:
    filename = build_pesquisa_filename("competência FGTS", "docx")
    assert filename.startswith("pesquisa_")
    assert filename.endswith(".docx")
    assert "FGTS" in filename


def test_build_pesquisa_filename_odt() -> None:
    filename = build_pesquisa_filename("test topic", "odt")
    assert filename.endswith(".odt")


def test_build_pesquisa_filename_sanitizes_special_chars() -> None:
    filename = build_pesquisa_filename("alvará judicial @#$% 123", "docx")
    assert "@" not in filename
    assert "#" not in filename
    assert "$" not in filename
    assert "%" not in filename