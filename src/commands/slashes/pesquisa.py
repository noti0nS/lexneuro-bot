import asyncio
import logging
import re
from datetime import datetime
from typing import Any

import discord
from discord.ext import commands
from openai import APIError

from ...config import build_openai_chat_completion_kwargs, get_openai_config
from ...helpers.ai_tools import (
    ContentFilterError,
    run_research_loop,
)
from ...helpers.async_utils import await_task_with_heartbeats
from ...helpers.content import get_completion_text
from ...helpers.documents import generate_document
from ...helpers.llm import get_provider_error_detail
from ...helpers.send import send_document_result
from ...helpers.ui import EXTENSAO_CHOICES, FORMATO_CHOICES
from ...prompts.pesquisa import (
    EXTENSAO_LABELS,
    build_pesquisa_messages,
    build_refinement_message,
)


def build_pesquisa_filename(tema: str, user_id: int, output_format: str) -> str:
    safe_tema = re.sub(r"[^\w\s-]", "", tema).strip().lower()
    safe_tema = re.sub(r"[-\s]+", "_", safe_tema) or "pesquisa"
    if len(safe_tema) > 60:
        safe_tema = safe_tema[:60]
    epoch = int(datetime.now().timestamp())
    ext_map = {"pdf": ".pdf", "docx": ".docx", "odt": ".odt"}
    return f"pesquisa_{safe_tema}_{user_id}_{epoch}{ext_map[output_format]}"


