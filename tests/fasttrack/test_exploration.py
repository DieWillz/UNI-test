import tempfile
import unittest
from types import SimpleNamespace

from uni.config import Config
from uni.contracts import ToolResult
from uni.event_loop import EventLoop
from uni.session_log import SessionLogger


class ExplorationBrain:
    async def chat(self, _messages, **_kwargs):
        return SimpleNamespace(
            error=None,
            text='{"thought":"Сравню собак рядом с человеком.","next_query":"гигантские собаки рядом с человеком"}',
            tool_calls=[],
        )


class ExplorationExecutor:
    def __init__(self, screenshot_dir):
        self.calls = []
        self.screenshot_dir = screenshot_dir

    async def execute(self, name, args=None):
        args = args or {}
        self.calls.append((name, args))
        if name == "browser.search_images":
            return ToolResult(success=True, data={"images": []}, message="images")
        if name == "browser.save_screenshot":
            return ToolResult(success=True, data={"path": str(self.screenshot_dir / "shot.png")}, message="saved")
        if name == "vision.analyze_screen":
            return ToolResult(success=True, data={"analysis": "На экране крупные собаки."}, message="seen")
        return ToolResult(success=True, message="ok")


class ExplorationTests(unittest.IsolatedAsyncioTestCase):
    async def test_exploration_is_bounded_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = SessionLogger(directory)
            executor = ExplorationExecutor(logger.screenshot_dir)
            config = Config()
            config.agent.exploration_steps = 2
            config.agent.speak_responses = False
            loop = EventLoop(
                brain=ExplorationBrain(),
                capabilities=SimpleNamespace(get_names=lambda: []),
                memory=SimpleNamespace(get_context=lambda: "", set=lambda *_: None),
                tool_executor=executor,
                config=config,
                session_logger=logger,
            )
            answer = await loop._explore_web("крупные собаки")
            names = [name for name, _ in executor.calls]
            self.assertEqual(names.count("browser.search_images"), 2)
            self.assertEqual(names.count("browser.save_screenshot"), 2)
            self.assertEqual(names.count("vision.analyze_screen"), 2)
            self.assertNotIn("browser.click_selector", names)
            self.assertIn("2 шага", answer)
            log_text = logger.log_path.read_text(encoding="utf-8")
            self.assertIn("THOUGHT", log_text)
            self.assertIn("SCREENSHOT", log_text)
