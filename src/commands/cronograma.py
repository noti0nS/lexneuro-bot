import logging
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any, cast, final, override

import discord
from discord.ext import commands
from openai import APIError

from ..config import (
    OpenAIRequestConfig,
    build_openai_chat_completion_kwargs,
    get_openai_config,
)
from ..helpers.documents import generate_document
from ..helpers.llm import get_provider_error_detail
from ..helpers.ui import (
    FORMAT_EMOJIS,
    FORMAT_LABELS,
    PYTHON_WEEKDAY,
    WEEKDAY_OPTIONS,
)
from ..prompts.cronograma import build_cronograma_messages, format_date_pt


def parse_test_date(raw: str) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Use o formato YYYY-MM-DD (ex: 2026-06-15).") from exc


def compute_study_window(
    *,
    test_date: date,
    today: date,
    days_before_test: int,
    selected_weekdays: list[int],
) -> tuple[list[date], str | None]:
    window_start = today + timedelta(days=1)
    window_end = test_date - timedelta(days=days_before_test)

    if window_end <= window_start:
        return [], "A prova está muito próxima. Não há janela de estudo suficiente."

    filtered: list[date] = []
    current = window_start
    while current <= window_end:
        if current.weekday() in selected_weekdays:
            filtered.append(current)
        current += timedelta(days=1)

    if not filtered:
        return (
            [],
            "Nenhum dia de estudo disponível com essa combinação de dias da semana.",
        )

    return filtered, None


async def _generate_cronograma_content(
    msg_target: discord.abc.Messageable,
    openai_client: Any,
    openai_config: OpenAIRequestConfig,
    messages: list[dict[str, str]],
    user_id: int,
) -> str | None:
    max_message_length = 2000
    response_chunks: list[str] = []
    finish_reason = None
    curr_content = ""

    request_started_at = datetime.now().timestamp()
    first_chunk_logged = False

    try:
        logging.info(
            "Cronograma LLM stream starting (user ID: %s, model: %s)",
            user_id,
            openai_config["model"],
        )
        async for chunk in await openai_client.chat.completions.create(
            **build_openai_chat_completion_kwargs(openai_config, messages, stream=True)
        ):
            if finish_reason is not None:
                break

            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue

            finish_reason = choice.finish_reason
            new_content = choice.delta.content or ""

            if not first_chunk_logged and new_content:
                logging.info(
                    "Cronograma LLM first chunk (user ID: %s, elapsed: %.2fs)",
                    user_id,
                    datetime.now().timestamp() - request_started_at,
                )
                first_chunk_logged = True

            if not new_content and finish_reason is None:
                continue

            curr_content += new_content

            if len(curr_content) > max_message_length:
                split_at = curr_content.rfind("\n", 0, max_message_length)
                if split_at == -1:
                    split_at = max_message_length
                response_chunks.append(curr_content[:split_at])
                curr_content = curr_content[split_at:]

        if curr_content:
            response_chunks.append(curr_content)

        elapsed = datetime.now().timestamp() - request_started_at
        logging.info(
            "Cronograma LLM stream completed (user ID: %s, chunks: %s, elapsed: %.2fs)",
            user_id,
            len(response_chunks),
            elapsed,
        )

    except APIError as exc:
        logging.exception(
            "Provider error while streaming cronograma: %s",
            get_provider_error_detail(exc),
        )
        await msg_target.send(
            f"O provedor do modelo interrompeu a geração. Detalhe: `{str(exc)[:500]}`"
        )
        return None
    except Exception:
        logging.exception("Error while streaming cronograma")
        await msg_target.send(
            "Não consegui gerar o cronograma agora. Verifique os logs."
        )
        return None

    if not response_chunks:
        await msg_target.send("Não foi possível gerar o cronograma.")
        return None

    for content in response_chunks:
        await msg_target.send(content)

    return "".join(response_chunks)


@final
class WeekdaySelect(discord.ui.Select["WeekdaySelectView"]):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Selecione os dias da semana em que você pode estudar",
            options=[
                discord.SelectOption(label=choice.name, value=choice.value)
                for choice in WEEKDAY_OPTIONS
            ],
            min_values=1,
            max_values=7,
        )

    @override
    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()


