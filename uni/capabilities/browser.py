from __future__ import annotations

import base64
import re
from datetime import datetime
from pathlib import Path

from uni.browser_session import BrowserSession
from uni.contracts import ToolResult
from .base import Capability


class BrowserCapability(Capability):
    name = "browser"
    description = "Управление одной persistent Chrome-сессией"

    def __init__(self, session: BrowserSession, screenshot_dir: str | Path = ".uni-logs/screenshots"):
        self.session = session
        self.screenshot_dir = Path(screenshot_dir).resolve()

    async def navigate(self, url: str) -> ToolResult:
        if not url.strip():
            return ToolResult(success=False, message="URL не указан")
        try:
            page = await self.session.navigate(url.strip())
            return ToolResult(
                success=True,
                data={"url": page.url, "title": await page.title()},
                message=f"Открыто: {page.url}",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка браузера: {exc}")

    async def search_web(self, query: str) -> ToolResult:
        if not query.strip():
            return ToolResult(success=False, message="Поисковый запрос пуст")
        try:
            page, results = await self.session.search_web(query.strip())
            return ToolResult(
                success=True,
                data={"query": query.strip(), "url": page.url, "results": results},
                message=f"Открыт поиск: {query.strip()}. Найдено результатов: {len(results)}",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка поиска: {exc}")

    async def search_images(self, query: str) -> ToolResult:
        if not query.strip():
            return ToolResult(success=False, message="Поисковый запрос пуст")
        try:
            page, results = await self.session.search_images(query.strip())
            return ToolResult(
                success=True,
                data={"query": query.strip(), "url": page.url, "images": results},
                message=f"Открыт поиск изображений: {query.strip()}. Найдено: {len(results)}",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка поиска изображений: {exc}")

    async def click_selector(self, selector: str) -> ToolResult:
        if not selector:
            return ToolResult(success=False, message="CSS-селектор не указан")
        try:
            page = await self.session.active_page()
            loc = page.locator(selector).first
            await self.session.click_locator(loc, timeout=10_000)
            return ToolResult(success=True, message=f"Клик выполнен: {selector}")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка клика: {exc}")

    async def type_selector(self, selector: str, text: str) -> ToolResult:
        if not selector:
            return ToolResult(success=False, message="CSS-селектор не указан")
        try:
            page = await self.session.active_page()
            loc = page.locator(selector).first
            await self.session.fill_locator(loc, text, timeout=10_000)
            return ToolResult(success=True, message=f"Текст введён в {selector}")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка ввода: {exc}")

    async def extract_text(self, max_chars: int = 5000) -> ToolResult:
        try:
            page = await self.session.active_page()
            text = (await page.locator("body").inner_text(timeout=10_000)).strip()
            return ToolResult(
                success=True,
                data={"url": page.url, "title": await page.title(), "text": text[:max_chars]},
                message=f"Текст страницы получен: {page.url}",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка чтения страницы: {exc}")

    async def screenshot(self) -> ToolResult:
        try:
            page = await self.session.active_page()
            data = await page.screenshot(full_page=False)
            b64 = base64.b64encode(data).decode("ascii")
            return ToolResult(
                success=True,
                data={"url": page.url, "image_data": f"data:image/png;base64,{b64}"},
                message="Скриншот активной вкладки сделан",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка скриншота: {exc}")

    async def save_screenshot(self, label: str = "browser") -> ToolResult:
        try:
            page = await self.session.active_page()
            safe_label = re.sub(r"[^a-zA-Zа-яА-ЯёЁ0-9_-]+", "_", label).strip("_")[:60] or "browser"
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
            path = self.screenshot_dir / f"{timestamp}_{safe_label}.png"
            await page.screenshot(path=str(path), full_page=False)
            return ToolResult(
                success=True,
                data={"url": page.url, "path": str(path)},
                message=f"Скриншот сохранён: {path}",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка сохранения скриншота: {exc}")

    async def current_tab(self) -> ToolResult:
        try:
            page = await self.session.active_page()
            return ToolResult(
                success=True,
                data={"url": page.url, "title": await page.title()},
                message=f"Активная вкладка: {await page.title()}",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка вкладки: {exc}")

    async def execute(self, action: str, **kwargs) -> ToolResult:
        if action == "navigate":
            return await self.navigate(kwargs.get("url", ""))
        if action == "search_web":
            return await self.search_web(kwargs.get("query", ""))
        if action == "search_images":
            return await self.search_images(kwargs.get("query", ""))
        if action == "click_selector":
            return await self.click_selector(kwargs.get("selector", ""))
        if action == "type_selector":
            return await self.type_selector(kwargs.get("selector", ""), kwargs.get("text", ""))
        if action == "extract_text":
            return await self.extract_text(int(kwargs.get("max_chars", 5000)))
        if action == "screenshot":
            return await self.screenshot()
        if action == "save_screenshot":
            return await self.save_screenshot(str(kwargs.get("label", "browser")))
        if action == "current_tab":
            return await self.current_tab()
        return ToolResult(success=False, message=f"Неизвестное действие browser.{action}")
