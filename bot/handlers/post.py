""" /post flow: choose channel, then send content."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from bot.handlers.filters import PrivateChatFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import Settings
from bot.db import Database
from bot.services.parsing import format_channel_label
from bot.services.publishing import PublishError, publish_message

router = Router(name="post")


class PostStates(StatesGroup):
    choosing_channel = State()
    waiting_content = State()


def _channel_keyboard(channels: list, default_id: int | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for ch in channels:
        label = ch.title or ch.username or str(ch.channel_id)
        if default_id is not None and ch.channel_id == default_id:
            label = f"⭐ {label}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=f"post_ch:{ch.channel_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="post_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("post"), PrivateChatFilter())
async def cmd_post(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    channels = await db.list_channels()
    default_id = settings.default_channel_id

    if not channels and default_id is None:
        await message.answer("Нет каналов. Сначала /bind или задайте DEFAULT_CHANNEL_ID.")
        return

    if len(channels) == 1 and default_id is None:
        ch = channels[0]
        await state.set_state(PostStates.waiting_content)
        await state.update_data(channel_id=ch.channel_id)
        label = format_channel_label(ch.channel_id, ch.title, ch.username)
        await message.answer(
            f"📝 Публикация в {label}\n\nОтправьте текст или медиа с подписью.\n/cancel — отмена.",
            parse_mode="HTML",
        )
        return

    if not channels and default_id is not None:
        await state.set_state(PostStates.waiting_content)
        await state.update_data(channel_id=default_id)
        await message.answer(
            f"📝 Публикация в канал <code>{default_id}</code> (DEFAULT_CHANNEL_ID).\n\n"
            "Отправьте текст или медиа с подписью.\n/cancel — отмена.",
            parse_mode="HTML",
        )
        return

    await state.set_state(PostStates.choosing_channel)
    await message.answer(
        "Выберите канал для публикации:",
        reply_markup=_channel_keyboard(channels, default_id),
    )


@router.callback_query(PostStates.choosing_channel, F.data == "post_cancel")
async def post_cancel_cb(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await query.message.edit_text("Публикация отменена.")  # type: ignore[union-attr]
    await query.answer()


@router.callback_query(PostStates.choosing_channel, F.data.startswith("post_ch:"))
async def post_choose_cb(query: CallbackQuery, state: FSMContext, db: Database) -> None:
    channel_id = int(query.data.split(":", 1)[1])  # type: ignore[union-attr]
    ch = await db.get_channel(channel_id)
    await state.set_state(PostStates.waiting_content)
    await state.update_data(channel_id=channel_id)
    label = (
        format_channel_label(ch.channel_id, ch.title, ch.username)
        if ch
        else f"<code>{channel_id}</code>"
    )
    await query.message.edit_text(  # type: ignore[union-attr]
        f"📝 Публикация в {label}\n\nОтправьте текст или медиа с подписью.\n/cancel — отмена.",
        parse_mode="HTML",
    )
    await query.answer()


@router.message(Command("cancel"), StateFilter(PostStates))
async def cancel_post(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Публикация отменена.")


@router.message(PostStates.waiting_content)
async def post_content(message: Message, state: FSMContext, bot) -> None:
    if message.text and message.text.startswith("/"):
        await message.answer("Сначала отправьте контент поста или /cancel.")
        return
    data = await state.get_data()
    channel_id = data.get("channel_id")
    if channel_id is None:
        await state.clear()
        await message.answer("Сессия сброшена. Начните снова с /post.")
        return
    try:
        sent = await publish_message(bot, int(channel_id), message)
    except PublishError as exc:
        await message.answer(f"❌ {exc.message}")
        return
    await state.clear()
    await message.answer(
        f"✅ Опубликовано в канал <code>{channel_id}</code> (message_id={sent.message_id}).",
        parse_mode="HTML",
    )
