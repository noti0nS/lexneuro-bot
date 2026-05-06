from src.prompts.pesquisa import (
    CONTEXTO_LABELS,
    EXTENSAO_LABELS,
    REFINEMENT_PROMPT,
    build_pesquisa_messages,
    build_refinement_message,
)
from src.commands.pesquisa import (
    CONTEXTO_CHOICES,
    EXTENSAO_CHOICES,
    FORMATO_CHOICES,
    build_pesquisa_filename,
)


def test_build_messages_defaults() -> None:
    messages = build_pesquisa_messages(tema="FGTS e sucessão")
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "FGTS e sucessão" in messages[1]["content"]


def test_build_messages_all_params() -> None:
    messages = build_pesquisa_messages(
        tema="alvará judicial",
        contexto="npj",
        extensao="completo",
        paginas=10,
        modo_pensamento=True,
        instrucoes_extras="3 peças: inicial, contestação, reconvenção",
    )
    system = messages[0]["content"]
    assert "alvará judicial" in system
    assert "NPJ" in system
    assert "advogado sênior" in system
    assert "Dossiê Completo" in system
    assert "10" in system
    assert "True" in system
    assert "3 peças" in system


def test_build_messages_paginas_in_prompt() -> None:
    messages = build_pesquisa_messages(tema="test", paginas=7)
    assert "7" in messages[0]["content"]


def test_build_messages_npj_context() -> None:
    messages = build_pesquisa_messages(tema="test", contexto="npj")
    assert "advogado sênior" in messages[0]["content"]


def test_build_messages_programacao_context() -> None:
    messages = build_pesquisa_messages(tema="test", contexto="programacao")
    assert "documentação técnica" in messages[0]["content"]


def test_build_messages_extensao_curto() -> None:
    messages = build_pesquisa_messages(tema="test", extensao="curto")
    assert "Direto ao Ponto" in messages[0]["content"]


def test_build_messages_extensao_completo() -> None:
    messages = build_pesquisa_messages(tema="test", extensao="completo")
    assert "Dossiê Completo" in messages[0]["content"]


def test_build_messages_modo_pensamento_true() -> None:
    messages = build_pesquisa_messages(tema="test", modo_pensamento=True)
    assert "True" in messages[0]["content"]


def test_build_messages_modo_pensamento_false() -> None:
    messages = build_pesquisa_messages(tema="test", modo_pensamento=False)
    assert "False" in messages[0]["content"]


def test_build_messages_instrucoes_extras() -> None:
    messages = build_pesquisa_messages(
        tema="test", instrucoes_extras="incluir quadro comparativo"
    )
    assert "incluir quadro comparativo" in messages[0]["content"]


def test_build_messages_instrucoes_extras_none() -> None:
    messages = build_pesquisa_messages(tema="test", instrucoes_extras=None)
    assert "Nenhuma" in messages[0]["content"]


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


def test_contexto_labels_keys() -> None:
    assert set(CONTEXTO_LABELS.keys()) == {"academico", "npj", "programacao"}


def test_extensao_labels_keys() -> None:
    assert set(EXTENSAO_LABELS.keys()) == {"curto", "padrao", "completo"}


def test_contexto_choices_count() -> None:
    assert len(CONTEXTO_CHOICES) == 3


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
