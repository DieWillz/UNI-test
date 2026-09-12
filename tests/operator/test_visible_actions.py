from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from uni.operator.visible_actions import VisibleDesktopDriver, VisibleTarget


def make_target(x: int = 100, y: int = 200, width: int = 50, height: int = 30) -> VisibleTarget:
    return VisibleTarget(name="Test", role="button", x=x, y=y, width=width, height=height)


@pytest.mark.asyncio
async def test_click_moves_to_center_and_clicks() -> None:
    computer = AsyncMock()
    computer.execute = AsyncMock(return_value=MagicMock(success=True, message="clicked"))
    driver = VisibleDesktopDriver(computer)
    target = make_target(x=100, y=200, width=50, height=30)
    result = await driver.click(target)
    assert result.success
    # Center of (100, 200, 50, 30) = (125, 215)
    computer.execute.assert_called_once_with("click_human", x=125, y=215, button="left")


@pytest.mark.asyncio
async def test_fill_clicks_then_types_short_text() -> None:
    computer = AsyncMock()
    computer.execute = AsyncMock(side_effect=[
        MagicMock(success=True, message="clicked"),  # click
        MagicMock(success=True, message="selected"),  # ctrl+a
        MagicMock(success=True, message="typed"),     # type_unicode
    ])
    driver = VisibleDesktopDriver(computer)
    target = make_target()
    result = await driver.fill(target, text="hello")
    assert result.success
    assert computer.execute.call_count == 3


@pytest.mark.asyncio
async def test_fill_uses_paste_for_long_text() -> None:
    computer = AsyncMock()
    computer.execute = AsyncMock(side_effect=[
        MagicMock(success=True, message="clicked"),  # click
        MagicMock(success=True, message="selected"),  # ctrl+a
        MagicMock(success=True, message="pasted"),    # paste
    ])
    driver = VisibleDesktopDriver(computer)
    target = make_target()
    result = await driver.fill(target, text="a" * 150)
    assert result.success
    assert computer.execute.call_count == 3


@pytest.mark.asyncio
async def test_press_delegates_to_computer() -> None:
    computer = AsyncMock()
    computer.execute = AsyncMock(return_value=MagicMock(success=True, message="pressed"))
    driver = VisibleDesktopDriver(computer)
    result = await driver.press(key="enter")
    assert result.success
    computer.execute.assert_called_once_with("press", key="enter")


@pytest.mark.asyncio
async def test_focus_just_clicks() -> None:
    computer = AsyncMock()
    computer.execute = AsyncMock(return_value=MagicMock(success=True, message="clicked"))
    driver = VisibleDesktopDriver(computer)
    target = make_target()
    result = await driver.focus(target)
    assert result.success
    computer.execute.assert_called_once()


@pytest.mark.asyncio
async def test_click_failure_returns_error() -> None:
    computer = AsyncMock()
    computer.execute = AsyncMock(side_effect=RuntimeError("mouse failed"))
    driver = VisibleDesktopDriver(computer)
    target = make_target()
    result = await driver.click(target)
    assert not result.success
    assert "mouse failed" in result.message
