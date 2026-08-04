"""Orchestration workflows (Level: EventLoop / AppLaunch).

These live ABOVE capabilities: a workflow may drive browser, computer and
vision capabilities through the ToolExecutor, but a capability must never call
another capability (architecture invariant).
"""
from __future__ import annotations

import asyncio
from typing import Any

from uni.contracts import ToolResult


class AppLaunchWorkflow:
    """Launch / focus applications with a programmatic-first, UI-fallback strategy."""

    def __init__(self, tool_executor, *, xtoys_url: str = "https://xtoys.app") -> None:
        self.tool_executor = tool_executor
        self.xtoys_url = xtoys_url

    async def open_xtoys(self) -> ToolResult:
        """Open the XToys web app.

        Strategy (per design review):
          1. Recover the BrowserSession if its context was closed.
          2. Navigate to the exact XToys URL.
          3. Confirm host + title.
          4. Only if programmatic open is impossible, fall back to Windows UI
             (find the browser/shortcut via vision, click with the mouse).
        Never toggles the device or changes intensity.
        """
        # 1+2: programmatic open (ensures browser is alive internally)
        nav = await self.tool_executor.execute(
            "browser.navigate", {"url": self.xtoys_url}
        )
        if nav.success and isinstance(nav.data, dict):
            url = str(nav.data.get("url", ""))
            title = str(nav.data.get("title", ""))
            if "xtoys" in url.lower() or "xtoys" in title.lower():
                return ToolResult(
                    success=True,
                    data=nav.data,
                    message="Вкладка XToys.app открыта и выбрана",
                )
            # navigated but not xtoys (e.g. connection closed mid-flight)
            if "ERR" in str(nav.message) or "closed" in str(nav.message).lower():
                return await self._ui_fallback("XToys.app")
            return ToolResult(
                success=False,
                message=f"Открыт не XToys: {url} — {nav.message}",
            )
        # 3: navigate failed -> try UI fallback
        return await self._ui_fallback("XToys.app")

    async def _ui_fallback(self, window_title: str) -> ToolResult:
        """Last-resort: locate the window/shortcut on screen and click it."""
        located = await self.tool_executor.execute(
            "vision.find_desktop_element",
            {"description": f"{window_title} window or desktop shortcut"},
        )
        if not located.success or not isinstance(located.data, dict):
            return ToolResult(
                success=False,
                message=(
                    f"Не удалось открыть {window_title} программно, и на экране "
                    "не найдена соответствующая иконка/окно для клика мышью."
                ),
            )
        try:
            x = float(located.data["x"]) + float(located.data.get("width", 0)) / 2
            y = float(located.data["y"]) + float(located.data.get("height", 0)) / 2
        except (KeyError, TypeError, ValueError):
            return ToolResult(success=False, message="Vision вернула неполные координаты")
        clicked = await self.tool_executor.execute(
            "computer.click", {"x": round(x), "y": round(y)}
        )
        if not clicked.success:
            return ToolResult(success=False, message=f"Клик мышью не сработал: {clicked.message}")
        await asyncio.sleep(3.0)
        focused = await self.tool_executor.execute(
            "browser.current_tab", {}
        )
        if focused.success and isinstance(focused.data, dict):
            url = str(focused.data.get("url", ""))
            if "xtoys" in url.lower():
                return ToolResult(
                    success=True,
                    data=focused.data,
                    message="XToys открыт через клик мышью по найденной иконке",
                )
        return ToolResult(
            success=False,
            message="Клик выполнен, но вкладка XToys не подтверждена",
        )
