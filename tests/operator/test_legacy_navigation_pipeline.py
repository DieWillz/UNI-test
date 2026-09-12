"""Legacy navigation uses the real mission executor/verifier, never tool ACKs."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from uni.contracts import ToolResult, Verification, VerificationStatus
from uni.event_loop import EventLoop
from uni.operator.action_registry import DEFAULT_ACTION_REGISTRY
from uni.operator.models import SceneSnapshot
from uni.operator.runtime import OperatorRuntime


class NavigationTool:
    def __init__(self):
        self.calls = []

    def canonical_name(self, name):
        return DEFAULT_ACTION_REGISTRY.canonical_name(name)

    async def execute(self, name, params):
        self.calls.append((name, params))
        return ToolResult(success=True, message="navigation accepted")


class NavigationScene:
    def __init__(self, after_url):
        self.after_url = after_url
        self.calls = 0

    async def observe(self):
        self.calls += 1
        observed = datetime.now(timezone.utc).isoformat()
        return SceneSnapshot(browser={
            "url": self.after_url if self.calls > 1 else "https://before.invalid/",
            "session_id": "session-1", "tab_id": "tab-1",
            "snapshot_id": f"snapshot-{self.calls}", "observed_at": observed,
        })


@pytest.mark.parametrize("after_url, expected", [
    ("https://before.invalid/", VerificationStatus.NOT_VERIFIED),
    ("https://requested.invalid/", VerificationStatus.VERIFIED),
])
async def test_navigation_ack_requires_fresh_matching_observation(after_url, expected):
    tool = NavigationTool()
    runtime = OperatorRuntime(brain=SimpleNamespace(), browser_session=SimpleNamespace(),
                              computer=SimpleNamespace(), vision=None, tool_executor=tool)
    scenes = NavigationScene(after_url)
    runtime.perception = runtime.executor.perception = scenes
    loop = object.__new__(EventLoop)
    loop.tool_executor = tool
    loop._agent_ref = SimpleNamespace(operator=runtime)
    loop._tool_lock = asyncio.Lock()
    loop._log = lambda *_args: None
    loop._current_actions = []
    loop._current_observations = []
    loop._current_verification = Verification()

    result = await loop._run_tool("browser.navigate", {"url": "https://requested.invalid/"})

    assert scenes.calls == 2
    assert tool.calls == [("browser.navigate", {"url": "https://requested.invalid/"})]
    assert loop._current_verification.status is expected
    assert len(loop._current_observations) == 2
    assert bool(loop._current_verification.evidence) is (expected is VerificationStatus.VERIFIED)
    if expected is VerificationStatus.NOT_VERIFIED:
        assert "not_verified" in result.message
