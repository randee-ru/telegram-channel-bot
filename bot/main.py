"""Application entrypoint."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiohttp.web import AppRunner
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.agent_api import start_agent_api
from bot.config import Settings, get_settings
from bot.db import Database
from bot.handlers import setup_routers
from bot.middlewares.allowlist import AllowlistMiddleware


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )
    # Avoid leaking request bodies / tokens from HTTP libs
    logging.getLogger("aiogram.event").setLevel(logging.INFO)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


async def on_startup(bot: Bot, db: Database) -> None:
    await db.init()
    me = await bot.get_me()
    logging.getLogger(__name__).info(
        "Bot started as @%s (id=%s). Secrets are not logged.",
        me.username,
        me.id,
    )


async def main() -> None:
    setup_logging()
    settings: Settings = get_settings()
    if not settings.allowed_ids:
        logging.getLogger(__name__).warning(
            "ALLOWED_USER_IDS is empty — all write commands will be rejected."
        )

    db = Database(settings.db_path)
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp["settings"] = settings
    dp["db"] = db

    # Inject settings/db into handlers via middleware-style workflow data
    @dp.update.outer_middleware()
    async def inject_deps(handler, event, data):
        data["settings"] = settings
        data["db"] = db
        return await handler(event, data)

    dp.message.middleware(AllowlistMiddleware(settings))
    dp.callback_query.middleware(AllowlistMiddleware(settings))

    dp.include_router(setup_routers())

    await on_startup(bot, db)
    api_runner: AppRunner | None = await start_agent_api(bot, db, settings)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if api_runner is not None:
            await api_runner.cleanup()
        await bot.session.close()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
