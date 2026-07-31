import unittest

from uni.capabilities.xtoys import XToysCapability


class FakeSpeedElement:
    def __init__(self):
        self.text = "Speed\n0"

    async def is_visible(self):
        return True

    async def inner_text(self):
        return self.text

    async def evaluate(self, _script):
        return "Fredorch Rotary\nSpeed\n0"

    async def bounding_box(self):
        return {"x": 100.0, "y": 50.0, "width": 40.0, "height": 200.0}


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
        self.element.text = "Speed\n25"


class FakePage:
    def __init__(self):
        self.element = FakeSpeedElement()
        self.mouse = FakeMouse(self.element)

    async def evaluate(self, _script, _args):
        return {"ok": False, "reason": "На странице нет видимого input[type=range]"}

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

    async def test_custom_speed_div_is_clicked_and_ui_value_verified(self):
        session = FakeSession()
        capability = XToysCapability(session, url="https://xtoys.app", max_intensity=50)
        result = await capability.set_intensity(value=25)
        self.assertTrue(result.success)
        self.assertEqual(result.data["control"], "custom_vertical_speed")
        self.assertEqual(result.data["displayed_value"], 25)
        self.assertTrue(result.data["verified_ui"])
        self.assertFalse(result.data["verified_physical"])
        self.assertEqual(session.page.mouse.moves[0][2], 12)

    async def test_maximum_is_rejected_before_any_click(self):
        session = FakeSession()
        capability = XToysCapability(session, url="https://xtoys.app", max_intensity=50)
        result = await capability.set_intensity(value=80)
        self.assertFalse(result.success)
        self.assertEqual(session.page.mouse.clicks, [])


if __name__ == "__main__":
    unittest.main()
