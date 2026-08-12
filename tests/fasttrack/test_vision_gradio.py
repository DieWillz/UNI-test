import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from uni.capabilities.vision import VisionCapability


class FakeClient:
    def __init__(self, *_args, **_kwargs):
        self.paths = []

    def predict(self, *, img, prompt, api_name):
        path = img.path if hasattr(img, "path") else img["path"]
        self.paths.append(path)
        if not os.path.exists(path):
            raise AssertionError("temporary image must exist during predict")
        return f"{api_name}: {prompt}"


class VisionGradioTests(unittest.TestCase):
    def test_temp_image_is_removed_after_predict(self):
        config = SimpleNamespace(
            capabilities=SimpleNamespace(
                vision=SimpleNamespace(
                    gradio_url="http://127.0.0.1:7860/",
                    gradio_api_name="/answer_question",
                    gradio_fallback_api_name="/answer_question_1",
                )
            )
        )
        capability = object.__new__(VisionCapability)
        capability.config = config
        capability._gradio_client = None
        fake = FakeClient()
        with patch("gradio_client.Client", return_value=fake):
            answer = capability._gradio_predict(Image.new("RGB", (16, 16), "white"), "describe")
        self.assertIn("/answer_question", answer)
        self.assertEqual(len(fake.paths), 1)
        self.assertFalse(os.path.exists(fake.paths[0]))

    def test_fallback_is_limited_to_missing_endpoint_errors(self):
        self.assertTrue(VisionCapability._is_missing_endpoint_error(RuntimeError("api_name not found")))
        self.assertFalse(VisionCapability._is_missing_endpoint_error(RuntimeError("model out of memory")))
