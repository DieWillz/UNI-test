"""Normalized inbound/outbound message models for transport adapters.

These are the only shapes a transport must produce for UNI and consume back from
UNI. Platform-specific detail (Telegram Update, MessageEntity, chat.id) must
not leak past the adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence
from datetime import datetime


@dataclass(frozen=True)
class Attachment:
    """A single inbound or outbound file/media attachment."""

    media_type: str  # e.g. "photo", "document", "voice", "video"
    filename: str
    size_bytes: int
    content_ref: str  # opaque reference the adapter resolves for delivery
    caption: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InboundMessage:
    """Normalized message arriving from any transport."""

    transport: str  # e.g. "telegram"
    message_id: str  # stable per-transport id for dedup
    conversation_id: str  # stable per-conversation id
    user_id: str  # stable per-user id
    username: str | None = None
    text: str = ""
    attachments: Sequence[Attachment] = field(default_factory=list)
    reply_to: str | None = None  # id of the message this replies to
    timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Sanity only — transport adapters are responsible for valid values.
        object.__setattr__(self, "text", str(self.text or ""))


@dataclass(frozen=True)
class OutboundMessage:
    """Normalized message UNI sends back to a transport."""

    text: str = ""
    attachments: Sequence[Attachment] = field(default_factory=list)
    reply_to: str | None = None  # id of the inbound message to reply to
    parse_mode: str | None = None  # transport-specific, e.g. "MarkdownV2"
    metadata: dict[str, Any] = field(default_factory=dict)
