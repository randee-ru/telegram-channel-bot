"""Restrict write commands to ALLOWED_USER_IDS."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import Settings

logger = logging.getLogger(__name__)

REJECT_TEXT = "⛔ Доступ запрещён. Вы не в списке операторов бота."


class AllowlistMiddleware(BaseMiddleware):
    """Reject non-allowlisted users for private write interactions."""

    def __init__(self, settings: Settings, *, public_commands: frozenset[str] | None = None) -> None:
        self.settings = settings
        # /start is allowed for everyone (shows help + rejection context)
        self.public_commands = public_commands or frozenset({"start"})

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        # Allow /start always
        if isinstance(event, Message) and event.text:
            cmd = event.text.split()[0].lstrip("/").split("@")[0].lower()
            if cmd in self.public_commands:
                return await handler(event, data)

        if self.settings.is_allowed(user.id):
            return await handler(event, data)

        logger.warning("Rejected user_id=%s (not in allowlist)", user.id)
        if isinstance(event, Message):
            await event.answer(REJECT_TEXT)
        elif isinstance(event, CallbackQuery):
            await event.answer(REJECT_TEXT, show_alert=True)
        return None
