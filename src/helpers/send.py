from io import BytesIO
from typing import cast

import discord


async def send_followup_chunked(
    interaction: discord.Interaction, text: str, *, max_len: int = 2000
) -> None:
    if len(text) <= max_len:
        await interaction.followup.send(text)
        return

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        split_at = remaining.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    for chunk in chunks:
        await interaction.followup.send(chunk)


async def send_document_result(
    interaction: discord.Interaction,
    content: str,
    filename: str,
    file_bytes: bytes,
    *,
    label: str = "Documento",
) -> None:
    max_file_size = int(7.5 * 1024 * 1024)

    if len(file_bytes) < max_file_size:
        file = discord.File(
            fp=BytesIO(file_bytes),
            filename=filename,
        )
        await interaction.followup.send(
            f"{label} concluída! Aqui está o documento:",
            file=file,
        )
        return

    channel = interaction.channel
    if channel is None:
        await interaction.followup.send(
            "Não foi possível criar uma thread para enviar o documento.",
        )
        return

    thread_name = f"{label}: {filename.rsplit('.', 1)[0][:80]}"
    if isinstance(channel, discord.TextChannel) or (
        getattr(channel, "type", None) == discord.ChannelType.text
    ):
        thread = await cast(discord.TextChannel, channel).create_thread(
            name=thread_name,
            type=discord.ChannelType.public_thread,
        )
    else:
        await interaction.followup.send(
            "Não foi possível criar uma thread neste canal.",
        )
        return

    max_message_length = 1900
    chunks: list[str] = []
    current_chunk = ""

    for line in content.split("\n"):
        if len(current_chunk) + len(line) + 1 > max_message_length:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            remaining_line = line
            while len(remaining_line) > max_message_length:
                chunks.append(remaining_line[:max_message_length])
                remaining_line = remaining_line[max_message_length:]
            current_chunk = remaining_line + "\n"
        else:
            current_chunk += line + "\n"

    if current_chunk:
        chunks.append(current_chunk)

    await thread.send(
        f"**{label} concluída!** O documento foi dividido em {len(chunks)} partes.\n"
        + "(O arquivo original excede o limite de tamanho do Discord, então foi enviado em mensagens.)"
    )

    for i, chunk in enumerate(chunks, 1):
        await thread.send(f"**Parte {i}/{len(chunks)}**\n```\n{chunk}\n```")

    await interaction.followup.send(
        f"{label} concluída! O documento foi enviado na thread: {thread.mention}"
    )
