#!/usr/bin/env python3
"""CLI for agents (Боря / Лилу): control the Telegram channel bot via Bot API + SQLite.

Works without the local HTTP Agent API (prefers direct aiogram + aiosqlite).

Usage:
  python tools/tgctl.py channels
  python tools/tgctl.py post --text "hello" [--channel ID]
  python tools/tgctl.py posts [--channel ID] [--limit 20]
  python tools/tgctl.py search "query"
  python tools/tgctl.py info [--channel ID]
  python tools/tgctl.py set-default CHANNEL_ID
  python tools/tgctl.py reply --chat-id ID --message-id ID --text "..."
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as `python tools/tgctl.py`
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from aiogram import Bot  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.exceptions import TelegramAPIError  # noqa: E402

from bot.config import Settings, get_settings  # noqa: E402
from bot.db import Database  # noqa: E402
from bot.services.publishing import PublishError, publish_text  # noqa: E402
from bot.services.replies import ReplyError, send_reply_text  # noqa: E402


def _print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


async def _resolve_channel(
    db: Database, settings: Settings, channel_id: int | None
) -> int:
    if channel_id is not None:
        return channel_id
    default = await db.get_default_channel()
    if default is not None:
        return default.channel_id
    if settings.default_channel_id is not None:
        return settings.default_channel_id
    channels = await db.list_channels()
    if len(channels) == 1:
        return channels[0].channel_id
    raise SystemExit(
        "channel_id required: pass --channel, or set-default / DEFAULT_CHANNEL_ID"
    )


async def cmd_channels(db: Database) -> None:
    channels = await db.list_channels()
    _print_json(
        [
            {
                "channel_id": c.channel_id,
                "title": c.title,
                "username": c.username,
                "is_default": c.is_default,
                "created_at": c.created_at,
            }
            for c in channels
        ]
    )


async def cmd_set_default(db: Database, channel_id: int) -> None:
    ch = await db.set_default_channel(channel_id)
    if ch is None:
        raise SystemExit(f"Channel {channel_id} is not bound. Use /bind in Telegram first.")
    _print_json(
        {
            "ok": True,
            "channel_id": ch.channel_id,
            "title": ch.title,
            "is_default": ch.is_default,
        }
    )


async def cmd_info(bot: Bot, db: Database, settings: Settings, channel_id: int | None) -> None:
    cid = await _resolve_channel(db, settings, channel_id)
    try:
        chat = await bot.get_chat(cid)
    except TelegramAPIError as exc:
        raise SystemExit(f"Telegram error: {exc}") from exc
    member_count = None
    try:
        member_count = await bot.get_chat_member_count(cid)
    except TelegramAPIError:
        pass
    bound = await db.get_channel(cid)
    _print_json(
        {
            "channel_id": chat.id,
            "type": chat.type,
            "title": chat.title,
            "username": chat.username,
            "description": getattr(chat, "description", None),
            "member_count": member_count,
            "is_default": bound.is_default if bound else False,
            "bound": bound is not None,
        }
    )


async def cmd_post(
    bot: Bot,
    db: Database,
    settings: Settings,
    text: str,
    channel_id: int | None,
    parse_mode: str | None,
) -> None:
    cid = await _resolve_channel(db, settings, channel_id)
    try:
        sent = await publish_text(bot, cid, text, parse_mode=parse_mode)
    except PublishError as exc:
        raise SystemExit(exc.message) from exc
    await db.save_channel_post(
        channel_id=cid,
        message_id=sent.message_id,
        date=sent.date.isoformat() if sent.date else None,
        text=text,
        caption=None,
        media_type="text",
        raw_json=None,
    )
    await db.log_agent_job(
        "cli_post",
        {"channel_id": cid, "text_len": len(text)},
        {"message_id": sent.message_id},
    )
    _print_json({"ok": True, "channel_id": cid, "message_id": sent.message_id})


async def cmd_reply(
    bot: Bot,
    db: Database,
    chat_id: int,
    message_id: int,
    text: str,
    parse_mode: str | None,
) -> None:
    try:
        sent = await send_reply_text(
            bot, chat_id, message_id, text, parse_mode=parse_mode
        )
    except ReplyError as exc:
        raise SystemExit(exc.message) from exc
    await db.log_agent_job(
        "cli_reply",
        {"chat_id": chat_id, "message_id": message_id},
        {"message_id": sent.message_id},
    )
    _print_json(
        {
            "ok": True,
            "chat_id": chat_id,
            "reply_to_message_id": message_id,
            "message_id": sent.message_id,
        }
    )


async def cmd_posts(db: Database, settings: Settings, channel_id: int | None, limit: int) -> None:
    cid = channel_id
    if cid is None:
        default = await db.get_default_channel()
        if default is not None:
            cid = default.channel_id
        elif settings.default_channel_id is not None:
            cid = settings.default_channel_id
    posts = await db.list_recent_posts(cid, limit=limit)
    _print_json(
        [
            {
                "id": p.id,
                "channel_id": p.channel_id,
                "message_id": p.message_id,
                "date": p.date,
                "text": p.text,
                "caption": p.caption,
                "media_type": p.media_type,
                "created_at": p.created_at,
            }
            for p in posts
        ]
    )


async def cmd_search(
    db: Database, query: str, channel_id: int | None, limit: int
) -> None:
    posts = await db.search_posts(query, channel_id=channel_id, limit=limit)
    _print_json(
        [
            {
                "id": p.id,
                "channel_id": p.channel_id,
                "message_id": p.message_id,
                "date": p.date,
                "text": p.text,
                "caption": p.caption,
                "media_type": p.media_type,
            }
            for p in posts
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Telegram channel bot control for agents")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("channels", help="List bound channels")

    p_post = sub.add_parser("post", help="Publish text to channel")
    p_post.add_argument("--text", required=True)
    p_post.add_argument("--channel", type=int, default=None)
    p_post.add_argument("--parse-mode", default=None, choices=["HTML", "Markdown", "MarkdownV2"])

    p_posts = sub.add_parser("posts", help="List recent stored posts")
    p_posts.add_argument("--channel", type=int, default=None)
    p_posts.add_argument("--limit", type=int, default=20)

    p_search = sub.add_parser("search", help="Search stored posts")
    p_search.add_argument("query")
    p_search.add_argument("--channel", type=int, default=None)
    p_search.add_argument("--limit", type=int, default=20)

    p_info = sub.add_parser("info", help="Channel info via Bot API")
    p_info.add_argument("--channel", type=int, default=None)

    p_def = sub.add_parser("set-default", help="Set default personal channel")
    p_def.add_argument("channel_id", type=int)

    p_reply = sub.add_parser("reply", help="Reply to a message")
    p_reply.add_argument("--chat-id", type=int, required=True)
    p_reply.add_argument("--message-id", type=int, required=True)
    p_reply.add_argument("--text", required=True)
    p_reply.add_argument("--parse-mode", default=None, choices=["HTML", "Markdown", "MarkdownV2"])

    return p


async def async_main(argv: list[str] | None = None) -> None:
    # Load .env from project root when cwd differs
    import os

    os.chdir(_ROOT)
    get_settings.cache_clear()
    settings: Settings = get_settings()
    db = Database(settings.db_path)
    await db.init()

    args = build_parser().parse_args(argv)
    bot: Bot | None = None

    try:
        if args.command == "channels":
            await cmd_channels(db)
            return
        if args.command == "set-default":
            await cmd_set_default(db, args.channel_id)
            return
        if args.command == "posts":
            await cmd_posts(db, settings, args.channel, args.limit)
            return
        if args.command == "search":
            await cmd_search(db, args.query, args.channel, args.limit)
            return

        bot = Bot(
            token=settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        if args.command == "info":
            await cmd_info(bot, db, settings, args.channel)
        elif args.command == "post":
            await cmd_post(bot, db, settings, args.text, args.channel, args.parse_mode)
        elif args.command == "reply":
            await cmd_reply(
                bot, db, args.chat_id, args.message_id, args.text, args.parse_mode
            )
        else:
            raise SystemExit(f"Unknown command: {args.command}")
    finally:
        if bot is not None:
            await bot.session.close()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
