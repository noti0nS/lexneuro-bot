from src.commands.relatorio import (
    RELATORIO_FORMAT_CHOICES,
    build_relatorio_filename,
)
from src.prompts.relatorio import RELATORIO_SYSTEM_PROMPT, build_relatorio_messages


def test_build_messages_minimal() -> None:
    messages = build_relatorio_messages(
        titulo="Teste de Relatório",
        descricao="Objetivo do teste.",
        autor="Fulano",
        data="16 de maio de 2026",
    )
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "Teste de Relatório" in messages[0]["content"]
    assert "Fulano" in messages[0]["content"]
    assert "16 de maio de 2026" in messages[0]["content"]
    assert "Objetivo do teste." in messages[1]["content"]


def test_build_messages_all_params() -> None:
    messages = build_relatorio_messages(
        titulo="Árvores",
        descricao="Aprofundar conhecimento.",
        autor="Beltrano",
        data="1 de junho de 2026",
        topicos="Árvore B, Árvore B+",
        secoes="Definição, Complexidade",
        paginas=4,
        pesquisar=True,
        instrucoes="foco em comparação",
        fonte_arquivo="Texto extraído do PDF.",
    )
    system = messages[0]["content"]
    user = messages[1]["content"]

    assert "Árvores" in system
    assert "Beltrano" in system
    assert "1 de junho de 2026" in system
    assert "4" in system
    assert "Árvore B, Árvore B+" in system
    assert "Definição, Complexidade" in system
    assert "Sim" in system

    assert "Aprofundar conhecimento." in user
    assert "foco em comparação" in user
    assert "Texto extraído do PDF." in user
    assert "### FONTE (extraída do arquivo)" in user


def test_build_messages_autor_in_prompt() -> None:
    messages = build_relatorio_messages(
        titulo="T", descricao="D", autor="Ciclano", data="hoje"
    )
    assert "Ciclano" in messages[0]["content"]


def test_build_messages_data_in_prompt() -> None:
    messages = build_relatorio_messages(
        titulo="T", descricao="D", autor="A", data="16 de maio de 2026"
    )
    assert "16 de maio de 2026" in messages[0]["content"]


def test_build_messages_topicos_interpolated() -> None:
    messages = build_relatorio_messages(
        titulo="T",
        descricao="D",
        autor="A",
        data="d",
        topicos="Heap, Trie",
    )
    assert "Heap, Trie" in messages[0]["content"]


def test_build_messages_topicos_default_when_empty() -> None:
    messages = build_relatorio_messages(
        titulo="T", descricao="D", autor="A", data="d", topicos=""
    )
    assert "(inferir da descrição)" in messages[0]["content"]


def test_build_messages_secoes_interpolated() -> None:
    messages = build_relatorio_messages(
        titulo="T",
        descricao="D",
        autor="A",
        data="d",
        secoes="Definição, Usos",
    )
    assert "Definição, Usos" in messages[0]["content"]


def test_build_messages_secoes_default_when_empty() -> None:
    messages = build_relatorio_messages(
        titulo="T", descricao="D", autor="A", data="d", secoes=""
    )
    assert "(decidir automaticamente)" in messages[0]["content"]


def test_build_messages_pesquisar_true() -> None:
    messages = build_relatorio_messages(
        titulo="T", descricao="D", autor="A", data="d", pesquisar=True
    )
    assert "Sim" in messages[0]["content"]
    assert "web_search" in messages[0]["content"]


def test_build_messages_pesquisar_false() -> None:
    messages = build_relatorio_messages(
        titulo="T", descricao="D", autor="A", data="d", pesquisar=False
    )
    assert "Não" in messages[0]["content"]
    assert "treinamento" in messages[0]["content"]


def test_build_messages_returns_list_of_dicts() -> None:
    messages = build_relatorio_messages(titulo="T", descricao="D", autor="A", data="d")
    assert isinstance(messages, list)
    assert len(messages) == 2
    for msg in messages:
        assert isinstance(msg, dict)
        assert "role" in msg
        assert "content" in msg


