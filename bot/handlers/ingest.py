"""Capture channel_post / edited_channel_post (and optional discussion messages) into SQLite."""

from __future__ import annotations

import logging
from datetime import timezone

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from bot.db import Database

logger = logging.getLogger(__name__)

router = Router(name="ingest")


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


def _message_date_iso(message: Message) -> str | None:
    if message.date is None:
        return None
    dt = message.date
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


async def _persist(message: Message, db: Database, *, source: str) -> None:
    chat = message.chat
    try:
        raw = message.model_dump_json(exclude_none=True)
    except Exception:  # noqa: BLE001 — best-effort snapshot
        raw = None
    await db.save_channel_post(
        channel_id=chat.id,
        message_id=message.message_id,
        date=_message_date_iso(message),
        text=message.text,
        caption=message.caption,
        media_type=_media_type(message),
        raw_json=raw,
    )
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


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), F.is_automatic_forward)
async def on_discussion_auto_forward(message: Message, db: Database) -> None:
    """Optional: store discussion-group mirrors of channel posts."""
    await _persist(message, db, source="discussion_auto_forward")
