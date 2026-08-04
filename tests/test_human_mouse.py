"""Тесты человеко-подобной мыши: математика (human_motion) + win32-исполнитель (human_mouse).

Запуск:
    PYTHONPATH=C:\\LLM\\UNI C:\\LLM\\python312\\python.exe -m pytest tests/test_human_mouse.py -q
"""
from __future__ import annotations

import sys
import types
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# 1) human_motion — чистая математика (без win32)
# ---------------------------------------------------------------------------
from uni.human_motion import (
    MotionPoint,
    build_heart_path,
    build_spiral_path,
    build_wander_path,
    generate_path,
    step_delays,
)


def test_minimum_jerk_bell_shape() -> None:
    """Профиль скорости minimum-jerk: разгон в середине, ноль на концах."""
    from uni.human_motion import _minimum_jerk

    assert _minimum_jerk(0.0) == 0.0
    assert abs(_minimum_jerk(1.0) - 1.0) < 1e-9
    mid = (_minimum_jerk(0.5 + 1e-4) - _minimum_jerk(0.5 - 1e-4)) / 2e-4
    early = (_minimum_jerk(0.1 + 1e-4) - _minimum_jerk(0.1 - 1e-4)) / 2e-4
    assert mid > early


def test_generate_path_reaches_target() -> None:
    path = generate_path((0.0, 0.0), (300.0, 200.0))
    assert path[0].x == 0.0 and path[0].y == 0.0
    assert path[-1].x == 300.0 and path[-1].y == 200.0
    assert all(path[i].t <= path[i + 1].t + 1e-9 for i in range(len(path) - 1))


def test_step_delays_sum_equals_duration() -> None:
    path = generate_path((0.0, 0.0), (400.0, 400.0))
    delays = step_delays(path, 1.5)
    assert abs(sum(delays) - 1.5) < 1e-6


def test_figure_endpoints_t_in_01() -> None:
    for fn, args in (
        (build_spiral_path, ((500.0, 500.0), 100.0)),
        (build_heart_path, ((500.0, 500.0), 8.0)),
        (build_wander_path, ((40.0, 40.0, 800.0, 600.0), 6.0)),
    ):
        pts = fn(*args)
        assert len(pts) > 8
        assert all(0.0 <= p.t <= 1.0 + 1e-9 for p in pts)
        assert isinstance(pts[0], MotionPoint)


def test_wander_stays_in_bounds() -> None:
    x0, y0, w, h = 40.0, 40.0, 800.0, 600.0
    pts = build_wander_path((x0, y0, w, h), 4.0)
    assert all(x0 - 1 <= p.x <= x0 + w + 1 and y0 - 1 <= p.y <= y0 + h + 1 for p in pts)


# ---------------------------------------------------------------------------
# 2) human_mouse — win32-исполнитель с моком win32api
#    Проверяем КРИТИЧЕСКИЙ баг: mouse_event НЕ должен получать абсолютные
#    координаты (dx/dy относительные) — только 0,0 после SetCursorPos.
# ---------------------------------------------------------------------------
def _make_win32_mock():
    """in-memory мок win32api: отслеживает порядок SetCursorPos / mouse_event."""
    mod = types.ModuleType("win32api")
    mod._calls = []
    mod._pos = [640, 360]

    def GetCursorPos():
        return tuple(mod._pos)

    def SetCursorPos(xy):
        mod._pos = [int(xy[0]), int(xy[1])]
        mod._calls.append(("SetCursorPos", tuple(xy)))

    def mouse_event(*args):
        mod._calls.append(("mouse_event", tuple(args)))

    mod.GetCursorPos = GetCursorPos
    mod.SetCursorPos = SetCursorPos
    mod.mouse_event = mouse_event
    return mod


import asyncio  # noqa: E402

from uni import human_mouse as hm_module  # noqa: E402


def _run_with_mock(fn):
    """Подменяем uni.human_mouse.win32api на свежий мок и выполняем fn(win32_mock)."""
    win32_mock = _make_win32_mock()
    with mock.patch.object(hm_module, "win32api", win32_mock):
        fn(win32_mock)


def test_click_uses_relative_zero_coords() -> None:
    """Клик НЕ телепортирует курсор: mouse_event вызывается с (evt, 0, 0, 0, 0)."""
    from uni.human_mouse import HumanMouseController, HumanMouseSettings

    def _go(win32_mock):
        ctrl = HumanMouseController(HumanMouseSettings(show_badge=False))
        asyncio.run(ctrl.click(300, 200, "left"))

    _run_with_mock(_go)
    # win32_mock недоступен снаружи; проверяем через повторный захват звонков
    # проще — подменим напрямую и считаем звонки
    win32_mock = _make_win32_mock()
    with mock.patch.object(hm_module, "win32api", win32_mock):
        ctrl = HumanMouseController(HumanMouseSettings(show_badge=False))
        asyncio.run(ctrl.click(300, 200, "left"))
    events = [c for c in win32_mock._calls if c[0] == "mouse_event"]
    assert len(events) == 2
    for _name, args in events:
        assert args[1] == 0 and args[2] == 0, f"mouse_event получил абсолютные координаты: {args}"


def test_drag_uses_relative_zero_coords() -> None:
    win32_mock = _make_win32_mock()
    with mock.patch.object(hm_module, "win32api", win32_mock):
        from uni.human_mouse import HumanMouseController, HumanMouseSettings

        ctrl = HumanMouseController(HumanMouseSettings(show_badge=False))
        asyncio.run(ctrl.drag(100, 100, 400, 300, "left"))
    events = [c for c in win32_mock._calls if c[0] == "mouse_event"]
    assert len(events) == 2
    for _name, args in events:
        assert args[1] == 0 and args[2] == 0


def test_move_sets_cursor_to_target() -> None:
    """move_to выставляет курсор ровно в цель через SetCursorPos."""
    win32_mock = _make_win32_mock()
    with mock.patch.object(hm_module, "win32api", win32_mock):
        from uni.human_mouse import HumanMouseController, HumanMouseSettings

        ctrl = HumanMouseController(HumanMouseSettings(show_badge=False))
        asyncio.run(ctrl.move_to(123, 456))
    assert tuple(win32_mock._pos) == (123, 456)


def test_cancel_stops_drag_midpath() -> None:
    """cancel() прерывает движение — курсор не доходит до конечной точки."""
    win32_mock = _make_win32_mock()
    with mock.patch.object(hm_module, "win32api", win32_mock):
        from uni.human_mouse import HumanMouseController, HumanMouseSettings

        ctrl = HumanMouseController(HumanMouseSettings(show_badge=False, move_duration=5.0))

        async def _run():
            task = asyncio.create_task(ctrl.drag(0, 0, 1000, 1000, "left"))
            await asyncio.sleep(0.2)
            ctrl.cancel()
            await task

        asyncio.run(_run())
    assert tuple(win32_mock._pos) != (1000, 1000)


# ---------------------------------------------------------------------------
# 3) driver фасад — имя API прежнее, внутри human_mouse
# ---------------------------------------------------------------------------
def test_driver_facade_imports_and_api() -> None:
    from uni.motion.driver import SmoothMouseDriver

    for name in ("move_to", "click", "drag_to", "wander", "circle", "draw", "wiggle", "cancel"):
        assert hasattr(SmoothMouseDriver, name)
