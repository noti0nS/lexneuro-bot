import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Literal

import discord
import httpx
import yaml
from discord.ext import commands

from ...helpers.ui import ACAO_JSON_CHOICES

JSON_EXTENSIONS = (".json", ".yaml", ".yml")
JSON_CONTENT_TYPES = (
    "application/json",
    "text/plain",
    "application/octet-stream",
    "application/x-yaml",
    "text/yaml",
    "text/x-yaml",
)


def _attachment_is_json(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    filename = attachment.filename.lower()
    return content_type in JSON_CONTENT_TYPES or filename.endswith(JSON_EXTENSIONS)


@dataclass(frozen=True)
class JsonOutput:
    text: str
    kind: Literal["message", "code"] = "code"
    code_lang: str = "json"
    file_ext: str = ".txt"

    @staticmethod
    def message(text: str) -> "JsonOutput":
        return JsonOutput(text=text, kind="message")

    @staticmethod
    def code(text: str, lang: str) -> "JsonOutput":
        return JsonOutput(text=text, kind="code", code_lang=lang)


def _parse_as_object(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    try:
        obj = yaml.safe_load(text)
        if obj is None:
            raise ValueError("O texto está vazio ou contém apenas comentários YAML.")
        return obj
    except yaml.YAMLError:
        raise ValueError("Não foi possível interpretar o texto como JSON ou YAML.")


def _ensure_yaml(text: str) -> Any:
    try:
        obj = yaml.safe_load(text)
        if obj is None:
            raise ValueError("O texto está vazio ou contém apenas comentários YAML.")
        return obj
    except yaml.YAMLError:
        raise ValueError("Não foi possível interpretar o texto como YAML.")


def _handle_validate(text: str) -> JsonOutput:
    try:
        json.loads(text)
        return JsonOutput.message("JSON válido.")
    except json.JSONDecodeError:
        pass

    try:
        yaml.safe_load(text)
        return JsonOutput.message("YAML válido.")
    except yaml.YAMLError:
        pass

    raise ValueError("Texto não é JSON nem YAML válido.")


def _handle_format(text: str) -> JsonOutput:
    return JsonOutput.code(
        json.dumps(_parse_as_object(text), indent=2, ensure_ascii=False), "json"
    )


def _handle_minify(text: str) -> JsonOutput:
    return JsonOutput.code(
        json.dumps(_parse_as_object(text), separators=(",", ":"), ensure_ascii=False),
        "json",
    )


def _handle_json2yaml(text: str) -> JsonOutput:
    return JsonOutput.code(
        yaml.safe_dump(
            _parse_as_object(text), allow_unicode=True, sort_keys=False
        ).rstrip("\n"),
        "yaml",
    )


def _handle_yaml2json(text: str) -> JsonOutput:
    return JsonOutput.code(
        json.dumps(_ensure_yaml(text), indent=2, ensure_ascii=False), "json"
    )


_HANDLERS: dict[str, Callable[[str], JsonOutput]] = {
    "validar": _handle_validate,
    "formatar": _handle_format,
    "minificar": _handle_minify,
    "json2yaml": _handle_json2yaml,
    "yaml2json": _handle_yaml2json,
}


def register_json_command(
    discord_bot: commands.Bot,
    state: Any,
    httpx_client: httpx.AsyncClient,
) -> None:
    @discord_bot.tree.command(
        name="json",
        description="Valide, formate, minifique ou converta entre JSON e YAML",
    )
    @discord.app_commands.describe(
        acao="Ação a ser executada",
        texto="Texto JSON ou YAML para processar",
        arquivo="Arquivo .json, .yaml ou .yml",
    )
    @discord.app_commands.choices(acao=ACAO_JSON_CHOICES)
    async def json_command(
        interaction: discord.Interaction,
        acao: discord.app_commands.Choice[str],
        texto: str | None = None,
        arquivo: discord.Attachment | None = None,
    ) -> None:
        acao_valor = acao.value

        if (not texto or not texto.strip()) and arquivo is None:
            await interaction.response.send_message(
                "Informe um texto JSON/YAML ou anexe um arquivo .json/.yaml.",
                ephemeral=True,
            )
            return

        input_text = (texto or "").strip()

        if arquivo is not None:
            if not _attachment_is_json(arquivo):
                await interaction.response.send_message(
                    "Tipo de arquivo não suportado. Envie um arquivo .json, .yaml ou .yml.",
                    ephemeral=True,
                )
                return

            logging.info(
                "JSON file download started (user ID: %s, file: %s)",
                interaction.user.id,
                arquivo.filename,
            )
            try:
                response = await httpx_client.get(arquivo.url)
                response.raise_for_status()
            except Exception:
                logging.exception(
                    "JSON file download failed (user ID: %s, file: %s)",
                    interaction.user.id,
                    arquivo.filename,
                )
                await interaction.response.send_message(
                    "Não consegui baixar o anexo. Tente novamente.",
                    ephemeral=True,
                )
                return

            file_text = response.text.strip()
            if not file_text:
                await interaction.response.send_message(
                    "O arquivo parece estar vazio.", ephemeral=True
                )
                return

            if input_text:
                input_text = f"{input_text}\n{file_text}"
            else:
                input_text = file_text

        if not input_text:
            await interaction.response.send_message(
                "O texto está vazio.", ephemeral=True
            )
            return

        max_chars = 100000
        if len(input_text) > max_chars:
            logging.warning(
                "JSON input truncated (user ID: %s, original length: %s)",
                interaction.user.id,
                len(input_text),
            )
            input_text = input_text[:max_chars]

        logging.info(
            "JSON command (user ID: %s, acao: %s, chars: %s)",
            interaction.user.id,
            acao_valor,
            len(input_text),
        )

        await interaction.response.defer(ephemeral=True)

        try:
            result = _HANDLERS[acao_valor](input_text)
        except json.JSONDecodeError as exc:
            await interaction.edit_original_response(
                content=f"JSON inválido na linha {exc.lineno}, coluna {exc.colno}:\n```\n{exc.msg}\n```"
            )
            return
        except yaml.YAMLError as exc:
            detail = str(exc)
            mark = getattr(exc, "problem_mark", None)
            if mark is not None:
                detail = f"linha {mark.line + 1}, coluna {mark.column + 1}: {detail}"
            await interaction.edit_original_response(
                content=f"YAML inválido:\n```\n{detail[:1500]}\n```"
            )
            return
        except ValueError as exc:
            await interaction.edit_original_response(content=f"Erro: {exc}")
            return

        if result.kind == "message":
            await interaction.edit_original_response(content=result.text)
        else:
            await _deliver_code_result(interaction, result)


async def _deliver_code_result(
    interaction: discord.Interaction, result: JsonOutput
) -> None:
    formatted = f"```{result.code_lang}\n{result.text}\n```"
    if len(formatted) <= 2000:
        await interaction.edit_original_response(content=formatted)
    else:
        discord_file = discord.File(
            BytesIO(result.text.encode("utf-8")),
            filename=f"output{result.file_ext}",
        )
        await interaction.edit_original_response(
            content="Resultado muito longo — enviado como arquivo.",
            attachments=[discord_file],
        )
