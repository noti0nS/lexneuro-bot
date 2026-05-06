from src.prompts import (
    ABNT_SYSTEM_PROMPT,
    build_abnt_messages,
    build_system_prompt,
    load_abnt_reference,
    load_discord_markdown_reference,
)


def test_build_abnt_messages_includes_system_and_filename() -> None:
    messages = build_abnt_messages(
        filename="paper.docx",
        document_text="Conteudo base",
        instructions=None,
        document_was_truncated=False,
        max_document_chars=1000,
    )

    assert messages[0]["role"] == "system"
    assert messages[0]["content"].startswith(ABNT_SYSTEM_PROMPT)
    assert load_abnt_reference().splitlines()[0] in messages[0]["content"]
    assert "Nome do arquivo: paper.docx" in messages[1]["content"]
    assert '"score": numero_entre_0_e_1' in messages[1]["content"]


def test_build_system_prompt_always_includes_discord_reference() -> None:
    system_prompt = build_system_prompt(None)
    markdown_reference = load_discord_markdown_reference()

    assert "Regras obrigatórias de markdown do Discord" in system_prompt
    assert markdown_reference.splitlines()[0] in system_prompt


def test_build_system_prompt_preserves_existing_prompt_text() -> None:
    base_prompt = "Hoje é {date}"
    system_prompt = build_system_prompt(base_prompt)

    assert system_prompt.startswith(base_prompt)
    assert "Não invente sintaxe de markdown" in system_prompt


def test_build_abnt_messages_adds_truncation_notice() -> None:
    messages = build_abnt_messages(
        filename="long.odt",
        document_text="Parte do texto",
        instructions="Foque em clareza",
        document_was_truncated=True,
        max_document_chars=1500,
    )
    user_content = messages[1]["content"]

    assert "Instruções adicionais do usuário" in user_content
    assert "primeiros 1,500 caracteres" in user_content
