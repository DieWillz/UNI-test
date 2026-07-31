import unittest

from uni.contracts import ToolResult
from uni.tools.executors import ToolExecutor


class FakeCapability:
    def __init__(self):
        self.calls = []

    async def execute(self, action, **kwargs):
        self.calls.append((action, kwargs))
        return ToolResult(success=True, message="ok", data=kwargs)


class FakeRegistry:
    def __init__(self, capability):
        self.capability = capability

    def get(self, name):
        return self.capability if name == "browser" else None


class ExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_dotted_and_api_alias_use_same_route(self):
        capability = FakeCapability()
        executor = ToolExecutor(FakeRegistry(capability))
        first = await executor.execute("browser.search_web", {"query": "one"})
        second = await executor.execute("browser_search_web", {"query": "two"})
        self.assertTrue(first.success and second.success)
        self.assertEqual(capability.calls, [("search_web", {"query": "one"}), ("search_web", {"query": "two"})])

    async def test_unknown_tool_is_failure(self):
        result = await ToolExecutor(FakeRegistry(FakeCapability())).execute("unknown.tool", {})
        self.assertFalse(result.success)
