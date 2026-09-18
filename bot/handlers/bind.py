""" /bind channel flow."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from bot.handlers.filters import PrivateChatFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.db import Database
from bot.services.channels import (
    ChannelBindError,
    bind_from_forward,
    bind_from_text,
)
from bot.services.parsing import format_channel_label

router = Router(name="bind")


class BindStates(StatesGroup):
    waiting_channel = State()


@router.message(Command("bind"), PrivateChatFilter())
async def cmd_bind(message: Message, state: FSMContext) -> None:
    await state.set_state(BindStates.waiting_channel)
    await message.answer(
        "🔗 Привязка канала\n\n"
        "Перешлите пост из канала (не скрывая автора) или отправьте "
        "@username / числовой ID канала.\n\n"
        "Бот уже должен быть администратором с правом «Публикация сообщений».\n"
        "Отмена: /cancel"
    )


@router.message(Command("cancel"), StateFilter(BindStates))
async def cancel_bind(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Привязка отменена.")


@router.message(BindStates.waiting_channel, F.forward_from_chat | F.forward_origin)
async def bind_forwarded(message: Message, state: FSMContext, bot, db: Database) -> None:
    try:
        bound = await bind_from_forward(bot, db, message, message.from_user.id)  # type: ignore[union-attr]
    except ChannelBindError as exc:
        await message.answer(f"❌ {exc.message}")
        return
    await state.clear()
    label = format_channel_label(bound.channel_id, bound.title, bound.username)
    await message.answer(f"✅ Канал привязан: {label}", parse_mode="HTML")


@router.message(BindStates.waiting_channel, F.text)
async def bind_text(message: Message, state: FSMContext, bot, db: Database) -> None:
    if message.text and message.text.startswith("/"):
        return
    try:
        bound = await bind_from_text(bot, db, message.text or "", message.from_user.id)  # type: ignore[union-attr]
    except ChannelBindError as exc:
        await message.answer(f"❌ {exc.message}")
        return
    await state.clear()
    label = format_channel_label(bound.channel_id, bound.title, bound.username)
    await message.answer(f"✅ Канал привязан: {label}", parse_mode="HTML")


@router.message(BindStates.waiting_channel)
async def bind_invalid(message: Message) -> None:
    await message.answer(
        "Отправьте пересланный пост из канала, @username или числовой ID. /cancel — отмена."
    )
