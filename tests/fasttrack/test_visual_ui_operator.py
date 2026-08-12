import unittest
from unittest.mock import patch

from uni.capabilities.computer import ComputerCapability
from uni.capabilities.vision import parse_spatial_location
from uni.contracts import ToolResult
from uni.visual_ui_operator import VisualUIOperator


class FakeVisualExecutor:
    def __init__(self, vision_success=True):
        self.calls = []
        self.vision_success = vision_success
        self.field_value = ""

    async def execute(self, action, args=None):
        args = args or {}
        self.calls.append((action, args))
        if action == "vision.find_desktop_element":
            if not self.vision_success:
                return ToolResult(success=False, message="too broad")
            if args.get("description") == "Speed slider":
                return ToolResult(
                    success=True,
                    data={"x": 10, "y": 20, "width": 40, "height": 100, "confidence": 0.9},
                    message="found slider",
                )
            return ToolResult(
                success=True,
                data={"x": 10, "y": 20, "width": 40, "height": 20, "confidence": 0.9},
                message="found",
            )
        if action == "computer.find_accessible_element":
            return ToolResult(
                success=True,
                data={"x": 10, "y": 20, "width": 40, "height": 20, "confidence": 1.0},
                message="refined",
            )
        if action == "computer.paste":
            self.field_value = args["text"]
            return ToolResult(success=True, message="pasted")
        if action == "computer.read_accessible_value":
            return ToolResult(success=True, data={"value": self.field_value}, message="read")
        if action == "computer.read_focused_accessible_text":
            return ToolResult(success=True, data={"name": "Address", "value": "https://vk.com/im"}, message="read")
        if action in {"computer.set_accessible_value", "computer.replace_accessible_text"}:
            self.field_value = args["text"]
            return ToolResult(success=True, data={"value": self.field_value}, message="set")
        return ToolResult(success=True, message="ok")


class VisualUIOperatorTests(unittest.IsolatedAsyncioTestCase):
    def test_normalized_moondream_box_is_scaled(self):
        location = parse_spatial_location([0.1, 0.2, 0.2, 0.3], (1000, 500))
        self.assertEqual((location.x, location.y), (100, 100))
        self.assertAlmostEqual(location.width, 100)
        self.assertAlmostEqual(location.height, 50)

    def test_broad_moondream_box_is_never_clickable(self):
        with self.assertRaisesRegex(ValueError, "too broad"):
            parse_spatial_location([0.0, 0.0, 1.0, 0.98], (1000, 500))

    async def test_click_uses_box_center_and_reobserves(self):
        executor = FakeVisualExecutor()
        operator = VisualUIOperator(executor, max_steps=4)
        result = await operator.click_visible("button")
        self.assertTrue(result.success)
        self.assertEqual(executor.calls[1], ("computer.click", {"x": 30, "y": 30}))
        self.assertEqual(executor.calls[2][0], "vision.observe_desktop")

    async def test_draft_does_not_send(self):
        executor = FakeVisualExecutor()
        operator = VisualUIOperator(executor, max_steps=16)
        result = await operator.draft_telegram_message("Ася", "Привет")
        self.assertTrue(result.success)
        names = [name for name, _ in executor.calls]
        self.assertIn("computer.paste", names)
        self.assertNotIn("computer.press", names)
        self.assertTrue(result.data["requires_confirmation"])
        self.assertEqual(result.data["account"], "telegram_uni")
        self.assertEqual(executor.calls[0], ("computer.focus_app", {"app": "telegram_uni"}))

    async def test_confirm_is_separate_enter_action(self):
        executor = FakeVisualExecutor()
        operator = VisualUIOperator(executor, max_steps=4)
        result = await operator.send_focused_draft()
        self.assertTrue(result.success)
        self.assertEqual(executor.calls[0], ("computer.focus_app", {"app": "telegram_uni"}))
        self.assertEqual(executor.calls[-1], ("computer.press", {"key": "enter"}))

    async def test_unknown_telegram_account_fails_closed(self):
        executor = FakeVisualExecutor()
        operator = VisualUIOperator(executor, max_steps=4)
        result = await operator.draft_telegram_message("contact", "text", account="unknown")
        self.assertFalse(result.success)
        self.assertEqual(executor.calls, [])

    async def test_accessibility_refines_an_unsafe_vision_result(self):
        executor = FakeVisualExecutor(vision_success=False)
        operator = VisualUIOperator(executor, max_steps=4)
        result = await operator.click_visible(
            "the visible chat row",
            accessible_name="Ася",
            control_type="list_item",
        )
        self.assertTrue(result.success)
        self.assertEqual(executor.calls[1][0], "computer.find_accessible_element")
        self.assertEqual(executor.calls[2], ("computer.click", {"x": 30, "y": 30}))

    async def test_read_active_url_uses_focused_accessibility_and_restores_page_focus(self):
        executor = FakeVisualExecutor()
        operator = VisualUIOperator(executor, max_steps=5)
        result = await operator.read_active_url()
        self.assertTrue(result.success)
        self.assertEqual(result.data["url"], "https://vk.com/im")
        self.assertIn(("computer.press", {"key": "ctrl+l"}), executor.calls)
        self.assertIn(("computer.read_focused_accessible_text", {}), executor.calls)
        self.assertEqual(executor.calls[-1], ("computer.press", {"key": "esc"}))

    async def test_vertical_slider_uses_requested_height_and_reobserves(self):
        executor = FakeVisualExecutor()
        operator = VisualUIOperator(executor, max_steps=4)
        result = await operator.set_vertical_slider("Speed slider", 25)
        self.assertTrue(result.success)
        self.assertEqual(executor.calls[1], ("computer.click", {"x": 30, "y": 94}))
        self.assertEqual(executor.calls[2], ("vision.observe_desktop", {}))


