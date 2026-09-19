from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from bot.db import Database
from bot.services.post_policy import (
    PROTECTED_CHANNEL_ID,
    PostPolicy,
    PostPolicyError,
    check_can_post,
)


def test_protected_channel_window_uses_moscow_time() -> None:
    check_can_post(PROTECTED_CHANNEL_ID, datetime(2026, 9, 19, 9, 0))
    check_can_post(PROTECTED_CHANNEL_ID, datetime(2026, 9, 19, 20, 59))
    with pytest.raises(PostPolicyError, match="09:00"):
        check_can_post(PROTECTED_CHANNEL_ID, datetime(2026, 9, 19, 8, 59))
    with pytest.raises(PostPolicyError, match="21:00"):
        check_can_post(PROTECTED_CHANNEL_ID, datetime(2026, 9, 19, 21, 0))


def test_other_channels_are_unchanged() -> None:
    check_can_post(-1001234567890, datetime(2026, 9, 19, 3, 0))


@pytest.mark.asyncio
async def test_one_successful_post_per_moscow_hour(tmp_path: Path) -> None:
    db = Database(tmp_path / "policy.db")
    await db.init()
    policy = PostPolicy(db)
    now = datetime(2026, 9, 19, 12, 15)

    reserved = await policy.reserve_post(PROTECTED_CHANNEL_ID, now)
    await policy.record_post(PROTECTED_CHANNEL_ID, reserved)
    with pytest.raises(PostPolicyError, match="одного успешного поста"):
        await policy.reserve_post(PROTECTED_CHANNEL_ID, datetime(2026, 9, 19, 12, 59))

    next_hour = await policy.reserve_post(
        PROTECTED_CHANNEL_ID, datetime(2026, 9, 19, 13, 0)
    )
    await policy.record_post(PROTECTED_CHANNEL_ID, next_hour)


@pytest.mark.asyncio
async def test_failed_publish_releases_reservation(tmp_path: Path) -> None:
    db = Database(tmp_path / "policy.db")
    await db.init()
    policy = PostPolicy(db)
    now = datetime(2026, 9, 19, 12, 15)
    reserved = await policy.reserve_post(PROTECTED_CHANNEL_ID, now)
    await policy.release_post(PROTECTED_CHANNEL_ID, reserved)
    await policy.reserve_post(PROTECTED_CHANNEL_ID, now)
