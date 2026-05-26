from src.commands.slashes.pesquisa import EXTENSAO_CHOICES
from src.helpers.content import build_filename
from src.helpers.documents import DOCUMENT_FORMAT_CHOICES
from src.prompts.pesquisa import (
    EXTENSAO_LABELS,
    REFINEMENT_PROMPT,
    build_pesquisa_messages,
    build_refinement_message,
    detect_domain,
)


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


def test_build_messages_includes_abnt_reference_for_legal() -> None:
    from src.prompts.abnt import load_abnt_reference

    messages = build_pesquisa_messages(tema="artigo 5 constituição federal")
    abnt_ref = load_abnt_reference()
    assert abnt_ref.splitlines()[0] in messages[0]["content"]


def test_build_messages_no_abnt_reference_for_non_legal() -> None:
    from src.prompts.abnt import load_abnt_reference

    messages = build_pesquisa_messages(
        tema="O Papel dos Sistemas de Informação no Apoio ao Processo Decisório"
    )
    abnt_ref = load_abnt_reference()
    assert abnt_ref.splitlines()[0] not in messages[0]["content"]


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


def test_refinement_prompt_with_juridico_domain() -> None:
    msg = build_refinement_message("juridico")
    assert "ANÁLISE PRELIMINAR" in msg
    assert "jurídico" in msg


def test_refinement_prompt_with_tecnologia_domain() -> None:
    msg = build_refinement_message("tecnologia")
    assert "tecnologia/programação" in msg


def test_refinement_prompt_with_geral_domain() -> None:
    msg = build_refinement_message("geral")
    assert "acadêmico-científico" in msg


def test_refinement_prompt_format_placeholder() -> None:
    assert "{dominio_label}" in REFINEMENT_PROMPT


def test_extensao_labels_keys() -> None:
    assert set(EXTENSAO_LABELS.keys()) == {"curto", "padrao", "completo"}


def test_extensao_choices_count() -> None:
    assert len(EXTENSAO_CHOICES) == 3


def test_format_choices_count() -> None:
    assert len(DOCUMENT_FORMAT_CHOICES) == 4


def test_detect_domain_juridico() -> None:
    assert detect_domain("artigo 5 da constituição federal") == "juridico"
    assert detect_domain("jurisprudência do STF sobre habeas corpus") == "juridico"
    assert detect_domain("FGTS e sucessão trabalhista") == "juridico"
    assert detect_domain("alvará judicial para levantamento de valores") == "juridico"


def test_detect_domain_tecnologia() -> None:
    assert detect_domain("programação em Python com machine learning") == "tecnologia"
    assert detect_domain("arquitetura de software e banco de dados") == "tecnologia"
    assert detect_domain("docker e kubernetes em cloud computing") == "tecnologia"


def test_detect_domain_geral() -> None:
    assert (
        detect_domain(
            "O Papel dos Sistemas de Informação no Apoio ao Processo Decisório Organizacional"
        )
        == "geral"
    )
    assert detect_domain("impactos da globalização na economia brasileira") == "geral"
    assert detect_domain("história da arte renascentista") == "geral"


def test_build_pesquisa_messages_general_topic_has_correct_domain() -> None:
    messages = build_pesquisa_messages(
        tema="O Papel dos Sistemas de Informação no Apoio ao Processo Decisório Organizacional"
    )
    system = messages[0]["content"]
    assert "Domínio Classificado" in system
    assert "geral" in system
    assert "Domínio Geral/Acadêmico" in system
    assert "jurisprudência" not in system


def test_build_pesquisa_messages_tech_topic_has_correct_domain() -> None:
    messages = build_pesquisa_messages(tema="programação funcional em Rust")
    system = messages[0]["content"]
    assert "tecnologia" in system
    assert "Domínio Tecnológico" in system


def test_build_pesquisa_messages_legal_topic_has_correct_domain() -> None:
    messages = build_pesquisa_messages(tema="prescrição penal no código penal")
    system = messages[0]["content"]
    assert "juridico" in system
    assert "Domínio Jurídico" in system


def test_build_pesquisa_filename_docx() -> None:
    filename = build_filename(
        "pesquisa", "competência FGTS", user_id=123456, ext=".docx"
    )
    assert filename.startswith("pesquisa_")
    assert filename.endswith(".docx")
    assert "_123456_" in filename


def test_build_pesquisa_filename_odt() -> None:
    filename = build_filename("pesquisa", "test topic", user_id=789, ext=".odt")
    assert "_789_" in filename
    assert filename.endswith(".odt")


def test_build_pesquisa_filename_sanitizes_special_chars() -> None:
    filename = build_filename(
        "pesquisa", "alvará judicial @#$% 123", user_id=5, ext=".docx"
    )
    assert "@" not in filename
    assert "#" not in filename
    assert "$" not in filename
    assert "%" not in filename
