"""Parsing helpers unit tests."""

from __future__ import annotations

from bot.services.parsing import (
    parse_channel_ref,
    parse_message_ref,
    private_channel_id_from_tme_c,
)


def test_parse_channel_username():
    r = parse_channel_ref("@My_Channel")
    assert r is not None
    assert r.username == "My_Channel"
    assert r.channel_id is None


def test_parse_channel_numeric():
    r = parse_channel_ref("-1001234567890")
    assert r is not None
    assert r.channel_id == -1001234567890


def test_parse_channel_invalid():
    assert parse_channel_ref("") is None
    assert parse_channel_ref("ab") is None  # too short username


def test_private_channel_id():
    assert private_channel_id_from_tme_c(1234567890) == -1001234567890


def test_parse_tme_private_link():
    ref = parse_message_ref("https://t.me/c/1234567890/42")
    assert ref is not None
    assert ref.chat_id == -1001234567890
    assert ref.message_id == 42


def test_parse_tme_public_link():
    ref = parse_message_ref("https://t.me/mychannel/99")
    assert ref is not None
    assert ref.username == "mychannel"
    assert ref.chat_id is None
    assert ref.message_id == 99


def test_parse_chat_msg_pair():
    ref = parse_message_ref("-1001234567890 15")
    assert ref is not None
    assert ref.chat_id == -1001234567890
    assert ref.message_id == 15

    ref2 = parse_message_ref("-1001:20")
    assert ref2 is not None
    assert ref2.chat_id == -1001
    assert ref2.message_id == 20
