import asyncio
import json
import logging
from datetime import datetime
from typing import Any

import discord
import httpx
from discord.ext import commands

from ...helpers.async_utils import await_task_with_heartbeats
from ...helpers.content import get_completion_text
from ...helpers.attachments import (
    attachment_is_supported_word_document,
    read_word_attachment,
)
from ...helpers.llm import (
    LLMAborted,
    execute_chat_completion,
    llm_error_handling,
)
from ...prompts import build_abnt_messages


def parse_abnt_evaluation_json(raw_content: str) -> tuple[float, list[str]]:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_json") from exc

    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")

    score = payload.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError("invalid_score")

    improvements = payload.get("improvements")
    if not isinstance(improvements, list):
        raise ValueError("invalid_improvements")

    normalized_improvements = []
    for improvement in improvements:
        if not isinstance(improvement, str):
            raise ValueError("invalid_improvement_item")

        clean_text = improvement.strip()
        if clean_text:
            normalized_improvements.append(clean_text)

    normalized_score = max(0.0, min(1.0, float(score)))
    return normalized_score, normalized_improvements


def build_abnt_result_message(score: float, improvements: list[str]) -> str:
    score_percent = round(score * 100)

    if score >= 0.9:
        return (
            f"Análise ABNT concluída. Pontuação: {score_percent}%.\n"
            "Seu documento já está bom o suficiente."
        )

    if improvements:
        improvement_lines = "\n".join(
            f"- {improvement}" for improvement in improvements
        )
    else:
        improvement_lines = "- Nenhum ponto específico foi retornado pelo avaliador."

    if score >= 0.7:
        return (
            f"Análise ABNT concluída. Pontuação: {score_percent}%.\n"
            "Seu documento está no caminho certo. Ajuste os pontos abaixo para melhorar ainda mais:\n"
            f"{improvement_lines}"
        )

    return (
        f"Análise ABNT concluída. Pontuação: {score_percent}%.\n"
        "Seu documento precisa de revisão para atender melhor às normas ABNT. Priorize os pontos abaixo:\n"
        f"{improvement_lines}"
    )


def register_abnt_command(
    discord_bot: commands.Bot,
    state: Any,
    httpx_client: httpx.AsyncClient,
    user_has_permission: Any,
) -> None:
    @discord_bot.tree.command(
        name="abnt",
        description="Avalie um documento DOCX ou ODT conforme ABNT e receba melhorias",
    )
    async def abnt_command(
        interaction: discord.Interaction,
        document: discord.Attachment,
        instructions: str | None = None,
    ) -> None:
        if not attachment_is_supported_word_document(document):
            await interaction.response.send_message(
                "Tipo de documento não suportado. Envie um arquivo `.docx` ou `.odt`.",
                ephemeral=True,
            )
            return

        if not user_has_permission(interaction.user, interaction.channel, state.config):
            await interaction.response.send_message(
                "Você não tem permissão para usar este bot aqui.", ephemeral=True
            )
            return

        max_document_chars = state.config.get("abnt", {}).get(
            "max_document_chars", state.config.get("max_text", 100000)
        )
        logging.info(
            "ABNT attachment read started (user ID: %s, file: %s)",
            interaction.user.id,
            document.filename,
        )
        try:
            document_text, document_was_truncated = await read_word_attachment(
                document, max_document_chars, httpx_client
            )
        except ValueError:
            await interaction.response.send_message(
                "Tipo de documento não suportado. Envie um arquivo `.docx` ou `.odt`.",
                ephemeral=True,
            )
            return
        except Exception:
            logging.exception("Error while reading ABNT attachment")
            await interaction.response.send_message(
                "Não consegui ler o anexo. Tente novamente com um arquivo `.docx` ou `.odt` válido.",
                ephemeral=True,
            )
            return
        logging.info(
            "ABNT attachment read completed (user ID: %s, file: %s, chars: %s, truncated: %s)",
            interaction.user.id,
            document.filename,
            len(document_text),
            document_was_truncated,
        )

        if not document_text.strip():
            await interaction.response.send_message(
                "O documento anexado parece estar vazio.", ephemeral=True
            )
            return

        is_dm = (
            interaction.channel is not None
            and interaction.channel.type == discord.ChannelType.private
        )
        await interaction.response.send_message(
            f"Opa! Estou analisando o documento '**{document.filename}**', {interaction.user.mention}. Um momento...",
            ephemeral=is_dm,
        )

        logging.info(
            "ABNT command received (user ID: %s, file: %s, chars: %s)",
            interaction.user.id,
            document.filename,
            len(document_text),
        )

        raw_output = ""
        request_started_at = datetime.now().timestamp()
        try:
            async with llm_error_handling(interaction, "ABNT"):
                messages = build_abnt_messages(
                    filename=document.filename,
                    document_text=document_text,
                    instructions=instructions,
                    document_was_truncated=document_was_truncated,
                    max_document_chars=max_document_chars,
                )
                logging.info(
                    "ABNT LLM request started (user ID: %s, model: %s, file: %s, message_count: %s)",
                    interaction.user.id,
                    state.curr_model,
                    document.filename,
                    len(messages),
                )
                completion_task = asyncio.create_task(
                    execute_chat_completion(
                        config=state.config,
                        model_name=state.curr_model,
                        messages=messages,
                    )
                )
                completion = await await_task_with_heartbeats(
                    completion_task,
                    (
                        "ABNT LLM request still running "
                        f"(user ID: {interaction.user.id}, model: {state.curr_model}, file: {document.filename})"
                    ),
                )
                elapsed = datetime.now().timestamp() - request_started_at
                logging.info(
                    "ABNT LLM request completed (user ID: %s, model: %s, file: %s, elapsed: %.2fs)",
                    interaction.user.id,
                    state.curr_model,
                    document.filename,
                    elapsed,
                )
                raw_output = get_completion_text(completion)
        except LLMAborted:
            return

        try:
            score, improvements = parse_abnt_evaluation_json(raw_output)
            output = build_abnt_result_message(score, improvements)
            logging.info(
                "ABNT evaluation parsed (user ID: %s, file: %s, score: %.3f, improvements: %s)",
                interaction.user.id,
                document.filename,
                score,
                len(improvements),
            )
        except ValueError as exc:
            logging.warning(
                "ABNT evaluation JSON parse failed (user ID: %s, file: %s, reason: %s, output_preview: %s)",
                interaction.user.id,
                document.filename,
                exc,
                raw_output[:300],
            )
            await interaction.followup.send(
                "Não consegui interpretar a avaliação ABNT do provedor. Tente novamente em alguns instantes."
            )
            return

        if not output:
            await interaction.followup.send(
                "Não foi possível gerar o resultado da avaliação ABNT."
            )
            return

        await interaction.followup.send(output)
