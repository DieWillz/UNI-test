"""Tests for camera capture_base64_frame encoding (headless, synthetic frame).

Дублирует проверку кодирования кадра без реальной камеры (cv2/numpy).
См. также tests/test_feed_injector.py.
"""
from __future__ import annotations

import base64

import numpy as np

from uni.capabilities.camera import _frame_to_base64


def test_frame_to_base64_is_jpeg_data_url() -> None:
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    frame[:, :, 1] = 128  # зелёный
    uri = _frame_to_base64(frame)
    assert uri.startswith("data:image/jpeg;base64,")
    body = uri.split(",", 1)[1]
    decoded = base64.b64decode(body)
    assert decoded[:2] == b"\xff\xd8"  # JPEG SOI
