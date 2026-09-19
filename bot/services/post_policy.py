"""Posting policy for the protected Telegram channel.

The policy is deliberately scoped to one channel. Other channels continue to
use the existing publishing behaviour unchanged.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bot.db import Database

MOSCOW = ZoneInfo("Europe/Moscow")
PROTECTED_CHANNEL_ID = -1002575306027
POSTING_START_HOUR = 9
POSTING_END_HOUR = 21


class PostPolicyError(Exception):
    """A post is not allowed by the channel posting policy."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def local_moscow_time(now: datetime | None = None) -> datetime:
    """Return ``now`` in Moscow time, treating naive values as Moscow time."""
    if now is None:
        return datetime.now(MOSCOW)
    if now.tzinfo is None:
        return now.replace(tzinfo=MOSCOW)
    return now.astimezone(MOSCOW)


def _hour_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%d-%H")


def check_can_post(channel_id: int, now: datetime | None = None) -> None:
    """Check the time window for the protected channel.

    The SQLite-backed one-post-per-hour check is performed by ``PostPolicy``;
    this small synchronous function is also useful for deterministic tests.
    """
    if channel_id != PROTECTED_CHANNEL_ID:
        return
    local_now = local_moscow_time(now)
    if not POSTING_START_HOUR <= local_now.hour < POSTING_END_HOUR:
        raise PostPolicyError(
            "Публикация в канал @tochka_vx разрешена только с 09:00 до 21:00 "
            "по московскому времени."
        )


class PostPolicy:
    """SQLite-backed policy gate with an atomic hourly reservation."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def check_can_post(
        self, channel_id: int, now: datetime | None = None
    ) -> None:
        check_can_post(channel_id, now)
        if channel_id != PROTECTED_CHANNEL_ID:
            return
        local_now = local_moscow_time(now)
        if await self.db.publish_slot_exists(channel_id, _hour_key(local_now)):
            raise PostPolicyError(
                "Публикация в канал @tochka_vx отклонена: разрешён не более "
                "одного успешного поста в календарный час по московскому времени."
            )

    async def reserve_post(
        self, channel_id: int, now: datetime | None = None
    ) -> datetime:
        """Atomically reserve a slot before the network publish call."""
        local_now = local_moscow_time(now)
        await self.check_can_post(channel_id, local_now)
        if channel_id == PROTECTED_CHANNEL_ID:
            reserved = await self.db.reserve_publish_slot(
                channel_id, local_now.isoformat(), _hour_key(local_now)
            )
            if not reserved:
                raise PostPolicyError(
                    "Публикация в канал @tochka_vx отклонена: разрешён не более "
                    "одного успешного поста в календарный час по московскому времени."
                )
        return local_now

    async def record_post(
        self, channel_id: int, now: datetime | None = None
    ) -> None:
        """Mark a reserved slot successful after Telegram accepts the post."""
        if channel_id == PROTECTED_CHANNEL_ID:
            local_now = local_moscow_time(now)
            await self.db.record_publish(
                channel_id, local_now.isoformat(), _hour_key(local_now)
            )

    async def release_post(
        self, channel_id: int, now: datetime | None = None
    ) -> None:
        """Release only a failed pending reservation."""
        if channel_id == PROTECTED_CHANNEL_ID:
            local_now = local_moscow_time(now)
            await self.db.release_publish_slot(channel_id, _hour_key(local_now))
