"""Dorch/XToys compatibility tool tests for the canonical Intiface path.

The historical DOM slider path is intentionally not tested: device motion must
never depend on xtoys.app or Playwright.
"""
import unittest

from uni.capabilities.xtoys import XToysCapability


class ForbiddenBrowserSession:
    async def page_for_host(self, *_args, **_kwargs):
        raise AssertionError("device control must not touch browser DOM")


class FakeBridge:
    def status(self):
        return {"connected": True, "devices": ["Synthetic Dorch"], "value": 0}


class FakeCoordinator:
    def __init__(self):
        self.current_value = 0
        self.calls = []
        self._bridge = FakeBridge()

    async def set_intensity(self, source, value):
        self.calls.append((source, int(value)))
        self.current_value = int(value)
        return True

    def status(self):
        return {
            "active_source": "manual",
            "current_value": self.current_value,
            "max_intensity": 65,
            "emergency_stop": False,
        }


class XToysIntifaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_positive_power_uses_coordinator_not_browser(self):
        coordinator = FakeCoordinator()
        capability = XToysCapability(ForbiddenBrowserSession(), url="https://xtoys.app", max_intensity=65)
        capability.coordinator = coordinator

        result = await capability.set_intensity(value=25)

        self.assertTrue(result.success, result.message)
        self.assertEqual(coordinator.calls, [("manual", 25)])
        self.assertEqual(result.data["requested_percent"], 25)
        self.assertFalse(result.data["verified_physical"])

    async def test_hard_max_is_applied_before_coordinator(self):
        coordinator = FakeCoordinator()
        capability = XToysCapability(ForbiddenBrowserSession(), url="https://xtoys.app", max_intensity=65)
        capability.coordinator = coordinator

        result = await capability.set_intensity(value=95)

        self.assertTrue(result.success, result.message)
        self.assertEqual(coordinator.calls[-1], ("manual", 65))
        self.assertEqual(result.data["requested_percent"], 65)

    async def test_status_comes_from_intiface_coordinator(self):
        coordinator = FakeCoordinator()
        capability = XToysCapability(ForbiddenBrowserSession(), url="https://xtoys.app", max_intensity=65)
        capability.coordinator = coordinator

        result = await capability.get_status()

        self.assertTrue(result.success, result.message)
        self.assertTrue(result.data["connected"])
        self.assertEqual(result.data["devices"], ["Synthetic Dorch"])
        self.assertEqual(result.data["status"], "not_verified")


if __name__ == "__main__":
    unittest.main()
