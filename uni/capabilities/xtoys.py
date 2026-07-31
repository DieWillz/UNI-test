import asyncio
from typing import Optional
import pyautogui
from uni.contracts import ToolResult
from .base import Capability
from .browser import BrowserCapability
from .vision import VisionCapability

class XToysCapability(Capability):
    name = "xtoys"
    description = "Управление XToys.app"

    def __init__(self, browser: BrowserCapability, vision: Optional[VisionCapability] = None, url: str = "https://xtoys.app"):
        self.browser = browser
        self.vision = vision
        self.url = url
        self._connected = False

    async def _ensure_connected(self) -> ToolResult:
        if self._connected:
            return ToolResult(success=True, message="Уже на xtoys.app")
        result = await self.browser.navigate(self.url)
        if result.success:
            self._connected = True
            await asyncio.sleep(3)
            return ToolResult(success=True, message="XToys.app открыт")
        return result

    async def _find_element(self, selector: str, description: str) -> Optional[dict]:
        try:
            await self.browser._init()
            el = await self.browser._page.query_selector(selector)
            if el:
                box = await el.bounding_box()
                if box:
                    return {"x": box["x"] + box["width"]/2, "y": box["y"] + box["height"]/2}
        except:
            pass
        if self.vision:
            res = await self.vision.find_element(description)
            if res.success and res.data:
                return res.data
        return None

    async def toggle(self, device: str = "device") -> ToolResult:
        conn = await self._ensure_connected()
        if not conn.success:
            return conn
        selector = f'[data-device="{device}"] .toggle, .toggle:has-text("{device}")'
        elem = await self._find_element(selector, f"кнопка включения для {device}")
        if not elem:
            return ToolResult(success=False, message=f"Не найден элемент для {device}")
        result = await self.browser.execute("click_selector", {"selector": selector})
        if not result.success and elem:
            pyautogui.click(elem["x"], elem["y"])
        return ToolResult(success=True, message=f"Переключено устройство {device}")

    async def set_intensity(self, device: str = "device", value: int = 50) -> ToolResult:
        conn = await self._ensure_connected()
        if not conn.success:
            return conn
        value = max(0, min(100, value))
        selector = f'[data-device="{device}"] input[type="range"], .slider:has-text("{device}")'
        elem = await self._find_element(selector, f"слайдер интенсивности для {device}")
        if not elem:
            return ToolResult(success=False, message=f"Не найден слайдер для {device}")
        try:
            await self.browser._init()
            slider = await self.browser._page.query_selector(selector)
            if slider:
                box = await slider.bounding_box()
                if box:
                    percent = value / 100.0
                    x = box["x"] + box["width"] * percent
                    y = box["y"] + box["height"] / 2
                    pyautogui.click(x, y)
                    return ToolResult(success=True, message=f"Интенсивность {device} установлена на {value}%")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")
        return ToolResult(success=False, message="Не удалось установить интенсивность")

    async def select_pattern(self, device: str = "device", pattern: str = "wave") -> ToolResult:
        conn = await self._ensure_connected()
        if not conn.success:
            return conn
        selector = f'[data-device="{device}"] .pattern-{pattern}, .pattern:has-text("{pattern}")'
        elem = await self._find_element(selector, f"кнопка паттерна {pattern} для {device}")
        if not elem:
            return ToolResult(success=False, message=f"Паттерн {pattern} не найден")
        result = await self.browser.execute("click_selector", {"selector": selector})
        if not result.success and elem:
            pyautogui.click(elem["x"], elem["y"])
        return ToolResult(success=True, message=f"Паттерн {pattern} выбран для {device}")

    async def get_status(self, device: str = "device") -> ToolResult:
        conn = await self._ensure_connected()
        if not conn.success:
            return conn
        if self.vision:
            res = await self.vision.analyze_screen(f"Найди информацию об устройстве {device} на экране. Статус и интенсивность.")
            if res.success:
                return ToolResult(success=True, data=res.data, message="Статус получен через Vision")
        return ToolResult(success=False, message="Не удалось получить статус")

    async def execute(self, action: str, **kwargs) -> ToolResult:
        device = kwargs.get("device", "device")
        if action == "toggle":
            return await self.toggle(device)
        elif action == "set_intensity":
            return await self.set_intensity(device, kwargs.get("value", 50))
        elif action == "select_pattern":
            return await self.select_pattern(device, kwargs.get("pattern", "wave"))
        elif action == "get_status":
            return await self.get_status(device)
        return ToolResult(success=False, message=f"Неизвестное действие: {action}")
