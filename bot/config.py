"""Environment-based configuration (no secrets in code)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    allowed_user_ids: str = Field(default="", alias="ALLOWED_USER_IDS")
    default_channel_id: int | None = Field(default=None, alias="DEFAULT_CHANNEL_ID")
    db_path: Path = Field(default=Path("./data/bot.db"), alias="DB_PATH")

    @field_validator("telegram_bot_token")
    @classmethod
    def token_must_be_nonempty(cls, value: str) -> str:
        token = (value or "").strip()
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        return token

    @property
    def allowed_ids(self) -> frozenset[int]:
        raw = (self.allowed_user_ids or "").strip()
        if not raw:
            return frozenset()
        result: set[int] = set()
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            result.add(int(part))
        return frozenset(result)

    def is_allowed(self, user_id: int) -> bool:
        return user_id in self.allowed_ids


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance. Clear cache in tests via get_settings.cache_clear()."""
    return Settings()  # type: ignore[call-arg]
