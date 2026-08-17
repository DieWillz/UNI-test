"""Тест маршрутизации Agent.act_on_screen (N-04b).

Проверяет, что Agent.act_on_screen собирает VisualActionAgent из capability
computer/vision и делегирует цикл, не ломая ничего. Без реального конфига:
создаём объект Agent в обход __init__ и подменяем capabilities/session_logger/speech.
"""

from __future__ import annotations

import asyncio

from uni.agent import Agent


class _FakeCap:
    def __init__(self, name):
        self.name = name

    def get(self, key):
        return {"computer": self._computer, "vision": self._vision}.get(key)

    def register(self, cap):
        pass


class _FakeComputer:
    use_human_motion = True

    def __init__(self):
        self.clicks = []

    async def click_human(self, x, y, button="left"):
        self.clicks.append((x, y))
        from uni.contracts import ToolResult
        return ToolResult(success=True, message=f"click {x},{y}")


class _FakeVision:
    def __init__(self, locate=None, verify_yes=True):
        self.locate = locate
        self.verify_yes = verify_yes
        self.analyze_calls = 0

    async def find_desktop_element(self, desc):
        from uni.contracts import ToolResult
        if self.locate is None:
            return ToolResult(success=False, message="нет")
        return ToolResult(success=True, data=self.locate, message="найдено")

    async def analyze_desktop(self, prompt):
        from uni.contracts import ToolResult
        self.analyze_calls += 1
        ans = "да, цель достигнута" if self.verify_yes else "нет"
        return ToolResult(success=True, data={"analysis": ans}, message=ans)


class _FakeSessionLogger:
    enabled = False  # logger выключен -> лямбда log не дёрнется (проверка безопасности)

    def log(self, event, message):
        pass


class _FakeToolExecutor:
    """Минимальный double для Agent.tool_executor (нужен act_on_screen)."""
    def __init__(self):
        self.mode = "auto"
        self._token = 0

    def set_control_mode(self, control_mode: str):
        self.mode = control_mode
        self._token += 1
        return self._token

    def reset_control_mode(self, token):
        self.mode = "auto"
        return True


def _make_agent(locate=None, verify_yes=True):
    agent = Agent.__new__(Agent)  # обход тяжёлого __init__
    agent.session_logger = _FakeSessionLogger()


    class _Speech:
        spoken = []

        async def speak(self, text):
            _Speech.spoken.append(text)

    agent.speech = _Speech()

    computer = _FakeComputer()
    vision = _FakeVision(locate=locate, verify_yes=verify_yes)
    registry = _FakeCap("reg")
    registry._computer = computer
    registry._vision = vision
    agent.capabilities = registry
    agent.tool_executor = _FakeToolExecutor()
    return agent, computer, vision


def test_act_on_screen_success():
    el = {"x": 100, "y": 100, "width": 80, "height": 30, "confidence": 0.9}
    agent, computer, _ = _make_agent(locate=el, verify_yes=True)
    out = asyncio.run(agent.act_on_screen("открой блокнот"))
    assert out["status"] == "verified"
    assert len(computer.clicks) == 1
    assert computer.clicks[0] == (140, 115)


def test_act_on_screen_blocked_on_dangerous_goal():
    agent, computer, _ = _make_agent(locate={"x": 0, "y": 0, "width": 1, "height": 1, "confidence": 0.9})
    out = asyncio.run(agent.act_on_screen("format disk C:"))
    assert out["status"] == "blocked"
    assert len(computer.clicks) == 0


def test_act_on_screen_missing_capability():
    agent = Agent.__new__(Agent)
    agent.session_logger = _FakeSessionLogger()

    class _EmptyReg:
        def get(self, key):
            return None

    agent.capabilities = _EmptyReg()
    out = asyncio.run(agent.act_on_screen("цель"))
    assert out["status"] == "failed"
    assert "capability" in out["error"]
