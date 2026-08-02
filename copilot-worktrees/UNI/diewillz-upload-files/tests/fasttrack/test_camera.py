import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from uni.capabilities.camera import CameraCapability
from uni.config import Config
from uni.contracts import ToolResult
from uni.event_loop import EventLoop


class FakeCapture:
    def __init__(self, *_args, **_kwargs):
        self.opened = True
        self.released = False

    def isOpened(self):
        return self.opened and not self.released

    def set(self, *_args):
        return True

    def read(self):
        return True, np.zeros((120, 160, 3), dtype=np.uint8)

    def release(self):
        self.released = True


class CameraCapabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_camera_refuses_to_start_without_notice(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "uni.capabilities.camera.cv2.VideoCapture"
        ) as video_capture:
            camera = CameraCapability(directory)
            result = await camera.start(notice_ack=False)
            self.assertFalse(result.success)
            video_capture.assert_not_called()

    async def test_announced_camera_captures_and_releases(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "uni.capabilities.camera.cv2.VideoCapture", side_effect=FakeCapture
        ):
            camera = CameraCapability(directory)
            self.assertTrue((await camera.start(notice_ack=True)).success)
            frame = await camera.snapshot("test")
            self.assertTrue(frame.success)
            self.assertTrue(Path(frame.data["path"]).is_file())
            self.assertEqual(frame.data["brightness"], 0.0)
            stopped = await camera.stop()
            self.assertTrue(stopped.success)
            self.assertTrue(stopped.data["was_open"])


class FakeExecutor:
    def __init__(self, events):
        self.events = events

    async def execute(self, action, args=None):
        self.events.append(action)
        if action == "camera.snapshot":
            return ToolResult(success=True, data={"path": "frame.jpg"}, message="frame")
        if action == "vision.analyze_file":
            return ToolResult(success=True, data={"analysis": "видна комната"}, message="seen")
        return ToolResult(success=True, message="ok")


class FakeMemory:
    def get_context(self):
        return ""

    def get(self, _key, default=None):
        return default

    def set(self, _key, _value):
        return None


class FakeCapabilities:
    def get_names(self):
        return []


class CameraEventLoopTests(unittest.IsolatedAsyncioTestCase):
    def make_loop(self, events):
        config = Config()
        config.capabilities.camera.sample_interval_seconds = 0.05
        config.capabilities.camera.reminder_interval_seconds = 0.05
        return EventLoop(
            brain=None,
            capabilities=FakeCapabilities(),
            memory=FakeMemory(),
            tool_executor=FakeExecutor(events),
            config=config,
        )

    async def test_one_shot_notice_precedes_camera_start_and_stop(self):
        events = []
        loop = self.make_loop(events)

        async def announced(text):
            events.append(f"speak:{text}")
            return True

        loop._speak = announced
        answer = await loop._camera_look()
        self.assertTrue(events[0].startswith("speak:Я включаю камеру"))
        self.assertLess(events.index("camera.start"), events.index("camera.snapshot"))
        self.assertLess(events.index("camera.snapshot"), events.index("camera.stop"))
        self.assertIn("Я закончила смотреть", answer)

    async def test_long_watch_reminds_and_announces_completion(self):
        events = []
        loop = self.make_loop(events)

        async def announced(text):
            events.append(f"speak:{text}")
            return True

        loop._speak = announced
        await loop._camera_watch_worker(0.16)
        spoken = " ".join(item for item in events if item.startswith("speak:"))
        self.assertIn("всё ещё наблюдаю", spoken)
        self.assertIn("закончила наблюдение", spoken)
        self.assertIn("camera.stop", events)