def test_build_messages_descricao_as_user_message() -> None:
    messages = build_relatorio_messages(
        titulo="T",
        descricao="Descrição do trabalho acadêmico.",
        autor="A",
        data="d",
    )
    assert messages[1]["role"] == "user"
    assert "Descrição do trabalho acadêmico." in messages[1]["content"]


def test_build_messages_instrucoes_block() -> None:
    messages = build_relatorio_messages(
        titulo="T",
        descricao="D",
        autor="A",
        data="d",
        instrucoes="use diagramas",
    )
    assert "Instruções adicionais:" in messages[1]["content"]
    assert "use diagramas" in messages[1]["content"]


def test_build_messages_instrucoes_omitted() -> None:
    messages = build_relatorio_messages(
        titulo="T", descricao="D", autor="A", data="d", instrucoes=""
    )
    assert "Instruções adicionais:" not in messages[1]["content"]


def test_build_messages_fonte_arquivo_block() -> None:
    messages = build_relatorio_messages(
        titulo="T",
        descricao="D",
        autor="A",
        data="d",
        fonte_arquivo="Conteúdo do arquivo anexo.",
    )
    assert "### FONTE (extraída do arquivo)" in messages[1]["content"]
    assert "Conteúdo do arquivo anexo." in messages[1]["content"]


def test_build_messages_fonte_arquivo_omitted() -> None:
    messages = build_relatorio_messages(
        titulo="T", descricao="D", autor="A", data="d", fonte_arquivo=""
    )
    assert "### FONTE" not in messages[1]["content"]


def test_format_choices_count() -> None:
    assert len(RELATORIO_FORMAT_CHOICES) == 3
    values = {c.value for c in RELATORIO_FORMAT_CHOICES}
    assert values == {"pdf", "docx", "odt"}


def test_build_relatorio_filename_docx() -> None:
    filename = build_relatorio_filename(
        "Árvores B e Trie", user_id=123456, output_format="docx"
    )
    assert filename.startswith("relatorio_")
    assert filename.endswith(".docx")
    assert "_123456_" in filename


def test_build_relatorio_filename_pdf() -> None:
    filename = build_relatorio_filename(
        "Relatório de Teste", user_id=789, output_format="pdf"
    )
    assert "_789_" in filename
    assert filename.endswith(".pdf")


def test_build_relatorio_filename_sanitizes_special_chars() -> None:
    filename = build_relatorio_filename(
        "árvore @#$% 123", user_id=5, output_format="odt"
    )
    assert "@" not in filename
    assert "#" not in filename
    assert "$" not in filename
    assert "%" not in filename


def test_system_prompt_contains_structure_rules() -> None:
    messages = build_relatorio_messages(titulo="T", descricao="D", autor="A", data="d")
    system = messages[0]["content"]
    assert "REGRAS DE ESTRUTURA" in system
    assert "REGRAS DE REDAÇÃO" in system
    assert "Clareza acima de erudição" in system


def test_system_prompt_contains_no_intro_rule() -> None:
    messages = build_relatorio_messages(titulo="T", descricao="D", autor="A", data="d")
    system = messages[0]["content"]
    assert "sem introduções" in system.lower()
    assert "sem comentários meta-textuais" in system.lower()


def test_system_prompt_template_is_string() -> None:
    assert isinstance(RELATORIO_SYSTEM_PROMPT, str)
    assert "{titulo}" in RELATORIO_SYSTEM_PROMPT
    assert "{autor}" in RELATORIO_SYSTEM_PROMPT
    assert "{data}" in RELATORIO_SYSTEM_PROMPT
    assert "{paginas}" in RELATORIO_SYSTEM_PROMPT
    assert "{topicos}" in RELATORIO_SYSTEM_PROMPT
    assert "{secoes}" in RELATORIO_SYSTEM_PROMPT
    assert "{pesquisar_label}" in RELATORIO_SYSTEM_PROMPT
