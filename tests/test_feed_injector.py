"""Tests for uni.context.feed_injector (no network, no camera)."""
from __future__ import annotations

import base64
import random

from uni.context.feed_injector import ContextFeedInjector, _sanitize
from uni.capabilities.camera import _frame_to_base64 as cam_frame_to_base64

import numpy as np


def test_sanitize_strips_dangerous_chars() -> None:
    # Главное: HTML-теги удаляются целиком (нет внедрения разметки/скриптов).
    assert "<script>" not in _sanitize('<script>alert("x")</script> привет')
    assert "</script>" not in _sanitize('<script>alert("x")</script> привет')
    assert "привет" in _sanitize('<script>alert("x")</script> привет')


def test_add_remove_feeds_dedup() -> None:
    inj = ContextFeedInjector()
    assert inj.add_feed_url("https://example.com") is True
    assert inj.add_feed_url("https://example.com") is False  # dedup
    assert "https://example.com" in inj.list_feeds()
    assert inj.remove_feed_url("https://example.com") is True
    assert inj.list_feeds() == []


def test_build_style_hint_respects_rate() -> None:
    inj = ContextFeedInjector()
    inj.cache_local_hints(["говори мягко", "добавь игривости"])
    # rate=0 -> no hint
    assert inj.build_style_hint(0.0) == ""
    # with rate and hints, returns a non-empty bracketed hint
    rng = random.Random(7)
    out = inj.build_style_hint(1.0, rng=rng)
    assert out.startswith("\n[Стилевая подсказка")
    assert "говори мягко" in out or "добавь игривости" in out


def test_build_style_hint_empty_without_hints() -> None:
    inj = ContextFeedInjector()
    assert inj.build_style_hint(1.0) == ""


def test_external_scrape_default_off() -> None:
    inj = ContextFeedInjector()  # allow_external_scrape=False по умолчанию
    assert inj._allow_external_scrape is False


def test_frame_to_base64_roundtrip() -> None:
    # синтетический BGR-кадр 4x4 (без реальной камеры)
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    frame[:, :, 2] = 255  # синий канал
    uri = cam_frame_to_base64(frame)
    assert uri.startswith("data:image/jpeg;base64,")
    decoded = base64.b64decode(uri.split(",", 1)[1])
    assert decoded[:2] == b"\xff\xd8"  # JPEG SOI marker