@final
class WeekdaySelectView(discord.ui.View):
    def __init__(
        self,
        *,
        msg_target: discord.abc.Messageable,
        state: Any,
        test_date: date,
        subjects: str,
        hours_per_day: int,
        instructions: str | None,
    ) -> None:
        super().__init__(timeout=None)
        self._msg_target = msg_target
        self._state = state
        self._test_date = test_date
        self._subjects = subjects
        self._hours_per_day = hours_per_day
        self._instructions = instructions
        self.add_item(WeekdaySelect())

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.primary)
    async def confirm(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[discord.ui.View],
    ) -> None:
        for child in self.children:
            child.disabled = True  # pyright: ignore[reportAttributeAccessIssue]
        await interaction.response.edit_message(view=self)
        try:
            await self._process_selection(interaction)
        except Exception:
            logging.exception("Unexpected error in cronograma weekday confirm")
            try:
                await interaction.followup.send("Erro inesperado. Tente novamente.")
            except discord.HTTPException:
                pass

    async def _process_selection(self, interaction: discord.Interaction) -> None:
        logging.info(
            "Cronograma weekday confirm (user ID: %s, model: %s)",
            interaction.user.id,
            self._state.curr_model,
        )

        select = next(
            (item for item in self.children if isinstance(item, discord.ui.Select)),
            None,
        )
        if select is None:
            await interaction.followup.send("Erro interno: seletor não encontrado.")
            return

        selected_values = select.values
        if not selected_values:
            await interaction.followup.send("Selecione pelo menos um dia da semana.")
            return

        selected_weekdays = [
            PYTHON_WEEKDAY[v] for v in selected_values if v in PYTHON_WEEKDAY
        ]

        state_config = self._state.config
        cronograma_config = state_config.get("cronograma", {})
        days_before_test = cronograma_config.get("days_before_test", 3)

        today = datetime.now().date()
        calendar_dates, error = compute_study_window(
            test_date=self._test_date,
            today=today,
            days_before_test=days_before_test,
            selected_weekdays=selected_weekdays,
        )

        if error:
            await interaction.followup.send(error)
            return

        view = FormatSelectView(
            msg_target=self._msg_target,
            state=self._state,
            test_date=self._test_date,
            subjects=self._subjects,
            hours_per_day=self._hours_per_day,
            instructions=self._instructions,
            calendar_dates=calendar_dates,
        )
        await interaction.followup.send(
            "Selecione o formato de saída:",
            view=view,
        )


@final
class FormatSelectView(discord.ui.View):
    def __init__(
        self,
        *,
        msg_target: discord.abc.Messageable,
        state: Any,
        test_date: date,
        subjects: str,
        hours_per_day: int,
        instructions: str | None,
        calendar_dates: list[date],
    ) -> None:
        super().__init__(timeout=None)
        self._msg_target = msg_target
        self._state = state
        self._test_date = test_date
        self._subjects = subjects
        self._hours_per_day = hours_per_day
        self._instructions = instructions
        self._calendar_dates = calendar_dates

        for fmt in ("pdf", "md", "docx", "odt"):
            self.add_item(FormatButton(fmt, FORMAT_LABELS[fmt], FORMAT_EMOJIS[fmt]))

    async def handle_format(self, interaction: discord.Interaction, fmt: str) -> None:
        for child in self.children:
            child.disabled = True  # pyright: ignore[reportAttributeAccessIssue]
        await interaction.response.edit_message(view=self)

        day_count = len(self._calendar_dates)
        await self._msg_target.send(
            f"Gerando cronograma para {day_count} dia{'s' if day_count != 1 else ''} de estudo..."
        )

        state_config = self._state.config
        openai_client, openai_config = get_openai_config(
            state_config, self._state.curr_model
        )
        logging.info(
            "Cronograma LLM config (user ID: %s, model: %s, format: %s)",
            interaction.user.id,
            openai_config["model"],
            fmt,
        )

        messages = build_cronograma_messages(
            test_date=self._test_date,
            subjects=self._subjects,
            hours_per_day=self._hours_per_day,
            instructions=self._instructions,
            calendar_dates=self._calendar_dates,
        )

        content = await _generate_cronograma_content(
            self._msg_target,
            openai_client,
            openai_config,
            messages,
            interaction.user.id,
        )

        if not content:
            return

        try:
            test_date_formatted = format_date_pt(self._test_date)
            title = f"Cronograma de Estudos — Prova: {test_date_formatted}"
            file_bytes, ext = generate_document(content, title, fmt)
        except RuntimeError as exc:
            await self._msg_target.send(str(exc))
            return

        filename = (
            f"cronograma_{test_date_formatted.replace('/', '-').replace(' ', '_')}{ext}"
        )
        discord_file = discord.File(BytesIO(file_bytes), filename=filename)
        await self._msg_target.send(file=discord_file)


