"""Reply to channel / discussion messages."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

from bot.services.parsing import MessageRef

logger = logging.getLogger(__name__)


class ReplyError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


async def resolve_message_ref(bot: Bot, ref: MessageRef) -> tuple[int, int]:
    if ref.chat_id is not None:
        return ref.chat_id, ref.message_id
    assert ref.username
    try:
        chat = await bot.get_chat(f"@{ref.username}")
    except TelegramAPIError as exc:
        raise ReplyError(f"Не удалось найти чат @{ref.username}.") from exc
    return chat.id, ref.message_id


def message_ref_from_forward(message: Message) -> MessageRef | None:
    """Build MessageRef from a forwarded message."""
    if message.forward_from_chat is not None and message.forward_from_message_id is not None:
        return MessageRef(
            chat_id=message.forward_from_chat.id,
            username=message.forward_from_chat.username,
            message_id=message.forward_from_message_id,
        )
    fo = getattr(message, "forward_origin", None)
    if fo is not None:
        chat = getattr(fo, "chat", None)
        msg_id = getattr(fo, "message_id", None)
        if chat is not None and msg_id is not None:
            return MessageRef(
                chat_id=chat.id,
                username=getattr(chat, "username", None),
                message_id=int(msg_id),
            )
    return None


async def send_reply(
    bot: Bot,
    chat_id: int,
    reply_to_message_id: int,
    source: Message,
) -> Message:
    try:
        if source.text and not (
            source.photo
            or source.video
            or source.document
            or source.audio
            or source.voice
            or source.animation
            or source.sticker
        ):
            sent = await bot.send_message(
                chat_id=chat_id,
                text=source.text,
                entities=source.entities,
                reply_to_message_id=reply_to_message_id,
                parse_mode=None,
            )
        else:
            sent = await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=source.chat.id,
                message_id=source.message_id,
                reply_to_message_id=reply_to_message_id,
            )
        logger.info(
            "Replied in chat_id=%s to message_id=%s new_msg_id=%s",
            chat_id,
            reply_to_message_id,
            getattr(sent, "message_id", None),
        )
        return sent  # type: ignore[return-value]
    except TelegramAPIError as exc:
        logger.exception("Reply failed chat_id=%s message_id=%s", chat_id, reply_to_message_id)
        raise ReplyError(
            "Не удалось ответить. Для постов канала нужен доступ бота к каналу; "
            "для обсуждений — бот должен быть в группе обсуждений."
        ) from exc


async def send_reply_text(
    bot: Bot,
    chat_id: int,
    reply_to_message_id: int,
    text: str,
    *,
    parse_mode: str | None = None,
) -> Message:
    """Reply with plain text — for agent API / CLI."""
    try:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
            parse_mode=parse_mode,
        )
        logger.info(
            "Replied text in chat_id=%s to message_id=%s new_msg_id=%s",
            chat_id,
            reply_to_message_id,
            sent.message_id,
        )
        return sent
    except TelegramAPIError as exc:
        logger.exception(
            "Reply text failed chat_id=%s message_id=%s", chat_id, reply_to_message_id
        )
        raise ReplyError(
            "Не удалось ответить. Для постов канала нужен доступ бота к каналу; "
            "для обсуждений — бот должен быть в группе обсуждений."
        ) from exc
