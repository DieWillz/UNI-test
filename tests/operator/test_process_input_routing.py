from __future__ import annotations

from types import SimpleNamespace

import pytest

from uni.event_loop import EventLoop


class Memory:
    def append_exchange(self, *_args):
        return True


async def no_override(_text):
    return False


async def no_speak(_text):
    return True


def make_loop() -> EventLoop:
    loop = object.__new__(EventLoop)
    loop._maybe_autonomous_override = no_override
    loop._log = lambda *_args, **_kwargs: None
    loop._speak = no_speak
    loop._clean_answer = lambda text: text
    loop._history = []
    loop.memory = Memory()
    return loop


@pytest.mark.asyncio
async def test_direct_command_has_priority_over_visual_or_operator() -> None:
    loop = make_loop()
    direct = SimpleNamespace(action="browser.navigate", args={"url": "https://x"})
    loop.parse_direct_command = lambda _text: direct
    loop._execute_direct = lambda _direct: _async_value("direct")
    loop._try_operator_mission = lambda _text: _async_fail("operator should not run")
    loop._try_visual_command = lambda _text: _async_fail("visual should not run")

    assert await loop._process_input("открой сайт x.com") == "direct"


async def _async_value(value):
    return value


async def _async_fail(message):
    raise AssertionError(message)


@pytest.mark.asyncio
async def test_complex_task_uses_operator_before_legacy_visual_fallback() -> None:
    loop = make_loop()
    loop.parse_direct_command = lambda _text: None
    loop._try_operator_mission = lambda _text: _async_value("operator")
    loop._try_visual_command = lambda _text: _async_fail("visual should not run")
    loop._free_form = lambda _text: _async_fail("free form should not run")

    result = await loop._process_input("Открой браузер, найди Blender и скачай установщик")

    assert result == "operator"


@pytest.mark.asyncio
async def test_open_start_routes_to_operator() -> None:
    """'открой Пуск' goes to Operator."""
    loop = make_loop()
    loop.parse_direct_command = lambda _text: None
    loop._try_operator_mission = lambda _text: _async_value("operator")
    loop._try_visual_command = lambda _text: _async_fail("visual should not run")
    loop._free_form = lambda _text: _async_fail("free form should not run")

    result = await loop._process_input("открой Пуск")

    assert result == "operator"


@pytest.mark.asyncio
async def test_open_paint_routes_to_operator() -> None:
    """'открой Paint' goes to Operator."""
    loop = make_loop()
    loop.parse_direct_command = lambda _text: None
    loop._try_operator_mission = lambda _text: _async_value("operator")
    loop._try_visual_command = lambda _text: _async_fail("visual should not run")
    loop._free_form = lambda _text: _async_fail("free form should not run")

    result = await loop._process_input("открой Paint")

    assert result == "operator"


@pytest.mark.asyncio
async def test_open_website_routes_to_operator() -> None:
    """'открой сайт coral travel' goes to Operator."""
    loop = make_loop()
    loop.parse_direct_command = lambda _text: None
    loop._try_operator_mission = lambda _text: _async_value("operator")
    loop._try_visual_command = lambda _text: _async_fail("visual should not run")
    loop._free_form = lambda _text: _async_fail("free form should not run")

    result = await loop._process_input("открой сайт coral travel")

    assert result == "operator"


@pytest.mark.asyncio
async def test_question_stays_in_free_form() -> None:
    """Questions stay in free form, not Operator."""
    loop = make_loop()
    loop.parse_direct_command = lambda _text: None
    # Mocks mimic real methods: return None for non-matching inputs
    async def mock_operator(_text):
        return None
    async def mock_visual(_text):
        return None
    loop._try_operator_mission = mock_operator
    loop._try_visual_command = mock_visual
    loop._free_form = lambda _text: _async_value("free_form")

    result = await loop._process_input("что такое Playwright?")

    assert result == "free_form"
