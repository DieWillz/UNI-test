"""B-07 Регрессия — 3× integration-сценария управления ПК под зрением.

Сквозные сценарии через VisualActionAgent (с моками computer/vision),
покрывающие ключевые пути: успешное выполнение, блокировка опасной цели,
экстренная остановка. Запускаются как единый набор (3 сценария).
"""

from __future__ import annotations

import asyncio

from uni.contracts import ToolResult
from uni.tools.visual_action import VisualActionAgent


class _Comp:
    def __init__(self):
        self.use_human_motion = True
        self.clicks = []
    async def click_human(self, x, y, button="left"):
        self.clicks.append((x, y))
        return ToolResult(success=True, message="ok")
    async def click(self, x, y, button="left"):
        self.clicks.append((x, y))
        return ToolResult(success=True, message="ok")


class _Vis:
    def __init__(self, locate_result, verify_yes=True):
        self.locate_result = locate_result
        self.verify_yes = verify_yes
    async def find_desktop_element(self, description):
        if self.locate_result is None:
            return ToolResult(success=False, message="не найдено")
        return ToolResult(success=True, data=self.locate_result, message="найдено")
    async def analyze_desktop(self, prompt):
        ans = "да, достигнуто" if self.verify_yes else "нет, не достигнуто"
        return ToolResult(success=True, data={"analysis": ans}, message=ans)


def test_integration_success():
    """Сценарий 1: цель выполнена — клик + verify успех."""
    el = {"x": 10, "y": 10, "width": 20, "height": 20, "confidence": 0.9}
    agent = VisualActionAgent(_Comp(), _Vis(el, verify_yes=True))
    out = asyncio.run(agent.act_on_screen("открой блокнот"))
    assert out["status"] == "verified"
    assert len(agent._computer.clicks) == 1


def test_integration_blocked():
    """Сценарий 2: опасная цель заблокирована (blacklist)."""
    agent = VisualActionAgent(_Comp(), _Vis(None))
    out = asyncio.run(agent.act_on_screen("taskkill /f /im notepad.exe"))
    assert out["status"] == "blocked"
    assert len(agent._computer.clicks) == 0


def test_integration_stop():
    """Сценарий 3: экстренная остановка прерывает цикл."""
    # locate стабильно находит, но verify всегда "нет" -> цикл бы шёл до max_steps;
    # ставим stop на 1-м шаге -> interrupted, клик не производится.
    el = {"x": 5, "y": 5, "width": 10, "height": 10, "confidence": 0.9}
    agent = VisualActionAgent(_Comp(), _Vis(el, verify_yes=False), max_steps=5)
    agent.request_stop()
    out = asyncio.run(agent.act_on_screen("цель"))
    assert out["status"] == "interrupted"
    assert len(agent._computer.clicks) == 0
