"""Tests for watched_chats (news sources) and feed helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.db import Database
from bot.handlers.ingest import _has_ingestible_content, _is_not_bot_command, _media_type


@pytest.fixture
async def db(tmp_path: Path):
    database = Database(tmp_path / "watched.db")
    await database.init()
    return database


@pytest.mark.asyncio
async def test_upsert_list_touch_deactivate(db: Database):
    w = await db.upsert_watched_chat(
        -100501,
        chat_type="supergroup",
        title="News Group",
        username="news_grp",
        role="news_source",
    )
    assert w.chat_id == -100501
    assert w.chat_type == "supergroup"
    assert w.is_active is True
    assert w.last_message_at is None

    await db.touch_last_message(-100501, "2026-09-18T12:00:00+00:00")
    again = await db.get_watched_chat(-100501)
    assert again is not None
    assert again.last_message_at == "2026-09-18T12:00:00+00:00"

    await db.upsert_watched_chat(
        -100502,
        chat_type="channel",
        title="Other",
        username=None,
        role="news_source",
    )
    active = await db.list_watched_chats(role="news_source")
    assert {c.chat_id for c in active} == {-100501, -100502}

    assert await db.deactivate_watched_chat(-100501) is True
    active2 = await db.list_watched_chats()
    assert {c.chat_id for c in active2} == {-100502}
    all_chats = await db.list_watched_chats(active_only=False)
    assert len(all_chats) == 2
    inactive = await db.get_watched_chat(-100501)
    assert inactive is not None and inactive.is_active is False

    # Re-join reactivates
    re = await db.upsert_watched_chat(
        -100501,
        chat_type="supergroup",
        title="News Group",
        username="news_grp",
        is_active=True,
    )
    assert re.is_active is True


@pytest.mark.asyncio
async def test_save_post_with_watched_workflow(db: Database):
    """Mirrors ingest: save post + upsert watched + touch last_message."""
    await db.save_channel_post(
        channel_id=-100777,
        message_id=1,
        date="2026-09-18T15:00:00+00:00",
        text="Breaking",
        media_type="text",
    )
    await db.upsert_watched_chat(
        -100777,
        chat_type="channel",
        title="Src",
        username="src",
        role="news_source",
    )
    await db.touch_last_message(-100777, "2026-09-18T15:00:00+00:00")
    w = await db.get_watched_chat(-100777)
    assert w is not None
    assert w.last_message_at == "2026-09-18T15:00:00+00:00"
    posts = await db.list_recent_posts(-100777)
    assert len(posts) == 1


@pytest.mark.asyncio
async def test_list_feed_excludes_own(db: Database):
    await db.upsert_channel(-1002392010070, title="Own", username="randee_create", bound_by=1)
    await db.set_default_channel(-1002392010070)
    await db.save_channel_post(
        channel_id=-1002392010070, message_id=1, text="own post", media_type="text"
    )
    await db.save_channel_post(
        channel_id=-100888, message_id=2, text="news post", media_type="text"
    )

    feed = await db.list_feed(limit=10, exclude_chat_ids=[-1002392010070])
    assert len(feed) == 1
    assert feed[0].text == "news post"

    all_feed = await db.list_feed(limit=10)
    assert len(all_feed) == 2

    one = await db.list_feed(limit=10, chat_id=-100888)
    assert len(one) == 1


def test_ingest_helpers_skip_service_and_commands():
    class _FakeChat:
        type = "supergroup"
        id = -1001
        title = "G"
        username = None

    class _FakeMsg:
        def __init__(self, **kwargs):
            self.text = kwargs.get("text")
            self.caption = kwargs.get("caption")
            self.photo = kwargs.get("photo")
            self.video = None
            self.document = None
            self.audio = None
            self.voice = None
            self.animation = None
            self.sticker = None
            self.video_note = None
            self.poll = None
            self.chat = _FakeChat()
            self.message_id = 1
            self.date = None

    assert _is_not_bot_command(_FakeMsg(text="/bind")) is False
    assert _is_not_bot_command(_FakeMsg(text="hello")) is True
    assert _is_not_bot_command(_FakeMsg(photo=[object()])) is True

    assert _has_ingestible_content(_FakeMsg(text="hi")) is True
    assert _has_ingestible_content(_FakeMsg(caption="cap", photo=[object()])) is True
    assert _has_ingestible_content(_FakeMsg()) is False
    assert _media_type(_FakeMsg(text="x")) == "text"
