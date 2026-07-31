import asyncio
import base64
from playwright.async_api import async_playwright
from uni.contracts import ToolResult
from .base import Capability

class BrowserCapability(Capability):
    name = "browser"
    description = "Управление браузером через Playwright"

    def __init__(self, headless: bool = False, viewport_width: int = 1280, viewport_height: int = 720):
        self.headless = headless
        self.viewport = {"width": viewport_width, "height": viewport_height}
        self._browser = None
        self._page = None
        self._playwright = None

    async def _init(self):
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._page = await self._browser.new_page(viewport=self.viewport)

    async def navigate(self, url: str) -> ToolResult:
        try:
            await self._init()
            await self._page.goto(url)
            return ToolResult(success=True, message=f"Перешли на {url}")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    async def click_selector(self, selector: str) -> ToolResult:
        try:
            await self._init()
            await self._page.click(selector)
            return ToolResult(success=True, message=f"Клик по {selector}")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    async def type_selector(self, selector: str, text: str) -> ToolResult:
        try:
            await self._init()
            await self._page.fill(selector, text)
            return ToolResult(success=True, message=f"Введено '{text[:20]}' в {selector}")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    async def screenshot(self) -> ToolResult:
        try:
            await self._init()
            data = await self._page.screenshot(full_page=True)
            b64 = base64.b64encode(data).decode("utf-8")
            return ToolResult(success=True, data=f"data:image/png;base64,{b64}", message="Скриншот сделан")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    async def execute(self, action: str, **kwargs) -> ToolResult:
        if action == "navigate":
            return await self.navigate(kwargs.get("url", ""))
        elif action == "click_selector":
            return await self.click_selector(kwargs.get("selector", ""))
        elif action == "type_selector":
            return await self.type_selector(kwargs.get("selector", ""), kwargs.get("text", ""))
        elif action == "screenshot":
            return await self.screenshot()
        return ToolResult(success=False, message=f"Неизвестное действие: {action}")
