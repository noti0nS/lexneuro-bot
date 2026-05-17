import logging
import re
from datetime import datetime
from typing import Any

import discord
from discord.ext import commands
from openai import APIError

from ...config import get_openai_config
from ...helpers.ai_tools import ContentFilterError, run_research_loop
from ...helpers.documents import DOCUMENT_FORMAT_CHOICES, generate_document
from ...helpers.llm import get_provider_error_detail
from ...helpers.send import send_document_result
from ...prompts.jurisprudencia import build_jurisprudencia_messages

TRIBUNAL_CHOICES = [
    discord.app_commands.Choice(name="Todos os tribunais", value="todos"),
    discord.app_commands.Choice(name="STF — Supremo Tribunal Federal", value="stf"),
    discord.app_commands.Choice(name="STJ — Superior Tribunal de Justiça", value="stj"),
    discord.app_commands.Choice(
        name="TST — Tribunal Superior do Trabalho", value="tst"
    ),
    discord.app_commands.Choice(
        name="TJDFT — Tribunal de Justiça do DF", value="tjdft"
    ),
    discord.app_commands.Choice(name="TJSP — Tribunal de Justiça de SP", value="tjsp"),
    discord.app_commands.Choice(name="TJRJ — Tribunal de Justiça do RJ", value="tjRJ"),
]


def build_jurisprudencia_filename(consulta: str, user_id: int, ext: str) -> str:
    safe_consulta = re.sub(r"[^\w\s-]", "", consulta).strip().lower()
    safe_consulta = re.sub(r"[-\s]+", "_", safe_consulta) or "jurisprudencia"
    if len(safe_consulta) > 40:
        safe_consulta = safe_consulta[:40]
    epoch = int(datetime.now().timestamp())
    return f"jurisprudencia_{safe_consulta}_{user_id}_{epoch}{ext}"


def register_jurisprudencia_command(
    discord_bot: commands.Bot,
    state: Any,
    user_has_permission: Any,
) -> None:
    @discord_bot.tree.command(
        name="jurisprudencia",
        description="Pesquise e resuma jurisprudência dos tribunais brasileiros",
    )
    @discord.app_commands.describe(
        consulta="Tema jurídico a ser pesquisado (ex: prescrição intercorrente na execução fiscal)",
        tribunal="Tribunal onde buscar (padrão: todos)",
        periodo="Período desejado (ex: 2023-2024, últimos 2 anos, após 2020)",
        formato="Formato de saída da pesquisa",
    )
    @discord.app_commands.choices(
        tribunal=TRIBUNAL_CHOICES,
        formato=DOCUMENT_FORMAT_CHOICES,
    )
    async def jurisprudencia_command(
        interaction: discord.Interaction,
        consulta: str,
        tribunal: discord.app_commands.Choice[str] | None = None,
        periodo: str | None = None,
        formato: discord.app_commands.Choice[str] | None = None,
    ) -> None:
        tribunal_valor = tribunal.value if tribunal else "todos"
        formato_valor = formato.value if formato else "docx"

        if not consulta.strip():
            await interaction.response.send_message(
                "Descreva o tema da pesquisa de jurisprudência.",
                ephemeral=True,
            )
            return

        if len(consulta.strip()) < 5:
            await interaction.response.send_message(
                "Descreva melhor o tema da pesquisa (mínimo 5 caracteres).",
                ephemeral=True,
            )
            return

        if not user_has_permission(interaction.user, interaction.channel, state.config):
            await interaction.response.send_message(
                "Você não tem permissão para usar este bot aqui.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Buscando jurisprudência... Isso pode levar alguns minutos.",
            ephemeral=True,
        )

        logging.info(
            "Jurisprudencia started (user ID: %s, consulta: %r, tribunal: %s, periodo: %s, formato: %s)",
            interaction.user.id,
            consulta[:80],
            tribunal_valor,
            periodo,
            formato_valor,
        )

        messages: list[dict[str, Any]] = build_jurisprudencia_messages(
            consulta=consulta,
            tribunal=tribunal_valor,
            periodo=periodo,
        )

        jur_config = state.config.get("jurisprudencia", {})
        max_iterations = jur_config.get("max_search_iterations", 12)
        search_results_count = jur_config.get("search_results_per_query", 8)
        max_pages = jur_config.get("max_page_fetches", 5)
        jur_model = jur_config.get("model")
        curr_model = jur_model if jur_model else state.curr_model

        openai_client, openai_config = get_openai_config(state.config, curr_model)

        try:
            raw_output = await run_research_loop(
                openai_client=openai_client,
                openai_config=openai_config,
                messages=messages,
                max_iterations=max_iterations,
                search_results_per_topic=search_results_count,
                max_page_fetches=max_pages,
                user_id=interaction.user.id,
            )

            logging.info(
                "Jurisprudencia LLM request completed (user ID: %s, model: %s)",
                interaction.user.id,
                openai_config["model"],
            )

        except ContentFilterError:
            await interaction.followup.send(
                "A geração da pesquisa foi bloqueada pelo filtro de conteúdo do provedor."
            )
            return
        except APIError as exc:
            logging.exception(
                "Provider error while generating jurisprudencia: %s",
                get_provider_error_detail(exc),
            )
            await interaction.followup.send(
                "O provedor do modelo interrompeu a geração da pesquisa. "
                + f"Detalhe do provedor: `{str(exc)[:500]}`"
            )
            return
        except Exception:
            logging.exception("Error while generating jurisprudencia research")
            await interaction.followup.send(
                "Não consegui gerar a pesquisa de jurisprudência agora. "
                + "Verifique os logs e tente novamente."
            )
            return

        if not raw_output.strip():
            await interaction.followup.send(
                "Não foi possível encontrar jurisprudência relevante sobre o tema. "
                + "Tente refinar a consulta ou ampliar o período."
            )
            return

        try:
            file_bytes, ext = generate_document(raw_output, consulta, formato_valor)
            filename = build_jurisprudencia_filename(consulta, interaction.user.id, ext)
        except Exception:
            logging.exception("Error while generating jurisprudencia document file")
            await interaction.followup.send(
                "Não consegui gerar o arquivo do documento. "
                + "O conteúdo será enviado em mensagens."
            )
            await send_document_result(
                interaction,
                raw_output,
                "jurisprudencia.txt",
                b"",
                label="Jurisprudência",
            )
            return

        await send_document_result(
            interaction, raw_output, filename, file_bytes, label="Jurisprudência"
        )