class TelegramWindowSelectionTests(unittest.TestCase):
    def setUp(self):
        self.computer = ComputerCapability(
            telegram_uni_path=r"C:\LLM\UNI\Telegram\Telegram.exe",
            telegram_user_path=r"C:\Users\user\AppData\Roaming\Telegram Desktop\Telegram.exe",
        )
        self.windows = {
            101: {"pid": 1001, "title": "Telegram"},
            102: {"pid": 1002, "title": "Personal chat"},
        }
        self.paths = {
            1001: r"C:\LLM\UNI\Telegram\Telegram.exe",
            1002: r"C:\Users\user\AppData\Roaming\Telegram Desktop\Telegram.exe",
        }

    def _focus(self, alias):
        def enumerate_windows(callback, extra):
            for hwnd in self.windows:
                callback(hwnd, extra)

        with (
            patch("uni.capabilities.computer.win32gui.EnumWindows", side_effect=enumerate_windows),
            patch(
                "uni.capabilities.computer.win32gui.IsWindowVisible",
                side_effect=lambda hwnd: hwnd in self.windows,
            ),
            patch(
                "uni.capabilities.computer.win32gui.GetWindowText",
                side_effect=lambda hwnd: self.windows[hwnd]["title"],
            ),
            patch(
                "uni.capabilities.computer.win32gui.GetClassName",
                return_value="Qt51519QWindowIcon",
            ),
            patch(
                "uni.capabilities.computer.win32process.GetWindowThreadProcessId",
                side_effect=lambda hwnd: (1, self.windows[hwnd]["pid"]),
            ),
            patch.object(
                self.computer,
                "_query_process_path",
                side_effect=lambda pid: self.paths[pid],
            ),
            patch.object(ComputerCapability, "_activate_window") as activate,
        ):
            result = self.computer._focus_app(alias)
        return result, activate

    def test_uni_alias_selects_only_portable_account(self):
        (success, title), activate = self._focus("telegram_uni")
        self.assertTrue(success)
        self.assertEqual(title, "Telegram")
        activate.assert_called_once_with(101)

    def test_user_alias_selects_only_personal_account(self):
        (success, title), activate = self._focus("telegram_user")
        self.assertTrue(success)
        self.assertEqual(title, "Personal chat")
        activate.assert_called_once_with(102)

    def test_generic_telegram_fails_closed_when_ambiguous(self):
        (success, message), activate = self._focus("telegram")
        self.assertFalse(success)
        self.assertIn("несколько Telegram-клиентов", message)
        activate.assert_not_called()
