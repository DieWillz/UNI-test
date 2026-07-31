import json
import tempfile
import unittest
from pathlib import Path

from uni.working_memory import WorkingMemory


class WorkingMemoryTests(unittest.TestCase):
    def test_complete_exchange_persists_and_restores_as_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "working.json"
            memory = WorkingMemory(path)
            self.assertTrue(memory.append_exchange("Открой XToys", "XToys открыт."))
            restored = WorkingMemory(path)
            self.assertEqual(
                restored.recent_messages(),
                [
                    {"role": "user", "content": "Открой XToys"},
                    {"role": "assistant", "content": "XToys открыт."},
                ],
            )

    def test_transient_and_last_tool_values_are_not_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "working.json"
            memory = WorkingMemory(path)
            memory.set("_pending_message", {"text": "draft"})
            memory.set("last_browser.navigate", {"url": "https://example.com"})
            restored = WorkingMemory(path)
            self.assertIsNone(restored.get("_pending_message"))
            self.assertIsNone(restored.get("last_browser.navigate"))
            self.assertEqual(restored.list_keys(), [])

    def test_explicit_facts_are_separate_from_dialogue(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "working.json"
            memory = WorkingMemory(path)
            memory.set("preferred_name", "DieWill")
            memory.append_exchange("Привет", "Привет!")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["version"], 2)
            self.assertEqual(data["facts"], {"preferred_name": "DieWill"})
            self.assertEqual(len(data["dialogue"]), 1)

    def test_secrets_are_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "working.json"
            memory = WorkingMemory(path)
            memory.append_exchange("пароль: secret123", "token=abcdef принят")
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("secret123", text)
            self.assertNotIn("abcdef", text)
            self.assertIn("[REDACTED]", text)

    def test_subtitle_hallucination_is_not_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "working.json"
            memory = WorkingMemory(path)
            saved = memory.append_exchange("Редактор субтитров Н. Закомолдина", "Что открыть?")
            self.assertFalse(saved)
            self.assertEqual(memory.recent_messages(), [])

    def test_legacy_file_is_backed_up_and_technical_keys_are_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "working.json"
            path.write_text(
                json.dumps({"last_browser.navigate": "junk", "preferred_name": "DieWill"}),
                encoding="utf-8",
            )
            memory = WorkingMemory(path)
            self.assertEqual(memory.get("preferred_name"), "DieWill")
            self.assertIsNone(memory.get("last_browser.navigate"))
            self.assertEqual(len(list(Path(directory).glob("working.legacy-*.json"))), 1)

    def test_dialogue_is_bounded_by_complete_turns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "working.json"
            memory = WorkingMemory(path, max_dialogue_turns=5)
            for index in range(8):
                memory.append_exchange(f"user {index}", f"assistant {index}")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(data["dialogue"]), 5)
            self.assertEqual(data["dialogue"][0]["user"], "user 3")


if __name__ == "__main__":
    unittest.main()
