"""Channel binding helpers."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Chat, Message

from bot.db import BoundChannel, Database
from bot.services.parsing import ChannelRef, format_channel_label, parse_channel_ref

logger = logging.getLogger(__name__)


class ChannelBindError(Exception):
    """User-facing bind failure."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


async def resolve_chat(bot: Bot, ref: ChannelRef) -> Chat:
    if ref.channel_id is not None:
        try:
            return await bot.get_chat(ref.channel_id)
        except TelegramAPIError as exc:
            raise ChannelBindError(
                "Не удалось найти чат по ID. Убедитесь, что бот добавлен в канал "
                "как администратор."
            ) from exc
    assert ref.username
    try:
        return await bot.get_chat(f"@{ref.username}")
    except TelegramAPIError as exc:
        raise ChannelBindError(
            f"Не удалось найти канал @{ref.username}. Проверьте username и права бота."
        ) from exc


async def ensure_bot_can_post(bot: Bot, chat: Chat) -> None:
    if chat.type not in (ChatType.CHANNEL, ChatType.SUPERGROUP):
        raise ChannelBindError(
            "Привязать можно только канал (или супергруппу). "
            f"Тип чата: {chat.type}."
        )
    me = await bot.me()
    try:
        member = await bot.get_chat_member(chat.id, me.id)
    except TelegramAPIError as exc:
        raise ChannelBindError(
            "Бот не состоит в этом канале. Добавьте бота администратором "
            "с правом «Публикация сообщений»."
        ) from exc

    status = member.status
    if status not in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
    ):
        raise ChannelBindError(
            "Бот должен быть администратором канала с правом публикации сообщений."
        )

    can_post = getattr(member, "can_post_messages", None)
    # Creator always can; for channels can_post_messages matters
    if chat.type == ChatType.CHANNEL and status == ChatMemberStatus.ADMINISTRATOR:
        if can_post is False:
            raise ChannelBindError(
                "У бота нет права «Публикация сообщений». Включите его в настройках "
                "администраторов канала."
            )


async def bind_from_forward(bot: Bot, db: Database, message: Message, user_id: int) -> BoundChannel:
    origin = message.forward_from_chat or message.forward_origin
    chat: Chat | None = None

    if message.forward_from_chat is not None:
        chat = message.forward_from_chat
    else:
        # aiogram 3 MessageOriginChannel
        fo = getattr(message, "forward_origin", None)
        if fo is not None and getattr(fo, "chat", None) is not None:
            chat = fo.chat

    if chat is None:
        raise ChannelBindError(
            "Перешлите пост из канала (не скрывая автора) или отправьте @username / ID канала."
        )

    # Refresh chat info via API
    fresh = await bot.get_chat(chat.id)
    await ensure_bot_can_post(bot, fresh)
    bound = await db.upsert_channel(
        fresh.id,
        title=fresh.title,
        username=fresh.username,
        bound_by=user_id,
    )
    logger.info("Bound channel_id=%s by user_id=%s", fresh.id, user_id)
    return bound


async def bind_from_text(bot: Bot, db: Database, text: str, user_id: int) -> BoundChannel:
    ref = parse_channel_ref(text)
    if ref is None:
        raise ChannelBindError(
            "Не распознан канал. Отправьте @username, числовой ID или перешлите пост из канала."
        )
    chat = await resolve_chat(bot, ref)
    await ensure_bot_can_post(bot, chat)
    bound = await db.upsert_channel(
        chat.id,
        title=chat.title,
        username=chat.username,
        bound_by=user_id,
    )
    logger.info("Bound channel_id=%s by user_id=%s", chat.id, user_id)
    return bound


def channels_list_text(channels: list[BoundChannel]) -> str:
    if not channels:
        return "Нет привязанных каналов. Используйте /bind."
    lines = ["📎 Привязанные каналы:"]
    for ch in channels:
        lines.append(f"• {format_channel_label(ch.channel_id, ch.title, ch.username)}")
    return "\n".join(lines)
