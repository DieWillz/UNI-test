"""Тест маршрутизации голосовых команд в event_loop (N-13).

Проверяет, что EventLoop._try_visual_command перехватывает фразы
«открой X» / «кликни X» / «нажми X» и направляет в Agent.act_on_screen,
а обычный текст (не команда ПК) возвращает None (передаётся LLM-циклу).
"""

from __future__ import annotations

import asyncio

from uni.event_loop import EventLoop


class _FakeVisualAgent:
    def __init__(self, status="success"):
        self.calls = []
        self._status = status

    async def act_on_screen(self, goal, max_steps=8, screen_size=None):
        self.calls.append(goal)
        return {"status": self._status, "steps": [], "error": None}


def _make_loop(status="success"):
    loop = EventLoop.__new__(EventLoop)  # обход тяжёлого __init__
    agent = _FakeVisualAgent(status=status)
    loop._agent_ref = agent
    return loop, agent


def test_visual_route_opens_target():
    loop, agent = _make_loop("success")
    out = asyncio.run(loop._try_visual_command("открой блокнот"))
    assert out is not None
    assert "Готово" in out
    assert agent.calls == ["открой блокнот"] or agent.calls == ["блокнот"]


def test_visual_route_click_target():
    loop, agent = _make_loop("success")
    out = asyncio.run(loop._try_visual_command("кликни по кнопке сохранить"))
    assert out is not None
    assert "Готово" in out


def test_visual_route_blocked():
    loop, agent = _make_loop("blocked")
    out = asyncio.run(loop._try_visual_command("нажми запустить задачу"))
    assert out is not None
    assert "заблокирована" in out


def test_non_visual_text_returns_none():
    loop, agent = _make_loop("success")
    out = asyncio.run(loop._try_visual_command("привет, как дела?"))
    assert out is None
    assert agent.calls == []  # act_on_screen не вызывался


def test_visual_route_no_agent_returns_none():
    loop = EventLoop.__new__(EventLoop)
    loop._agent_ref = None
    out = asyncio.run(loop._try_visual_command("открой настройки"))
    assert out is None
