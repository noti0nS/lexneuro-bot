import asyncio
import logging
import types
from base64 import b64encode
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import discord
import httpx
from discord.ext import commands
from discord.ui import LayoutView, TextDisplay

from .commands.abnt import register_abnt_command
from .commands.cronograma import register_cronograma_command
from .commands.status import register_status_commands
from .helpers.status_scheduler import start_status_scheduler
from .commands.model import register_model_command
from .commands.pesquisa import register_pesquisa_command
from .config import (
    build_openai_chat_completion_kwargs,
    get_config,
    get_openai_config,
)
from .helpers.ui import (
    EMBED_COLOR_COMPLETE,
    MAX_MESSAGE_NODES,
    STREAMING_INDICATOR,
    VISION_MODEL_TAGS,
)
from .helpers.content import sanitize_discord_markdown
from .prompts import build_system_prompt


@dataclass
class MsgNode:
    role: Literal["user", "assistant"] = "assistant"
    text: str | None = None
    images: list[dict[str, Any]] = field(default_factory=list)
    has_bad_attachments: bool = False
    fetch_parent_failed: bool = False
    parent_msg: discord.Message | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def should_process_message(
    message: discord.Message,
    bot_user: discord.ClientUser,
    msg_nodes: dict[int, MsgNode],
) -> bool:
    if message.author.bot:
        return False

    if message.channel.type == discord.ChannelType.private:
        return True

    if bot_user in message.mentions:
        return True

    reference = message.reference
    if reference is None:
        return False

    cached_parent = reference.cached_message
    if cached_parent is not None:
        return cached_parent.author == bot_user

    parent_msg_id = reference.message_id
    if parent_msg_id is None:
        return False

    parent_node = msg_nodes.get(parent_msg_id)
    return parent_node is not None and parent_node.role == "assistant"


def user_has_permission(
    user: discord.User | discord.Member,
    channel: Any | None,
    config: dict[str, Any],
) -> bool:
    is_dm = channel is not None and channel.type == discord.ChannelType.private

    role_ids = {role.id for role in getattr(user, "roles", ())}
    channel_ids = set(
        filter(
            None,
            (
                getattr(channel, "id", None),
                getattr(channel, "parent_id", None),
                getattr(channel, "category_id", None),
            ),
        )
    )

    allow_dms = config.get("allow_dms", True)
    permissions = config["permissions"]
    user_is_admin = user.id in permissions["users"]["admin_ids"]

    (
        (allowed_user_ids, blocked_user_ids),
        (allowed_role_ids, blocked_role_ids),
        (allowed_channel_ids, blocked_channel_ids),
    ) = (
        (perm["allowed_ids"], perm["blocked_ids"])
        for perm in (
            permissions["users"],
            permissions["roles"],
            permissions["channels"],
        )
    )

    allow_all_users = (
        not allowed_user_ids if is_dm else not allowed_user_ids and not allowed_role_ids
    )
    is_good_user = (
        user_is_admin
        or allow_all_users
        or user.id in allowed_user_ids
        or any(role_id in allowed_role_ids for role_id in role_ids)
    )
    is_bad_user = (
        not is_good_user
        or user.id in blocked_user_ids
        or any(role_id in blocked_role_ids for role_id in role_ids)
    )

    allow_all_channels = not allowed_channel_ids
    is_good_channel = (
        user_is_admin or allow_dms
        if is_dm
        else allow_all_channels
        or any(channel_id in allowed_channel_ids for channel_id in channel_ids)
    )
    is_bad_channel = not is_good_channel or any(
        channel_id in blocked_channel_ids for channel_id in channel_ids
    )

    return not is_bad_user and not is_bad_channel


