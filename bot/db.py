"""SQLite persistence for bound channels, watched sources, posts, and agent audit."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BoundChannel:
    channel_id: int
    title: str | None
    username: str | None
    bound_by: int
    created_at: str
    is_default: bool = False


@dataclass(frozen=True, slots=True)
class ChannelPost:
    id: int
    channel_id: int
    message_id: int
    date: str | None
    text: str | None
    caption: str | None
    media_type: str | None
    raw_json: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class WatchedChat:
    chat_id: int
    chat_type: str
    title: str | None
    username: str | None
    role: str
    added_at: str
    last_message_at: str | None
    is_active: bool = True


def _row_to_channel(row: aiosqlite.Row) -> BoundChannel:
    keys = row.keys()
    return BoundChannel(
        channel_id=row["channel_id"],
        title=row["title"],
        username=row["username"],
        bound_by=row["bound_by"],
        created_at=row["created_at"],
        is_default=bool(row["is_default"]) if "is_default" in keys else False,
    )


def _row_to_post(row: aiosqlite.Row) -> ChannelPost:
    return ChannelPost(
        id=row["id"],
        channel_id=row["channel_id"],
        message_id=row["message_id"],
        date=row["date"],
        text=row["text"],
        caption=row["caption"],
        media_type=row["media_type"],
        raw_json=row["raw_json"],
        created_at=row["created_at"],
    )


def _row_to_watched(row: aiosqlite.Row) -> WatchedChat:
    return WatchedChat(
        chat_id=row["chat_id"],
        chat_type=row["chat_type"],
        title=row["title"],
        username=row["username"],
        role=row["role"],
        added_at=row["added_at"],
        last_message_at=row["last_message_at"],
        is_active=bool(row["is_active"]),
    )


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
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    is_default INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS reply_targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    set_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(chat_id, message_id)
                );

                CREATE TABLE IF NOT EXISTS channel_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    date TEXT,
                    text TEXT,
                    caption TEXT,
                    media_type TEXT,
                    raw_json TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(channel_id, message_id)
                );

                CREATE TABLE IF NOT EXISTS watched_chats (
                    chat_id INTEGER PRIMARY KEY,
                    chat_type TEXT NOT NULL,
                    title TEXT,
                    username TEXT,
                    role TEXT NOT NULL DEFAULT 'news_source',
                    added_at TEXT NOT NULL DEFAULT (datetime('now')),
                    last_message_at TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS agent_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    payload_json TEXT,
                    result_json TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS publish_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER NOT NULL,
                    posted_at TEXT NOT NULL,
                    hour_key TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    UNIQUE(channel_id, hour_key)
                );

                CREATE INDEX IF NOT EXISTS idx_channel_posts_channel_date
                    ON channel_posts(channel_id, date DESC);

                CREATE INDEX IF NOT EXISTS idx_watched_chats_role_active
                    ON watched_chats(role, is_active);

                CREATE INDEX IF NOT EXISTS idx_publish_log_channel_hour
                    ON publish_log(channel_id, hour_key);
                """
            )
            await self._migrate(db)
            await db.commit()
        logger.info("Database initialized at %s", self.path)

    async def _migrate(self, db: aiosqlite.Connection) -> None:
        """Safe additive migrations for existing DBs."""
        cols = {
            r[1]
            for r in await (await db.execute("PRAGMA table_info(channels)")).fetchall()
        }
        if "is_default" not in cols:
            await db.execute(
                "ALTER TABLE channels ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0"
            )
            logger.info("Migrated channels: added is_default")

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
        return _row_to_channel(row)

    async def list_channels(self) -> list[BoundChannel]:
        async with self.connection() as db:
            cursor = await db.execute(
                "SELECT * FROM channels ORDER BY is_default DESC, created_at ASC, channel_id ASC"
            )
            rows = await cursor.fetchall()
        return [_row_to_channel(r) for r in rows]

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
        return _row_to_channel(row)

    async def delete_channel(self, channel_id: int) -> bool:
        async with self.connection() as db:
            cursor = await db.execute(
                "DELETE FROM channels WHERE channel_id = ?",
                (channel_id,),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def set_default_channel(self, channel_id: int) -> BoundChannel | None:
        """Mark one channel as default (clears previous). Returns None if unknown."""
        async with self.connection() as db:
            exists = await (
                await db.execute(
                    "SELECT 1 FROM channels WHERE channel_id = ?",
                    (channel_id,),
                )
            ).fetchone()
            if exists is None:
                return None
            await db.execute("UPDATE channels SET is_default = 0")
            await db.execute(
                "UPDATE channels SET is_default = 1 WHERE channel_id = ?",
                (channel_id,),
            )
            await db.commit()
            row = await (
                await db.execute(
                    "SELECT * FROM channels WHERE channel_id = ?",
                    (channel_id,),
                )
            ).fetchone()
        assert row is not None
        return _row_to_channel(row)

    async def get_default_channel(self) -> BoundChannel | None:
        async with self.connection() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM channels WHERE is_default = 1 LIMIT 1"
                )
            ).fetchone()
        if row is None:
            return None
        return _row_to_channel(row)

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

    async def save_channel_post(
        self,
        *,
        channel_id: int,
        message_id: int,
        date: str | None = None,
        text: str | None = None,
        caption: str | None = None,
        media_type: str | None = None,
        raw_json: str | None = None,
    ) -> ChannelPost:
        async with self.connection() as db:
            await db.execute(
                """
                INSERT INTO channel_posts
                    (channel_id, message_id, date, text, caption, media_type, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel_id, message_id) DO UPDATE SET
                    date = excluded.date,
                    text = excluded.text,
                    caption = excluded.caption,
                    media_type = excluded.media_type,
                    raw_json = excluded.raw_json
                """,
                (channel_id, message_id, date, text, caption, media_type, raw_json),
            )
            await db.commit()
            row = await (
                await db.execute(
                    "SELECT * FROM channel_posts WHERE channel_id = ? AND message_id = ?",
                    (channel_id, message_id),
                )
            ).fetchone()
        assert row is not None
        return _row_to_post(row)

    async def list_recent_posts(
        self, channel_id: int | None = None, *, limit: int = 20
    ) -> list[ChannelPost]:
        limit = max(1, min(int(limit), 200))
        async with self.connection() as db:
            if channel_id is None:
                cursor = await db.execute(
                    """
                    SELECT * FROM channel_posts
                    ORDER BY datetime(COALESCE(date, created_at)) DESC, message_id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT * FROM channel_posts
                    WHERE channel_id = ?
                    ORDER BY datetime(COALESCE(date, created_at)) DESC, message_id DESC
                    LIMIT ?
                    """,
                    (channel_id, limit),
                )
            rows = await cursor.fetchall()
        return [_row_to_post(r) for r in rows]

    async def get_post(
        self, channel_id: int, message_id: int
    ) -> ChannelPost | None:
        async with self.connection() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM channel_posts WHERE channel_id = ? AND message_id = ?",
                    (channel_id, message_id),
                )
            ).fetchone()
        if row is None:
            return None
        return _row_to_post(row)

    async def search_posts(
        self,
        query: str,
        *,
        channel_id: int | None = None,
        limit: int = 20,
    ) -> list[ChannelPost]:
        limit = max(1, min(int(limit), 200))
        pattern = f"%{query}%"
        async with self.connection() as db:
            if channel_id is None:
                cursor = await db.execute(
                    """
                    SELECT * FROM channel_posts
                    WHERE (text LIKE ? OR caption LIKE ?)
                    ORDER BY datetime(COALESCE(date, created_at)) DESC, message_id DESC
                    LIMIT ?
                    """,
                    (pattern, pattern, limit),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT * FROM channel_posts
                    WHERE channel_id = ?
                      AND (text LIKE ? OR caption LIKE ?)
                    ORDER BY datetime(COALESCE(date, created_at)) DESC, message_id DESC
                    LIMIT ?
                    """,
                    (channel_id, pattern, pattern, limit),
                )
            rows = await cursor.fetchall()
        return [_row_to_post(r) for r in rows]

    async def upsert_watched_chat(
        self,
        chat_id: int,
        *,
        chat_type: str,
        title: str | None = None,
        username: str | None = None,
        role: str = "news_source",
        is_active: bool = True,
    ) -> WatchedChat:
        async with self.connection() as db:
            await db.execute(
                """
                INSERT INTO watched_chats
                    (chat_id, chat_type, title, username, role, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    chat_type = excluded.chat_type,
                    title = COALESCE(excluded.title, watched_chats.title),
                    username = COALESCE(excluded.username, watched_chats.username),
                    role = excluded.role,
                    is_active = excluded.is_active
                """,
                (
                    chat_id,
                    chat_type,
                    title,
                    username,
                    role,
                    1 if is_active else 0,
                ),
            )
            await db.commit()
            row = await (
                await db.execute(
                    "SELECT * FROM watched_chats WHERE chat_id = ?",
                    (chat_id,),
                )
            ).fetchone()
        assert row is not None
        return _row_to_watched(row)

    async def list_watched_chats(
        self,
        role: str | None = None,
        *,
        active_only: bool = True,
    ) -> list[WatchedChat]:
        clauses: list[str] = []
        params: list[Any] = []
        if role is not None:
            clauses.append("role = ?")
            params.append(role)
        if active_only:
            clauses.append("is_active = 1")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self.connection() as db:
            cursor = await db.execute(
                f"""
                SELECT * FROM watched_chats
                {where}
                ORDER BY
                    datetime(COALESCE(last_message_at, added_at)) DESC,
                    chat_id ASC
                """,
                params,
            )
            rows = await cursor.fetchall()
        return [_row_to_watched(r) for r in rows]

    async def get_watched_chat(self, chat_id: int) -> WatchedChat | None:
        async with self.connection() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM watched_chats WHERE chat_id = ?",
                    (chat_id,),
                )
            ).fetchone()
        if row is None:
            return None
        return _row_to_watched(row)

    async def touch_last_message(
        self, chat_id: int, when: str | None = None
    ) -> None:
        async with self.connection() as db:
            if when is None:
                await db.execute(
                    """
                    UPDATE watched_chats
                    SET last_message_at = datetime('now')
                    WHERE chat_id = ?
                    """,
                    (chat_id,),
                )
            else:
                await db.execute(
                    """
                    UPDATE watched_chats
                    SET last_message_at = ?
                    WHERE chat_id = ?
                    """,
                    (when, chat_id),
                )
            await db.commit()

    async def deactivate_watched_chat(self, chat_id: int) -> bool:
        async with self.connection() as db:
            cursor = await db.execute(
                """
                UPDATE watched_chats SET is_active = 0 WHERE chat_id = ?
                """,
                (chat_id,),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def list_feed(
        self,
        *,
        limit: int = 20,
        chat_id: int | None = None,
        exclude_chat_ids: list[int] | None = None,
    ) -> list[ChannelPost]:
        """Recent ingested posts across sources (optional chat filter / exclusions)."""
        limit = max(1, min(int(limit), 200))
        clauses: list[str] = []
        params: list[Any] = []
        if chat_id is not None:
            clauses.append("channel_id = ?")
            params.append(chat_id)
        if exclude_chat_ids:
            placeholders = ",".join("?" for _ in exclude_chat_ids)
            clauses.append(f"channel_id NOT IN ({placeholders})")
            params.extend(exclude_chat_ids)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        async with self.connection() as db:
            cursor = await db.execute(
                f"""
                SELECT * FROM channel_posts
                {where}
                ORDER BY datetime(COALESCE(date, created_at)) DESC, message_id DESC
                LIMIT ?
                """,
                params,
            )
            rows = await cursor.fetchall()
        return [_row_to_post(r) for r in rows]

    async def log_agent_job(
        self,
        action: str,
        payload: Mapping[str, Any] | None = None,
        result: Mapping[str, Any] | None = None,
    ) -> int:
        async with self.connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO agent_jobs (action, payload_json, result_json)
                VALUES (?, ?, ?)
                """,
                (
                    action,
                    json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                ),
            )
            await db.commit()
            return int(cursor.lastrowid or 0)

    async def publish_slot_exists(self, channel_id: int, hour_key: str) -> bool:
        async with self.connection() as db:
            row = await (
                await db.execute(
                    """
                    SELECT 1 FROM publish_log
                    WHERE channel_id = ? AND hour_key = ?
                    LIMIT 1
                    """,
                    (channel_id, hour_key),
                )
            ).fetchone()
        return row is not None

    async def reserve_publish_slot(
        self, channel_id: int, posted_at: str, hour_key: str
    ) -> bool:
        """Reserve one channel/hour slot atomically across bot processes."""
        async with self.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                await db.execute(
                    """
                    INSERT INTO publish_log (channel_id, posted_at, hour_key, status)
                    VALUES (?, ?, ?, 'pending')
                    """,
                    (channel_id, posted_at, hour_key),
                )
            except aiosqlite.IntegrityError:
                await db.rollback()
                return False
            await db.commit()
        return True

    async def record_publish(
        self, channel_id: int, posted_at: str, hour_key: str
    ) -> None:
        async with self.connection() as db:
            await db.execute(
                """
                INSERT INTO publish_log (channel_id, posted_at, hour_key, status)
                VALUES (?, ?, ?, 'success')
                ON CONFLICT(channel_id, hour_key) DO UPDATE SET
                    posted_at = excluded.posted_at,
                    status = 'success'
                """,
                (channel_id, posted_at, hour_key),
            )
            await db.commit()

    async def release_publish_slot(self, channel_id: int, hour_key: str) -> None:
        async with self.connection() as db:
            await db.execute(
                """
                DELETE FROM publish_log
                WHERE channel_id = ? AND hour_key = ? AND status = 'pending'
                """,
                (channel_id, hour_key),
            )
            await db.commit()
