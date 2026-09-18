"""Config / allowlist tests (no Telegram API)."""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from bot.config import Settings, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_allowed_ids_parsing(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "999999:TESTTOKEN_FOR_UNIT_TESTS_ONLY")
    monkeypatch.setenv("ALLOWED_USER_IDS", "111, 222,333")
    s = Settings()  # type: ignore[call-arg]
    assert s.allowed_ids == frozenset({111, 222, 333})
    assert s.is_allowed(222)
    assert not s.is_allowed(999)


def test_empty_allowlist(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "999999:TESTTOKEN_FOR_UNIT_TESTS_ONLY")
    monkeypatch.setenv("ALLOWED_USER_IDS", "")
    s = Settings()  # type: ignore[call-arg]
    assert s.allowed_ids == frozenset()
    assert not s.is_allowed(1)


def test_default_db_path(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "999999:TESTTOKEN_FOR_UNIT_TESTS_ONLY")
    monkeypatch.delenv("DB_PATH", raising=False)
    s = Settings()  # type: ignore[call-arg]
    assert str(s.db_path).endswith("bot.db")


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    # Ensure .env is not loaded with a real token during tests
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
