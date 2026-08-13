"""Тесты closed-loop агента (P1.7 / D3).

Используем ПОДДЕЛЬНЫЙ ToolExecutor — без реального Windows/VLM/мыши.
Проверяем, что act_on_screen собирает шаги и завершается success.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from uni.capabilities.computer_vision_agent import ComputerVisionAgent
from uni.contracts import ToolResult


class _FakeExecutor:
    """Возвращает заданные ответы вместо реальных capability."""

    def __init__(self, responses: dict[str, ToolResult]) -> None:
        self._resp = responses
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, action: str, args: dict) -> ToolResult:
        self.calls.append((action, args))
        return self._resp.get(action, ToolResult(success=False, message="нет мока"))


def _make_executor_for_goal(goal_text: str) -> _FakeExecutor:
    return _FakeExecutor({
        "vision.capture_screen_png": ToolResult(success=True, data={"path": "x.png"}),
        "vision.analyze_desktop": ToolResult(
            success=True, data={"analysis": '{"action": "click", "x": 100, "y": 200}'}
        ),
        "computer.click": ToolResult(success=True, message="клик"),
        "computer.type_text": ToolResult(success=True, message="ввод"),
    })


@pytest.mark.asyncio
async def test_act_on_screen_opens_notepad() -> None:
    exe = _make_executor_for_goal("открой блокнот")
    agent = ComputerVisionAgent(exe, max_steps=8)
    result = await agent.act_on_screen("открой блокнот")
    assert result["status"] == "success"
    assert any(c[0] == "computer.click" for c in exe.calls)
    # был хотя бы один шаг клика
    assert any(s["action"] == "click" for s in result["steps"])


@pytest.mark.asyncio
async def test_act_on_screen_fails_on_bad_vision() -> None:
    exe = _FakeExecutor({
        "vision.capture_screen_png": ToolResult(success=True, data={"path": "x.png"}),
        "vision.analyze_desktop": ToolResult(success=True, data={"analysis": "не понял"}),
        "computer.click": ToolResult(success=True),
    })
    agent = ComputerVisionAgent(exe, max_steps=4)
    result = await agent.act_on_screen("сделай что-то")
    assert result["status"] == "failed"
