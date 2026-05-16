import inspect

from src.commands.jurisprudencia import (
    JURISPRUDENCIA_TOOLS,
    build_jurisprudencia_filename,
)
from src.helpers.ui import FORMATO_JURISPRUDENCIA_CHOICES, TRIBUNAL_CHOICES
from src.prompts.jurisprudencia import (
    JURISPRUDENCIA_SYSTEM_PROMPT,
    TRIBUNAL_LABELS,
    build_jurisprudencia_messages,
)


def test_build_messages_defaults() -> None:
    messages = build_jurisprudencia_messages(consulta="prescrição intercorrente")
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "prescrição intercorrente" in messages[1]["content"]
    assert "Todos os tribunais" in messages[1]["content"]
    assert "sem restrição" in messages[1]["content"]


def test_build_messages_all_params() -> None:
    messages = build_jurisprudencia_messages(
        consulta="responsabilidade civil do Estado",
        tribunal="stf",
        periodo="2023-2024",
    )
    user_msg = messages[1]["content"]
    assert "responsabilidade civil do Estado" in user_msg
    assert "STF — Supremo Tribunal Federal" in user_msg
    assert "2023-2024" in user_msg


def test_build_messages_tribunal_stf() -> None:
    messages = build_jurisprudencia_messages(consulta="test", tribunal="stf")
    assert "STF" in messages[1]["content"]


def test_build_messages_tribunal_todos() -> None:
    messages = build_jurisprudencia_messages(consulta="test", tribunal="todos")
    assert "Todos os tribunais" in messages[1]["content"]


def test_build_messages_tribunal_label_resolved() -> None:
    assert TRIBUNAL_LABELS["stf"] == "STF — Supremo Tribunal Federal"
    assert TRIBUNAL_LABELS["stj"] == "STJ — Superior Tribunal de Justiça"
    assert TRIBUNAL_LABELS["todos"] == "Todos os tribunais"


def test_build_messages_periodo() -> None:
    messages = build_jurisprudencia_messages(consulta="test", periodo="últimos 2 anos")
    assert "últimos 2 anos" in messages[1]["content"]


def test_build_messages_periodo_none() -> None:
    messages = build_jurisprudencia_messages(consulta="test", periodo=None)
    assert "sem restrição" in messages[1]["content"]


def test_build_messages_periodo_empty() -> None:
    messages = build_jurisprudencia_messages(consulta="test", periodo="")
    assert "sem restrição" in messages[1]["content"]


def test_build_messages_periodo_whitespace() -> None:
    messages = build_jurisprudencia_messages(consulta="test", periodo="   ")
    assert "sem restrição" in messages[1]["content"]


def test_build_messages_returns_list_of_dicts() -> None:
    messages = build_jurisprudencia_messages(consulta="test")
    assert isinstance(messages, list)
    for msg in messages:
        assert isinstance(msg, dict)
        assert "role" in msg
        assert "content" in msg


def test_build_messages_system_role_first() -> None:
    messages = build_jurisprudencia_messages(consulta="test")
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_tribunal_choices_count() -> None:
    assert len(TRIBUNAL_CHOICES) == 7


def test_tribunal_choices_count_within_discord_limit() -> None:
    assert len(TRIBUNAL_CHOICES) <= 25


def test_format_choices_count() -> None:
    assert len(FORMATO_JURISPRUDENCIA_CHOICES) == 4


def test_system_prompt_contains_court_domains() -> None:
    assert "portal.stf.jus.br" in JURISPRUDENCIA_SYSTEM_PROMPT
    assert "stj.jus.br" in JURISPRUDENCIA_SYSTEM_PROMPT
    assert "tst.jus.br" in JURISPRUDENCIA_SYSTEM_PROMPT


def test_system_prompt_contains_anti_hallucination() -> None:
    assert "NUNCA invente" in JURISPRUDENCIA_SYSTEM_PROMPT


def test_system_prompt_contains_conclusao_section() -> None:
    assert "CONCLUSÃO" in JURISPRUDENCIA_SYSTEM_PROMPT


def test_tool_schemas_defined() -> None:
    assert len(JURISPRUDENCIA_TOOLS) == 2
    tool_names = [t["function"]["name"] for t in JURISPRUDENCIA_TOOLS]
    assert "web_search" in tool_names
    assert "fetch_page" in tool_names


def test_tool_schemas_valid_openai_format() -> None:
    for tool in JURISPRUDENCIA_TOOLS:
        assert "type" in tool
        assert tool["type"] == "function"
        assert "function" in tool
        assert "name" in tool["function"]
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]


def test_build_jurisprudencia_filename() -> None:
    filename = build_jurisprudencia_filename("prescrição intercorrente", 123, ".docx")
    assert filename.startswith("jurisprudencia_")
    assert "prescri" in filename and "intercorrente" in filename
    assert "_123_" in filename
    assert filename.endswith(".docx")


def test_build_jurisprudencia_filename_truncation() -> None:
    long_name = "a" * 80
    filename = build_jurisprudencia_filename(long_name, 1, ".docx")
    safe_part = filename.split("_")[1]
    assert len(safe_part) <= 40


def test_build_jurisprudencia_filename_special_chars() -> None:
    filename = build_jurisprudencia_filename("ação & recurso!", 456, ".docx")
    assert "_recurso" in filename
    assert "&" not in filename
    assert "!" not in filename


def test_build_jurisprudencia_messages_signature() -> None:
    sig = inspect.signature(build_jurisprudencia_messages)
    params = sig.parameters
    assert "consulta" in params
    assert "tribunal" in params
    assert "periodo" in params
    assert "modo_pensamento" not in params
