from typing import Any

import discord
from discord.ext import commands

_HELP_TEXT = """\
# Comandos do LexNeuro

## Slash commands
**`/model <nome>`** — Visualiza ou troca o modelo LLM (troca: admin).
**`/abnt <documento> [instrucoes]`** — Avalia conformidade ABNT de `.docx`/`.odt`.
**`/peca <enunciado> [arquivo] [tipo] [area] [instrucoes] [format]`** — Gera peça processual. Suporta `.pdf`/`.docx`/`.odt` como entrada.
**`/cronograma <data> <materias> [horas] [instrucoes]`** — Cria cronograma de estudos com seleção interativa de dias e formato (PDF/DOCX/ODT/MD).
**`/pesquisa <tema> [extensao] [paginas] [auto_refinar] [format]`** — Pesquisa web + gera documento ABNT.
**`/jurisprudencia <consulta> [tribunal] [periodo] [formato]`** — Pesquisa jurisprudência em tribunais brasileiros (STF/STJ/TST e mais).
**`/relatorio <titulo> <descricao> [topicos] [secoes] [paginas] [pesquisar] [arquivo] [instrucoes] [formato]`** — Gera relatório acadêmico com opção de pesquisa web.
**`/regex <descricao> [exemplos] [linguagem]`** — Cria e testa expressões regulares.
**`/sql <consulta> [arquivo] [dialeto]`** — Formata e explica consultas SQL (PostgreSQL, MySQL, SQLite, etc.).
**`/json <acao> [texto] [arquivo]`** — Valida, formata, minifica ou converte JSON/YAML.
**`/status-time`** — Mostra tempo até a próxima troca automática de status.
**`/status-reset`** — Força regeneração imediata do status (admin).
**`/help`** — Esta mensagem.

## Chat com IA
Mencione **@LexNeuro** ou **responda a uma mensagem dele** para conversar com o modelo de linguagem. O bot mantém o contexto da conversa por reply chain.

## Trigger commands
Use o prefixo **`lex!`** (sem mencionar o bot):
**`lex!capture <codigo>`** — Renderiza código como imagem com syntax highlight.
  Ex: `lex!capture lang=python: print("hello")`
"""


def register_help_command(
    discord_bot: commands.Bot,
    state: Any,
) -> None:
    del state

    @discord_bot.tree.command(
        name="help",
        description="Explica todos os comandos disponíveis",
    )
    async def help_command(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(_HELP_TEXT, ephemeral=True)
