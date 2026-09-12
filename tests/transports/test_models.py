"""Tests for UNI transport models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from uni.transports.models import Attachment, InboundMessage, OutboundMessage


def test_inbound_message_default_text_empty() -> None:
    msg = InboundMessage(transport="telegram", message_id="m1", conversation_id="c1", user_id="u1")
    assert msg.text == ""
    assert msg.attachments == []


def test_inbound_message_text_stripped_to_str() -> None:
    msg = InboundMessage(
        transport="telegram",
        message_id="m1",
        conversation_id="c1",
        user_id="u1",
        text=42,  # non-str input coerced
    )
    assert msg.text == "42"


def test_attachment_defaults() -> None:
    a = Attachment(media_type="photo", filename="p.png", size_bytes=100, content_ref="/tmp/p.png")
    assert a.caption is None
    assert a.metadata == {}


def test_outbound_message_defaults() -> None:
    o = OutboundMessage(text="hi")
    assert o.reply_to is None
    assert o.parse_mode is None
    assert o.attachments == []


def test_inbound_message_metadata_immutable_safe() -> None:
    meta = {"key": "value"}
    msg = InboundMessage(
        transport="telegram",
        message_id="m1",
        conversation_id="c1",
        user_id="u1",
        metadata=meta,
    )
    # sanity: dataclass frozen
    with pytest.raises(Exception):
        msg.metadata = {"new": "val"}
