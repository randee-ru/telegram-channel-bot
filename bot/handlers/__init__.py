"""Register all routers."""

from aiogram import Router

from bot.handlers.bind import router as bind_router
from bot.handlers.channels import router as channels_router
from bot.handlers.ingest import router as ingest_router
from bot.handlers.post import router as post_router
from bot.handlers.reply import router as reply_router
from bot.handlers.start import router as start_router


def setup_routers() -> Router:
    root = Router(name="root")
    # Command routers first; ingest last so /commands are not swallowed.
    root.include_router(start_router)
    root.include_router(bind_router)
    root.include_router(channels_router)
    root.include_router(post_router)
    root.include_router(reply_router)
    root.include_router(ingest_router)
    return root
