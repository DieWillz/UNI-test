from types import SimpleNamespace

import pytest

import uni.capabilities.computer as computer_module
from uni.contracts import Verification
from uni.event_loop import EventLoop
from uni.operator.action_registry import DEFAULT_ACTION_REGISTRY
from uni.operator.planner import MissionPlanner
from uni.tools.executors import ToolExecutor
from uni.utils.file_lock import acquire_lock, release_lock


def test_computer_capability_imports_launch_locks() -> None:
    assert computer_module.acquire_lock is acquire_lock
    assert computer_module.release_lock is release_lock


def test_planner_accepts_python_literal_object_from_local_model() -> None:
    raw = (
        "{'goal':'ignored','steps':[{'id':'1','action':'operator.observe',"
        "'params':{},'retry_budget':0,'dependencies':[]}]}"
    )
    plan = MissionPlanner.parse_plan_text(raw, "inspect desktop", DEFAULT_ACTION_REGISTRY)
    assert plan.goal == "inspect desktop"
    assert plan.steps[0].action == "operator.observe"


@pytest.mark.asyncio
async def test_existing_open_browser_request_forces_desktop_mouse_route() -> None:
    loop = object.__new__(EventLoop)

    async def no_override(_):
        return False

    async def no_speak(_):
        return None

    async def operator(goal):
        assert ToolExecutor._control_mode.get() == "mouse_only"
        assert "coral.ru" in goal
        return SimpleNamespace(
            actions=[], observations=[], verification=Verification(),
            status=SimpleNamespace(value="not_verified"), message="desktop-route",
        )

    loop._maybe_autonomous_override = no_override
    loop._speak = no_speak
    loop._log = lambda *args: None
    loop._clean_answer = lambda value: value
    loop._history = []
    loop.memory = SimpleNamespace()
    loop._current_actions, loop._current_observations = [], []
    loop._agent_ref = SimpleNamespace(run_operator=operator)
    loop.parse_direct_command = lambda _: (_ for _ in ()).throw(
        AssertionError("existing browser request reached direct browser.navigate route")
    )

    answer = await loop._process_input(
        "используя мой браузер который прямо сейчас открыт введи в адресной строке coral.ru"
    )
    assert answer == "desktop-route"
    assert ToolExecutor._control_mode.get() == "auto"
