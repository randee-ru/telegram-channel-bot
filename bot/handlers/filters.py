"""Shared filters."""

from aiogram.enums import ChatType
from aiogram.filters import Filter
from aiogram.types import Message


class PrivateChatFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        return message.chat.type == ChatType.PRIVATE
