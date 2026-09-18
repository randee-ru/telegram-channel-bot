"""Local-only HTTP API for Grok Bot agents (Боря / Лилу)."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.config import Settings
from bot.db import BoundChannel, ChannelPost, Database
from bot.services.publishing import PublishError, publish_text
from bot.services.replies import ReplyError, send_reply_text

logger = logging.getLogger(__name__)

BOT_KEY = web.AppKey("bot", Bot)
DB_KEY = web.AppKey("db", Database)
SETTINGS_KEY = web.AppKey("settings", Settings)


def _channel_dict(ch: BoundChannel) -> dict[str, Any]:
    return {
        "channel_id": ch.channel_id,
        "title": ch.title,
        "username": ch.username,
        "bound_by": ch.bound_by,
        "created_at": ch.created_at,
        "is_default": ch.is_default,
    }


def _post_dict(post: ChannelPost, *, include_raw: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": post.id,
        "channel_id": post.channel_id,
        "message_id": post.message_id,
        "date": post.date,
        "text": post.text,
        "caption": post.caption,
        "media_type": post.media_type,
        "created_at": post.created_at,
    }
    if include_raw:
        data["raw_json"] = post.raw_json
    return data


def _error(status: int, code: str, message: str) -> web.Response:
    return web.json_response(
        {"ok": False, "error": {"code": code, "message": message}},
        status=status,
    )


def _ok(payload: dict[str, Any] | list[Any] | None = None, **extra: Any) -> web.Response:
    body: dict[str, Any] = {"ok": True}
    if payload is not None:
        body["data"] = payload
    body.update(extra)
    return web.json_response(body)


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if request.path == "/health":
        return await handler(request)
    settings: Settings = request.app[SETTINGS_KEY]
    expected = settings.agent_api_token
    if not expected:
        return _error(503, "api_disabled", "Agent API is disabled")

    auth = request.headers.get("Authorization", "")
    token: str | None = None
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if not token:
        token = request.headers.get("X-Agent-Token")
    if not token or token != expected:
        return _error(401, "unauthorized", "Invalid or missing agent token")
    return await handler(request)


async def health(_request: web.Request) -> web.Response:
    return _ok({"status": "up"})


async def list_channels(request: web.Request) -> web.Response:
    db: Database = request.app[DB_KEY]
    channels = await db.list_channels()
    return _ok([_channel_dict(c) for c in channels])


async def set_default_channel(request: web.Request) -> web.Response:
    db: Database = request.app[DB_KEY]
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _error(400, "bad_json", "Expected JSON body")
    channel_id = body.get("channel_id")
    if channel_id is None:
        return _error(400, "missing_field", "channel_id is required")
    try:
        channel_id = int(channel_id)
    except (TypeError, ValueError):
        return _error(400, "invalid_field", "channel_id must be an integer")
    ch = await db.set_default_channel(channel_id)
    if ch is None:
        return _error(404, "not_found", f"Channel {channel_id} is not bound")
    await db.log_agent_job("set_default", {"channel_id": channel_id}, _channel_dict(ch))
    return _ok(_channel_dict(ch))


async def channel_info(request: web.Request) -> web.Response:
    bot: Bot = request.app[BOT_KEY]
    db: Database = request.app[DB_KEY]
    settings: Settings = request.app[SETTINGS_KEY]
    raw = request.rel_url.query.get("channel_id")
    channel_id: int | None = None
    if raw:
        try:
            channel_id = int(raw)
        except ValueError:
            return _error(400, "invalid_field", "channel_id must be an integer")
    if channel_id is None:
        default = await db.get_default_channel()
        if default is not None:
            channel_id = default.channel_id
        elif settings.default_channel_id is not None:
            channel_id = settings.default_channel_id
        else:
            return _error(400, "missing_field", "channel_id required (no default set)")
    try:
        chat = await bot.get_chat(channel_id)
    except TelegramAPIError as exc:
        return _error(502, "telegram_error", str(exc))
    member_count: int | None = None
    try:
        member_count = await bot.get_chat_member_count(channel_id)
    except TelegramAPIError:
        member_count = None
    bound = await db.get_channel(channel_id)
    data = {
        "channel_id": chat.id,
        "type": chat.type,
        "title": chat.title,
        "username": chat.username,
        "description": getattr(chat, "description", None),
        "member_count": member_count,
        "bound": _channel_dict(bound) if bound else None,
    }
    return _ok(data)


async def resolve_channel_id(
    db: Database, settings: Settings, body: dict[str, Any]
) -> int | web.Response:
    if body.get("channel_id") is not None:
        try:
            return int(body["channel_id"])
        except (TypeError, ValueError):
            return _error(400, "invalid_field", "channel_id must be an integer")
    default = await db.get_default_channel()
    if default is not None:
        return default.channel_id
    if settings.default_channel_id is not None:
        return settings.default_channel_id
    channels = await db.list_channels()
    if len(channels) == 1:
        return channels[0].channel_id
    return _error(
        400,
        "missing_field",
        "channel_id required (set default via POST /channels/default or bind one channel)",
    )


async def post_to_channel(request: web.Request) -> web.Response:
    bot: Bot = request.app[BOT_KEY]
    db: Database = request.app[DB_KEY]
    settings: Settings = request.app[SETTINGS_KEY]
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _error(400, "bad_json", "Expected JSON body")
    text = body.get("text")
    if not text or not str(text).strip():
        return _error(400, "missing_field", "text is required")
    resolved = await resolve_channel_id(db, settings, body)
    if isinstance(resolved, web.Response):
        return resolved
    channel_id = resolved
    parse_mode = body.get("parse_mode")
    try:
        sent = await publish_text(
            bot, channel_id, str(text), parse_mode=parse_mode
        )
    except PublishError as exc:
        await db.log_agent_job(
            "post",
            {"channel_id": channel_id, "text_len": len(str(text))},
            {"ok": False, "error": exc.message},
        )
        return _error(502, "publish_failed", exc.message)
    result = {
        "channel_id": channel_id,
        "message_id": sent.message_id,
        "date": sent.date.isoformat() if sent.date else None,
    }
    await db.log_agent_job(
        "post",
        {"channel_id": channel_id, "text_len": len(str(text))},
        result,
    )
    # Persist our own post so agents can read it back immediately
    await db.save_channel_post(
        channel_id=channel_id,
        message_id=sent.message_id,
        date=sent.date.isoformat() if sent.date else None,
        text=str(text),
        caption=None,
        media_type="text",
        raw_json=None,
    )
    return _ok(result)


async def reply_to_message(request: web.Request) -> web.Response:
    bot: Bot = request.app[BOT_KEY]
    db: Database = request.app[DB_KEY]
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _error(400, "bad_json", "Expected JSON body")
    try:
        chat_id = int(body["chat_id"])
        message_id = int(body["message_id"])
    except (KeyError, TypeError, ValueError):
        return _error(400, "missing_field", "chat_id and message_id are required integers")
    text = body.get("text")
    if not text or not str(text).strip():
        return _error(400, "missing_field", "text is required")
    parse_mode = body.get("parse_mode")
    try:
        sent = await send_reply_text(
            bot, chat_id, message_id, str(text), parse_mode=parse_mode
        )
    except ReplyError as exc:
        await db.log_agent_job(
            "reply",
            {"chat_id": chat_id, "message_id": message_id},
            {"ok": False, "error": exc.message},
        )
        return _error(502, "reply_failed", exc.message)
    result = {
        "chat_id": chat_id,
        "reply_to_message_id": message_id,
        "message_id": sent.message_id,
    }
    await db.log_agent_job("reply", {"chat_id": chat_id, "message_id": message_id}, result)
    return _ok(result)


async def list_posts(request: web.Request) -> web.Response:
    db: Database = request.app[DB_KEY]
    raw_ch = request.rel_url.query.get("channel_id")
    channel_id: int | None = None
    if raw_ch:
        try:
            channel_id = int(raw_ch)
        except ValueError:
            return _error(400, "invalid_field", "channel_id must be an integer")
    limit = 20
    if request.rel_url.query.get("limit"):
        try:
            limit = int(request.rel_url.query["limit"])
        except ValueError:
            return _error(400, "invalid_field", "limit must be an integer")
    if channel_id is None:
        default = await db.get_default_channel()
        if default is not None:
            channel_id = default.channel_id
    posts = await db.list_recent_posts(channel_id, limit=limit)
    return _ok([_post_dict(p) for p in posts])


async def search_posts(request: web.Request) -> web.Response:
    db: Database = request.app[DB_KEY]
    q = request.rel_url.query.get("q", "").strip()
    if not q:
        return _error(400, "missing_field", "q is required")
    raw_ch = request.rel_url.query.get("channel_id")
    channel_id: int | None = None
    if raw_ch:
        try:
            channel_id = int(raw_ch)
        except ValueError:
            return _error(400, "invalid_field", "channel_id must be an integer")
    limit = 20
    if request.rel_url.query.get("limit"):
        try:
            limit = int(request.rel_url.query["limit"])
        except ValueError:
            return _error(400, "invalid_field", "limit must be an integer")
    posts = await db.search_posts(q, channel_id=channel_id, limit=limit)
    return _ok([_post_dict(p) for p in posts])


def create_app(bot: Bot, db: Database, settings: Settings) -> web.Application:
    app = web.Application(middlewares=[auth_middleware])
    app[BOT_KEY] = bot
    app[DB_KEY] = db
    app[SETTINGS_KEY] = settings
    app.router.add_get("/health", health)
    app.router.add_get("/channels", list_channels)
    app.router.add_post("/channels/default", set_default_channel)
    app.router.add_get("/channels/info", channel_info)
    app.router.add_post("/post", post_to_channel)
    app.router.add_post("/reply", reply_to_message)
    app.router.add_get("/posts", list_posts)
    app.router.add_get("/posts/search", search_posts)
    return app


async def start_agent_api(
    bot: Bot, db: Database, settings: Settings
) -> web.AppRunner | None:
    """Start local Agent API if AGENT_API_TOKEN is set. Returns runner or None."""
    if not settings.agent_api_enabled:
        logger.warning(
            "AGENT_API_TOKEN unset — Agent HTTP API is disabled "
            "(CLI via Bot+SQLite still works)."
        )
        return None
    app = create_app(bot, db, settings)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(
        runner,
        host=settings.agent_api_host,
        port=settings.agent_api_port,
    )
    await site.start()
    logger.info(
        "Agent API listening on http://%s:%s (auth required except /health)",
        settings.agent_api_host,
        settings.agent_api_port,
    )
    return runner
