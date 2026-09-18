"""Database unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.db import Database


@pytest.fixture
async def db(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    await database.init()
    return database


@pytest.mark.asyncio
async def test_upsert_and_list(db: Database):
    await db.upsert_channel(
        -100111,
        title="News",
        username="news_channel",
        bound_by=42,
    )
    await db.upsert_channel(
        -100222,
        title="Alerts",
        username=None,
        bound_by=42,
    )
    channels = await db.list_channels()
    assert len(channels) == 2
    by_id = {c.channel_id: c for c in channels}
    assert by_id[-100111].username == "news_channel"
    assert by_id[-100222].title == "Alerts"

    # Update existing
    updated = await db.upsert_channel(
        -100111,
        title="News Renamed",
        username="news_channel",
        bound_by=99,
    )
    assert updated.title == "News Renamed"
    assert updated.bound_by == 99
    assert len(await db.list_channels()) == 2


@pytest.mark.asyncio
async def test_get_and_delete(db: Database):
    await db.upsert_channel(-1001, title="X", username=None, bound_by=1)
    ch = await db.get_channel(-1001)
    assert ch is not None
    assert ch.title == "X"
    assert await db.get_channel(-9999) is None
    assert await db.delete_channel(-1001) is True
    assert await db.delete_channel(-1001) is False


@pytest.mark.asyncio
async def test_reply_target(db: Database):
    await db.set_reply_target(-1001, 55, set_by=7)
    await db.set_reply_target(-1001, 55, set_by=8)  # upsert
