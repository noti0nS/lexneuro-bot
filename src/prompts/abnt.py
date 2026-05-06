from pathlib import Path

from .discord_markdown import build_system_prompt

ABNT_REFERENCE_PATH = Path(__file__).with_name("abnt_reference.md")

ABNT_SYSTEM_PROMPT = """\
Você é um avaliador acadêmico especializado em normas ABNT para trabalhos brasileiros.
Avalie o documento e responda EXCLUSIVAMENTE em JSON válido.
Não reescreva o documento, não inclua texto fora do JSON e não use markdown.
"""

ABNT_USER_PROMPT = """\
Avalie o documento abaixo com base em regras ABNT.

Regras:
- Retorne apenas um objeto JSON no formato:
  {"score": numero_entre_0_e_1, "improvements": ["item 1", "item 2"]}
- "score" deve representar a conformidade ABNT geral.
- "improvements" deve conter os principais pontos objetivos para melhorar a conformidade ABNT.
- Não invente informações externas ao documento.
- Se não houver melhorias relevantes, retorne "improvements": [].
"""


def load_abnt_reference() -> str:
    try:
        reference = ABNT_REFERENCE_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(
            f"Não foi possível carregar a referência ABNT em {ABNT_REFERENCE_PATH}"
        ) from exc

    if not reference:
        raise RuntimeError(
            f"O arquivo de referência ABNT está vazio: {ABNT_REFERENCE_PATH}"
        )

    return reference


def build_abnt_messages(
    filename: str,
    document_text: str,
    instructions: str | None,
    document_was_truncated: bool,
    max_document_chars: int,
) -> list[dict[str, str]]:
    reference = load_abnt_reference()
    system_prompt = (
        f"{ABNT_SYSTEM_PROMPT}\n"
        "Use as diretrizes abaixo como fonte de verdade para a avaliação:\n\n"
        f"{reference}"
    )
    system_prompt = build_system_prompt(system_prompt)
    user_prompt = ABNT_USER_PROMPT

    if instructions:
        user_prompt += f"\n\nInstruções adicionais do usuário:\n{instructions.strip()}"

    if document_was_truncated:
        user_prompt += f"\n\nAviso: o documento foi limitado aos primeiros {max_document_chars:,} caracteres por configuração do bot."

    user_prompt += f"\n\nNome do arquivo: {filename}"
    user_prompt += f"\n\nDocumento:\n{document_text}"

    return [
        dict(role="system", content=system_prompt),
        dict(role="user", content=user_prompt),
    ]
