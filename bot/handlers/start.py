""" /start help."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from bot.handlers.filters import PrivateChatFilter
from aiogram.types import Message

from bot.config import Settings

router = Router(name="start")

HELP_TEXT = """\
🤖 <b>Бот управления каналами</b>

Команды (только в личке, для операторов из ALLOWED_USER_IDS):

/start — эта справка
/bind — привязать канал (бот должен быть админом с правом публикации)
/channels — список привязанных каналов
/post — опубликовать пост в канал
/reply — ответить на пост канала / сообщение в обсуждении
/cancel — отменить текущий сценарий

Как привязать канал:
1. Добавьте бота в канал как администратора («Публикация сообщений»).
2. /bind и перешлите любой пост из канала <i>или</i> отправьте @username / ID.

Как получить свой Telegram ID: напишите @userinfobot.
"""


@router.message(CommandStart(), PrivateChatFilter())
@router.message(Command("help"), PrivateChatFilter())
async def cmd_start(message: Message, settings: Settings) -> None:
    extra = ""
    if message.from_user and not settings.is_allowed(message.from_user.id):
        extra = (
            "\n\n⚠️ Вы пока не в списке операторов. "
            "Администратор должен добавить ваш ID в ALLOWED_USER_IDS."
        )
    await message.answer(HELP_TEXT + extra, parse_mode="HTML")


@router.message(Command("cancel"), PrivateChatFilter())
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    await state.clear()
    if current:
        await message.answer("Текущий сценарий отменён.")
    else:
        await message.answer("Нечего отменять.")
