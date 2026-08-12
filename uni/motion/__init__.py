"""Пакет плавного движения мыши (MVP xtoys browser mouse)."""

from __future__ import annotations

from uni.motion.driver import SmoothMouseDriver
from uni.motion.label import CursorLabelConfig, CursorLabelOverlay
from uni.motion.trajectory import (
    MousePath,
    build_circle_path,
    build_move_path,
    build_wander_path,
)

__all__ = [
    "SmoothMouseDriver",
    "CursorLabelConfig",
    "CursorLabelOverlay",
    "MousePath",
    "build_move_path",
    "build_wander_path",
    "build_circle_path",
]
