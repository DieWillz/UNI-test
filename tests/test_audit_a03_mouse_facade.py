"""FIX-AUDIT A-03/A-04: SmoothMouseDriver — реальный фасад над HumanMouseController.

Тест НЕ использует hasattr (как требовал аудит). Мокаем HumanMouseController
на уровне uni.human_mouse (чтобы не требовать реального win32), создаём
SmoothMouseDriver и проверяем, что методы ДЕЛЕГИРУЮТ в контроллер.
Также проверяем A-04: cancel() вызывает human.cancel() (реальное прерывание),
а не release() на asyncio.Lock.
"""

from __future__ import annotations

from unittest import mock

import pytest

from uni.motion.driver import SmoothMouseDriver


@pytest.fixture
def human_mock():
    """Мок HumanMouseController на уровне модуля (без win32)."""
    with mock.patch("uni.human_mouse.HumanMouseController") as hmc_cls:
        inst = mock.MagicMock()
        # _current_pos / _screen_size — СИНХРОННЫЕ методы (staticmethod в human_mouse.py)
        inst._current_pos = mock.MagicMock(return_value=(100, 100))
        inst._screen_size = mock.MagicMock(return_value=(1920, 1080))
        # остальные — async
        inst.move_to = mock.AsyncMock()
        inst.click = mock.AsyncMock()
        inst.drag = mock.AsyncMock()
        inst.cancel = mock.MagicMock()
        inst.play_points = mock.AsyncMock()
        hmc_cls.return_value = inst
        yield inst


def test_facade_accepts_label_kwarg(human_mock):
    # A-03: mouse_show.py вызывает SmoothMouseDriver(label=...); раньше падало
    # (TypeError: unexpected keyword 'label'). Теперь принимается.
    d = SmoothMouseDriver(label="x")  # не должно бросать
    assert d._human is not None


def test_facade_delegates_move_to(human_mock):
    d = SmoothMouseDriver()
    import asyncio
    asyncio.run(d.move_to(10, 20))
    human_mock.move_to.assert_awaited_once_with(10, 20)


def test_facade_delegates_click(human_mock):
    d = SmoothMouseDriver()
    import asyncio
    asyncio.run(d.click(5, 6, button="right"))
    human_mock.click.assert_awaited_once_with(5, 6, "right")


def test_facade_delegates_drag_to(human_mock):
    human_mock._current_pos.return_value = (1, 1)
    d = SmoothMouseDriver()
    import asyncio
    asyncio.run(d.drag_to(50, 60))
    human_mock.drag.assert_awaited_once_with(1, 1, 50, 60)


def test_facade_screen_size_delegates(human_mock):
    d = SmoothMouseDriver()
    assert d.screen_size == (1920, 1080)
    human_mock._screen_size.assert_called()


def test_facade_cancel_calls_human_cancel(human_mock):
    # A-04: cancel() должен вызывать human.cancel() (реальное прерывание),
    # а НЕ release() на asyncio.Lock.
    d = SmoothMouseDriver()
    d.cancel()
    human_mock.cancel.assert_called_once()
    # убеждаемся, что старой заглушки (release на lock) нет: _busy отсутствует
    assert not hasattr(d, "_busy")
