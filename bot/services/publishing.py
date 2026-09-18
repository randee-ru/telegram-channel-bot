"""Publish posts to channels."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

logger = logging.getLogger(__name__)


class PublishError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


async def publish_message(bot: Bot, channel_id: int, source: Message) -> Message:
    """Copy user's message content to the channel (text or media+caption)."""
    try:
        if source.text and not source.photo and not source.video and not source.document and not source.audio and not source.voice and not source.animation and not source.sticker and not source.video_note:
            sent = await bot.send_message(
                chat_id=channel_id,
                text=source.text,
                entities=source.entities,
                parse_mode=None,
            )
        else:
            sent = await bot.copy_message(
                chat_id=channel_id,
                from_chat_id=source.chat.id,
                message_id=source.message_id,
            )
        logger.info(
            "Published to channel_id=%s from user_id=%s msg_id=%s",
            channel_id,
            source.from_user.id if source.from_user else None,
            sent.message_id,
        )
        return sent  # type: ignore[return-value]
    except TelegramAPIError as exc:
        logger.exception("Publish failed channel_id=%s", channel_id)
        raise PublishError(
            "Не удалось опубликовать. Проверьте, что бот — админ канала "
            "с правом публикации сообщений."
        ) from exc


async def publish_text(
    bot: Bot,
    channel_id: int,
    text: str,
    *,
    parse_mode: str | None = None,
) -> Message:
    """Publish plain text (or HTML/Markdown) to a channel — for agent API / CLI."""
    try:
        sent = await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode=parse_mode,
        )
        logger.info(
            "Published text to channel_id=%s msg_id=%s",
            channel_id,
            sent.message_id,
        )
        return sent
    except TelegramAPIError as exc:
        logger.exception("Publish text failed channel_id=%s", channel_id)
        raise PublishError(
            "Не удалось опубликовать. Проверьте, что бот — админ канала "
            "с правом публикации сообщений."
        ) from exc