@final
class FormatButton(discord.ui.Button["FormatSelectView"]):
    def __init__(self, fmt: str, label: str, emoji: str) -> None:
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.primary
            if fmt == "pdf"
            else discord.ButtonStyle.secondary,
        )
        self._fmt = fmt

    @override
    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if view is None:
            return
        await view.handle_format(interaction, self._fmt)


def register_cronograma_command(
    discord_bot: commands.Bot,
    state: Any,
) -> None:
    @discord_bot.tree.command(
        name="cronograma",
        description="Gere um cronograma de estudos personalizado",
    )
    @discord.app_commands.describe(
        test_date="Data da prova (YYYY-MM-DD). Ex: 2026-06-15",
        subjects="Matérias separadas por vírgula. Ex: Direito Civil, Processo Penal, Constitucional",
        hours_per_day="Horas disponíveis por dia para estudo",
        instructions="Instruções adicionais para o cronograma",
    )
    async def cronograma_command(
        interaction: discord.Interaction,
        test_date: str,
        subjects: str,
        hours_per_day: int = 4,
        instructions: str | None = None,
    ) -> None:
        try:
            parsed_date = parse_test_date(test_date)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        today = datetime.now().date()
        if parsed_date <= today:
            await interaction.response.send_message(
                "A data da prova deve ser no futuro.", ephemeral=True
            )
            return

        min_days = state.config.get("cronograma", {}).get("days_before_test", 3) + 2
        if (parsed_date - today).days < min_days:
            await interaction.response.send_message(
                "A prova está muito próxima. Não há janela de estudo suficiente.",
                ephemeral=True,
            )
            return

        if not subjects.strip():
            await interaction.response.send_message(
                "Informe pelo menos uma matéria.", ephemeral=True
            )
            return

        if hours_per_day <= 0:
            await interaction.response.send_message(
                "As horas por dia devem ser positivas.", ephemeral=True
            )
            return

        if hours_per_day > 16:
            await interaction.response.send_message(
                f"Ninguém estuda {hours_per_day}h por dia. Seja realista.",
                ephemeral=True,
            )
            return

        channel = interaction.channel
        is_dm = isinstance(channel, discord.DMChannel)
        if channel is None or (
            not isinstance(channel, discord.TextChannel) and not is_dm
        ):
            await interaction.response.send_message(
                "Erro: comando deve ser usado em um canal de texto ou DM.",
                ephemeral=True,
            )
            return

        if is_dm:
            await interaction.response.defer()
            test_date_formatted = format_date_pt(parsed_date)
            msg_target: discord.abc.Messageable = cast(discord.abc.Messageable, channel)
        else:
            assert isinstance(channel, discord.TextChannel)
            await interaction.response.defer()
            test_date_formatted = format_date_pt(parsed_date)
            try:
                thread = await channel.create_thread(
                    name=f"Cronograma: {test_date_formatted}",
                    type=discord.ChannelType.public_thread,
                )
            except discord.HTTPException as exc:
                await interaction.followup.send(
                    f"Erro ao criar thread: {exc}", ephemeral=True
                )
                return

            await interaction.edit_original_response(
                content=f"Cronograma criado: {thread.mention}"
            )
            msg_target = thread

        view = WeekdaySelectView(
            msg_target=msg_target,
            state=state,
            test_date=parsed_date,
            subjects=subjects.strip(),
            hours_per_day=hours_per_day,
            instructions=instructions,
        )
        await msg_target.send(
            "Selecione os dias da semana em que você pode estudar:",
            view=view,
        )
