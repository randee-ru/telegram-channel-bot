""" /reply flow: target message, then reply text/media."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from bot.handlers.filters import PrivateChatFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.db import Database
from bot.services.parsing import parse_message_ref
from bot.services.replies import (
    ReplyError,
    message_ref_from_forward,
    resolve_message_ref,
    send_reply,
)

router = Router(name="reply")


class ReplyStates(StatesGroup):
    waiting_target = State()
    waiting_content = State()


@router.message(Command("reply"), PrivateChatFilter())
async def cmd_reply(message: Message, state: FSMContext) -> None:
    await state.set_state(ReplyStates.waiting_target)
    await message.answer(
        "↩️ Ответ на сообщение\n\n"
        "Перешлите целевое сообщение из канала / обсуждения "
        "или отправьте ссылку t.me / пару `chat_id message_id`.\n\n"
        "Примеры:\n"
        "• https://t.me/c/1234567890/42\n"
        "• https://t.me/channelname/42\n"
        "• <code>-1001234567890 42</code>\n\n"
        "/cancel — отмена",
        parse_mode="HTML",
    )


@router.message(Command("cancel"), StateFilter(ReplyStates))
async def cancel_reply(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ответ отменён.")


@router.message(ReplyStates.waiting_target, F.forward_from_chat | F.forward_origin)
async def reply_target_forward(message: Message, state: FSMContext, db: Database) -> None:
    ref = message_ref_from_forward(message)
    if ref is None or ref.chat_id is None:
        await message.answer(
            "Не удалось определить исходное сообщение. "
            "Перешлите пост, не скрывая автора, или вставьте ссылку t.me."
        )
        return
    await db.set_reply_target(ref.chat_id, ref.message_id, message.from_user.id)  # type: ignore[union-attr]
    await state.set_state(ReplyStates.waiting_content)
    await state.update_data(chat_id=ref.chat_id, message_id=ref.message_id)
    await message.answer(
        f"Цель: chat_id=<code>{ref.chat_id}</code>, message_id=<code>{ref.message_id}</code>.\n\n"
        "Отправьте текст или медиа для ответа.\n/cancel — отмена.",
        parse_mode="HTML",
    )


@router.message(ReplyStates.waiting_target, F.text)
async def reply_target_text(message: Message, state: FSMContext, bot, db: Database) -> None:
    if message.text and message.text.startswith("/"):
        return
    ref = parse_message_ref(message.text or "")
    if ref is None:
        await message.answer(
            "Не распознана цель. Перешлите сообщение, вставьте ссылку t.me "
            "или <code>chat_id message_id</code>. /cancel — отмена.",
            parse_mode="HTML",
        )
        return
    try:
        chat_id, message_id = await resolve_message_ref(bot, ref)
    except ReplyError as exc:
        await message.answer(f"❌ {exc.message}")
        return
    await db.set_reply_target(chat_id, message_id, message.from_user.id)  # type: ignore[union-attr]
    await state.set_state(ReplyStates.waiting_content)
    await state.update_data(chat_id=chat_id, message_id=message_id)
    await message.answer(
        f"Цель: chat_id=<code>{chat_id}</code>, message_id=<code>{message_id}</code>.\n\n"
        "Отправьте текст или медиа для ответа.\n/cancel — отмена.",
        parse_mode="HTML",
    )


@router.message(ReplyStates.waiting_target)
async def reply_target_invalid(message: Message) -> None:
    await message.answer(
        "Перешлите сообщение или отправьте ссылку / chat_id+message_id. /cancel — отмена."
    )


@router.message(ReplyStates.waiting_content)
async def reply_content(message: Message, state: FSMContext, bot) -> None:
    if message.text and message.text.startswith("/"):
        await message.answer("Отправьте текст ответа или /cancel.")
        return
    data = await state.get_data()
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    if chat_id is None or message_id is None:
        await state.clear()
        await message.answer("Сессия сброшена. Начните снова с /reply.")
        return
    try:
        sent = await send_reply(bot, int(chat_id), int(message_id), message)
    except ReplyError as exc:
        await message.answer(f"❌ {exc.message}")
        return
    await state.clear()
    await message.answer(
        f"✅ Ответ отправлен (message_id={sent.message_id}).",
    )
