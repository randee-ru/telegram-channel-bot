"""Channel list formatting (offline)."""

from __future__ import annotations

from bot.db import BoundChannel
from bot.services.channels import channels_list_text


def test_empty_list():
    text = channels_list_text([])
    assert "Нет привязанных" in text


def test_nonempty_list():
    channels = [
        BoundChannel(
            channel_id=-1001,
            title="Тест",
            username="test",
            bound_by=1,
            created_at="2026-01-01",
        )
    ]
    text = channels_list_text(channels)
    assert "Тест" in text
    assert "-1001" in text
