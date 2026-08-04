import unittest

from uni.capabilities.xtoys import XToysCapability


class FakeSpeedElement:
    """Mimics the Fredorch Speed panel on xtoys.app: a WIDE block (~1164x655),
    not a thin vertical slider. Text includes 'Speed' and the current value."""

    def __init__(self):
        self.text = "Fredorch Rotary\nSpeed\n0"

    async def is_visible(self):
        return True

    async def inner_text(self):
        return self.text

    async def evaluate(self, _script):
        return "Fredorch Rotary\nSpeed\n0"

    async def bounding_box(self):
        # wide panel: width > height (the old geometry guard rejected this)
        return {"x": 100.0, "y": 50.0, "width": 1164.0, "height": 655.0}


class FakeLocator:
    def __init__(self, element):
        self.element = element

    async def count(self):
        return 1

    def nth(self, _index):
        return self.element


class FakeMouse:
    def __init__(self, element):
        self.element = element
        self.moves = []
        self.clicks = []

    async def move(self, x, y, steps=1):
        self.moves.append((x, y, steps))

    async def click(self, x, y):
        self.clicks.append((x, y))
        # a click at the top of the panel sets a high value; bottom -> low.
        # For the test we just bump it to 25 to simulate a verified change.
        self.element.text = "Fredorch Rotary\nSpeed\n25"


class FakePage:
    def __init__(self):
        self.element = FakeSpeedElement()
        self.mouse = FakeMouse(self.element)

    async def evaluate(self, script, _args=None):
        # The XToys capability tries two JS probes. Distinguish them by content.
        if "querySelectorAll('input[type=\"range\"]')" in script:
            return {"ok": False, "reason": "На странице нет видимого input[type=range]"}
        # Otherwise treat it as the Speed-panel finder (the new _FIND_SPEED_JS).
        r = await self.element.bounding_box()
        return {
            "ok": True,
            "rect": {"x": r["x"], "y": r["y"], "w": r["width"], "h": r["height"]},
            "displayed": int(self.element.text.split("\n")[-1]),
        }

    def locator(self, _selector):
        return FakeLocator(self.element)

    async def wait_for_timeout(self, _milliseconds):
        return None


class FakeSession:
    def __init__(self):
        self.page = FakePage()

    async def page_for_host(self, _host, create_url=None):
        return self.page


class XToysCustomSpeedTests(unittest.IsolatedAsyncioTestCase):
    def test_vertical_point_maps_zero_to_bottom_and_hundred_to_top(self):
        box = {"x": 100.0, "y": 50.0, "width": 40.0, "height": 200.0}
        self.assertEqual(XToysCapability._vertical_slider_point(box, 0), (120.0, 247.0))
        self.assertEqual(XToysCapability._vertical_slider_point(box, 100), (120.0, 53.0))

    async def test_custom_speed_wide_panel_is_clicked_and_ui_value_verified(self):
        session = FakeSession()
        capability = XToysCapability(session, url="https://xtoys.app", max_intensity=90)
        result = await capability.set_intensity(value=25)
        self.assertTrue(result.success, result.message)
        self.assertEqual(result.data["control"], "custom_speed_panel")
        self.assertEqual(result.data["displayed_value"], 25)
        self.assertTrue(result.data["verified_ui"])
        self.assertFalse(result.data["verified_physical"])
        self.assertEqual(session.page.mouse.moves[0][2], 12)

    async def test_maximum_reaches_ui_without_clamp(self):
        # По ТЗ п.4: кламп max_intensity снят — запрос ДОХОДИТ до UI (клик есть).
        # В этом мок-UI клик имитирует фикс 25, поэтому верификация UI не проходит
        # (это особенность тестового FakeMouse, не кламп). Главное — кламп убран.
        session = FakeSession()
        capability = XToysCapability(session, url="https://xtoys.app", max_intensity=90)
        result = await capability.set_intensity(value=95)
        self.assertTrue(session.page.mouse.clicks)  # дошло до UI, клампа нет
        self.assertFalse(result.success)  # UI-верификация не подтвердила 95 в моке


if __name__ == "__main__":
    unittest.main()