def register_pesquisa_command(
    discord_bot: commands.Bot,
    state: Any,
    user_has_permission: Any,
) -> None:
    @discord_bot.tree.command(
        name="pesquisa",
        description="Gere um documento de pesquisa formatado em ABNT a partir de um tema",
    )
    @discord.app_commands.describe(
        tema="Tema da pesquisa em texto livre (ex: competência FGTS falecimento)",
        extensao="Nível de detalhe do documento",
        paginas="Número alvo de páginas (1–50). Sobrepõe a extensão se conflitar.",
        auto_refinar="Auto-refinamento (self-Q&A) antes da geração",
        format="Formato do arquivo de saída",
    )
    @discord.app_commands.choices(
        extensao=EXTENSAO_CHOICES,
        auto_refinar=[
            discord.app_commands.Choice(name="Sim", value="true"),
            discord.app_commands.Choice(name="Não (recomendado)", value="false"),
        ],
        format=FORMATO_CHOICES,
    )
    async def pesquisa_command(
        interaction: discord.Interaction,
        tema: str,
        extensao: str = "padrao",
        paginas: int = 3,
        auto_refinar: str = "false",
        format: discord.app_commands.Choice[str] | None = None,
    ) -> None:
        formato_valor = format.value if format else "docx"

        if not tema.strip():
            await interaction.response.send_message(
                "Descreva sua pesquisa. Exemplo: " + "`competência FGTS falecimento`",
                ephemeral=True,
            )
            return

        if paginas < 1:
            await interaction.response.send_message(
                "O número de páginas deve ser no mínimo 1.",
                ephemeral=True,
            )
            return

        if paginas > 50:
            await interaction.response.send_message(
                "O número de páginas não pode exceder 50.",
                ephemeral=True,
            )
            return

        if not user_has_permission(interaction.user, interaction.channel, state.config):
            await interaction.response.send_message(
                "Você não tem permissão para usar este bot aqui.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Pesquisando e gerando o documento... Isso pode levar alguns minutos.",
            ephemeral=True,
        )

        logging.info(
            "Pesquisa started (user ID: %s, tema: %r, extensao: %s, paginas: %s, auto_refinar: %s, formato: %s)",
            interaction.user.id,
            tema[:80],
            extensao,
            paginas,
            auto_refinar == "true",
            formato_valor,
        )

        messages: list[dict[str, Any]] = build_pesquisa_messages(
            tema=tema,
            extensao=extensao,
            paginas=paginas,
        )

        pesquisa_config = state.config.get("pesquisa", {})
        max_iterations = pesquisa_config.get("max_tool_iterations", 15)
        search_results_count = pesquisa_config.get("search_results_per_topic", 8)
        max_pages = pesquisa_config.get("max_page_fetches", 5)
        refinement_enabled = auto_refinar == "true"

        model = pesquisa_config.get("model")
        curr_model = model if model else state.curr_model

        openai_client, openai_config = get_openai_config(state.config, curr_model)

        reasoning_effort: str | None = "high" if refinement_enabled else None

        raw_output = ""
        request_started_at = datetime.now().timestamp()

        try:
            # Phase 1: Refinement (self-Q&A) — optional pre-generation step
            if refinement_enabled:
                saved_len = len(messages)
                messages.append({"role": "user", "content": build_refinement_message()})
                logging.info(
                    "Pesquisa refinement started (user ID: %s, model: %s)",
                    interaction.user.id,
                    openai_config["model"],
                )
                try:
                    refinement_task = asyncio.create_task(
                        openai_client.chat.completions.create(
                            **build_openai_chat_completion_kwargs(
                                openai_config,
                                messages,
                                stream=False,
                                tool_choice="none",
                                reasoning_effort=reasoning_effort,
                            )
                        )
                    )
                    refinement_completion = await await_task_with_heartbeats(
                        refinement_task,
                        (
                            "Pesquisa refinement still running "
                            f"(user ID: {interaction.user.id}, "
                            f"model: {openai_config['model']})"
                        ),
                    )
                    refinement_text = get_completion_text(refinement_completion)
                    if refinement_text.strip():
                        messages.append(
                            {"role": "assistant", "content": refinement_text}
                        )
                        logging.info(
                            "Pesquisa refinement completed (user ID: %s, length: %s)",
                            interaction.user.id,
                            len(refinement_text),
                        )
                        extensao_label = EXTENSAO_LABELS.get(extensao, extensao)
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Análise concluída. Agora prossiga com a pesquisa web e "
                                    f"redija o documento com exatamente {paginas} página(s) — nem menos, nem mais "
                                    f"({extensao_label}). Use as ferramentas de busca para reunir "
                                    "fontes antes de redigir.\n\n"
                                    "IMPORTANTE: Comece diretamente pelo conteúdo do documento. "
                                    'Não inclua introduções como "Aqui está o documento" — '
                                    "seu output deve iniciar com o título ou primeiro parágrafo."
                                ),
                            }
                        )
                    else:
                        logging.warning(
                            "Pesquisa refinement returned empty output (user ID: %s)",
                            interaction.user.id,
                        )
                        del messages[saved_len:]
                except APIError as exc:
                    logging.warning(
                        "Pesquisa refinement API error (user ID: %s): %s",
                        interaction.user.id,
                        get_provider_error_detail(exc),
                    )
                    del messages[saved_len:]
                except Exception:
                    logging.warning(
                        "Pesquisa refinement failed (user ID: %s)",
                        interaction.user.id,
                        exc_info=True,
                    )
                    del messages[saved_len:]

            # Phase 2: Research & generation (tool-calling loop)
            raw_output = await run_research_loop(
                openai_client=openai_client,
                openai_config=openai_config,
                messages=messages,
                max_iterations=max_iterations,
                search_results_per_topic=search_results_count,
                max_page_fetches=max_pages,
                reasoning_effort=reasoning_effort,
                user_id=interaction.user.id,
            )

            elapsed = datetime.now().timestamp() - request_started_at
            logging.info(
                "Pesquisa LLM request completed (user ID: %s, model: %s, elapsed: %.2fs)",
                interaction.user.id,
                openai_config["model"],
                elapsed,
            )

        except ContentFilterError as exc:
            logging.error(
                "Pesquisa LLM content filter triggered (user ID: %s)",
                interaction.user.id,
            )
            await interaction.followup.send(str(exc))
            return
        except APIError as exc:
            logging.exception(
                "Provider error while generating pesquisa: %s",
                get_provider_error_detail(exc),
            )
            await interaction.followup.send(
                "O provedor do modelo interrompeu a geração do documento. "
                + f"Detalhe do provedor: `{str(exc)[:500]}`"
            )
            return
        except Exception:
            logging.exception("Error while generating pesquisa document")
            await interaction.followup.send(
                "Não consegui gerar o documento de pesquisa agora. "
                + "Verifique os logs e tente novamente."
            )
            return

        if not raw_output.strip():
            await interaction.followup.send(
                "Não foi possível gerar o conteúdo do documento."
            )
            return

        # Generate document file
        try:
            file_bytes, _ = generate_document(raw_output, tema, formato_valor)
            filename = build_pesquisa_filename(tema, interaction.user.id, formato_valor)
        except Exception:
            logging.exception("Error while generating document file")
            await interaction.followup.send(
                "Não consegui gerar o arquivo do documento. "
                + "O conteúdo será enviado em mensagens."
            )
            await send_document_result(
                interaction, raw_output, "pesquisa.txt", b"", label="Pesquisa"
            )
            return

        await send_document_result(
            interaction, raw_output, filename, file_bytes, label="Pesquisa"
        )
