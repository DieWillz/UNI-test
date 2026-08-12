"""Tests for uni.motion.trajectory (pure math, no GUI).

Run:
    PYTHONPATH=C:\\LLM\\UNI C:\\LLM\\python312\\python.exe -m pytest tests/test_motion_trajectory.py -q
"""
from __future__ import annotations

import math
from pathlib import Path

from uni.motion.trajectory import (
    MousePath,
    build_circle_path,
    build_move_path,
    build_wander_path,
    clamp,
    ease_in_out_cubic,
)


def test_clamp_bounds() -> None:
    assert clamp(5.0, 0.0, 1.0) == 1.0
    assert clamp(-2.0, 0.0, 1.0) == 0.0
    assert clamp(0.5, 0.0, 1.0) == 0.5


def test_ease_endpoints() -> None:
    assert ease_in_out_cubic(0.0) == 0.0
    assert abs(ease_in_out_cubic(1.0) - 1.0) < 1e-9
    # monotonic increasing
    assert ease_in_out_cubic(0.25) < ease_in_out_cubic(0.75)


def test_build_move_path_reaches_target() -> None:
    rng = __import__("random").Random(1)
    path = build_move_path((0.0, 0.0), (800.0, 600.0), 1.0, rng=rng)
    assert isinstance(path, MousePath)
    assert len(path.points) == len(path.delays)
    assert len(path.points) > 8
    # finishes exactly at the target
    fx, fy = path.points[-1]
    assert (fx, fy) == (800.0, 600.0)


def test_build_move_path_short_distance_single_point() -> None:
    # distance < 1 px -> one point, single delay (no division by zero)
    path = build_move_path((10.0, 10.0), (10.3, 10.2), 0.5)
    assert len(path.points) == 1
    assert path.delays[0] >= 0.02


def test_build_move_path_duration_sum() -> None:
    rng = __import__("random").Random(2)
    path = build_move_path((0.0, 0.0), (400.0, 400.0), 2.0, rng=rng)
    # sum of delays approximates requested duration (humanize jitter within 0.7..1.3)
    assert 1.2 <= path.duration <= 2.8


def test_build_wander_path_inside_bounds() -> None:
    rng = __import__("random").Random(3)
    bounds = (100.0, 100.0, 800.0, 600.0)
    path = build_wander_path(bounds, 4.0, rng=rng)
    assert len(path.points) == len(path.delays)
    x0, y0, w, h = bounds
    for (x, y) in path.points:
        assert x0 <= x <= x0 + w
        assert y0 <= y <= y0 + h


def test_build_circle_path_close_to_center_radius() -> None:
    center = (500.0, 500.0)
    path = build_circle_path(center, 100.0, turns=1.0, duration=2.0)
    assert len(path.points) == len(path.delays)
    cx, cy = center
    for (x, y) in path.points:
        dist = math.hypot(x - cx, y - cy)
        assert abs(dist - 100.0) < 1.0  # within sampling tolerance


def test_path_mismatched_lengths_raises() -> None:
    try:
        MousePath(points=((0.0, 0.0),), delays=())
    except ValueError:
        return
    raise AssertionError("MousePath should reject mismatched points/delays")
