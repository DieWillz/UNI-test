import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace

from uni.config import Config
from uni.contracts import ToolResult
from uni.event_loop import EventLoop
from uni.roles.loader import RoleLoader


class FakeBrain:
    def __init__(self):
        self.messages = None

    async def chat(self, messages, **_kwargs):
        self.messages = messages
        return SimpleNamespace(error=None, text="короткий ответ", tool_calls=[])


class FakeMemory:
    def get_context(self, *args):
        return ""

    def set(self, *_args):
        return None


class TrackingExecutor:
    def __init__(self):
        self.audio_active = 0
        self.max_audio_active = 0
        self.browser_started = asyncio.Event()
        self.browser_release = asyncio.Event()

    async def execute(self, name, _args=None):
        if name in {"speech.listen", "speech.speak"}:
            self.audio_active += 1
            self.max_audio_active = max(self.max_audio_active, self.audio_active)
            await asyncio.sleep(0.03)
            self.audio_active -= 1
            if name == "speech.listen":
                return ToolResult(success=True, data="тест", message="ok")
            return ToolResult(success=True, message="ok")
        if name == "browser.navigate":
            self.browser_started.set()
            await self.browser_release.wait()
            return ToolResult(success=True, message="opened")
        return ToolResult(success=True, message="ok")


class RealtimeRoleTests(unittest.IsolatedAsyncioTestCase):
    def make_loop(self):
        config = Config()
        config.agent.speak_responses = True
        executor = TrackingExecutor()
        loop = EventLoop(
            brain=FakeBrain(),
            capabilities=SimpleNamespace(get_names=lambda: []),
            memory=FakeMemory(),
            tool_executor=executor,
            config=config,
            role_prompt="ROLE MARKER",
        )
        return loop, executor

    def test_role_loads_independently_of_cwd(self):
        role = RoleLoader().load("xtoys_mistress")
        self.assertIn("Госпожа", role.system_prompt)
        self.assertEqual(RoleLoader().roles_dir, Path(__file__).resolve().parents[2] / "uni" / "roles")

    async def test_role_is_in_llm_system_prompt(self):
        loop, _ = self.make_loop()
        await loop._free_form("привет")
        self.assertIn("ROLE MARKER", loop.brain.messages[0]["content"])

    async def test_recording_and_tts_do_not_overlap(self):
        loop, executor = self.make_loop()
        await asyncio.gather(loop._listen_once(), loop._speak("ответ"))
        self.assertEqual(executor.max_audio_active, 1)

    async def test_slow_browser_action_does_not_block_next_utterance(self):
        loop, executor = self.make_loop()
        self.assertTrue(loop._schedule_input("открой сайт example.com"))
        await asyncio.wait_for(executor.browser_started.wait(), timeout=1)
        self.assertTrue(loop._schedule_input("помощь"))
        await asyncio.sleep(0.08)
        self.assertGreaterEqual(len(loop._background_tasks), 1)
        executor.browser_release.set()
        await asyncio.gather(*list(loop._background_tasks), return_exceptions=True)
        self.assertEqual(len(loop._background_tasks), 0)
