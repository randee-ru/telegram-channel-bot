"""Capture channel posts and group/supergroup messages into SQLite for agents."""

from __future__ import annotations

import logging
from datetime import timezone

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import ChatMemberUpdated, Message

from bot.db import Database

logger = logging.getLogger(__name__)

router = Router(name="ingest")

_ACTIVE_MEMBER_STATUSES = frozenset(
    {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.RESTRICTED,
    }
)
_LEFT_STATUSES = frozenset(
    {
        ChatMemberStatus.LEFT,
        ChatMemberStatus.KICKED,
    }
)


def _media_type(message: Message) -> str | None:
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.document:
        return "document"
    if message.audio:
        return "audio"
    if message.voice:
        return "voice"
    if message.animation:
        return "animation"
    if message.sticker:
        return "sticker"
    if message.video_note:
        return "video_note"
    if message.poll:
        return "poll"
    if message.text:
        return "text"
    return None


def _has_ingestible_content(message: Message) -> bool:
    """Skip pure service messages (join/leave/title change) with no payload."""
    if message.text or message.caption:
        return True
    media = _media_type(message)
    return media is not None and media != "text"


def _is_not_bot_command(message: Message) -> bool:
    """True when message is not a slash-command (so command handlers can match)."""
    return not (bool(message.text) and message.text.startswith("/"))


def _message_date_iso(message: Message) -> str | None:
    if message.date is None:
        return None
    dt = message.date
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _chat_type_str(message: Message) -> str:
    chat_type = message.chat.type
    if isinstance(chat_type, ChatType):
        return chat_type.value
    return str(chat_type)


async def _persist(message: Message, db: Database, *, source: str) -> None:
    if not _has_ingestible_content(message):
        logger.debug(
            "Skip empty/service message chat_id=%s message_id=%s source=%s",
            message.chat.id,
            message.message_id,
            source,
        )
        return

    chat = message.chat
    try:
        raw = message.model_dump_json(exclude_none=True)
    except Exception:  # noqa: BLE001 — best-effort snapshot
        raw = None

    date_iso = _message_date_iso(message)
    await db.save_channel_post(
        channel_id=chat.id,
        message_id=message.message_id,
        date=date_iso,
        text=message.text,
        caption=message.caption,
        media_type=_media_type(message),
        raw_json=raw,
    )
    await db.upsert_watched_chat(
        chat.id,
        chat_type=_chat_type_str(message),
        title=chat.title,
        username=chat.username,
        role="news_source",
        is_active=True,
    )
    await db.touch_last_message(chat.id, date_iso)
    logger.info(
        "Ingested %s chat_id=%s message_id=%s media=%s",
        source,
        chat.id,
        message.message_id,
        _media_type(message),
    )


@router.channel_post()
async def on_channel_post(message: Message, db: Database) -> None:
    await _persist(message, db, source="channel_post")


@router.edited_channel_post()
async def on_edited_channel_post(message: Message, db: Database) -> None:
    await _persist(message, db, source="edited_channel_post")


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    _is_not_bot_command,
)
async def on_group_message(message: Message, db: Database) -> None:
    """Ingest all group/supergroup messages (including discussion auto-forwards)."""
    source = (
        "discussion_auto_forward"
        if message.is_automatic_forward
        else "group_message"
    )
    await _persist(message, db, source=source)


@router.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated, db: Database) -> None:
    """Track bot join/leave for watched news sources."""
    chat = event.chat
    if chat.type not in {
        ChatType.CHANNEL,
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    }:
        return

    chat_type = chat.type.value if isinstance(chat.type, ChatType) else str(chat.type)
    new_status = event.new_chat_member.status
    old_status = event.old_chat_member.status

    if new_status in _ACTIVE_MEMBER_STATUSES:
        await db.upsert_watched_chat(
            chat.id,
            chat_type=chat_type,
            title=chat.title,
            username=chat.username,
            role="news_source",
            is_active=True,
        )
        logger.info(
            "Bot joined/activated in chat_id=%s type=%s title=%r (status %s→%s)",
            chat.id,
            chat_type,
            chat.title,
            old_status,
            new_status,
        )
    elif new_status in _LEFT_STATUSES:
        existed = await db.get_watched_chat(chat.id)
        if existed is None:
            # Record as inactive so we know we were removed
            await db.upsert_watched_chat(
                chat.id,
                chat_type=chat_type,
                title=chat.title,
                username=chat.username,
                role="news_source",
                is_active=False,
            )
        else:
            await db.deactivate_watched_chat(chat.id)
        logger.info(
            "Bot left/kicked from chat_id=%s type=%s (status %s→%s)",
            chat.id,
            chat_type,
            old_status,
            new_status,
        )
