from types import SimpleNamespace

import pytest

from uni.contracts import ToolResult, Verification
from uni.event_loop import EventLoop
from uni.operator.action_registry import DEFAULT_ACTION_REGISTRY
from uni.operator.executor import MissionExecutor
from uni.operator.models import PlanStep, SceneSnapshot, TargetSpec
from uni.operator.perception import PerceptionBroker
from uni.operator.permissions import MissionPermissions
from uni.operator.planner import MissionPlanner
from uni.operator.windows_provider import WindowsProvider
from uni.tools.executors import ToolExecutor


@pytest.fixture
def mouse_mode():
    token = ToolExecutor.set_control_mode('mouse_only')
    try:
        yield
    finally:
        ToolExecutor.reset_control_mode(token)


@pytest.mark.asyncio
async def test_mouse_perception_never_attaches_to_browser(mouse_mode):
    calls = []
    async def browser():
        calls.append('cdp')
        return SceneSnapshot()
    async def windows():
        return SceneSnapshot(active_window={'title': 'Chrome'})
    scene = await PerceptionBroker(SimpleNamespace(inspect=browser), SimpleNamespace(inspect=windows)).observe()
    assert calls == []
    assert scene.active_window['title'] == 'Chrome'


def test_mouse_planner_offers_desktop_not_browser_or_files(mouse_mode):
    import json
    catalog = json.loads(MissionPlanner(None)._catalog_text())
    names = {item['name'] for item in catalog}
    assert 'operator.desktop.click' in names
    assert 'operator.desktop.fill' in names
    assert not any(name.startswith(('browser.', 'operator.browser.', 'operator.file.')) for name in names)


@pytest.mark.asyncio
async def test_mouse_executor_rejects_browser_even_for_supplied_plan(mouse_mode):
    executor = MissionExecutor(planner=None, perception=None, tool_executor=None)
    async def unexpected_dispatch(*args, **kwargs):
        raise AssertionError('mouse mode dispatched a browser action')
    executor._call_action = unexpected_dispatch
    result = await executor._execute_step('test', PlanStep(id='1', action='browser.navigate', params={'url': 'https://example.org'}), SceneSnapshot(), MissionPermissions())
    assert result.status.value == 'blocked'
    assert 'mouse_only' in result.error


@pytest.mark.asyncio
@pytest.mark.parametrize('action,expected', [('click', ['click_human']), ('fill', ['click_human', 'press', 'paste'])])
async def test_mouse_desktop_uses_physical_input_not_uia_mutation(mouse_mode, action, expected):
    mutations = []
    async def execute(action_name, **params):
        if action_name == 'list_visible_windows':
            return ToolResult(success=True, data={'windows': []})
        if action_name == 'inspect_accessible_elements':
            return ToolResult(success=True, data={'elements': [{'name': 'Address', 'role': 'Edit', 'x': 10, 'y': 20, 'width': 100, 'height': 30}]})
        mutations.append(action_name)
        return ToolResult(success=True)
    result = await WindowsProvider(SimpleNamespace(execute=execute)).act(action, target=TargetSpec(name='Address'), text='example.org')
    assert result.success
    assert mutations == expected


@pytest.mark.asyncio
async def test_chat_mouse_request_bypasses_direct_and_keeps_previous_goal():
    loop = object.__new__(EventLoop)
    async def no_override(_): return False
    async def no_speak(_): pass
    async def operator(goal):
        assert ToolExecutor._control_mode.get() == 'mouse_only'
        assert 'Coral Travel' in goal
        return SimpleNamespace(actions=[], observations=[], verification=Verification(), status=SimpleNamespace(value='not_verified'), message='not_verified')
    loop._maybe_autonomous_override = no_override
    loop._speak = no_speak
    loop._log = lambda *a: None
    loop._clean_answer = lambda s: s
    loop._history = [{'role': 'user', 'content': 'Юни открой сайт Coral Travel'}]
    loop.memory = SimpleNamespace()
    loop._current_actions, loop._current_observations = [], []
    loop._agent_ref = SimpleNamespace(run_operator=operator)
    def wrong_route(_): raise AssertionError('mouse request reached direct/CDP route')
    loop.parse_direct_command = wrong_route
    assert await loop._process_input('используй мышку и запусти прямо в моем открытом окне') == 'not_verified'
    assert ToolExecutor._control_mode.get() == 'auto'
