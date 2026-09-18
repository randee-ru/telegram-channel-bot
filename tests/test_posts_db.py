"""Tests for channel_posts storage and search."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from bot.db import Database


@pytest.fixture
async def db(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    await database.init()
    return database


@pytest.mark.asyncio
async def test_save_and_list_posts(db: Database):
    await db.save_channel_post(
        channel_id=-1001,
        message_id=10,
        date="2026-09-18T10:00:00+00:00",
        text="Hello world",
        caption=None,
        media_type="text",
        raw_json='{"ok":true}',
    )
    await db.save_channel_post(
        channel_id=-1001,
        message_id=11,
        date="2026-09-18T11:00:00+00:00",
        text=None,
        caption="Photo caption",
        media_type="photo",
    )
    posts = await db.list_recent_posts(-1001, limit=10)
    assert len(posts) == 2
    assert posts[0].message_id == 11
    assert posts[1].text == "Hello world"

    one = await db.get_post(-1001, 10)
    assert one is not None
    assert one.media_type == "text"
    assert await db.get_post(-1001, 999) is None


@pytest.mark.asyncio
async def test_upsert_edited_post(db: Database):
    await db.save_channel_post(
        channel_id=-1002, message_id=1, text="v1", media_type="text"
    )
    await db.save_channel_post(
        channel_id=-1002, message_id=1, text="v2 edited", media_type="text"
    )
    posts = await db.list_recent_posts(-1002)
    assert len(posts) == 1
    assert posts[0].text == "v2 edited"


@pytest.mark.asyncio
async def test_search_posts(db: Database):
    await db.save_channel_post(
        channel_id=-1003, message_id=1, text="Alpha beta gamma", media_type="text"
    )
    await db.save_channel_post(
        channel_id=-1003, message_id=2, caption="beta photo", media_type="photo"
    )
    await db.save_channel_post(
        channel_id=-1003, message_id=3, text="unrelated", media_type="text"
    )
    hits = await db.search_posts("beta", channel_id=-1003)
    assert {h.message_id for h in hits} == {1, 2}
    all_hits = await db.search_posts("beta")
    assert len(all_hits) >= 2


@pytest.mark.asyncio
async def test_default_channel_flag(db: Database):
    await db.upsert_channel(-10010, title="A", username=None, bound_by=1)
    await db.upsert_channel(-10020, title="B", username=None, bound_by=1)
    assert await db.get_default_channel() is None
    set_a = await db.set_default_channel(-10010)
    assert set_a is not None and set_a.is_default
    set_b = await db.set_default_channel(-10020)
    assert set_b is not None and set_b.is_default
    channels = {c.channel_id: c for c in await db.list_channels()}
    assert channels[-10010].is_default is False
    assert channels[-10020].is_default is True
    assert await db.set_default_channel(-99999) is None


@pytest.mark.asyncio
async def test_migrate_existing_db(tmp_path: Path):
    """Old DB without is_default / channel_posts still migrates cleanly."""
    path = tmp_path / "legacy.db"
    async with aiosqlite.connect(path) as conn:
        await conn.execute(
            """
            CREATE TABLE channels (
                channel_id INTEGER PRIMARY KEY,
                title TEXT,
                username TEXT,
                bound_by INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        await conn.execute(
            "INSERT INTO channels (channel_id, title, username, bound_by) VALUES (?,?,?,?)",
            (-1001, "Old", None, 1),
        )
        await conn.commit()

    database = Database(path)
    await database.init()
    ch = await database.get_channel(-1001)
    assert ch is not None
    assert ch.is_default is False
    await database.save_channel_post(channel_id=-1001, message_id=1, text="x")
    assert len(await database.list_recent_posts(-1001)) == 1
