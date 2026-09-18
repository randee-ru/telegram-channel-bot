"""Agent HTTP API auth and basic routing tests (no live Telegram)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bot.agent_api import create_app
from bot.config import Settings
from bot.db import Database


@pytest.fixture
async def db(tmp_path: Path):
    database = Database(tmp_path / "api.db")
    await database.init()
    await database.upsert_channel(-100111, title="Test", username="testch", bound_by=1)
    return database


def _settings(**overrides) -> Settings:
    base = {
        "TELEGRAM_BOT_TOKEN": "1:TESTTOKEN",
        "ALLOWED_USER_IDS": "1",
        "AGENT_API_TOKEN": "secret-agent-token",
        "AGENT_API_PORT": "8787",
        "AGENT_API_HOST": "127.0.0.1",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
async def client(db: Database):
    bot = MagicMock()
    bot.get_chat = AsyncMock()
    bot.get_chat_member_count = AsyncMock(return_value=42)
    bot.send_message = AsyncMock()
    settings = _settings()
    app = create_app(bot, db, settings)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        yield client, settings
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_health_no_auth(client):
    cli, _ = client
    resp = await cli.get("/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_channels_rejects_without_token(client):
    cli, _ = client
    resp = await cli.get("/channels")
    assert resp.status == 401
    data = await resp.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_channels_with_bearer(client):
    cli, settings = client
    resp = await cli.get(
        "/channels",
        headers={"Authorization": f"Bearer {settings.agent_api_token}"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert len(data["data"]) == 1
    assert data["data"][0]["channel_id"] == -100111


@pytest.mark.asyncio
async def test_channels_with_x_agent_token(client):
    cli, settings = client
    resp = await cli.get(
        "/channels",
        headers={"X-Agent-Token": settings.agent_api_token},
    )
    assert resp.status == 200


@pytest.mark.asyncio
async def test_posts_and_search(client, db: Database):
    cli, settings = client
    await db.save_channel_post(
        channel_id=-100111, message_id=5, text="agent hello", media_type="text"
    )
    headers = {"Authorization": f"Bearer {settings.agent_api_token}"}
    resp = await cli.get("/posts?channel_id=-100111&limit=5", headers=headers)
    assert resp.status == 200
    data = await resp.json()
    assert data["data"][0]["text"] == "agent hello"

    resp = await cli.get("/posts/search?q=hello&channel_id=-100111", headers=headers)
    assert resp.status == 200
    assert len((await resp.json())["data"]) == 1


@pytest.mark.asyncio
async def test_set_default(client):
    cli, settings = client
    headers = {"Authorization": f"Bearer {settings.agent_api_token}"}
    resp = await cli.post(
        "/channels/default",
        json={"channel_id": -100111},
        headers=headers,
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["data"]["is_default"] is True
