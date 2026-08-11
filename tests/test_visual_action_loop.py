"""Мок-тест замкнутого цикла visual_action (без реального экрана/мыши).

Проверяет логику act_on_screen:
- done/успех когда verify возвращает «да»;
- не кликает, если locate вернул None (not_found);
- не кликает при низкой уверенности (clarify);
- останавливается по max_steps при неудачной проверке;
- блокирует опасные цели (blacklist).
"""

from __future__ import annotations

import asyncio

import pytest

from uni.tools import visual_action as va_module
from uni.tools.visual_action import VisualActionAgent


class _FakeComputer:
    def __init__(self):
        self.use_human_motion = True
        self.clicks = []

    async def click_human(self, x, y, button="left"):
        self.clicks.append((x, y))
        return __import__("uni.contracts", fromlist=["ToolResult"]).ToolResult(
            success=True, message=f"click {x},{y}"
        )

    async def click(self, x, y, button="left"):
        self.clicks.append((x, y))
        return __import__("uni.contracts", fromlist=["ToolResult"]).ToolResult(
            success=True, message=f"click {x},{y}"
        )


class _FakeVision:
    def __init__(self, locate_result=None, verify_yes=True):
        self.locate_result = locate_result
        self.verify_yes = verify_yes
        self.locate_calls = 0
        self.analyze_calls = 0

    async def find_desktop_element(self, description):
        from uni.contracts import ToolResult

        self.locate_calls += 1
        if self.locate_result is None:
            return ToolResult(success=False, message="не найдено")
        return ToolResult(success=True, data=self.locate_result, message="найдено")

    async def analyze_desktop(self, prompt):
        from uni.contracts import ToolResult

        self.analyze_calls += 1
        if self.verify_yes and "достигнут" in prompt.lower() or "достигнут" in prompt:
            answer = "да, цель достигнута"
        else:
            answer = "нет, пока не достигнуто"
        # verify_yes управляет ответом на вопрос проверки
        answer = "да, цель достигнута" if self.verify_yes else "нет, не достигнуто"
        return ToolResult(success=True, data={"analysis": answer}, message=answer)


def _make_agent(locate_result=None, verify_yes=True, max_steps=8):
    computer = _FakeComputer()
    vision = _FakeVision(locate_result=locate_result, verify_yes=verify_yes)
    return VisualActionAgent(computer, vision, max_steps=max_steps), computer, vision


def test_success_when_verify_yes():
    el = {"x": 100, "y": 100, "width": 80, "height": 30, "confidence": 0.9}
    agent, computer, _ = _make_agent(locate_result=el, verify_yes=True)
    out = asyncio.run(agent.act_on_screen("открой блокнот"))
    assert out["status"] == "success"
    assert len(computer.clicks) == 1
    assert computer.clicks[0] == (140, 115)  # центр


def test_no_click_when_not_found():
    agent, computer, _ = _make_agent(locate_result=None, verify_yes=False)
    out = asyncio.run(agent.act_on_screen("найди несуществующее"))
    assert out["status"] in ("failed", "clarify")
    assert len(computer.clicks) == 0


def test_clarify_on_low_confidence():
    el = {"x": 10, "y": 10, "width": 10, "height": 10, "confidence": 0.2}
    agent, computer, _ = _make_agent(locate_result=el, verify_yes=True)
    out = asyncio.run(agent.act_on_screen("цель"))
    assert out["status"] == "clarify"
    assert len(computer.clicks) == 0


def test_stop_at_max_steps_when_verify_fails():
    el = {"x": 50, "y": 50, "width": 20, "height": 20, "confidence": 0.8}
    agent, computer, _ = _make_agent(locate_result=el, verify_yes=False, max_steps=3)
    out = asyncio.run(agent.act_on_screen("цель", max_steps=3))
    assert out["status"] == "failed"
    assert len(computer.clicks) == 3  # кликал, но проверка не подтвердила


def test_blocked_on_dangerous_goal():
    agent, computer, _ = _make_agent(locate_result={"x": 0, "y": 0, "width": 1, "height": 1, "confidence": 0.9})
    out = asyncio.run(agent.act_on_screen("format disk C:"))
    assert out["status"] == "blocked"
    assert len(computer.clicks) == 0


def test_observe_text_safe_mode():
    agent, computer, vision = _make_agent(locate_result=None, verify_yes=True)
    out = asyncio.run(agent.observe_text("что на экране"))
    assert out["status"] == "success"
    assert len(computer.clicks) == 0
    assert vision.analyze_calls == 1


def test_request_stop_interrupts_cycle():
    # locate стабильно находит элемент, но verify всегда "нет" -> цикл бы шёл
    # до max_steps; ставим stop на 1-м шаге -> interrupted.
    el = {"x": 50, "y": 50, "width": 20, "height": 20, "confidence": 0.9}
    agent, computer, vision = _make_agent(locate_result=el, verify_yes=False, max_steps=5)
    agent.request_stop()
    out = asyncio.run(agent.act_on_screen("цель"))
    assert out["status"] == "interrupted"
    assert len(computer.clicks) == 0  # клик не произошёл после stop
    assert agent.status()["stopped"] is False  # флаг сброшен после прерывания


def test_status_reflects_active_steps():
    el = {"x": 10, "y": 10, "width": 10, "height": 10, "confidence": 0.9}
    agent, computer, vision = _make_agent(locate_result=el, verify_yes=True, max_steps=3)
    st = agent.status()
    assert st["active"] is False  # ещё не запускался
    assert st["steps"] == 0
    out = asyncio.run(agent.act_on_screen("цель"))
    assert out["status"] == "success"
    assert agent.status()["steps"] >= 1


def test_blocked_on_extended_blacklist():
    agent, computer, vision = _make_agent(locate_result={"x": 0, "y": 0, "width": 1, "height": 1, "confidence": 0.9})
    for bad in ("taskkill /f", "powershell что-то", "shutdown /s", "format C:", "net stop spooler", "bcdedit"):
        out = asyncio.run(agent.act_on_screen(bad))
        assert out["status"] == "blocked", f"ожидался blocked для {bad!r}, получил {out['status']}"
    assert len(computer.clicks) == 0


def test_blocked_in_system_zone():
    # элемент в верхней системной зоне (y близко к 0) -> клик заблокирован
    el = {"x": 5, "y": 2, "width": 20, "height": 10, "confidence": 0.9}
    agent, computer, vision = _make_agent(locate_result=el, verify_yes=True)
    out = asyncio.run(agent.act_on_screen("цель", screen_size=(1920, 1080)))
    assert out["status"] == "blocked"
    assert len(computer.clicks) == 0


def test_safe_zone_allows_normal_click():
    # элемент в центре экрана -> клик разрешён
    el = {"x": 900, "y": 500, "width": 100, "height": 40, "confidence": 0.9}
    agent, computer, vision = _make_agent(locate_result=el, verify_yes=True)
    out = asyncio.run(agent.act_on_screen("цель", screen_size=(1920, 1080)))
    assert out["status"] == "success"
    assert len(computer.clicks) == 1