def create_discord_bot(initial_config: dict[str, Any] | None = None) -> commands.Bot:
    config = initial_config or get_config()
    curr_model = next(iter(config["models"]))
    msg_nodes: dict[int, MsgNode] = {}
    channel_locks: dict[int, asyncio.Lock] = {}
    state = types.SimpleNamespace(config=config, curr_model=curr_model)

    intents = discord.Intents.default()
    intents.message_content = True
    activity = discord.CustomActivity(
        name=(state.config.get("status_message") or "github.com/noti0nS/lexneuro-bot")[
            :128
        ]
    )
    discord_bot = commands.Bot(
        intents=intents, activity=activity, command_prefix=commands.when_mentioned
    )
    httpx_client = httpx.AsyncClient()

    register_model_command(discord_bot, state)
    register_status_commands(discord_bot, state)
    register_abnt_command(discord_bot, state, httpx_client, user_has_permission)
    register_cronograma_command(discord_bot, state)
    register_pesquisa_command(discord_bot, state)

    @discord_bot.event
    async def on_ready() -> None:
        if client_id := state.config.get("client_id"):
            logging.info(
                "\n\nBOT INVITE URL:\nhttps://discord.com/oauth2/authorize?client_id=%s&permissions=412317191168&scope=bot\n",
                client_id,
            )

        await discord_bot.tree.sync()

        start_status_scheduler(discord_bot)

    @discord_bot.event
    async def on_message(new_msg: discord.Message) -> None:
        bot_user = discord_bot.user
        if bot_user is None:
            return

        if not should_process_message(new_msg, bot_user, msg_nodes):
            return

        if not user_has_permission(new_msg.author, new_msg.channel, state.config):
            return

        channel_lock = channel_locks.setdefault(new_msg.channel.id, asyncio.Lock())
        if channel_lock.locked():
            return

        openai_client, openai_config = get_openai_config(state.config, state.curr_model)
        accept_images = any(
            tag in state.curr_model.lower() for tag in VISION_MODEL_TAGS
        )
        max_text = state.config.get("max_text", 100000)
        max_images = state.config.get("max_images", 5) if accept_images else 0
        max_messages = state.config.get("max_messages", 25)

        messages = []
        user_warnings = set()
        curr_msg = new_msg

        while curr_msg is not None and len(messages) < max_messages:
            curr_node = msg_nodes.setdefault(curr_msg.id, MsgNode())

            async with curr_node.lock:
                if curr_node.text is None:
                    cleaned_content = curr_msg.content.removeprefix(
                        bot_user.mention
                    ).lstrip()

                    good_attachments = [
                        att
                        for att in curr_msg.attachments
                        if (content_type := att.content_type)
                        and any(
                            content_type.startswith(kind) for kind in ("text", "image")
                        )
                    ]

                    attachment_responses = await asyncio.gather(
                        *[httpx_client.get(att.url) for att in good_attachments]
                    )

                    curr_node.role = (
                        "assistant" if curr_msg.author == bot_user else "user"
                    )

                    curr_node.text = "\n".join(
                        ([cleaned_content] if cleaned_content else [])
                        + [
                            "\n".join(
                                filter(
                                    None,
                                    (embed.title, embed.description, embed.footer.text),
                                )
                            )
                            for embed in curr_msg.embeds
                        ]
                        + [
                            content
                            for component in curr_msg.components
                            if component.type == discord.ComponentType.text_display
                            and isinstance(
                                (content := getattr(component, "content", None)),
                                str,  # type: ignore[no-any-return]
                            )
                        ]
                        + [
                            resp.text
                            for att, resp in zip(good_attachments, attachment_responses)
                            if (content_type := att.content_type)
                            and content_type.startswith("text")
                        ]
                    )

                    curr_node.images = [
                        dict(
                            type="image_url",
                            image_url=dict(
                                url=f"data:{content_type};base64,{b64encode(resp.content).decode('utf-8')}"
                            ),
                        )
                        for att, resp in zip(good_attachments, attachment_responses)
                        if (content_type := att.content_type)
                        and content_type.startswith("image")
                    ]

                    if curr_node.role == "user" and (
                        curr_node.text or curr_node.images
                    ):
                        curr_node.text = f"<@{curr_msg.author.id}>: {curr_node.text}"

                    curr_node.has_bad_attachments = len(curr_msg.attachments) > len(
                        good_attachments
                    )

                    try:
                        is_dm = curr_msg.channel.type == discord.ChannelType.private
                        bot_mentioned = bot_user in curr_msg.mentions
                        if (
                            curr_msg.reference is None
                            and (
                                prev_msg_in_channel := (
                                    [
                                        message
                                        async for message in curr_msg.channel.history(
                                            before=curr_msg, limit=1
                                        )
                                    ]
                                    or [None]
                                )[0]
                            )
                            and prev_msg_in_channel.type
                            in (discord.MessageType.default, discord.MessageType.reply)
                            and (
                                (
                                    not bot_mentioned
                                    and prev_msg_in_channel.author == curr_msg.author
                                )
                                or (
                                    prev_msg_in_channel.author == bot_user
                                    and (bot_mentioned or is_dm)
                                )
                            )
                        ):
                            curr_node.parent_msg = prev_msg_in_channel
                        else:
                            reference = curr_msg.reference
                            if reference is not None and not isinstance(
                                curr_msg.channel, discord.Thread
                            ):
                                parent_msg_id = reference.message_id
                                if parent_msg_id is not None:
                                    curr_node.parent_msg = (
                                        reference.cached_message
                                        or await curr_msg.channel.fetch_message(
                                            parent_msg_id
                                        )
                                    )
                            if isinstance(curr_msg.channel, discord.Thread):
                                parent_is_thread_start = (
                                    curr_msg.reference is None
                                    and curr_msg.channel.parent is not None
                                    and curr_msg.channel.parent.type
                                    == discord.ChannelType.text
                                )

                                if parent_msg_id := (
                                    curr_msg.channel.id
                                    if parent_is_thread_start
                                    else getattr(reference, "message_id", None)
                                ):
                                    if parent_is_thread_start:
                                        parent_channel = curr_msg.channel.parent
                                        assert parent_channel is not None
                                        if isinstance(
                                            parent_channel, discord.TextChannel
                                        ):
                                            curr_node.parent_msg = (
                                                curr_msg.channel.starter_message
                                                or await parent_channel.fetch_message(
                                                    parent_msg_id
                                                )
                                            )
                                        else:
                                            curr_node.parent_msg = (
                                                curr_msg.channel.starter_message
                                            )
                                    else:
                                        curr_node.parent_msg = getattr(
                                            reference, "cached_message", None
                                        ) or await curr_msg.channel.fetch_message(
                                            parent_msg_id
                                        )

                    except (discord.NotFound, discord.HTTPException):
                        logging.debug(
                            "Could not fetch parent message (channel=%s)",
                            curr_msg.channel.id,
                        )
                        curr_node.fetch_parent_failed = True

                if curr_node.images[:max_images]:
                    content = [
                        dict(type="text", text=curr_node.text[:max_text])
                    ] + curr_node.images[:max_images]
                else:
                    content = curr_node.text[:max_text]

                if content != "":
                    messages.append(dict(content=content, role=curr_node.role))

                if len(curr_node.text) > max_text:
                    user_warnings.add(f"⚠️ Max {max_text:,} characters per message")
                if len(curr_node.images) > max_images:
                    user_warnings.add(
                        f"⚠️ Max {max_images} image{'' if max_images == 1 else 's'} per message"
                        if max_images > 0
                        else "⚠️ Can't see images"
                    )
                curr_msg = curr_node.parent_msg

        logging.debug(
            "Message received (user ID: %s, attachments: %s, conversation length: %s):\n%s",
            new_msg.author.id,
            len(new_msg.attachments),
            len(messages),
            new_msg.content,
        )

        now = datetime.now().astimezone()
        system_prompt = (
            (state.config.get("system_prompt") or "")
            .replace("{date}", now.strftime("%B %d %Y"))
            .replace("{time}", now.strftime("%H:%M:%S %Z%z"))
        )
        messages.append(dict(role="system", content=build_system_prompt(system_prompt)))

        curr_content = finish_reason = None
        response_msgs = []
        response_contents = []

        openai_kwargs = dict(
            model=openai_config["model"],
            messages=messages[::-1],
            stream=True,
            extra_headers=openai_config["extra_headers"],
            extra_query=openai_config["extra_query"],
            extra_body=openai_config["extra_body"],
        )

        use_plain_responses = state.config.get("use_plain_responses", False)
        response_embed: discord.Embed | None = None
        if use_plain_responses:
            max_message_length = 4000
        else:
            max_message_length = 4096 - len(STREAMING_INDICATOR)
            response_embed = discord.Embed.from_dict(
                dict(
                    fields=[
                        dict(name=warning, value="", inline=False)
                        for warning in sorted(user_warnings)
                    ]
                )
            )

        async def reply_helper(**reply_kwargs: Any) -> None:
            reply_target = new_msg if not response_msgs else response_msgs[-1]
            response_msg = await reply_target.reply(**reply_kwargs)
            response_msgs.append(response_msg)

            msg_nodes[response_msg.id] = MsgNode(parent_msg=new_msg)
            await msg_nodes[response_msg.id].lock.acquire()

        request_started_at = datetime.now().timestamp()
        first_chunk_logged = False
        async with channel_lock:
            try:
                logging.info(
                    "LLM streaming request started (user ID: %s, model: %s, message_count: %s, plain_mode: %s)",
                    new_msg.author.id,
                    openai_kwargs["model"],
                    len(messages),
                    use_plain_responses,
                )

                typing_ctx = new_msg.channel.typing()
                typing_active = False
                try:
                    await typing_ctx.__aenter__()
                    typing_active = True
                except discord.HTTPException as e:
                    if e.status != 429:
                        raise
                    logging.debug(
                        "Skipping typing indicator due to rate limit (channel=%s)",
                        new_msg.channel.id,
                    )

                try:
                    async for chunk in await openai_client.chat.completions.create(
                        **build_openai_chat_completion_kwargs(
                            openai_config, messages[::-1], stream=True
                        )
                    ):
                        if finish_reason is not None:
                            break

                        if not (choice := chunk.choices[0] if chunk.choices else None):
                            continue

                        finish_reason = choice.finish_reason
                        prev_content = curr_content or ""
                        curr_content = choice.delta.content or ""
                        new_content = (
                            prev_content
                            if finish_reason is None
                            else (prev_content + curr_content)
                        )

                        if response_contents == [] and new_content == "":
                            continue

                        start_next_msg = (
                            response_contents == []
                            or len(response_contents[-1] + new_content)
                            > max_message_length
                        )
                        if start_next_msg:
                            response_contents.append("")

                        response_contents[-1] += new_content
                        if not first_chunk_logged and (
                            new_content != "" or finish_reason is not None
                        ):
                            logging.info(
                                "LLM streaming first chunk received (user ID: %s, model: %s, elapsed: %.2fs)",
                                new_msg.author.id,
                                openai_kwargs["model"],
                                datetime.now().timestamp() - request_started_at,
                            )
                            first_chunk_logged = True

                    if use_plain_responses:
                        for content in response_contents:
                            sanitized = sanitize_discord_markdown(content)
                            await reply_helper(
                                view=LayoutView().add_item(
                                    TextDisplay(content=sanitized)
                                )
                            )
                    else:
                        assert response_embed is not None
                        for content in response_contents:
                            response_embed.description = sanitize_discord_markdown(
                                content
                            )
                            response_embed.color = EMBED_COLOR_COMPLETE
                            await reply_helper(embed=response_embed)
                finally:
                    if typing_active:
                        await typing_ctx.__aexit__(None, None, None)
                logging.info(
                    "LLM streaming request completed (user ID: %s, model: %s, finish_reason: %s, chunks: %s, elapsed: %.2fs)",
                    new_msg.author.id,
                    openai_kwargs["model"],
                    finish_reason,
                    len(response_contents),
                    datetime.now().timestamp() - request_started_at,
                )

            except discord.DiscordServerError:
                await new_msg.channel.send(
                    "O Discord está temporariamente indisponível. Tente novamente mais tarde. Status: https://discordstatus.com"
                )
                logging.exception(
                    "Discord 503 error while generating response (user ID: %s, model: %s)",
                    new_msg.author.id,
                    openai_kwargs["model"],
                )

            except discord.HTTPException as e:
                if e.status == 429:
                    rl_headers = {
                        k: e.response.headers.get(k)
                        for k in (
                            "X-RateLimit-Limit",
                            "X-RateLimit-Remaining",
                            "X-RateLimit-Reset",
                            "X-RateLimit-Reset-After",
                            "X-RateLimit-Scope",
                            "Retry-After",
                        )
                    }
                    logging.exception(
                        "Discord 429 rate limit (user ID: %s, model: %s, headers: %s)",
                        new_msg.author.id,
                        openai_kwargs["model"],
                        rl_headers,
                    )
                else:
                    logging.exception(
                        "Discord %s HTTP error while generating response (user ID: %s, model: %s)",
                        e.status,
                        new_msg.author.id,
                        openai_kwargs["model"],
                    )

            except Exception:
                logging.exception(
                    "Error while generating response (user ID: %s, model: %s)",
                    new_msg.author.id,
                    openai_kwargs["model"],
                )

        for response_msg in response_msgs:
            msg_nodes[response_msg.id].text = "".join(response_contents)
            msg_nodes[response_msg.id].lock.release()

        if (num_nodes := len(msg_nodes)) > MAX_MESSAGE_NODES:
            for msg_id in sorted(msg_nodes.keys())[: num_nodes - MAX_MESSAGE_NODES]:
                async with msg_nodes.setdefault(msg_id, MsgNode()).lock:
                    msg_nodes.pop(msg_id, None)

    return discord_bot
