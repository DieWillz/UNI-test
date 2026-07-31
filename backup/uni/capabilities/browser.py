"""Browser Capability - Playwright Chromium"""

import asyncio
import base64
from typing import Any
from playwright.async_api import async_playwright, Browser, Page

from ..capabilities.registry import Capability, ToolSchema


class BrowserCapability(Capability):
    def __init__(self, headless: bool = False, viewport_width: int = 1280, viewport_height: int = 720, timeout: int = 30000):
        super().__init__("browser")
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.timeout = timeout
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

        self.register_tool(ToolSchema(
            name="navigate",
            description="Navigate to URL",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"},
                    "wait_until": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle"], "default": "domcontentloaded"},
                },
                "required": ["url"],
            },
        ))
        self.register_tool(ToolSchema(
            name="click_selector",
            description="Click element by CSS selector",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                    "click_count": {"type": "integer", "default": 1},
                },
                "required": ["selector"],
            },
        ))
        self.register_tool(ToolSchema(
            name="type_selector",
            description="Type text into element",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"},
                    "text": {"type": "string", "description": "Text to type"},
                    "delay": {"type": "number", "default": 50, "description": "Delay between keystrokes (ms)"},
                    "clear_first": {"type": "boolean", "default": True},
                },
                "required": ["selector", "text"],
            },
        ))
        self.register_tool(ToolSchema(
            name="extract_text",
            description="Extract text from element",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"},
                },
                "required": ["selector"],
            },
        ))
        self.register_tool(ToolSchema(
            name="screenshot",
            description="Take page screenshot",
            parameters={
                "type": "object",
                "properties": {
                    "full_page": {"type": "boolean", "default": False},
                    "save_path": {"type": "string", "description": "Optional path to save"},
                },
            },
        ))
        self.register_tool(ToolSchema(
            name="wait_for_selector",
            description="Wait for element to appear",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "state": {"type": "string", "enum": ["attached", "detached", "visible", "hidden"], "default": "visible"},
                    "timeout": {"type": "integer", "default": 30000},
                },
                "required": ["selector"],
            },
        ))
        self.register_tool(ToolSchema(
            name="get_page_info",
            description="Get current page URL and title",
            parameters={"type": "object", "properties": {}},
        ))

    async def initialize(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._page = await self._browser.new_page()
        await self._page.set_viewport_size({"width": self.viewport_width, "height": self.viewport_height})
        self._page.set_default_timeout(self.timeout)

    async def shutdown(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def execute(self, tool_name: str, args: dict) -> Any:
        if not self._page:
            await self.initialize()
        method = getattr(self, f"_tool_{tool_name}", None)
        if not method:
            raise ValueError(f"Unknown tool: {tool_name}")
        return await method(args)

    async def _tool_navigate(self, args: dict) -> dict:
        await self._page.goto(args["url"], wait_until=args.get("wait_until", "domcontentloaded"))
        return {"success": True, "url": self._page.url}

    async def _tool_click_selector(self, args: dict) -> dict:
        await self._page.click(args["selector"], button=args.get("button", "left"), click_count=args.get("click_count", 1))
        return {"success": True}

    async def _tool_type_selector(self, args: dict) -> dict:
        if args.get("clear_first", True):
            await self._page.fill(args["selector"], "")
        await self._page.type(args["selector"], args["text"], delay=args.get("delay", 50))
        return {"success": True}

    async def _tool_extract_text(self, args: dict) -> dict:
        text = await self._page.inner_text(args["selector"])
        return {"success": True, "text": text}

    async def _tool_screenshot(self, args: dict) -> dict:
        screenshot_bytes = await self._page.screenshot(full_page=args.get("full_page", False))
        img_base64 = base64.b64encode(screenshot_bytes).decode()

        if save_path := args.get("save_path"):
            from pathlib import Path
            Path(save_path).write_bytes(screenshot_bytes)

        return {"success": True, "image_base64": img_base64}

    async def _tool_wait_for_selector(self, args: dict) -> dict:
        await self._page.wait_for_selector(args["selector"], state=args.get("state", "visible"), timeout=args.get("timeout", self.timeout))
        return {"success": True}

    async def _tool_get_page_info(self, args: dict) -> dict:
        return {
            "success": True,
            "url": self._page.url,
            "title": await self._page.title(),
        }