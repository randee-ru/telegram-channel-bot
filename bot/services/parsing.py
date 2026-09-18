"""Parse channel identifiers and t.me message links."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

# https://t.me/c/1234567890/42  (private channel: chat_id = -100{id})
# https://t.me/channelname/42
TME_LINK_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?:c/(\d+)/(\d+)|([A-Za-z0-9_]{4,})/(\d+))",
    re.IGNORECASE,
)

CHAT_MSG_RE = re.compile(
    r"^(-?\d+)\s*[:/\s]+\s*(\d+)$",
)


@dataclass(frozen=True, slots=True)
class MessageRef:
    """Reference to a Telegram message (for replies)."""

    chat_id: int | None  # None when only username known — resolve later
    username: str | None
    message_id: int


@dataclass(frozen=True, slots=True)
class ChannelRef:
    channel_id: int | None
    username: str | None


def parse_channel_ref(text: str) -> ChannelRef | None:
    """Parse @username, username, or numeric channel id."""
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("@"):
        return ChannelRef(channel_id=None, username=raw[1:])
    if re.fullmatch(r"-?\d+", raw):
        return ChannelRef(channel_id=int(raw), username=None)
    if re.fullmatch(r"[A-Za-z0-9_]{4,}", raw):
        return ChannelRef(channel_id=None, username=raw)
    return None


def private_channel_id_from_tme_c(numeric: int) -> int:
    """Convert t.me/c/<id>/msg to Telegram chat_id (-100...)."""
    s = str(numeric)
    if s.startswith("-100"):
        return int(s)
    return int(f"-100{numeric}")


def parse_message_ref(text: str) -> MessageRef | None:
    """Parse t.me link or 'chat_id message_id' / 'chat_id:message_id'."""
    raw = (text or "").strip()
    if not raw:
        return None

    m = TME_LINK_RE.search(raw)
    if m:
        if m.group(1) and m.group(2):
            return MessageRef(
                chat_id=private_channel_id_from_tme_c(int(m.group(1))),
                username=None,
                message_id=int(m.group(2)),
            )
        return MessageRef(
            chat_id=None,
            username=m.group(3),
            message_id=int(m.group(4)),
        )

    m2 = CHAT_MSG_RE.match(raw)
    if m2:
        return MessageRef(
            chat_id=int(m2.group(1)),
            username=None,
            message_id=int(m2.group(2)),
        )
    return None


def format_channel_label(channel_id: int, title: str | None, username: str | None) -> str:
    """HTML-safe label for operator messages."""
    name = html.escape(title or username or "без названия")
    uname = f" @{html.escape(username)}" if username else ""
    return f"{name}{uname} (<code>{channel_id}</code>)"
