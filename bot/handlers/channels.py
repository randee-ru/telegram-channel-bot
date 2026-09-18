""" /channels list."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from bot.handlers.filters import PrivateChatFilter
from aiogram.types import Message

from bot.db import Database
from bot.services.channels import channels_list_text

router = Router(name="channels")


@router.message(Command("channels"), PrivateChatFilter())
async def cmd_channels(message: Message, db: Database) -> None:
    channels = await db.list_channels()
    await message.answer(channels_list_text(channels), parse_mode="HTML")
