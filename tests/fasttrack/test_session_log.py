import tempfile
import unittest
from pathlib import Path

from uni.session_log import SessionLogger


class SessionLoggerTests(unittest.TestCase):
    def test_events_are_written_and_secrets_are_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = SessionLogger(directory)
            logger.log("user", "мой пароль: secret-value и token=abc123")
            text = logger.log_path.read_text(encoding="utf-8")
            self.assertIn("USER", text)
            self.assertIn("[REDACTED]", text)
            self.assertNotIn("secret-value", text)
            self.assertNotIn("abc123", text)
            self.assertTrue(logger.screenshot_dir.is_dir())

    def test_disabled_logger_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "logs"
            logger = SessionLogger(root, enabled=False)
            logger.log("user", "hello")
            self.assertFalse(root.exists())
