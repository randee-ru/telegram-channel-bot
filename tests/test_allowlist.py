"""Allowlist middleware logic (no live API)."""

from __future__ import annotations

import pytest

from bot.config import Settings
from bot.middlewares.allowlist import AllowlistMiddleware, REJECT_TEXT


def _settings(ids: str) -> Settings:
    return Settings(
        TELEGRAM_BOT_TOKEN="999999:TESTTOKEN_FOR_UNIT_TESTS_ONLY",
        ALLOWED_USER_IDS=ids,
    )


def test_reject_text_russian():
    assert "Доступ запрещён" in REJECT_TEXT


def test_middleware_public_commands():
    mw = AllowlistMiddleware(_settings("1"))
    assert "start" in mw.public_commands


def test_is_allowed_integration():
    s = _settings("10,20")
    assert s.is_allowed(10)
    assert not s.is_allowed(30)
