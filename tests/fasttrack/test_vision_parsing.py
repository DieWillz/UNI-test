import unittest

from uni.capabilities.vision import ElementLocation, extract_json_value


class VisionParsingTests(unittest.TestCase):
    def test_plain_and_fenced_json(self):
        plain = extract_json_value('{"x":1,"y":2,"width":3,"height":4,"confidence":0.9}')
        fenced = extract_json_value('```json\n{"x":1,"y":2,"width":3,"height":4,"confidence":0.9}\n```')
        self.assertEqual(plain, fenced)
        self.assertEqual(ElementLocation.model_validate(fenced).confidence, 0.9)

    def test_leading_text_and_null(self):
        self.assertEqual(extract_json_value('Ответ: {"ok": true}'), {"ok": True})
        self.assertIsNone(extract_json_value("null"))

    def test_trailing_text_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_json_value('{"ok": true} trailing')

    def test_invalid_bounds_are_rejected(self):
        with self.assertRaises(Exception):
            ElementLocation(x=-1, y=0, width=1, height=1, confidence=2)
