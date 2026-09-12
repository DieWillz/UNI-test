"""Shared fixtures for Telegram transport tests."""

from __future__ import annotations

from typing import Any

from unittest.mock import AsyncMock

import pytest

from uni.transports.telegram.adapter import (
    _ConcreteMediaSender,
    _ConcreteOutgoingSender,
)
from uni.transports.telegram.config import TelegramConfig


@pytest.fixture
def mock_sender() -> _ConcreteOutgoingSender:
    api = AsyncMock()
    return _ConcreteOutgoingSender(api)


@pytest.fixture
def mock_media_sender(mock_sender: _ConcreteOutgoingSender) -> _ConcreteMediaSender:
    api = AsyncMock()
    return _ConcreteMediaSender(api, TelegramConfig())


@pytest.fixture
def adapter(mock_sender: _ConcreteOutgoingSender, mock_media_sender: _ConcreteMediaSender) -> TelegramAdapter:
    from uni.transports.telegram.adapter import TelegramAdapter

    cfg = TelegramConfig(
        owner_user_ids=frozenset({123}),
        allowed_user_ids=frozenset({456}),
    )
    return TelegramAdapter(cfg, sender=mock_sender, media_sender=mock_media_sender)
