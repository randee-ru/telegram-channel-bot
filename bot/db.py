"""SQLite persistence for bound channels and optional reply targets."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from collections.abc import AsyncIterator

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BoundChannel:
    channel_id: int
    title: str | None
    username: str | None
    bound_by: int
    created_at: str


class Database:
    """Async SQLite wrapper."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
        finally:
            await db.close()

    async def init(self) -> None:
        async with self.connection() as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id INTEGER PRIMARY KEY,
                    title TEXT,
                    username TEXT,
                    bound_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS reply_targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    set_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(chat_id, message_id)
                );
                """
            )
            await db.commit()
        logger.info("Database initialized at %s", self.path)

    async def upsert_channel(
        self,
        channel_id: int,
        *,
        title: str | None,
        username: str | None,
        bound_by: int,
    ) -> BoundChannel:
        async with self.connection() as db:
            await db.execute(
                """
                INSERT INTO channels (channel_id, title, username, bound_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    title = excluded.title,
                    username = excluded.username,
                    bound_by = excluded.bound_by
                """,
                (channel_id, title, username, bound_by),
            )
            await db.commit()
            row = await (
                await db.execute(
                    "SELECT * FROM channels WHERE channel_id = ?",
                    (channel_id,),
                )
            ).fetchone()
        assert row is not None
        return BoundChannel(
            channel_id=row["channel_id"],
            title=row["title"],
            username=row["username"],
            bound_by=row["bound_by"],
            created_at=row["created_at"],
        )

    async def list_channels(self) -> list[BoundChannel]:
        async with self.connection() as db:
            cursor = await db.execute(
                "SELECT * FROM channels ORDER BY created_at ASC, channel_id ASC"
            )
            rows = await cursor.fetchall()
        return [
            BoundChannel(
                channel_id=r["channel_id"],
                title=r["title"],
                username=r["username"],
                bound_by=r["bound_by"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def get_channel(self, channel_id: int) -> BoundChannel | None:
        async with self.connection() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM channels WHERE channel_id = ?",
                    (channel_id,),
                )
            ).fetchone()
        if row is None:
            return None
        return BoundChannel(
            channel_id=row["channel_id"],
            title=row["title"],
            username=row["username"],
            bound_by=row["bound_by"],
            created_at=row["created_at"],
        )

    async def delete_channel(self, channel_id: int) -> bool:
        async with self.connection() as db:
            cursor = await db.execute(
                "DELETE FROM channels WHERE channel_id = ?",
                (channel_id,),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def set_reply_target(
        self, chat_id: int, message_id: int, set_by: int
    ) -> None:
        async with self.connection() as db:
            await db.execute(
                """
                INSERT INTO reply_targets (chat_id, message_id, set_by)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id, message_id) DO UPDATE SET
                    set_by = excluded.set_by,
                    created_at = datetime('now')
                """,
                (chat_id, message_id, set_by),
            )
            await db.commit()
